"""Contract of the Interpolator and Upscaler ports, with the real weights on the CPU.

Spec: specs/04-pipeline.md#stages (6, 7), specs/09-local-setup.md#6-gb-vram-model-profile [T-301]
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest

from app.adapters import rife_interpolator
from app.adapters.nvml_gpu_guard import NvmlGpuGuard
from app.adapters.realesrgan_upscaler import RealEsrganUpscaler
from app.adapters.rife_interpolator import RifeInterpolator
from app.adapters.torch_enhance import read_frame, write_frame
from app.domain.errors import RenderError
from app.ports.enhance import Frame, FrameSize, Interpolator, Upscaler
from app.ports.gpu_guard import GpuGuard

MODELS = Path(__file__).resolve().parents[3] / "models"
RIFE_WEIGHTS = MODELS / "rife" / "flownet_v4.25.pkl"
ESRGAN_WEIGHTS = MODELS / "realesrgan" / "realesr-general-x4v3.pth"
DEVICE = "cpu"
WIDTH = 130
HEIGHT = 97
SQUARE = 30
TOP = 30
START_LEFT = 10
TRAVEL_PX = 48

pytestmark = pytest.mark.skipif(
    not RIFE_WEIGHTS.exists() or not ESRGAN_WEIGHTS.exists(),
    reason="needs the RIFE and Real-ESRGAN weights: download_models.py --phase 4",
)


def guard() -> GpuGuard:
    return NvmlGpuGuard(empty_cache=lambda: None)


INTERPOLATORS: list[Callable[[], Interpolator]] = [
    lambda: RifeInterpolator(guard(), RIFE_WEIGHTS, DEVICE),
]
UPSCALERS: list[Callable[[], Upscaler]] = [
    lambda: RealEsrganUpscaler(guard(), ESRGAN_WEIGHTS, DEVICE),
]


def square_at(left: int, dtype: type[np.unsignedinteger[Any]] = np.uint8) -> Frame:
    frame = cast(Frame, np.zeros((HEIGHT, WIDTH, 3), dtype))
    frame[TOP : TOP + SQUARE, left : left + SQUARE] = np.iinfo(dtype).max
    return frame


def left_edge(frame: Frame) -> int:
    bright = frame[..., 0] > np.iinfo(frame.dtype).max / 2
    return int(np.nonzero(bright.any(axis=0))[0].min())


def textured(width: int, height: int) -> Frame:
    """Smooth colour with some edges, so that a seam between tiles would show."""
    y, x = np.mgrid[0:height, 0:width]
    base = np.stack((x / width, y / height, (x + y) / (width + height)), axis=2) * 200
    grid = ((x // 16 + y // 16) % 2 == 0)[..., None] * 40
    return cast(Frame, (base + grid).astype(np.uint8))


@pytest.mark.parametrize("build", INTERPOLATORS)
@pytest.mark.parametrize("time", [0.25, 0.5, 0.75])
def test_stage6_a_moving_square_lands_where_the_time_says(
    build: Callable[[], Interpolator], time: float
) -> None:
    with build().session() as session:
        middle = session.between(
            square_at(START_LEFT), square_at(START_LEFT + TRAVEL_PX), time=time
        )

    assert left_edge(middle) == pytest.approx(START_LEFT + TRAVEL_PX * time, abs=5)


@pytest.mark.parametrize("build", INTERPOLATORS)
def test_stage6_output_keeps_the_size_and_bit_depth_of_the_input(
    build: Callable[[], Interpolator],
) -> None:
    with build().session() as session:
        low = session.between(square_at(10), square_at(14))
        high = session.between(square_at(10, np.uint16), square_at(14, np.uint16))

    assert low.shape == (HEIGHT, WIDTH, 3)
    assert low.dtype == np.uint8
    assert high.shape == (HEIGHT, WIDTH, 3)
    assert high.dtype == np.uint16


@pytest.mark.parametrize("build", INTERPOLATORS)
def test_stage6_works_on_frame_files(build: Callable[[], Interpolator], tmp_path: Path) -> None:
    write_frame(tmp_path / "a.png", square_at(10))
    write_frame(tmp_path / "b.png", square_at(30))

    with build().session() as session:
        session.between_files(tmp_path / "a.png", tmp_path / "b.png", tmp_path / "m.png")

    assert left_edge(read_frame(tmp_path / "m.png")) == pytest.approx(20, abs=5)


@pytest.mark.parametrize("build", INTERPOLATORS)
@pytest.mark.parametrize("time", [0.0, 1.0, -0.1])
def test_stage6_time_must_be_between_the_frames(
    build: Callable[[], Interpolator], time: float
) -> None:
    with build().session() as session, pytest.raises(RenderError, match="time"):
        session.between(square_at(10), square_at(14), time=time)


@pytest.mark.parametrize("build", INTERPOLATORS)
def test_stage6_frames_must_match(build: Callable[[], Interpolator]) -> None:
    with build().session() as session, pytest.raises(RenderError, match="differ"):
        session.between(square_at(10), np.zeros((8, 8, 3), np.uint8))


def test_rife_runs_at_scale_half_for_large_frames(monkeypatch: pytest.MonkeyPatch) -> None:
    """A real frame above 4K is too slow for the CPU, so the scale itself is forced here."""
    monkeypatch.setattr(rife_interpolator, "flow_scale", lambda _w, _h: 0.5)

    with INTERPOLATORS[0]().session() as session:
        middle = session.between(square_at(10), square_at(14))

    assert middle.shape == (HEIGHT, WIDTH, 3)


@pytest.mark.parametrize("build", UPSCALERS)
def test_stage7_output_is_exactly_the_target_size(build: Callable[[], Upscaler]) -> None:
    frame = textured(64, 48)

    with build().session() as session:
        four_times = session.upscale(frame, FrameSize(256, 192))
        between = session.upscale(frame, FrameSize(150, 110))
        beyond = session.upscale(frame, FrameSize(320, 240))

    assert four_times.shape == (192, 256, 3)
    assert between.shape == (110, 150, 3)
    assert beyond.shape == (240, 320, 3)


@pytest.mark.parametrize("build", UPSCALERS)
def test_stage7_keeps_the_picture_and_the_bit_depth(build: Callable[[], Upscaler]) -> None:
    frame = textured(64, 48)
    deep = frame.astype(np.uint16) * 257

    with build().session() as session:
        low = session.upscale(frame, FrameSize(256, 192))
        high = session.upscale(deep, FrameSize(256, 192))

    assert low.dtype == np.uint8
    assert high.dtype == np.uint16
    means = low.reshape(48, 4, 64, 4, 3).mean(axis=(1, 3))
    assert np.abs(means - frame).mean() < 6
    assert np.abs(high / 257.0 - low).mean() < 2


@pytest.mark.parametrize("build", UPSCALERS)
def test_stage7_works_on_frame_files(build: Callable[[], Upscaler], tmp_path: Path) -> None:
    write_frame(tmp_path / "in.png", textured(64, 48))

    with build().session() as session:
        session.upscale_file(tmp_path / "in.png", tmp_path / "out.png", FrameSize(256, 192))

    assert read_frame(tmp_path / "out.png").shape == (192, 256, 3)


@pytest.mark.parametrize("build", UPSCALERS)
def test_stage7_tiles_leave_no_visible_seam(build: Callable[[], Upscaler]) -> None:
    """In cool mode this frame splits at 256 px, in normal mode it is one tile."""
    frame = textured(300, 40)

    with build().session(cool_mode=False) as session:
        whole = session.upscale(frame, FrameSize(1200, 160))
    with build().session(cool_mode=True) as session:
        tiled = session.upscale(frame, FrameSize(1200, 160))

    assert np.abs(whole.astype(np.int32) - tiled.astype(np.int32)).max() <= 2


@pytest.mark.parametrize("build", UPSCALERS)
def test_stage7_rejects_an_empty_target(build: Callable[[], Upscaler]) -> None:
    with build().session() as session, pytest.raises(RenderError, match="upscale"):
        session.upscale(textured(16, 16), FrameSize(0, 16))
