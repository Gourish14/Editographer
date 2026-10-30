"""Photo size and subject box with OpenCV and MediaPipe.

Spec: specs/04-pipeline.md#stages (4). Reuses the face model from models/mediapipe.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import mediapipe as mp
import numpy as np

from app.domain.errors import AnalysisError
from app.domain.photo import FocusBox, FocusSource

SALIENCY_WIDTH = 256
MIN_SALIENT_SHARE = 0.01
CENTER_BOX = FocusBox(0.25, 0.25, 0.5, 0.5, FocusSource.CENTER)


def read_image(image: Path) -> Any:
    """BGR pixels, EXIF rotation applied (OpenCV does this on read)."""
    pixels = cv2.imread(str(image), cv2.IMREAD_COLOR)
    if pixels is None:
        raise AnalysisError(f"Could not open {image.name}")
    return pixels


class OpenCvImageSizer:
    def size(self, image: Path) -> tuple[int, int]:
        height, width = read_image(image).shape[:2]
        return int(width), int(height)


class OpenCvSubjectLocator:
    """Largest face, else the spectral-residual saliency blob, else the center."""

    def __init__(self, face_model: Path) -> None:
        self._face_model = face_model

    def locate(self, image: Path) -> FocusBox:
        pixels = read_image(image)
        return self._face(pixels) or _saliency(pixels) or CENTER_BOX

    def _face(self, pixels: Any) -> FocusBox | None:
        vision = mp.tasks.vision
        options = vision.FaceDetectorOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(self._face_model)),
            running_mode=vision.RunningMode.IMAGE,
        )
        height, width = pixels.shape[:2]
        rgb = cv2.cvtColor(pixels, cv2.COLOR_BGR2RGB)
        with vision.FaceDetector.create_from_options(options) as detector:
            found = detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
        boxes = [d.bounding_box for d in found.detections]
        if not boxes:
            return None
        box = max(boxes, key=lambda b: b.width * b.height)
        return _clamped(
            box.origin_x / width,
            box.origin_y / height,
            box.width / width,
            box.height / height,
            FocusSource.FACE,
        )


def _saliency(pixels: Any) -> FocusBox | None:
    height, width = pixels.shape[:2]
    small = cv2.resize(pixels, (SALIENCY_WIDTH, max(1, round(height * SALIENCY_WIDTH / width))))
    detector: Any = cv2.saliency.StaticSaliencySpectralResidual_create()  # type: ignore[attr-defined]
    ok, saliency = detector.computeSaliency(small)
    if not ok:
        return None
    gray = cv2.GaussianBlur(saliency.astype(np.float32), (0, 0), 3)
    top = float(gray.max())
    if top <= 0:
        return None
    mask = (gray >= top * 0.6).astype(np.uint8)
    x, y, w, h = cv2.boundingRect(mask)
    small_h, small_w = gray.shape
    if w * h < MIN_SALIENT_SHARE * small_w * small_h:
        return None
    return _clamped(x / small_w, y / small_h, w / small_w, h / small_h, FocusSource.SALIENCY)


def _clamped(x: float, y: float, w: float, h: float, source: FocusSource) -> FocusBox:
    x0, y0 = max(0.0, x), max(0.0, y)
    return FocusBox(x0, y0, min(w, 1.0 - x0), min(h, 1.0 - y0), source)
