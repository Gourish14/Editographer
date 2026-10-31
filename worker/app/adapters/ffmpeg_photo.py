"""Builds FFmpeg filter graphs that turn a still photo into a clip.

Spec: specs/05-editing-brain.md#b7-reframing-rules-reframepy (photos) and
specs/04-pipeline.md#stages (6).

Pure text building, so it can be tested without FFmpeg. The image is one input frame and
zoompan turns it into exactly `frames` output frames (d=frames), and trim guards the count.
Ken Burns scales 1.0 to 1.12 toward the subject. Parallax splits the photo by depth into a near
layer (zooms to 1.12) and the whole photo behind it (zooms to 1.04), so near things move more.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from app.domain.photo import (
    KEN_BURNS_MAX_SCALE,
    PARALLAX_BACKGROUND_SCALE,
    PhotoAnalysis,
    PhotoMotion,
)

WORK_FORMAT = "yuv420p10le"
SUPERSAMPLE = 3
MASK_GAIN = 8
MASK_BLUR = 6


def photo_filter(analysis: PhotoAnalysis, width: int, height: int, fps: int, frames: int) -> str:
    """The -filter_complex text. Input 0 is the photo, input 1 the depth map when parallax.

    The result is labelled [v] and has exactly `frames` frames at `fps`.
    """
    if frames < 1:
        raise ValueError("A photo clip needs at least one frame")
    if analysis.motion is PhotoMotion.PARALLAX and analysis.depth is not None:
        return _parallax(analysis, width, height, fps, frames)
    return _ken_burns(analysis, width, height, fps, frames)


def photo_command(
    analysis: PhotoAnalysis,
    image: Path,
    target: Path,
    width: int,
    height: int,
    fps: int,
    frames: int,
) -> Sequence[str]:
    """A full ffmpeg argument list that writes the clip to `target`."""
    inputs = ["-i", str(image)]
    if analysis.motion is PhotoMotion.PARALLAX and analysis.depth is not None:
        inputs += ["-i", analysis.depth.map_file]
    return [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        *inputs,
        "-filter_complex",
        photo_filter(analysis, width, height, fps, frames),
        "-map",
        "[v]",
        "-frames:v",
        str(frames),
        "-an",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(target),
    ]


def _crop_to_ratio(analysis: PhotoAnalysis, width: int, height: int) -> str:
    """Cover-crop to the output ratio with the window centred on the subject, then supersample."""
    aspect = width / height
    cx, cy = analysis.focus.center_x, analysis.focus.center_y
    return (
        f"crop=w='min(iw,ih*{aspect:.6f})':h='min(ih,iw/{aspect:.6f})'"
        f":x='clip({cx:.4f}*iw-out_w/2,0,iw-out_w)':y='clip({cy:.4f}*ih-out_h/2,0,ih-out_h)',"
        f"scale={width * SUPERSAMPLE}:{height * SUPERSAMPLE}:flags=lanczos,setsar=1"
    )


def _progress(frames: int) -> str:
    """Eased 0 to 1 over the clip, smoothstep, from the output frame number `on`."""
    t = f"(on/{max(frames - 1, 1)})"
    return f"({t}*{t}*(3-2*{t}))"


def _zoompan(
    analysis: PhotoAnalysis, scale: float, width: int, height: int, fps: int, n: int
) -> str:
    cx, cy = analysis.focus.center_x, analysis.focus.center_y
    zoom = f"1+{scale - 1:.4f}*{_progress(n)}"
    return (
        f"zoompan=z='{zoom}':x='(iw-iw/zoom)*{cx:.4f}':y='(ih-ih/zoom)*{cy:.4f}'"
        f":d={n}:s={width}x{height}:fps={fps}"
    )


def _finish(frames: int) -> str:
    return f"trim=end_frame={frames},setpts=PTS-STARTPTS,format={WORK_FORMAT}"


def _ken_burns(analysis: PhotoAnalysis, width: int, height: int, fps: int, frames: int) -> str:
    chain = [
        f"[0:v]{_crop_to_ratio(analysis, width, height)}",
        _zoompan(analysis, KEN_BURNS_MAX_SCALE, width, height, fps, frames),
        _finish(frames),
    ]
    return ",".join(chain) + "[v]"


def _parallax(analysis: PhotoAnalysis, width: int, height: int, fps: int, frames: int) -> str:
    assert analysis.depth is not None
    crop = _crop_to_ratio(analysis, width, height)
    near = analysis.depth.near_threshold
    far_zoom = _zoompan(analysis, PARALLAX_BACKGROUND_SCALE, width, height, fps, frames)
    near_zoom = _zoompan(analysis, KEN_BURNS_MAX_SCALE, width, height, fps, frames)
    return ";".join(
        [
            f"[0:v]{crop},split=2[back][front]",
            f"[1:v]{crop},format=gray,lut=y='clip((val-{near})*{MASK_GAIN},0,255)',"
            f"gblur=sigma={MASK_BLUR}[mask]",
            f"[back]{far_zoom}[backz]",
            f"[front]{near_zoom}[frontz]",
            f"[mask]{near_zoom}[maskz]",
            "[frontz][maskz]alphamerge[near]",
            f"[backz][near]overlay=format=auto,{_finish(frames)}[v]",
        ]
    )
