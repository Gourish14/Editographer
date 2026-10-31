"""Gives each video segment its framing. Spec: specs/05-editing-brain.md#b7-reframing-rules

Flat clips get a subject-tracked crop path; 360 clips get a camera path with the B5 and B7 moves
(follow, beat spin on drops, FOV punches, tiny planet at a section change), pitch limit last.
Times in a path are segment time, so a ramped slot's source times go through its speed curve.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.brain.assign import Assignment
from app.domain.brain.effects import ZOOM_PUNCH, with_fov_punch
from app.domain.brain.ramps import timeline_time_at
from app.domain.brain.reframe import (
    FULL_TURN,
    FrameSize,
    SubjectBearing,
    SubjectPoint,
    crop_path,
    follow_camera,
    limit_pitch,
    ratio_value,
    with_beat_spin,
    with_tiny_planet,
)
from app.domain.models import FollowPoint
from app.domain.plan import Camera360, Effect, Reframe, ReframePoint, Speed
from app.domain.shots import SubjectSample

PANO_PREFIX = "OSMO360"
VIDEO = "video"
VIDEO_360 = "video360"
FOLLOW_MATCH_DEG = 40.0
TRACK_SUBJECT = "main"
FOLLOW_SUBJECT = "picked"


@dataclass(frozen=True)
class Framing:
    type: str
    reframe: Reframe
    camera360: Camera360 | None
    effects: tuple[Effect, ...]


def is_panoramic(camera_mode: str | None) -> bool:
    return (camera_mode or "").startswith(PANO_PREFIX)


def frame_segment(
    assignment: Assignment,
    speed: Speed,
    effects: tuple[Effect, ...],
    camera_mode: str | None,
    size: FrameSize | None,
    ratio: str,
    beats: Sequence[float],
    drop_start: bool,
    ends_section: bool,
    follow: FollowPoint | None,
) -> Framing:
    """Everything about how one segment is framed. `size` is the source's, when known."""
    slot = assignment.slot
    offsets = [
        (sample, sample.time - assignment.src_in)
        for sample in assignment.candidate.shot.measure.subject_track
        if assignment.src_in <= sample.time <= assignment.src_out
    ]
    times = [
        (sample, timeline_time_at(speed.curve, slot.duration, offset)) for sample, offset in offsets
    ]
    if not is_panoramic(camera_mode):
        return Framing(VIDEO, _flat(times, size, ratio), None, effects)
    inside = [round(beat - slot.start, 4) for beat in beats if slot.start < beat < slot.end]
    keys = [0.0, *inside, round(slot.duration, 4)]
    camera, kept = _camera(times, effects, keys, ratio, drop_start, ends_section, follow)
    return Framing(VIDEO_360, Reframe(mode="track", subject=TRACK_SUBJECT), camera, kept)


def _flat(times: list[tuple[SubjectSample, float]], size: FrameSize | None, ratio: str) -> Reframe:
    if not times or size is None:
        return Reframe()
    track = [
        SubjectPoint(time, sample.x * size.width, sample.y * size.height) for sample, time in times
    ]
    windows = crop_path(track, size, ratio_value(ratio))
    path = tuple(
        ReframePoint(
            t=round(window.time, 4),
            x=round((window.x + window.width / 2) / size.width, 5),
            y=round((window.y + window.height / 2) / size.height, 5),
        )
        for window in windows
    )
    return Reframe(mode="track", subject=TRACK_SUBJECT, path=path)


def _bearings(
    times: list[tuple[SubjectSample, float]], follow: FollowPoint | None
) -> list[SubjectBearing]:
    """Yaw of the subject over the segment. A picked point starts the camera on it."""
    track = [SubjectBearing(time, (sample.x - 0.5) * FULL_TURN) for sample, time in times]
    if follow is None:
        return track or [SubjectBearing(0.0, 0.0)]
    picked = (follow.x - 0.5) * FULL_TURN
    if track and abs((track[0].yaw - picked + 180) % FULL_TURN - 180) <= FOLLOW_MATCH_DEG:
        shift = picked - track[0].yaw
        return [SubjectBearing(bearing.time, bearing.yaw + shift) for bearing in track]
    return [SubjectBearing(0.0, picked)]


def _camera(
    times: list[tuple[SubjectSample, float]],
    effects: tuple[Effect, ...],
    keys: list[float],
    ratio: str,
    spins: bool,
    ends_section: bool,
    follow: FollowPoint | None,
) -> tuple[Camera360, tuple[Effect, ...]]:
    camera = follow_camera(
        _bearings(times, follow), keys, ratio, FOLLOW_SUBJECT if follow else TRACK_SUBJECT
    )
    spun_until = 0.0
    if spins and len(keys) >= 2:
        camera = with_beat_spin(camera, 0.0, keys[1])
        spun_until = keys[1]
    kept = []
    for effect in effects:
        if effect.type != ZOOM_PUNCH:
            kept.append(effect)
        elif effect.at >= spun_until and effect.duration > 0:
            camera = with_fov_punch(camera, effect.at, effect.duration)
    if ends_section and keys[-2] >= spun_until and keys[-1] > keys[-2]:
        camera = with_tiny_planet(camera, keys[-2], keys[-1])
    return limit_pitch(camera), tuple(kept)
