"""What analysis measures about shots. Spec: specs/05-editing-brain.md#b2-shot-scoring-scoringpy"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

Embedding = tuple[float, ...]
"""A CLIP vector as plain floats, so the domain needs neither numpy nor torch."""

NO_COLOR = "#000000"


class MotionDirection(StrEnum):
    """The way the picture moves. A camera panning right makes the picture move left."""

    LEFT = "left"
    RIGHT = "right"
    UP = "up"
    DOWN = "down"
    NONE = "none"


@dataclass(frozen=True)
class FrameSample:
    """One frame sampled at 4 fps from the proxy."""

    time: float
    motion: float
    camera_motion: float
    sharpness: float
    luma: float
    subject_area: float
    flow_x: float = 0.0
    flow_y: float = 0.0
    color: str = NO_COLOR


@dataclass(frozen=True)
class DetectedObject:
    """One detector box. Position and size are shares of the frame, 0..1."""

    label: str
    confidence: float
    center_x: float
    center_y: float
    width: float
    height: float

    @property
    def area(self) -> float:
        return self.width * self.height


@dataclass(frozen=True)
class FrameObjects:
    """Everything detected in one sampled frame; `time` matches its FrameSample."""

    time: float
    objects: tuple[DetectedObject, ...]


@dataclass(frozen=True)
class ShotVision:
    """What CLIP sees in one shot."""

    embedding: Embedding
    aesthetics: float


class TimeWindow(BaseModel):
    model_config = ConfigDict(frozen=True)

    start: float
    end: float


class ShotMeasure(BaseModel):
    """Raw per-shot numbers. Percentile ranks need every clip, so scoring waits for planning."""

    model_config = ConfigDict(frozen=True)

    start: float
    end: float
    motion: float
    subject: float
    sharpness: float
    stability: float
    luma: float
    peak_time: float
    usable: tuple[TimeWindow, ...]
    tags: tuple[str, ...] = ()
    action: float = 0.0
    aesthetics: float = 0.0
    motion_direction: MotionDirection = MotionDirection.NONE
    dominant_color: str = NO_COLOR
    embedding: Embedding = ()


def cosine_similarity(first: Sequence[float], second: Sequence[float]) -> float:
    """Cosine of two vectors. An empty or zero vector resembles nothing, so it gives 0."""
    if not first or not second:
        return 0.0
    length = math.sqrt(math.sumprod(first, first) * math.sumprod(second, second))
    return math.sumprod(first, second) / length if length else 0.0
