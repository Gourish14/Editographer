"""RIFE and Real-ESRGAN on the real GPU, kept small because it is shared.

Spec: specs/09-local-setup.md#6-gb-vram-model-profile [T-301]
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import torch

from app.adapters.nvml_gpu_guard import NvmlGpuGuard
from app.adapters.realesrgan_upscaler import RealEsrganUpscaler
from app.adapters.rife_interpolator import RifeInterpolator
from app.ports.enhance import FrameSize

MODELS = Path(__file__).resolve().parents[3] / "models"
RIFE_WEIGHTS = MODELS / "rife" / "flownet_v4.25.pkl"
ESRGAN_WEIGHTS = MODELS / "realesrgan" / "realesr-general-x4v3.pth"
SIDE = 128

pytestmark = [
    pytest.mark.gpu,
    pytest.mark.skipif(
        not torch.cuda.is_available() or not RIFE_WEIGHTS.exists() or not ESRGAN_WEIGHTS.exists(),
        reason="needs CUDA and the RIFE and Real-ESRGAN weights",
    ),
]


def test_rife_runs_in_fp16_and_leaves_no_vram_behind() -> None:
    first = np.zeros((SIDE, SIDE, 3), np.uint8)
    second = first.copy()
    first[40:80, 20:60] = 255
    second[40:80, 44:84] = 255
    before = torch.cuda.memory_allocated()

    with RifeInterpolator(NvmlGpuGuard(), RIFE_WEIGHTS).session() as session:
        middle = session.between(first, second)

    assert torch.cuda.memory_allocated() == before
    assert np.nonzero(middle[..., 0].max(axis=0) > 127)[0].min() == pytest.approx(32, abs=5)


def test_real_esrgan_runs_in_fp16_and_leaves_no_vram_behind() -> None:
    frame = np.full((SIDE // 2, SIDE // 2, 3), 128, np.uint8)
    before = torch.cuda.memory_allocated()

    with RealEsrganUpscaler(NvmlGpuGuard(), ESRGAN_WEIGHTS).session(cool_mode=True) as session:
        upscaled = session.upscale(frame, FrameSize(SIDE * 2, SIDE * 2))

    assert torch.cuda.memory_allocated() == before
    assert upscaled.shape == (SIDE * 2, SIDE * 2, 3)
    assert upscaled.mean() == pytest.approx(128, abs=4)
