"""Effect filters measured on real FFmpeg output. Spec: specs/05-editing-brain.md#b5 [T-118]"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from app.adapters.ffmpeg_filters import segment_filter
from app.domain.plan import Effect

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs FFmpeg on PATH")

WIDTH = 640
HEIGHT = 360
FPS = 30
FRAMES = 30
SQUARE = 20
ALLOWED_DRIFT_PIXELS = 2.0
BRIGHT = 128


@pytest.fixture(scope="module")
def centered_square(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A white square on the exact center of a black frame."""
    target = tmp_path_factory.mktemp("filters") / "square.mp4"
    left = (WIDTH - SQUARE) // 2
    top = (HEIGHT - SQUARE) // 2
    source = (
        f"color=black:s={WIDTH}x{HEIGHT}:r={FPS}:d=1,"
        f"drawbox=x={left}:y={top}:w={SQUARE}:h={SQUARE}:color=white:t=fill"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            source,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(target),
        ],
        check=True,
    )
    return target


def rendered(source: Path, effects: tuple[Effect, ...]) -> np.ndarray:
    chain = segment_filter(effects, WIDTH, HEIGHT, FPS, sharpen=False)
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-vf",
            f"{chain},format=gray",
            "-frames:v",
            str(FRAMES),
            "-f",
            "rawvideo",
            "-",
        ],
        capture_output=True,
        check=True,
    )
    return np.frombuffer(result.stdout, np.uint8).reshape(-1, HEIGHT, WIDTH)


def square_center(frame: np.ndarray) -> tuple[float, float]:
    rows, columns = np.nonzero(frame > BRIGHT)
    return float(columns.mean()), float(rows.mean())


@pytest.mark.parametrize("at", [0.0, 0.5])
def test_b5_a_zoom_punch_stays_centered_on_every_frame(centered_square: Path, at: float) -> None:
    punch = Effect(type="zoomPunch", at=at, duration=1.0 - at, strength=0.5)

    frames = rendered(centered_square, (punch,))

    assert len(frames) == FRAMES
    for index, frame in enumerate(frames):
        across, down = square_center(frame)
        assert across == pytest.approx((WIDTH - 1) / 2, abs=ALLOWED_DRIFT_PIXELS), f"frame {index}"
        assert down == pytest.approx((HEIGHT - 1) / 2, abs=ALLOWED_DRIFT_PIXELS), f"frame {index}"


def test_b5_a_zoom_punch_really_enlarges_the_frame(centered_square: Path) -> None:
    punch = Effect(type="zoomPunch", at=0.0, duration=1.0, strength=0.5)

    first = rendered(centered_square, (punch,))[0]

    columns = np.nonzero((first > BRIGHT).any(axis=0))[0]
    assert columns.max() - columns.min() + 1 == pytest.approx(SQUARE * 1.5, abs=3)


def test_b5_shake_and_zoom_together_keep_the_square_near_the_center(
    centered_square: Path,
) -> None:
    punch = Effect(type="zoomPunch", at=0.0, duration=1.0, strength=0.5)
    shake = Effect(type="shake", at=0.0, duration=1.0, strength=1.0)
    reach = 0.015 * WIDTH + ALLOWED_DRIFT_PIXELS

    frames = rendered(centered_square, (punch, shake))

    for index, frame in enumerate(frames):
        across, down = square_center(frame)
        assert abs(across - (WIDTH - 1) / 2) <= reach, f"frame {index}"
        assert abs(down - (HEIGHT - 1) / 2) <= reach, f"frame {index}"
