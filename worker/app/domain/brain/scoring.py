"""Shot scoring. Spec: specs/05-editing-brain.md#b2-shot-scoring-scoringpy

Phase 1 has motion, subject, sharpness and stability. Action and aesthetics weigh 0 until Phase 2,
and the remaining weights are renormalized to sum to 1.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from statistics import fmean, median, pvariance

from app.domain.shots import FrameSample, ShotMeasure, TimeWindow

MOTION_WEIGHT = 0.25
SUBJECT_WEIGHT = 0.20
SHARPNESS_WEIGHT = 0.15
STABILITY_WEIGHT = 0.10
WEIGHT_TOTAL = MOTION_WEIGHT + SUBJECT_WEIGHT + SHARPNESS_WEIGHT + STABILITY_WEIGHT

MIN_SCORE = 0.2
MIN_LUMA = 0.08
USABLE_MIN_SHARPNESS_SHARE = 0.5
USABLE_MIN_SEC = 0.5
SAMPLE_STEP_SEC = 0.25
FULL_SUBJECT_AREA = 0.25
SHAKE_HALF_POINT = 1.0
PEAK_SUBJECT_FLOOR = 0.1


class RejectReason(StrEnum):
    LOW_SCORE = "low_score"
    TOO_DARK = "too_dark"


@dataclass(frozen=True)
class ScoredShot:
    measure: ShotMeasure
    score: float
    reject_reason: RejectReason | None

    @property
    def is_usable(self) -> bool:
        return self.reject_reason is None


def measure_shot(frames: Sequence[FrameSample], start: float, end: float) -> ShotMeasure:
    """Boils a shot's sampled frames down to one set of numbers."""
    if not frames:
        raise ValueError("A shot needs at least one sampled frame")
    camera_shake = pvariance([frame.camera_motion for frame in frames])
    return ShotMeasure(
        start=start,
        end=end,
        motion=fmean(frame.motion for frame in frames),
        subject=fmean(min(1.0, frame.subject_area / FULL_SUBJECT_AREA) for frame in frames),
        sharpness=fmean(frame.sharpness for frame in frames),
        stability=1.0 - camera_shake / (camera_shake + SHAKE_HALF_POINT),
        luma=fmean(frame.luma for frame in frames),
        peak_time=_peak_time(frames),
        usable=_usable_windows(frames),
    )


def score_shots(shots: Sequence[ShotMeasure]) -> tuple[ScoredShot, ...]:
    """Scores every shot of a project 0..1 and marks the ones to reject."""
    motion = _percentile_ranks([shot.motion for shot in shots])
    sharpness = _percentile_ranks([shot.sharpness for shot in shots])
    return tuple(
        _scored(shot, motion_rank, sharpness_rank)
        for shot, motion_rank, sharpness_rank in zip(shots, motion, sharpness, strict=True)
    )


def _scored(shot: ShotMeasure, motion: float, sharpness: float) -> ScoredShot:
    score = (
        MOTION_WEIGHT * motion
        + SUBJECT_WEIGHT * shot.subject
        + SHARPNESS_WEIGHT * sharpness
        + STABILITY_WEIGHT * shot.stability
    ) / WEIGHT_TOTAL
    reason = None
    if shot.luma < MIN_LUMA:
        reason = RejectReason.TOO_DARK
    elif score < MIN_SCORE:
        reason = RejectReason.LOW_SCORE
    return ScoredShot(shot, round(score, 4), reason)


def _percentile_ranks(values: Sequence[float]) -> list[float]:
    """Share of the other values each one beats, 0 for the lowest and 1 for the highest."""
    if len(values) < 2:
        return [1.0 for _ in values]
    ordered = sorted(values)
    return [ordered.index(value) / (len(values) - 1) for value in values]


def _peak_time(frames: Sequence[FrameSample]) -> float:
    """The frame with the highest motion times subject; without a subject, the most motion."""
    best = max(
        frames,
        key=lambda frame: frame.motion * max(PEAK_SUBJECT_FLOOR, frame.subject_area),
    )
    return best.time


def _usable_windows(frames: Sequence[FrameSample]) -> tuple[TimeWindow, ...]:
    """Stretches of at least 0.5 s that are sharp for this shot and not too dark."""
    floor = median(frame.sharpness for frame in frames) * USABLE_MIN_SHARPNESS_SHARE
    windows: list[TimeWindow] = []
    run_start: float | None = None
    run_end = 0.0
    for frame in frames:
        if frame.sharpness >= floor and frame.luma >= MIN_LUMA:
            run_start = frame.time if run_start is None else run_start
            run_end = frame.time + SAMPLE_STEP_SEC
        else:
            windows.extend(_window(run_start, run_end))
            run_start = None
    windows.extend(_window(run_start, run_end))
    return tuple(windows)


def _window(start: float | None, end: float) -> list[TimeWindow]:
    if start is None or end - start < USABLE_MIN_SEC:
        return []
    return [TimeWindow(start=start, end=end)]
