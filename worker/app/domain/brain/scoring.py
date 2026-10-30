"""Shot scoring. Spec: specs/05-editing-brain.md#b2-shot-scoring-scoringpy

The action term A comes from object velocity peaks only for now; pose keypoints join it later.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from itertools import pairwise
from statistics import fmean, median, pvariance

from app.domain.brain.shot_tags import clip_tags, object_tags
from app.domain.shots import (
    Embedding,
    FrameObjects,
    FrameSample,
    MotionDirection,
    ShotMeasure,
    ShotVision,
    TimeWindow,
    cosine_similarity,
)

MOTION_WEIGHT = 0.25
SUBJECT_WEIGHT = 0.20
SHARPNESS_WEIGHT = 0.15
ACTION_WEIGHT = 0.15
AESTHETICS_WEIGHT = 0.15
STABILITY_WEIGHT = 0.10

MIN_SCORE = 0.2
MIN_LUMA = 0.08
DUPLICATE_SIMILARITY = 0.95
USABLE_MIN_SHARPNESS_SHARE = 0.5
USABLE_MIN_SEC = 0.5
SAMPLE_STEP_SEC = 0.25
FULL_SUBJECT_AREA = 0.25
SHAKE_HALF_POINT = 1.0
PEAK_SUBJECT_FLOOR = 0.1
PERSON_LABEL = "person"
MAX_OBJECT_STEP = 0.35
ACTION_PEAK_PERCENTILE = 0.9
DIRECTION_MIN_FLOW = 0.2
DIRECTION_MIN_AGREEMENT = 0.3


class RejectReason(StrEnum):
    LOW_SCORE = "low_score"
    TOO_DARK = "too_dark"
    DUPLICATE = "duplicate"


@dataclass(frozen=True)
class ScoredShot:
    measure: ShotMeasure
    score: float
    reject_reason: RejectReason | None

    @property
    def is_usable(self) -> bool:
        return self.reject_reason is None


def measure_shot(
    frames: Sequence[FrameSample],
    start: float,
    end: float,
    objects: Sequence[FrameObjects] = (),
) -> ShotMeasure:
    """Boils a shot's sampled frames down to one set of numbers."""
    if not frames:
        raise ValueError("A shot needs at least one sampled frame")
    people = _with_people(frames, objects)
    moving = people[1:] or people  # the first flow was measured across the cut before the shot
    camera_shake = pvariance([frame.camera_motion for frame in moving])
    return ShotMeasure(
        start=start,
        end=end,
        motion=fmean(frame.motion for frame in moving),
        subject=fmean(min(1.0, frame.subject_area / FULL_SUBJECT_AREA) for frame in people),
        sharpness=fmean(frame.sharpness for frame in people),
        stability=1.0 - camera_shake / (camera_shake + SHAKE_HALF_POINT),
        luma=fmean(frame.luma for frame in people),
        peak_time=_peak_time(moving),
        usable=_usable_windows(people),
        action=object_velocity_peak(objects),
        motion_direction=_motion_direction(moving),
        dominant_color=Counter(frame.color for frame in people).most_common(1)[0][0],
    )


def describe_shot(
    measure: ShotMeasure,
    vision: ShotVision,
    objects: Sequence[FrameObjects],
    vocabulary: Mapping[str, Embedding],
) -> ShotMeasure:
    """Adds what the models saw: aesthetics, the embedding and the tags."""
    tags = (*clip_tags(vision.embedding, vocabulary), *object_tags(objects))
    return measure.model_copy(
        update={
            "aesthetics": vision.aesthetics,
            "embedding": vision.embedding,
            "tags": tuple(dict.fromkeys(tags)),
        }
    )


def object_velocity_peak(objects: Sequence[FrameObjects]) -> float:
    """How fast the shot's fastest object gets, in frame widths per second."""
    speeds = [_fastest_object(before, after) for before, after in pairwise(objects)]
    if not speeds:
        return 0.0
    ordered = sorted(speeds)
    return ordered[math.ceil(ACTION_PEAK_PERCENTILE * len(ordered)) - 1]


