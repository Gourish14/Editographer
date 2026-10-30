"""FFmpeg filter text for 360 reframing. Spec: specs/08-osmo360.md (rules 6 to 8)

Pure text building, so it can be tested without FFmpeg. Measured on FFmpeg 9.0 and pinned by
tests/integration/test_ffmpeg_360.py, these v360 facts shape the graph:

- Per-frame animation works. yaw, pitch, roll and the FOVs are runtime commands, sent with sendcmd.
- Rotation commands accumulate by default, so `yaw 30` three times ends at 90. With `reset_rot=1`
  they become absolute, so frames match a static v360 exactly.
- Yaw only accepts -180 to 180, so unwrapped plan yaw is wrapped per frame.
- Every command rebuilds the remap table, so only values that change are sent, and the view
  renders at the pixels it really holds (rule 8) before scaling. From an 8K source that was about
  9 times faster than rendering at 8K.
- The projection is not a runtime option. So the graph splits at each projection change, with one
  v360 per sub-segment. Each sub-segment has its own instance name, or a command would reach all.

Stereographic v360 scales by tan(fov / 4), so plan FOV 160 would leave the horizon at the frame
edge, with no globe. The plan's FOV is a lens FOV like every other: `_stereographic_fov` converts
it so the image plane matches, which also keeps the center scale when the projection switches.

Times are frame counts, so the stream must already be conformed to `fps`, and any speed curve
must come before this filter.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import groupby

from app.domain.brain.reframe import (
    PROJECTION_RABBIT_HOLE,
    PROJECTION_RECTILINEAR,
    PROJECTION_TINY_PLANET,
    CameraPose,
    camera_at,
    view_pixel_width,
)
from app.domain.plan import Camera360

INPUT_PROJECTION = "e"
OUTPUT_PROJECTIONS = {
    PROJECTION_RECTILINEAR: "flat",
    PROJECTION_TINY_PLANET: "sg",
    PROJECTION_RABBIT_HOLE: "sg",
}
INTERPOLATION = "cubic"
MAX_LENS_FOV = 179.0
HALF_TURN = 180.0
FULL_TURN = 360.0


@dataclass(frozen=True)
class _Settings:
    """A pose as v360 options, already rounded so equal values compare equal."""

    yaw: str
    pitch: str
    roll: str
    h_fov: str
    v_fov: str


def view_size(
    camera: Camera360, duration: float, source_width: int, size: tuple[int, int], fps: int
) -> tuple[int, int]:
    """Spec 08 rule 8: the real pixels at the tightest FOV, capped at the output size."""
    width, height = size
    tightest = min(pose.fov for pose in _poses(camera, duration, fps))
    view_width = min(width, _even(view_pixel_width(source_width, tightest)))
    return view_width, min(height, _even(view_width * height / width))


def camera_filter(
    camera: Camera360,
    duration: float,
    source_width: int,
    size: tuple[int, int],
    fps: int,
) -> str:
    """The filter from conformed equirect frames to frames of `size`, one projection per run.

    A filter graph with one input and one output, so it fits in -vf after `fps`.
    """
    poses = _poses(camera, duration, fps)
    view = view_size(camera, duration, source_width, size, fps)
    runs = [list(run) for _, run in groupby(poses, key=lambda pose: pose.projection)]
    finish = "" if view == size else f"scale={size[0]}:{size[1]}:flags=lanczos"
    if len(runs) == 1:
        return ",".join(part for part in (_run_filter(runs[0], view, fps, 0), finish) if part)
    return _split_graph(runs, view, fps, finish)


def _poses(camera: Camera360, duration: float, fps: int) -> list[CameraPose]:
    return [camera_at(camera, index / fps) for index in range(max(1, round(duration * fps)))]


def _split_graph(runs: list[list[CameraPose]], view: tuple[int, int], fps: int, finish: str) -> str:
    branches = [f"split={len(runs)}" + "".join(f"[in{index}]" for index in range(len(runs)))]
    first_frame = 0
    for index, run in enumerate(runs):
        last_frame = first_frame + len(run)
        branches.append(
            f"[in{index}]trim=start_frame={first_frame}:end_frame={last_frame},"
            f"setpts=PTS-STARTPTS,{_run_filter(run, view, fps, index)}[out{index}]"
        )
        first_frame = last_frame
    joined = "".join(f"[out{index}]" for index in range(len(runs)))
    tail = f",{finish}" if finish else ""
    return ";".join([*branches, f"{joined}concat=n={len(runs)}:v=1:a=0{tail}"])


def _run_filter(run: list[CameraPose], view: tuple[int, int], fps: int, index: int) -> str:
    name = f"v360@p{index}"
    start = _settings(run[0], view)
    width, height = view
    projection = (
        f"{name}={INPUT_PROJECTION}:{OUTPUT_PROJECTIONS[run[0].projection]}"
        f":w={width}:h={height}:interp={INTERPOLATION}:reset_rot=1"
        f":yaw={start.yaw}:pitch={start.pitch}:roll={start.roll}"
        f":h_fov={start.h_fov}:v_fov={start.v_fov}"
    )
    commands = _commands(run, view, fps, name)
    return f"sendcmd=c='{commands}',{projection}" if commands else projection


def _commands(run: list[CameraPose], view: tuple[int, int], fps: int, name: str) -> str:
    """Commands for the frames after the first, sent only for values that changed.

    Each fires half a frame early, so rounding the time can never leave it a frame late.
    """
    settings = [_settings(pose, view) for pose in run]
    intervals = []
    for frame, (before, after) in enumerate(zip(settings, settings[1:], strict=False), start=1):
        changed = [
            f"{name} {option} {getattr(after, option)}"
            for option in ("yaw", "pitch", "roll", "h_fov", "v_fov")
            if getattr(after, option) != getattr(before, option)
        ]
        if changed:
            intervals.append(f"{(frame - 0.5) / fps:.6f} {','.join(changed)}")
    return ";".join(intervals)


def _settings(pose: CameraPose, view: tuple[int, int]) -> _Settings:
    width, height = view
    h_fov, v_fov = _lens_fovs(pose, height / width)
    return _Settings(
        yaw=f"{_wrap_yaw(pose.yaw):.3f}",
        pitch=f"{pose.pitch:.3f}",
        roll=f"{pose.roll:.3f}",
        h_fov=f"{h_fov:.3f}",
        v_fov=f"{v_fov:.3f}",
    )


def _lens_fovs(pose: CameraPose, tallness: float) -> tuple[float, float]:
    """h_fov and v_fov for v360. Both are needed, or v360 stretches the view."""
    half_width = math.tan(math.radians(min(pose.fov, MAX_LENS_FOV)) / 2)
    half_height = half_width * tallness
    if pose.projection == PROJECTION_RECTILINEAR:
        return _rectilinear_fov(half_width), _rectilinear_fov(half_height)
    return _stereographic_fov(half_width), _stereographic_fov(half_height)


def _rectilinear_fov(half_size: float) -> float:
    return 2 * math.degrees(math.atan(half_size))


def _stereographic_fov(half_size: float) -> float:
    """v360's own value for an image plane: its radius is 2 * tan(angle / 2), not tan(angle)."""
    return 4 * math.degrees(math.atan(half_size / 2))


def _wrap_yaw(yaw: float) -> float:
    return (yaw + HALF_TURN) % FULL_TURN - HALF_TURN


def _even(value: float) -> int:
    return max(2, round(value / 2) * 2)
