"""What analysis measures about shots. Spec: specs/05-editing-brain.md#b2-shot-scoring-scoringpy"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict


@dataclass(frozen=True)
class FrameSample:
    """One frame sampled at 4 fps from the proxy."""

    time: float
    motion: float
    camera_motion: float
    sharpness: float
    luma: float
    subject_area: float


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
