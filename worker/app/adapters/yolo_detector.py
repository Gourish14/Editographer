"""Object detection with YOLO nano. Spec: specs/04-pipeline.md#stages (3)

Ultralytics is AGPL-3.0, see specs/03-tech-stack.md#license-note.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from itertools import batched
from pathlib import Path
from typing import Any

from app.adapters.model_runtime import (
    CUDA_DEVICE,
    best_device,
    gpu_errors,
    pin_model_folders,
    require_file,
)
from app.adapters.proxy_frames import sampled_frames
from app.domain.shots import DetectedObject, FrameObjects
from app.ports.gpu_guard import GpuGuard

BATCH_FRAMES = 16
IMAGE_SIZE = 640
MIN_CONFIDENCE = 0.35
FP16 = 16


class YoloObjectDetector:
    def __init__(self, weights: Path, gpu: GpuGuard) -> None:
        self._weights = weights
        self._gpu = gpu

    def detect_objects(self, path: Path) -> tuple[FrameObjects, ...]:
        with gpu_errors(), self._gpu.loaded(self._load) as model:
            try:
                return tuple(_detect(model, sampled_frames(path)))
            finally:
                del model  # the guard frees VRAM on exit, so nothing may still hold the model

    def _load(self) -> Any:
        pin_model_folders(self._weights.parent.parent)
        from ultralytics.models import YOLO

        return YOLO(str(require_file(self._weights))).to(best_device())


def _detect(model: Any, frames: Iterable[tuple[float, Any]]) -> Iterator[FrameObjects]:
    precision = FP16 if best_device() == CUDA_DEVICE else None
    for batch in batched(frames, BATCH_FRAMES):
        results = model.predict(
            [frame for _, frame in batch],
            imgsz=IMAGE_SIZE,
            conf=MIN_CONFIDENCE,
            quantize=precision,
            batch=BATCH_FRAMES,
            verbose=False,
        )
        for (time, _), result in zip(batch, results, strict=True):
            yield FrameObjects(time, _objects(result))


def _objects(result: Any) -> tuple[DetectedObject, ...]:
    boxes = result.boxes
    return tuple(
        DetectedObject(result.names[int(label)], float(confidence), *map(float, box))
        for label, confidence, box in zip(
            boxes.cls.tolist(), boxes.conf.tolist(), boxes.xywhn.tolist(), strict=True
        )
    )
