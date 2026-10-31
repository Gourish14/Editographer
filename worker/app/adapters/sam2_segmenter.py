"""SAM 2.1 small (Apache-2.0) subject masks through the GPU guard.

Spec: specs/05-editing-brain.md#b8-text-and-audio. Weights live in models/sam2_1_small
(Hugging Face `facebook/sam2.1-hiera-small`, transformers format). The model is loaded only for
the call, so the next stage has the VRAM. A failure gives no masks, never a failed job.
"""

from __future__ import annotations

import importlib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import structlog

from app.adapters.opencv_photo import read_image
from app.ports.gpu_guard import GpuGuard
from app.ports.segmenter import Point

log = structlog.get_logger()

MASK_THRESHOLD = 0.0
MIN_SUBJECT_SHARE = 0.01
MAX_SUBJECT_SHARE = 0.85


class Sam2Segmenter:
    def __init__(self, model_dir: Path, gpu: GpuGuard) -> None:
        self._model_dir = model_dir
        self._gpu = gpu

    def track(
        self, frames: Sequence[Path], points: Sequence[Point], folder: Path
    ) -> tuple[Path, ...]:
        if not frames or not points or not (self._model_dir / "model.safetensors").is_file():
            return ()
        try:
            with self._gpu.loaded(self._load) as (model, processor, device):
                masks = _propagate(model, processor, device, frames, points)
        except Exception as error:  # noqa: BLE001 - masks are optional by spec
            log.warning("segmenter.failed", message=str(error))
            return ()
        return _write(masks, folder)

    def _load(self) -> tuple[Any, Any, str]:
        torch = importlib.import_module("torch")
        transformers = importlib.import_module("transformers")
        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.bfloat16 if device == "cuda" else torch.float32
        processor = transformers.Sam2VideoProcessor.from_pretrained(str(self._model_dir))
        model = transformers.Sam2VideoModel.from_pretrained(str(self._model_dir), dtype=dtype)
        return model.to(device).eval(), processor, device


def _propagate(
    model: Any, processor: Any, device: str, frames: Sequence[Path], points: Sequence[Point]
) -> list[Any]:
    torch = importlib.import_module("torch")
    images = [read_image(frame)[:, :, ::-1] for frame in frames]
    height, width = images[0].shape[:2]
    session = processor.init_video_session(
        video=images,
        inference_device=device,
        video_storage_device="cpu",
        dtype=model.dtype,
    )
    clicks = [[round(x * width), round(y * height)] for x, y in points]
    processor.add_inputs_to_inference_session(
        inference_session=session,
        frame_idx=0,
        obj_ids=1,
        input_points=[[clicks]],
        input_labels=[[[1] * len(clicks)]],
    )
    masks: dict[int, Any] = {}
    with torch.inference_mode():
        model(inference_session=session, frame_idx=0)  # the clicks are consumed by frame 0
        for output in model.propagate_in_video_iterator(session):
            resized = processor.post_process_masks(
                [output.pred_masks], original_sizes=[[height, width]], binarize=False
            )[0]
            masks[output.frame_idx] = (resized[0, 0] > MASK_THRESHOLD).cpu().numpy()
    return [masks[index] for index in range(len(images)) if index in masks]


def _write(masks: Sequence[Any], folder: Path) -> tuple[Path, ...]:
    """Gray PNGs, white is subject. A first mask that is empty or covers nearly everything is
    not a subject, so it gives no masks."""
    if len(masks) == 0:
        return ()
    share = float(np.mean(masks[0]))
    if not MIN_SUBJECT_SHARE <= share <= MAX_SUBJECT_SHARE:
        log.info("segmenter.no_subject", share=round(share, 3))
        return ()
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for index, mask in enumerate(masks, start=1):
        path = folder / f"{index:06d}.png"
        cv2.imwrite(str(path), mask.astype(np.uint8) * 255)
        paths.append(path)
    return tuple(paths)
