"""Depth Anything V2 Small (Apache-2.0, Small only) through the GPU guard.

Spec: specs/04-pipeline.md#stages (4). Weights live in models/depth_anything_v2_small.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from app.adapters.opencv_photo import read_image
from app.domain.errors import AnalysisError
from app.domain.photo import DepthSummary
from app.ports.gpu_guard import GpuGuard

LOW_PERCENTILE = 5
HIGH_PERCENTILE = 95
NEAR_PERCENTILE = 60


class DepthAnythingEstimator:
    """Loads the model only for the call, then unloads it so the next stage has the VRAM."""

    def __init__(self, model_dir: Path, gpu: GpuGuard) -> None:
        self._model_dir = model_dir
        self._gpu = gpu

    def estimate(self, image: Path, map_file: Path) -> DepthSummary:
        if not (self._model_dir / "model.safetensors").is_file():
            raise AnalysisError("Depth model is missing, run setup.bat to download it")
        pixels = read_image(image)
        height, width = pixels.shape[:2]
        with self._gpu.loaded(self._load) as (model, processor, device):
            raw = _predict(model, processor, device, pixels)
        depth = cv2.resize(raw, (width, height), interpolation=cv2.INTER_CUBIC)
        return _write_map(depth, map_file)

    def _load(self) -> tuple[Any, Any, str]:
        torch = importlib.import_module("torch")
        transformers = importlib.import_module("transformers")
        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if device == "cuda" else torch.float32
        processor = transformers.AutoImageProcessor.from_pretrained(str(self._model_dir))
        model = transformers.AutoModelForDepthEstimation.from_pretrained(
            str(self._model_dir), dtype=dtype
        )
        return model.to(device).eval(), processor, device


def _predict(model: Any, processor: Any, device: str, pixels: Any) -> Any:
    torch = importlib.import_module("torch")
    rgb = cv2.cvtColor(pixels, cv2.COLOR_BGR2RGB)
    inputs = processor(images=rgb, return_tensors="pt")
    values = inputs["pixel_values"].to(device=device, dtype=model.dtype)
    with torch.inference_mode():
        predicted = model(pixel_values=values).predicted_depth
    return predicted[0].float().cpu().numpy()


def _write_map(depth: Any, map_file: Path) -> DepthSummary:
    """Saves near-is-bright 8-bit and measures contrast on the raw map (flat scenes stay low)."""
    depth = np.clip(depth, 0.0, None)
    low, high = np.percentile(depth, [LOW_PERCENTILE, HIGH_PERCENTILE])
    contrast = float((high - low) / high) if high > 0 else 0.0
    span = float(depth.max() - depth.min()) or 1.0
    gray = ((depth - depth.min()) / span * 255.0).round().astype(np.uint8)
    map_file.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(map_file), gray):
        raise AnalysisError(f"Could not write {map_file.name}")
    near = int(np.percentile(gray, NEAR_PERCENTILE))
    return DepthSummary(contrast=contrast, near_threshold=near, map_file=str(map_file))
