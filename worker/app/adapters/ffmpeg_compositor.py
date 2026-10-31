"""Renders segments with FFmpeg and NVENC. Spec: specs/04-pipeline.md#stages (6, 8)"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import structlog

from app.adapters.ffmpeg_filters import (
    XFADE_BY_TRANSITION,
    StyleFinish,
    segment_filter,
    segment_graph,
    transition_graph,
)
from app.adapters.ffmpeg_photo import photo_command
from app.adapters.ffmpeg_runner import FfmpegError, run_tool
from app.adapters.ffmpeg_text_overlay import input_args, overlay_chain
from app.config import ROOT
from app.domain.brain.text_rules import TextItem
from app.domain.errors import ErrorCode, RenderError
from app.domain.look import BLURRED_TRANSITIONS, MOTION_BLUR, ZOOM_PUNCH, transition_frames
from app.domain.media import LogProfile
from app.domain.plan import Effect, Grade, Segment
from app.ports.render import NO_LOOK, EncodeProfile, NextClip, SegmentLook
from app.ports.speech import TextLayerRenderer

log = structlog.get_logger()

BASE_ARGUMENTS = ("ffmpeg", "-hide_banner", "-loglevel", "error", "-y")
OUT_OF_MEMORY_MARKERS = ("out of memory", "cannot allocate")
PHOTO_SEGMENT = "photo"
DJI_LOG_LUT = "dji_osmo360_dlogm_to_rec709.cube"
GENERIC_LOG_LUT = "generic_log_to_rec709.cube"


class FfmpegCompositor:
    def __init__(
        self, luts_dir: Path = ROOT / "luts", text_layer: TextLayerRenderer | None = None
    ) -> None:
        self._luts_dir = luts_dir
        self._text_layer = text_layer

    def render_segment(
        self,
        source: Path,
        segment: Segment,
        frames: int,
        profile: EncodeProfile,
        target: Path,
        look: SegmentLook = NO_LOOK,
    ) -> None:
        if segment.type == PHOTO_SEGMENT:
            self._render_photo(source, frames, profile, target, look)
            return
        inputs = _input(source, segment.src_in)
        clip = self._clip_chain(segment.effects, profile, segment.source.log_profile)
        blend_frames = _blend_frames(segment, frames, profile.fps, look.next_clip)
        finish = self._finish(segment, frames, blend_frames, profile.fps, look)
        if look.next_clip is None or blend_frames == 0:
            graph = segment_graph(clip, finish)
        else:
            preroll = blend_frames / profile.fps
            inputs += _input(look.next_clip.source, max(0.0, look.next_clip.src_in - preroll))
            graph = transition_graph(
                clip,
                self._clip_chain((), profile, look.next_clip.log_profile),
                XFADE_BY_TRANSITION[segment.transition_out.type],
                blend_frames,
                frames,
                profile.fps,
                finish,
            )
        _run(
            [
                *BASE_ARGUMENTS,
                *inputs,
                "-filter_complex",
                graph,
                "-map",
                "[out]",
                "-an",
                "-frames:v",
                str(frames),
                "-c:v",
                "hevc_nvenc",
                "-preset",
                profile.preset,
                "-rc",
                "vbr",
                "-cq",
                str(profile.quality),
                "-b:v",
                "0",
                "-profile:v",
                "main10",
                "-pix_fmt",
                "p010le",
                str(target),
            ]
        )

    def _render_photo(
        self, source: Path, frames: int, profile: EncodeProfile, target: Path, look: SegmentLook
    ) -> None:
        """A photo clip with the same encoder settings as video, so the join stays a copy."""
        if look.photo is None:
            raise RenderError(f"No photo analysis for {source.name}", ErrorCode.RENDER_FAILED)
        _run(
            list(
                photo_command(
                    look.photo,
                    source,
                    target,
                    profile.width,
                    profile.height,
                    profile.fps,
                    frames,
                    _hevc_args(profile),
                )
            )
        )

    def overlay_text(
        self,
        video: Path,
        items: Sequence[TextItem],
        profile: EncodeProfile,
        frames: int,
        target: Path,
    ) -> None:
        """Text spans cuts, so it goes on the joined video, keeping 10-bit HEVC and the count."""
        if self._text_layer is None:
            raise RenderError("No text renderer is set up", ErrorCode.RENDER_FAILED)
        layers = target.parent / f"{target.stem}_text"
        inputs = ["-i", str(video)]
        for index, item in enumerate(items):
            png = self._text_layer.render(
                item, profile.width, profile.height, layers / f"t{index}.png"
            )
            inputs += input_args(png, item, profile.fps)
        _run(
            [
                *BASE_ARGUMENTS,
                *inputs,
                "-filter_complex",
                overlay_chain("0:v", items, 1),
                "-map",
                "[vtext]",
                "-frames:v",
                str(frames),
                *_hevc_args(profile),
                str(target),
            ]
        )

    def _clip_chain(
        self, effects: Sequence[Effect], profile: EncodeProfile, log_profile: str | None
    ) -> str:
        return segment_filter(
            effects,
            profile.width,
            profile.height,
            profile.fps,
            profile.sharpen,
            self._log_lut(log_profile),
        )

    def _log_lut(self, log_profile: str | None) -> Path | None:
        """Spec 08 rule 4: DJI's LUT first. The generic one is a stated fallback, not DJI's."""
        if log_profile != LogProfile.DLOG_M.value:
            return None
        official = self._luts_dir / DJI_LOG_LUT
        if official.is_file():
            return official
        generic = self._luts_dir / GENERIC_LOG_LUT
        log.warning("render.dji_lut_missing", fallback=generic.name)
        return generic if generic.is_file() else None

    def _style_lut(self, grade: Grade) -> Path | None:
        path = self._luts_dir / f"{grade.lut}.cube"
        if path.is_file():
            return path
        log.warning("render.lut_missing", lut=grade.lut)
        return None

    def _finish(
        self, segment: Segment, frames: int, blend_frames: int, fps: int, look: SegmentLook
    ) -> StyleFinish:
        grade = look.grade
        return StyleFinish(
            lut=self._style_lut(grade) if grade else None,
            intensity=grade.intensity if grade else 1.0,
            grain=grade.grain if grade else 0.0,
            blur_amount=look.motion_blur,
            blur_windows=_blur_windows(segment, frames, blend_frames, fps),
        )

    def join(self, parts: Sequence[Path], target: Path) -> None:
        listing = target.with_suffix(".txt")
        listing.write_text(
            "".join(f"file '{part.as_posix()}'\n" for part in parts), encoding="utf-8"
        )
        _run(
            [
                *BASE_ARGUMENTS,
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(listing),
                "-c",
                "copy",
                str(target),
            ]
        )


def _hevc_args(profile: EncodeProfile) -> list[str]:
    """The video segments' encoder settings, for anything that must join with them."""
    return [
        "-c:v",
        "hevc_nvenc",
        "-preset",
        profile.preset,
        "-rc",
        "vbr",
        "-cq",
        str(profile.quality),
        "-b:v",
        "0",
        "-profile:v",
        "main10",
        "-pix_fmt",
        "p010le",
    ]


