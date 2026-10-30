"""Upscaling with Real-ESRGAN realesr-general-x4v3.

Spec: specs/04-pipeline.md#stages (7), specs/09-local-setup.md#6-gb-vram-model-profile
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import cv2
import numpy as np
import torch

from app.adapters.torch_enhance import (
    LoadedModel,
    check_frame,
    frame_to_tensor,
    guarded_model,
    model_precision,
    read_frame,
    read_weights,
    tensor_to_frame,
    write_frame,
)
from app.adapters.vendor.srvgg import SrVggNetCompact
from app.domain.errors import RenderError
from app.ports.enhance import Frame, FrameSize, UpscaleSession
from app.ports.gpu_guard import GpuGuard

MODEL_SCALE = 4
MODEL_FEATURES = 64
MODEL_CONVS = 32
TILE_PX = 512
COOL_TILE_PX = 256
TILE_PAD_PX = 10
"""Extra context around each tile, cut away after, so that tile borders do not show."""
STATE_KEY = "params"


@dataclass(frozen=True)
class Tile:
    """A box of the source frame, ends excluded."""

    left: int
    top: int
    right: int
    bottom: int


def tile_size(cool_mode: bool) -> int:
    return COOL_TILE_PX if cool_mode else TILE_PX


def tiles_of(width: int, height: int, size: int) -> Iterator[Tile]:
    for top in range(0, height, size):
        for left in range(0, width, size):
            yield Tile(left, top, min(left + size, width), min(top + size, height))


class _RealEsrganSession:
    def __init__(self, loaded: LoadedModel[SrVggNetCompact], device: str, tile: int) -> None:
        self._loaded = loaded
        self._device = device
        self._tile = tile
        self._precision = model_precision(device)

    def upscale(self, frame: Frame, size: FrameSize) -> Frame:
        check_frame(frame)
        if size.width <= 0 or size.height <= 0:
            raise RenderError(f"Cannot upscale to {size.width}x{size.height}")

        height, width = frame.shape[:2]
        canvas: Frame = np.empty((height * MODEL_SCALE, width * MODEL_SCALE, 3), frame.dtype)
        for tile in tiles_of(width, height, self._tile):
            self._upscale_tile(frame, tile, canvas)
        if canvas.shape[:2] == (size.height, size.width):
            return canvas
        target = (size.width, size.height)
        return cast(Frame, cv2.resize(canvas, target, interpolation=cv2.INTER_LANCZOS4))

    def _upscale_tile(self, frame: Frame, tile: Tile, canvas: Frame) -> None:
        height, width = frame.shape[:2]
        left = max(tile.left - TILE_PAD_PX, 0)
        top = max(tile.top - TILE_PAD_PX, 0)
        right = min(tile.right + TILE_PAD_PX, width)
        bottom = min(tile.bottom + TILE_PAD_PX, height)
        with torch.inference_mode():
            tensor = frame_to_tensor(frame[top:bottom, left:right], self._device, self._precision)
            output = self._loaded.model(tensor)
            inner = output[
                :,
                :,
                (tile.top - top) * MODEL_SCALE : (tile.bottom - top) * MODEL_SCALE,
                (tile.left - left) * MODEL_SCALE : (tile.right - left) * MODEL_SCALE,
            ]
            canvas[
                tile.top * MODEL_SCALE : tile.bottom * MODEL_SCALE,
                tile.left * MODEL_SCALE : tile.right * MODEL_SCALE,
            ] = tensor_to_frame(inner, frame.dtype)

    def upscale_file(self, source: Path, target: Path, size: FrameSize) -> None:
        write_frame(target, self.upscale(read_frame(source), size))


class RealEsrganUpscaler:
    def __init__(self, gpu: GpuGuard, weights: Path, device: str = "cuda") -> None:
        self._gpu = gpu
        self._weights = weights
        self._device = device

    def session(self, cool_mode: bool = False) -> AbstractContextManager[UpscaleSession]:
        return self._session(tile_size(cool_mode))

    @contextmanager
    def _session(self, tile: int) -> Iterator[UpscaleSession]:
        with guarded_model(self._gpu, self._load) as loaded:
            yield _RealEsrganSession(loaded, self._device, tile)

    def _load(self) -> SrVggNetCompact:
        state = read_weights(self._weights)
        model = SrVggNetCompact(MODEL_FEATURES, MODEL_CONVS, MODEL_SCALE)
        model.load_state_dict(state[STATE_KEY])
        return model.eval().to(self._device, model_precision(self._device))
