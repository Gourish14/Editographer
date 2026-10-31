"""Rules of the enhance adapters, no model weights needed.

Spec: specs/09-local-setup.md#6-gb-vram-model-profile, specs/04-pipeline.md#stages (6, 7) [T-301]
"""

from __future__ import annotations

import gc
import weakref
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import torch
from torch import nn

from app.adapters.nvml_gpu_guard import NvmlGpuGuard
from app.adapters.realesrgan_upscaler import (
    COOL_TILE_PX,
    TILE_PX,
    RealEsrganUpscaler,
    tile_size,
    tiles_of,
)
from app.adapters.rife_interpolator import RifeInterpolator, flow_scale, padded_side
from app.adapters.torch_enhance import (
    check_frame,
    frame_to_tensor,
    guarded_model,
    model_precision,
    read_frame,
    read_weights,
    tensor_to_frame,
    write_frame,
)
from app.domain.errors import ErrorCode, RenderError
from app.ports.enhance import Frame, FrameSize


def test_rife_keeps_full_scale_up_to_4k() -> None:
    assert flow_scale(1920, 1080) == 1.0
    assert flow_scale(3840, 2160) == 1.0


def test_rife_uses_scale_half_above_4k() -> None:
    assert flow_scale(5760, 2880) == 0.5
    assert flow_scale(7680, 4320) == 0.5


def test_rife_treats_a_vertical_4k_frame_like_a_horizontal_one() -> None:
    assert flow_scale(2160, 3840) == 1.0
    assert flow_scale(4320, 7680) == 0.5


def test_rife_pads_sides_to_what_the_network_can_halve() -> None:
    assert padded_side(1080, 1.0) == 1088
    assert padded_side(64, 1.0) == 64
    assert padded_side(4320, 0.5) == 4352


def test_real_esrgan_tiles_are_512_px_and_256_px_in_cool_mode() -> None:
    assert tile_size(cool_mode=False) == TILE_PX == 512
    assert tile_size(cool_mode=True) == COOL_TILE_PX == 256


def test_real_esrgan_tiles_cover_the_frame_once() -> None:
    covered = np.zeros((700, 1100), np.int32)

    for tile in tiles_of(1100, 700, 512):
        assert tile.right - tile.left <= 512
        assert tile.bottom - tile.top <= 512
        covered[tile.top : tile.bottom, tile.left : tile.right] += 1

    assert (covered == 1).all()


def test_only_the_gpu_runs_in_fp16() -> None:
    assert model_precision("cuda") == torch.half
    assert model_precision("cuda:0") == torch.half
    assert model_precision("cpu") == torch.float


def test_the_model_goes_through_the_guard_and_is_gone_before_vram_is_freed() -> None:
    held_when_freed: list[bool] = []
    references: list[weakref.ReferenceType[nn.Module]] = []

    def load() -> nn.Module:
        model = nn.Linear(1, 1)
        references.append(weakref.ref(model))
        return model

    def empty_cache() -> None:
        gc.collect()
        held_when_freed.append(references[0]() is not None)

    with guarded_model(NvmlGpuGuard(empty_cache=empty_cache), load) as loaded:
        assert isinstance(loaded.model, nn.Linear)

    assert held_when_freed == [False]


def test_a_closed_session_cannot_reach_the_model() -> None:
    with guarded_model(NvmlGpuGuard(empty_cache=lambda: None), lambda: nn.Linear(1, 1)) as loaded:
        pass

    with pytest.raises(RenderError, match="closed"):
        _ = loaded.model


def test_running_out_of_vram_is_reported_with_its_code() -> None:
    guard = NvmlGpuGuard(empty_cache=lambda: None)

    with pytest.raises(RenderError) as caught, guarded_model(guard, lambda: nn.Linear(1, 1)):
        raise torch.cuda.OutOfMemoryError("full")

    assert caught.value.code is ErrorCode.GPU_OUT_OF_MEMORY


def test_running_out_of_vram_while_loading_is_reported_with_its_code() -> None:
    def load() -> nn.Module:
        raise torch.cuda.OutOfMemoryError("full")

    with (
        pytest.raises(RenderError) as caught,
        guarded_model(NvmlGpuGuard(empty_cache=lambda: None), load),
    ):
        pass

    assert caught.value.code is ErrorCode.GPU_OUT_OF_MEMORY


def test_missing_weights_name_the_file_and_the_fix(tmp_path: Path) -> None:
    with pytest.raises(RenderError, match=r"nothing\.pkl.*setup\.bat"):
        read_weights(tmp_path / "nothing.pkl")


def test_a_checkpoint_cannot_run_code_while_loading(tmp_path: Path) -> None:
    path = tmp_path / "evil.pkl"
    torch.save({"weights": Path("not a tensor")}, path)

    with pytest.raises(Exception, match="(?i)weights.only"):
        read_weights(path)


def test_both_adapters_fail_clearly_without_weights(tmp_path: Path) -> None:
    guard = NvmlGpuGuard(empty_cache=lambda: None)

    with pytest.raises(RenderError), RifeInterpolator(guard, tmp_path / "x", "cpu").session():
        pass
    with pytest.raises(RenderError), RealEsrganUpscaler(guard, tmp_path / "x", "cpu").session():
        pass


@pytest.mark.parametrize(
    "frame",
    [
        np.zeros((4, 4), np.uint8),
        np.zeros((4, 4, 4), np.uint8),
        np.zeros((4, 4, 3), np.float32),
    ],
)
def test_frames_must_be_8_or_16_bit_rgb(frame: Frame) -> None:
    with pytest.raises(RenderError, match="RGB"):
        check_frame(frame)


@pytest.mark.parametrize("dtype", [np.uint8, np.uint16])
def test_a_frame_survives_the_trip_through_a_tensor(dtype: type[np.unsignedinteger[Any]]) -> None:
    maximum = np.iinfo(dtype).max
    frame = np.linspace(0, maximum, 48).reshape((2, 8, 3)).astype(dtype)

    back = tensor_to_frame(frame_to_tensor(frame, "cpu", torch.float), frame.dtype)

    assert back.dtype == frame.dtype
    assert np.abs(back.astype(np.int64) - frame.astype(np.int64)).max() <= maximum / 10_000


@pytest.mark.parametrize("dtype", [np.uint8, np.uint16])
def test_frame_files_keep_rgb_order_and_bit_depth(
    tmp_path: Path, dtype: type[np.unsignedinteger[Any]]
) -> None:
    frame = np.zeros((4, 6, 3), dtype)
    frame[..., 0] = np.iinfo(dtype).max
    path = tmp_path / "नया" / "frame.png"

    write_frame(path, frame)

    assert np.array_equal(read_frame(path), frame)


def test_a_missing_frame_file_is_a_render_error(tmp_path: Path) -> None:
    with pytest.raises(RenderError, match=r"gone\.png"):
        read_frame(tmp_path / "gone.png")


def test_an_unreadable_frame_file_is_a_render_error(tmp_path: Path) -> None:
    path = tmp_path / "bad.png"
    path.write_bytes(b"not an image")

    with pytest.raises(RenderError, match=r"bad\.png"):
        read_frame(path)


def test_an_unknown_frame_format_is_a_render_error(tmp_path: Path) -> None:
    with pytest.raises(RenderError, match=r"frame\.nope"):
        write_frame(tmp_path / "frame.nope", np.zeros((4, 4, 3), np.uint8))


def test_frame_size_is_a_value() -> None:
    assert FrameSize(8, 4) == FrameSize(8, 4)