def score_shots(shots: Sequence[ShotMeasure]) -> tuple[ScoredShot, ...]:
    """Scores every shot of a project 0..1 and marks the ones to reject."""
    motion = _percentile_ranks([shot.motion for shot in shots])
    sharpness = _percentile_ranks([shot.sharpness for shot in shots])
    action = _percentile_ranks([shot.action for shot in shots])
    scored = [
        _scored(shot, motion_rank, sharpness_rank, action_rank)
        for shot, motion_rank, sharpness_rank, action_rank in zip(
            shots, motion, sharpness, action, strict=True
        )
    ]
    return _reject_duplicates(scored)


def _scored(shot: ShotMeasure, motion: float, sharpness: float, action: float) -> ScoredShot:
    score = (
        MOTION_WEIGHT * motion
        + SUBJECT_WEIGHT * shot.subject
        + SHARPNESS_WEIGHT * sharpness
        + ACTION_WEIGHT * action
        + AESTHETICS_WEIGHT * shot.aesthetics
        + STABILITY_WEIGHT * shot.stability
    )
    reason = None
    if shot.luma < MIN_LUMA:
        reason = RejectReason.TOO_DARK
    elif score < MIN_SCORE:
        reason = RejectReason.LOW_SCORE
    return ScoredShot(shot, round(score, 4), reason)


def _reject_duplicates(scored: Sequence[ScoredShot]) -> tuple[ScoredShot, ...]:
    """Best first, a usable shot is dropped if it repeats a better shot that was kept."""
    result = list(scored)
    kept: list[Embedding] = []
    for index in sorted(range(len(scored)), key=lambda i: -scored[i].score):
        shot = scored[index]
        if not shot.is_usable:
            continue
        embedding = shot.measure.embedding
        if any(cosine_similarity(embedding, other) > DUPLICATE_SIMILARITY for other in kept):
            result[index] = replace(shot, reject_reason=RejectReason.DUPLICATE)
        else:
            kept.append(embedding)
    return tuple(result)


def _with_people(
    frames: Sequence[FrameSample], objects: Sequence[FrameObjects]
) -> list[FrameSample]:
    """F is face or person: each frame's subject is the larger of the face and any person."""
    people = {
        found.time: max(
            (box.area for box in found.objects if box.label == PERSON_LABEL), default=0.0
        )
        for found in objects
    }
    return [
        replace(frame, subject_area=max(frame.subject_area, people.get(frame.time, 0.0)))
        for frame in frames
    ]


def _fastest_object(before: FrameObjects, after: FrameObjects) -> float:
    """Each box is paired with the nearest same-label box; a far one is a different object."""
    elapsed = after.time - before.time
    if elapsed <= 0:
        return 0.0
    steps = [
        min(
            (
                math.dist((box.center_x, box.center_y), (old.center_x, old.center_y))
                for old in before.objects
                if old.label == box.label
            ),
            default=math.inf,
        )
        for box in after.objects
    ]
    return max((step for step in steps if step <= MAX_OBJECT_STEP), default=0.0) / elapsed


def _motion_direction(frames: Sequence[FrameSample]) -> MotionDirection:
    """The axis the flow agrees on; shaking back and forth cancels out to no direction."""
    flow_x = fmean(frame.flow_x for frame in frames)
    flow_y = fmean(frame.flow_y for frame in frames)
    drift = math.hypot(flow_x, flow_y)
    total = fmean(frame.motion for frame in frames)
    if drift < DIRECTION_MIN_FLOW or drift < total * DIRECTION_MIN_AGREEMENT:
        return MotionDirection.NONE
    if abs(flow_x) >= abs(flow_y):
        return MotionDirection.RIGHT if flow_x > 0 else MotionDirection.LEFT
    return MotionDirection.DOWN if flow_y > 0 else MotionDirection.UP


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
