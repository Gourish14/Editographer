"""Reframing rules and the 360 camera path.

Spec: specs/05-editing-brain.md#b7-reframing-rules-reframepy, specs/08-osmo360.md

Pure geometry. Yaw grows to the right, pitch grows upward (-90 is the nadir, where the selfie
stick sits) and FOV is horizontal, the same way spec 08 rule 8 measures it. Yaw is never wrapped
here, so a spin stays a spin: 0 to 360 is one full turn, not no movement.
"""

from __future__ import annotations

import math
from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.brain.ramps import EASE_OUT_EXPO, eased
from app.domain.plan import Camera360, CameraKeyframe, Motion

DEAD_ZONE_SHARE = 0.10
MAX_PAN_SHARE_PER_SEC = 0.15
THIRDS_OFFSET_SHARE = 1 / 6
MIN_TRAVEL_SHARE = 0.02

ONE_EURO_MIN_CUTOFF_HZ = 1.0
ONE_EURO_BETA = 1.5
ONE_EURO_DERIVATIVE_CUTOFF_HZ = 1.0

PROJECTION_RECTILINEAR = "rectilinear"
PROJECTION_TINY_PLANET = "tinyplanet"
PROJECTION_RABBIT_HOLE = "rabbithole"
FOLLOW_PITCH = -5.0
FOV_DEFAULT = 100.0
FOV_TALL = 90.0
TALL_RATIOS = frozenset({"9:16", "4:5"})
MIN_PITCH = -60.0
TINY_PLANET_PITCH = -90.0
RABBIT_HOLE_PITCH = 90.0
PLANET_FOV = 160.0
FULL_TURN = 360.0

KEN_BURNS_START_SCALE = 1.0
KEN_BURNS_END_SCALE = 1.12
KEN_BURNS = "kenburns"
PUSH_IN = "push_in"
FRAME_CENTER = 0.5


@dataclass(frozen=True)
class FrameSize:
    width: int
    height: int


@dataclass(frozen=True)
class SubjectPoint:
    """A subject center in source pixels."""

    time: float
    x: float
    y: float


@dataclass(frozen=True)
class CropWindow:
    """A crop at the output ratio, its top-left corner in source pixels."""

    time: float
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class SubjectBearing:
    """Where a subject sits on the sphere, in degrees of yaw."""

    time: float
    yaw: float


@dataclass(frozen=True)
class CameraPose:
    yaw: float
    pitch: float
    roll: float
    fov: float
    projection: str


@dataclass(frozen=True)
class PhotoWindow:
    """The visible part of a photo: its scale and center, as shares of the frame."""

    scale: float
    center_x: float
    center_y: float


def ratio_value(ratio: str) -> float:
    across, down = ratio.split(":")
    return float(across) / float(down)


def crop_size(source: FrameSize, ratio: float) -> tuple[float, float]:
    """The largest window at the output ratio that fits the source."""
    if source.width / source.height > ratio:
        return source.height * ratio, float(source.height)
    return float(source.width), source.width / ratio


def one_euro_filter(
    times: Sequence[float],
    values: Sequence[float],
    min_cutoff: float = ONE_EURO_MIN_CUTOFF_HZ,
    beta: float = ONE_EURO_BETA,
    derivative_cutoff: float = ONE_EURO_DERIVATIVE_CUTOFF_HZ,
) -> list[float]:
    """1 euro filter: heavy smoothing when the signal is slow, little lag when it is fast.

    `beta` depends on the signal's scale, so values are shares of a frame width or of a full turn.
    """
    smoothed = list(values[:1])
    slope = 0.0
    for index in range(1, len(values)):
        step = times[index] - times[index - 1]
        if step <= 0:
            smoothed.append(smoothed[-1])
            continue
        raw_slope = (values[index] - values[index - 1]) / step
        slope += _smoothing(derivative_cutoff, step) * (raw_slope - slope)
        weight = _smoothing(min_cutoff + beta * abs(slope), step)
        smoothed.append(smoothed[-1] + weight * (values[index] - smoothed[-1]))
    return smoothed


def _smoothing(cutoff: float, step: float) -> float:
    time_constant = 1.0 / (2.0 * math.pi * cutoff)
    return 1.0 / (1.0 + time_constant / step)


