"""What the RIFE and Real-ESRGAN adapters share: GPU sessions, tensors and frame files.

Spec: specs/09-local-setup.md#6-gb-vram-model-profile
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

import cv2
import numpy as np
import torch
from numpy.typing import NDArray
from torch import Tensor, nn

from app.domain.errors import ErrorCode, RenderError
from app.ports.enhance import Frame
from app.ports.gpu_guard import GpuGuard

CHANNELS = 3
FRAME_DIMENSIONS = 3
FRAME_TYPES = (np.uint8, np.uint16)


class LoadedModel[M: nn.Module]:
    """Owns the model. The guard can only free VRAM once nothing else points at the network."""

    def __init__(self, model: M) -> None:
        self._model: M | None = model

    @property
    def model(self) -> M:
        if self._model is None:
            raise RenderError("The model session is closed")
        return self._model

    def release(self) -> None:
        self._model = None


@contextmanager
def guarded_model[M: nn.Module](gpu: GpuGuard, load: Callable[[], M]) -> Iterator[LoadedModel[M]]:
    """Holds the GPU for one model, frees it on exit and reports running out of VRAM by code."""
    try:
        with gpu.loaded(lambda: LoadedModel(load())) as loaded:
            try:
                yield loaded
            finally:
                loaded.release()
    except torch.cuda.OutOfMemoryError as error:
        raise RenderError("The GPU ran out of memory", ErrorCode.GPU_OUT_OF_MEMORY) from error


def read_weights(path: Path) -> dict[str, Any]:
    """weights_only keeps a checkpoint file from running code while it unpickles."""
    if not path.is_file():
        raise RenderError(f"Model weights are missing: {path.name}. Run setup.bat.")
    return cast(dict[str, Any], torch.load(path, map_location="cpu", weights_only=True))


def model_precision(device: str) -> torch.dtype:
    """fp16 on the GPU to fit the VRAM budget. The CPU has no reason to use it."""
    return torch.half if device.startswith("cuda") else torch.float


def check_frame(frame: Frame) -> None:
    is_image = frame.ndim == FRAME_DIMENSIONS and frame.shape[2] == CHANNELS
    if not is_image or frame.dtype not in FRAME_TYPES:
        raise RenderError(f"Expected an 8 or 16 bit RGB frame, got {frame.shape} {frame.dtype}")


def frame_to_tensor(frame: Frame, device: str, precision: torch.dtype) -> Tensor:
    """One image of shape 1 x 3 x height x width, from 0 to 1."""
    scaled = frame.astype(np.float32) / np.iinfo(frame.dtype).max
    tensor = torch.from_numpy(scaled).permute(2, 0, 1).unsqueeze(0)
    return tensor.to(device=device, dtype=precision)


def tensor_to_frame(tensor: Tensor, dtype: np.dtype[Any]) -> Frame:
    scaled: NDArray[np.float32] = (
        tensor.squeeze(0).permute(1, 2, 0).clamp(0.0, 1.0).to("cpu", torch.float).numpy()
    )
    return cast(Frame, np.rint(scaled * np.iinfo(dtype).max).astype(dtype))


def read_frame(path: Path) -> Frame:
    """Goes through bytes because cv2.imread fails on Windows paths outside the code page."""
    data = np.fromfile(path, dtype=np.uint8) if path.is_file() else np.empty(0, np.uint8)
    decoded = cv2.imdecode(data, cv2.IMREAD_COLOR | cv2.IMREAD_ANYDEPTH) if data.size else None
    if decoded is None:
        raise RenderError(f"Cannot read the frame {path.name}")
    frame = cast(Frame, cv2.cvtColor(decoded, cv2.COLOR_BGR2RGB))
    check_frame(frame)
    return frame


def write_frame(path: Path, frame: Frame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        encoded_ok, encoded = cv2.imencode(path.suffix, cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
    except cv2.error as error:
        raise RenderError(f"Cannot write the frame {path.name}") from error
    if not encoded_ok:
        raise RenderError(f"Cannot write the frame {path.name}")
    encoded.tofile(path)
