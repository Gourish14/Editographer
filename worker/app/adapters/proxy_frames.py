"""The 4 fps frames every analysis adapter reads. Spec: specs/05-editing-brain.md#b2

One helper, so the sampler, YOLO and CLIP see the same frames at identical times.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import cv2

from app.domain.errors import AnalysisError

SAMPLES_PER_SEC = 4
FALLBACK_FPS = 30.0


def sampled_frames(path: Path) -> Iterator[tuple[float, Any]]:
    """Yields (time, BGR frame) one at a time, so a long clip never sits in memory."""
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise AnalysisError(f"Could not open {path.name}")
    try:
        fps = capture.get(cv2.CAP_PROP_FPS) or FALLBACK_FPS
        step = max(1, round(fps / SAMPLES_PER_SEC))
        index = 0
        while capture.grab():
            if index % step == 0:
                found, frame = capture.retrieve()
                if found:
                    yield index / fps, frame
            index += 1
    finally:
        capture.release()