def crop_path(
    track: Sequence[SubjectPoint],
    source: FrameSize,
    ratio: float,
    subject_count: int = 1,
) -> tuple[CropWindow, ...]:
    """B7 flat clips: one window per subject sample, starting on the subject at the cut."""
    width, height = crop_size(source, ratio)
    if not track:
        return (
            CropWindow(
                0.0, (source.width - width) / 2, (source.height - height) / 2, width, height
            ),
        )

    times = [point.time for point in track]
    aim_x = one_euro_filter(times, [point.x / source.width for point in track])
    aim_y = one_euro_filter(times, [point.y / source.width for point in track])
    lead = _thirds_lead(track, source, width) if subject_count == 1 else 0.0
    center_x = _inside(aim_x[0] * source.width + lead, width, source.width)
    center_y = _inside(aim_y[0] * source.width, height, source.height)

    windows = [_window(times[0], center_x, center_y, width, height)]
    for index in range(1, len(track)):
        reach = MAX_PAN_SHARE_PER_SEC * source.width * (times[index] - times[index - 1])
        move_x = _dead_zone(aim_x[index] * source.width + lead - center_x, DEAD_ZONE_SHARE * width)
        move_y = _dead_zone(aim_y[index] * source.width - center_y, DEAD_ZONE_SHARE * height)
        center_x = _inside(center_x + _limit(move_x, reach), width, source.width)
        center_y = _inside(center_y + _limit(move_y, reach), height, source.height)
        windows.append(_window(times[index], center_x, center_y, width, height))
    return tuple(windows)


def _thirds_lead(track: Sequence[SubjectPoint], source: FrameSize, width: float) -> float:
    """Puts a single subject on the third behind it, so it moves into the open two thirds."""
    travel = track[-1].x - track[0].x
    if abs(travel) < MIN_TRAVEL_SHARE * source.width:
        return 0.0
    return math.copysign(THIRDS_OFFSET_SHARE * width, travel)


def _dead_zone(offset: float, zone: float) -> float:
    """How far the subject has left the zone: the window only moves by that much, so no jumps."""
    return math.copysign(max(0.0, abs(offset) - zone), offset)


def _limit(move: float, reach: float) -> float:
    return max(-reach, min(reach, move))


def _inside(center: float, size: float, frame: int) -> float:
    return max(size / 2, min(frame - size / 2, center))


def _window(
    time: float, center_x: float, center_y: float, width: float, height: float
) -> CropWindow:
    return CropWindow(time, center_x - width / 2, center_y - height / 2, width, height)


def base_fov(ratio: str) -> float:
    return FOV_TALL if ratio in TALL_RATIOS else FOV_DEFAULT


def view_pixel_width(source_width: int, fov: float) -> float:
    """Spec 08 rule 8: the real pixels a view holds. 8K at FOV 100 is about 2130 px."""
    return source_width * fov / FULL_TURN


def unwrap_yaw(yaws: Sequence[float]) -> list[float]:
    """Removes the jumps at +-180, so a subject crossing behind the camera stays one smooth move."""
    unwrapped = list(yaws[:1])
    for yaw in yaws[1:]:
        turn = (yaw - unwrapped[-1] + FULL_TURN / 2) % FULL_TURN - FULL_TURN / 2
        unwrapped.append(unwrapped[-1] + turn)
    return unwrapped


def follow_camera(
    track: Sequence[SubjectBearing],
    beats: Sequence[float],
    ratio: str,
    subject: str | None = None,
) -> Camera360:
    """Subject follow, the default for every 360 clip: keyframes sit on the beats (spec 08 rule 6).

    `beats` are seconds into the segment, including its start and end.
    """
    fov = base_fov(ratio)
    times = [bearing.time for bearing in track]
    turns = [yaw / FULL_TURN for yaw in unwrap_yaw([bearing.yaw for bearing in track])]
    yaws = [turn * FULL_TURN for turn in one_euro_filter(times, turns)]
    return Camera360(
        follow=subject,
        keyframes=tuple(
            CameraKeyframe(t=beat, yaw=_sample(times, yaws, beat), pitch=FOLLOW_PITCH, fov=fov)
            for beat in beats
        ),
    )


def _sample(times: Sequence[float], values: Sequence[float], time: float) -> float:
    if not values:
        return 0.0
    index = bisect_right(times, time)
    if index == 0:
        return values[0]
    if index == len(values):
        return values[-1]
    start, end = times[index - 1], times[index]
    share = (time - start) / (end - start)
    return values[index - 1] + (values[index] - values[index - 1]) * share