def _input(source: Path, start: float) -> list[str]:
    return ["-hwaccel", "auto", "-ss", f"{start:.4f}", "-i", str(source)]


def _blend_frames(segment: Segment, frames: int, fps: int, next_clip: NextClip | None) -> int:
    """No next clip means no transition. An unknown type falls back to a hard cut."""
    kind = segment.transition_out.type
    if next_clip is None or kind not in XFADE_BY_TRANSITION:
        return 0
    return transition_frames(segment.transition_out, fps, frames)


def _blur_windows(
    segment: Segment, frames: int, blend_frames: int, fps: int
) -> tuple[tuple[float, float], ...]:
    """Times on the segment where something moves fast."""
    windows = [
        (effect.at, effect.at + effect.duration)
        for effect in segment.effects
        if effect.type == ZOOM_PUNCH
    ]
    if blend_frames and segment.transition_out.type in BLURRED_TRANSITIONS:
        windows.append(((frames - blend_frames) / fps, frames / fps))
    if not windows and any(effect.type == MOTION_BLUR for effect in segment.effects):
        windows.append((0.0, frames / fps))
    return tuple(windows)


def _run(arguments: list[str]) -> None:
    try:
        run_tool(arguments)
    except FfmpegError as error:
        message = str(error)
        code = (
            ErrorCode.GPU_OUT_OF_MEMORY
            if any(marker in message.lower() for marker in OUT_OF_MEMORY_MARKERS)
            else ErrorCode.RENDER_FAILED
        )
        raise RenderError(message, code) from error
