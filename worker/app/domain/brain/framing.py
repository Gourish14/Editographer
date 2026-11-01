"""Gives each video segment its framing. Spec: specs/05-editing-brain.md#b7-reframing-rules

Flat clips get a subject-tracked crop path; 360 clips get a camera path with the B5 and B7 moves
(follow, beat spin on drops, FOV punches, tiny planet at a section change), pitch limit last.
Times in a path are segment time, so a ramped slot's source times go through its speed curve.

A measured follow track (SAM 2 on the picked subject, specs/08-osmo360.md rule 5) beats the
detection track: it is the subject itself. Where it ends (the subject was lost) the camera holds
the last bearing it measured. Yaw is unwrapped before any smoothing or keyframing, so a subject
crossing the 0/360 seam moves the camera by the real angle, never the long way round.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

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


def resolve_follow_point(
    point: FollowPoint | None, panoramic: Sequence[str]
) -> tuple[FollowPoint | None, str | None]:
    """Which 360 clip the picked point belongs to (spec 08 rule 5), and a plan note if none.

    `panoramic` holds the 360 clip ids in project order. A point with no asset id belongs to the
    first 360 clip. An id that is not a 360 clip of this render drops the follow, with a note, so
    the point never lands on a clip it was not tapped on.
    """
    if point is None:
        return None, None
    if point.asset_id is None:
        if not panoramic:
            return None, None
        return replace(point, asset_id=panoramic[0]), None
    if point.asset_id in panoramic:
        return point, None
    return None, "Subject follow skipped: the picked clip is not a 360 clip of this project"


def follows(point: FollowPoint | None, asset_id: str) -> FollowPoint | None:
    """The picked point when it is meant for this clip: no asset id means every 360 clip."""
    if point is None or point.asset_id in (None, asset_id):
        return point
    return None


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
    follow_track: Sequence[SubjectSample] = (),
) -> Framing:
    """Everything about how one segment is framed. `size` is the source's, when known.

    `follow_track` is the measured track of the picked subject in this clip, in source time.
    """
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
    measured = _measured(follow_track, assignment, speed, slot.duration) if follow else []
    camera, kept = _camera(times, effects, keys, ratio, drop_start, ends_section, follow, measured)
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


def _measured(
    track: Sequence[SubjectSample], assignment: Assignment, speed: Speed, duration: float
) -> list[SubjectBearing]:
    """The picked subject's bearings over the segment, from the measured track.

    Samples inside the source window are used. With none inside, the camera holds the sample
    nearest the window start, preferring one before it: the subject was lost, or never reached.
    """
    if not track:
        return []
    start, end = assignment.src_in, assignment.src_out
    inside = [sample for sample in track if start <= sample.time <= end]
    if not inside:
        before = [sample for sample in track if sample.time < start]
        held = before[-1] if before else track[0]
        return [SubjectBearing(0.0, (held.x - 0.5) * FULL_TURN)]
    return [
        SubjectBearing(
            timeline_time_at(speed.curve, duration, sample.time - start),
            (sample.x - 0.5) * FULL_TURN,
        )
        for sample in inside
    ]


def _bearings(
    times: list[tuple[SubjectSample, float]],
    follow: FollowPoint | None,
    measured: list[SubjectBearing] | None = None,
) -> list[SubjectBearing]:
    """Yaw of the subject over the segment. A picked point starts the camera on it."""
    if measured:
        return measured
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
    measured: list[SubjectBearing],
) -> tuple[Camera360, tuple[Effect, ...]]:
    camera = follow_camera(
        _bearings(times, follow, measured), keys, ratio, FOLLOW_SUBJECT if follow else TRACK_SUBJECT
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