def with_beat_spin(camera: Camera360, start: float, beat_length: float) -> Camera360:
    """Drop: a 360 degree yaw spin over one beat. A slot shorter than a beat still gets it all."""
    end = min(start + beat_length, camera.keyframes[-1].t)
    pose = camera_at(camera, start)
    settled = camera_at(camera, end)
    return _replace_span(
        camera,
        start,
        end,
        (
            CameraKeyframe(
                t=start,
                yaw=pose.yaw,
                pitch=pose.pitch,
                roll=pose.roll,
                fov=pose.fov,
                ease=EASE_OUT_EXPO,
            ),
            CameraKeyframe(
                t=end,
                yaw=settled.yaw + FULL_TURN,
                pitch=settled.pitch,
                roll=settled.roll,
                fov=settled.fov,
            ),
        ),
        later_yaw=FULL_TURN,
    )


def with_tiny_planet(camera: Camera360, start: float, end: float) -> Camera360:
    """Section change: curls into a tiny planet between two beats."""
    return _with_planet(camera, start, end, PROJECTION_TINY_PLANET, TINY_PLANET_PITCH)


def with_rabbit_hole(camera: Camera360, start: float, end: float) -> Camera360:
    """Build before a drop: the inverse tiny planet, looking straight up."""
    return _with_planet(camera, start, end, PROJECTION_RABBIT_HOLE, RABBIT_HOLE_PITCH)


def _with_planet(
    camera: Camera360, start: float, end: float, projection: str, pitch: float
) -> Camera360:
    pose = camera_at(camera, start)
    return _replace_span(
        camera,
        start,
        end,
        (
            CameraKeyframe(t=start, yaw=pose.yaw, pitch=pose.pitch, roll=pose.roll, fov=pose.fov),
            CameraKeyframe(
                t=end,
                yaw=pose.yaw,
                pitch=pitch,
                roll=pose.roll,
                fov=PLANET_FOV,
                projection=projection,
            ),
        ),
    )


def _replace_span(
    camera: Camera360,
    start: float,
    end: float,
    span: tuple[CameraKeyframe, ...],
    later_yaw: float = 0.0,
) -> Camera360:
    """Swaps the keyframes between two times, turning the later ones so nothing unwinds."""
    before = tuple(key for key in camera.keyframes if key.t < start)
    after = tuple(
        key.model_copy(update={"yaw": key.yaw + later_yaw})
        for key in camera.keyframes
        if key.t > end
    )
    return camera.model_copy(update={"keyframes": (*before, *span, *after)})


def limit_pitch(camera: Camera360) -> Camera360:
    """Pitch stays above -60 outside a tiny planet, which keeps the selfie stick out of frame."""
    return camera.model_copy(
        update={
            "keyframes": tuple(
                key
                if key.projection == PROJECTION_TINY_PLANET
                else key.model_copy(update={"pitch": max(MIN_PITCH, key.pitch)})
                for key in camera.keyframes
            )
        }
    )


def camera_at(camera: Camera360, time: float) -> CameraPose:
    """The pose at a time. A span uses its end keyframe's projection, so a planet curls in."""
    keys = camera.keyframes
    if len(keys) == 1:
        return _pose_between(camera, keys[0], keys[0], 1.0)
    held = max(keys[0].t, min(keys[-1].t, time))
    index = min(bisect_right([key.t for key in keys], held), len(keys) - 1)
    first, second = keys[index - 1], keys[index]
    length = second.t - first.t
    share = (held - first.t) / length if length > 0 else 1.0
    return _pose_between(camera, first, second, eased(first.ease, share))


def _pose_between(
    camera: Camera360, first: CameraKeyframe, second: CameraKeyframe, share: float
) -> CameraPose:
    return CameraPose(
        _mix(first.yaw, second.yaw, share),
        _mix(first.pitch, second.pitch, share),
        _mix(first.roll, second.roll, share),
        _mix(first.fov, second.fov, share),
        second.projection or first.projection or camera.projection,
    )


def _mix(first: float, second: float, share: float) -> float:
    return first + (second - first) * share


def ken_burns_motion(subject: tuple[float, float] | None) -> Motion:
    """B7 photos: a push from 1.0 to 1.12 toward the subject (shares of the frame), else center."""
    focus_x, focus_y = subject or (FRAME_CENTER, FRAME_CENTER)
    return Motion(type=KEN_BURNS, direction=PUSH_IN, focus_x=focus_x, focus_y=focus_y)


def ken_burns_window(motion: Motion, progress: float) -> PhotoWindow:
    """The window at a share of the segment. The focus point holds still, so it stays inside."""
    scale = _mix(KEN_BURNS_START_SCALE, KEN_BURNS_END_SCALE, progress)
    return PhotoWindow(
        scale,
        motion.focus_x + (FRAME_CENTER - motion.focus_x) / scale,
        motion.focus_y + (FRAME_CENTER - motion.focus_y) / scale,
    )
