"""Keeps model libraries inside the project and offline. Spec: specs/README.md#hard-rules (2, 3)

Ultralytics, Hugging Face and torch hub default to caches in the user profile. Ultralytics also
sends usage analytics and can pip-install packages unless told it is offline. Call
`pin_model_folders` before importing any of them; `open_clip` and `ultralytics` are imported
only after it, inside the adapters' load functions.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import torch

from app.domain.errors import AnalysisError, ErrorCode

CUDA_DEVICE = "cuda"
CPU_DEVICE = "cpu"


def pin_model_folders(models_dir: Path) -> None:
    """Overrides rather than defaults: a value set on the machine must not escape the project."""
    os.environ.update(
        {
            "TORCH_HOME": str(models_dir / "torch"),
            "HF_HOME": str(models_dir / "huggingface"),
            "HF_HUB_OFFLINE": "1",
            "YOLO_CONFIG_DIR": str(models_dir / "ultralytics"),
            "YOLO_OFFLINE": "true",
            "YOLO_AUTOINSTALL": "false",
            "MPLCONFIGDIR": str(models_dir / "matplotlib"),
        }
    )


def best_device() -> str:
    return CUDA_DEVICE if torch.cuda.is_available() else CPU_DEVICE


def require_file(path: Path) -> Path:
    """Stops a library from trying to fetch a missing file."""
    if not path.is_file():
        raise AnalysisError(f"Missing model file {path.name}. Run setup.bat again.")
    return path


@contextmanager
def gpu_errors() -> Iterator[None]:
    """Turns running out of VRAM into the shared error code."""
    try:
        yield
    except torch.cuda.OutOfMemoryError as error:
        raise AnalysisError("The GPU ran out of memory", ErrorCode.GPU_OUT_OF_MEMORY) from error
