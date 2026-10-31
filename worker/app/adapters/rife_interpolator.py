"""Frame interpolation with Practical-RIFE 4.25.

Spec: specs/04-pipeline.md#stages (6), specs/09-local-setup.md#6-gb-vram-model-profile
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path

import torch
from torch.nn import functional

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
from app.adapters.vendor.rife_ifnet import IFNet
from app.domain.errors import RenderError
from app.ports.enhance import Frame, InterpolationSession
from app.ports.gpu_guard import GpuGuard

UHD_PIXELS = 3840 * 2160
FULL_SCALE = 1.0
ABOVE_4K_SCALE = 0.5
SIDE_MULTIPLE = 64
STATE_PREFIX = "module."
TRAINING_ONLY_PREFIXES = ("teacher.", "caltime.")


def flow_scale(width: int, height: int) -> float:
    """Spec: scale 0.5 above 4K. Counted in pixels so that vertical frames are treated alike."""
    return ABOVE_4K_SCALE if width * height > UHD_PIXELS else FULL_SCALE


def padded_side(side: int, scale: float) -> int:
    """The network halves the flow resolution many times, so sides must divide evenly."""
    multiple = int(SIDE_MULTIPLE / min(scale, FULL_SCALE))
    return math.ceil(side / multiple) * multiple


class _RifeSession:
    def __init__(self, loaded: LoadedModel[IFNet], device: str) -> None:
        self._loaded = loaded
        self._device = device
        self._precision = model_precision(device)

    def between(self, first: Frame, second: Frame, time: float = 0.5) -> Frame:
        check_frame(first)
        check_frame(second)
        if first.shape != second.shape or first.dtype != second.dtype:
            raise RenderError(f"Frames differ: {first.shape} and {second.shape}")
        if not 0.0 < time < 1.0:
            raise RenderError(f"Interpolation time must be inside 0 to 1, got {time}")

        height, width = first.shape[:2]
        scale = flow_scale(width, height)
        pad = (0, padded_side(width, scale) - width, 0, padded_side(height, scale) - height)
        with torch.inference_mode():
            img0 = functional.pad(frame_to_tensor(first, self._device, self._precision), pad)
            img1 = functional.pad(frame_to_tensor(second, self._device, self._precision), pad)
            middle = self._loaded.model(img0, img1, time, scale)
            return tensor_to_frame(middle[:, :, :height, :width], first.dtype)

    def between_files(self, first: Path, second: Path, target: Path, time: float = 0.5) -> None:
        write_frame(target, self.between(read_frame(first), read_frame(second), time))


class RifeInterpolator:
    def __init__(self, gpu: GpuGuard, weights: Path, device: str = "cuda") -> None:
        self._gpu = gpu
        self._weights = weights
        self._device = device

    def session(self) -> AbstractContextManager[InterpolationSession]:
        return self._session()

    @contextmanager
    def _session(self) -> Iterator[InterpolationSession]:
        with guarded_model(self._gpu, self._load) as loaded:
            yield _RifeSession(loaded, self._device)

    def _load(self) -> IFNet:
        state = {
            key.removeprefix(STATE_PREFIX): value
            for key, value in read_weights(self._weights).items()
            if not key.removeprefix(STATE_PREFIX).startswith(TRAINING_ONLY_PREFIXES)
        }
        model = IFNet()
        model.load_state_dict(state)
        return model.eval().to(self._device, model_precision(self._device))
