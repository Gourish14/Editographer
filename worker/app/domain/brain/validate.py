"""Validation before render.

Spec: specs/05-editing-brain.md#b11-validation-before-render-validatepy
"""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Sequence

from app.domain.brain.effects import SHAKE, SHAKE_CAP_SHARE
from app.domain.brain.pacing import beat_grid
from app.domain.brain.ramps import curve_source_length
from app.domain.errors import ErrorCode, RenderError
from app.domain.music import MusicMap
from app.domain.plan import EditPlan

ALLOWED_DRIFT_SEC = 0.002
PHOTO_SEGMENT = "photo"


def validate_plan(plan: EditPlan, music: MusicMap) -> None:
    """Raises PLAN_INVALID with every problem found, so a failure can be fixed in one go."""
    problems = [
        *_cuts_on_the_grid(plan, music),
        *_no_gaps(plan),
        *_source_covers_timeline(plan),
        *_shake_cap(plan, music),
    ]
    if problems:
        raise RenderError("; ".join(problems), ErrorCode.PLAN_INVALID)


def distance_to_grid(time: float, grid: Sequence[float]) -> float:
    position = bisect_left(grid, time)
    near = grid[max(0, position - 1) : position + 1]
    return min(abs(time - point) for point in near)


def _cuts_on_the_grid(plan: EditPlan, music: MusicMap) -> list[str]:
    grid = beat_grid(music)
    frame = 1.0 / plan.output.fps
    return [
        f"{segment.id} starts off the beat at {segment.at}"
        for segment in plan.segments
        if distance_to_grid(segment.at, grid) > frame
    ]


def _no_gaps(plan: EditPlan) -> list[str]:
    problems = []
    position = plan.music.start
    for segment in plan.segments:
        if abs(segment.at - position) > ALLOWED_DRIFT_SEC:
            problems.append(f"{segment.id} leaves a gap or overlap at {segment.at}")
        position = segment.at + segment.duration
    if abs(position - plan.music.end) > ALLOWED_DRIFT_SEC:
        problems.append(f"The plan ends at {position:.3f}, not at {plan.music.end:.3f}")
    return problems


def _source_covers_timeline(plan: EditPlan) -> list[str]:
    return [
        f"{segment.id} has a source window shorter than its slot"
        for segment in plan.segments
        if segment.type != PHOTO_SEGMENT
        and segment.src_out - segment.src_in
        < curve_source_length(segment.speed.curve, segment.duration) - ALLOWED_DRIFT_SEC
    ]


def _shake_cap(plan: EditPlan, music: MusicMap) -> list[str]:
    beats = sum(1 for beat in music.beats if plan.music.start <= beat.time < plan.music.end)
    shakes = sum(
        1 for segment in plan.segments for effect in segment.effects if effect.type == SHAKE
    )
    if shakes > beats * SHAKE_CAP_SHARE:
        return [f"{shakes} shakes on {beats} beats breaks the 40% cap"]
    return []
