"""Frame measurements with OpenCV and MediaPipe.

Spec: specs/05-editing-brain.md#b2-shot-scoring-scoringpy
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import mediapipe as mp
import numpy as np

from app.adapters.proxy_frames import sampled_frames
from app.domain.shots import FrameSample

ANALYSIS_WIDTH = 320
MAX_LUMA = 255.0
COLOR_BIN = 32


class OpenCvFrameSampler:
    """Reads the proxy once, measuring motion, sharpness, brightness and the largest face."""

    def __init__(self, face_model: Path) -> None:
        self._face_model = face_model

    def sample(self, path: Path) -> tuple[FrameSample, ...]:
        samples: list[FrameSample] = []
        previous: Any = None
        with self._face_detector() as faces:
            for time, frame in sampled_frames(path):
                small = _shrink(frame)
                gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                samples.append(_measure(time, small, gray, previous, faces))
                previous = gray
        return tuple(samples)

    def _face_detector(self) -> Any:
        vision = mp.tasks.vision
        options = vision.FaceDetectorOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(self._face_model)),
            running_mode=vision.RunningMode.IMAGE,
        )
        return vision.FaceDetector.create_from_options(options)


def _shrink(frame: Any) -> Any:
    height, width = frame.shape[:2]
    if width <= ANALYSIS_WIDTH:
        return frame
    return cv2.resize(frame, (ANALYSIS_WIDTH, round(height * ANALYSIS_WIDTH / width)))


def _measure(time: float, small: Any, gray: Any, previous: Any, faces: Any) -> FrameSample:
    motion, camera_motion, flow_x, flow_y = _flow(previous, gray)
    return FrameSample(
        time=time,
        motion=motion,
        camera_motion=camera_motion,
        sharpness=float(cv2.Laplacian(gray, cv2.CV_64F).var()),
        luma=float(gray.mean()) / MAX_LUMA,
        subject_area=_largest_face_area(small, faces),
        flow_x=flow_x,
        flow_y=flow_y,
        color=_dominant_color(small),
    )


def _flow(previous: Any, gray: Any) -> tuple[float, float, float, float]:
    """Mean flow is overall motion; the median is what the whole frame shares, the camera."""
    if previous is None:
        return 0.0, 0.0, 0.0, 0.0
    no_initial_flow: Any = None
    flow = cv2.calcOpticalFlowFarneback(previous, gray, no_initial_flow, 0.5, 2, 15, 2, 5, 1.2, 0)
    magnitude = np.linalg.norm(flow, axis=2)
    flow_x, flow_y = flow.mean(axis=(0, 1))
    return float(magnitude.mean()), float(np.median(magnitude)), float(flow_x), float(flow_y)


def _largest_face_area(small: Any, faces: Any) -> float:
    height, width = small.shape[:2]
    rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
    result = faces.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
    areas = [box.bounding_box.width * box.bounding_box.height for box in result.detections]
    return float(max(areas, default=0)) / float(width * height)


def _dominant_color(small: Any) -> str:
    """The middle of the most filled coarse RGB bin, as #rrggbb."""
    blue, green, red = np.moveaxis(small.astype(np.int64) // COLOR_BIN, 2, 0)
    bins = red * COLOR_BIN**2 + green * COLOR_BIN + blue
    values, counts = np.unique(bins, return_counts=True)
    winner = int(values[counts.argmax()])
    half = COLOR_BIN // 2
    channels = (winner // COLOR_BIN**2, winner // COLOR_BIN % COLOR_BIN, winner % COLOR_BIN)
    return "#" + "".join(f"{channel * COLOR_BIN + half:02x}" for channel in channels)
