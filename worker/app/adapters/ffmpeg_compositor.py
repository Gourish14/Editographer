"""Renders segments with FFmpeg and NVENC. Spec: specs/04-pipeline.md#stages (6, 8)"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from app.adapters.ffmpeg_filters import segment_filter
from app.adapters.ffmpeg_runner import FfmpegError, run_tool
from app.domain.errors import ErrorCode, RenderError
from app.domain.plan import Segment
from app.ports.render import EncodeProfile

BASE_ARGUMENTS = ("ffmpeg", "-hide_banner", "-loglevel", "error", "-y")
OUT_OF_MEMORY_MARKERS = ("out of memory", "cannot allocate")


class FfmpegCompositor:
    def render_segment(
        self, source: Path, segment: Segment, frames: int, profile: EncodeProfile, target: Path
    ) -> None:
        video_filter = segment_filter(
            segment.effects, profile.width, profile.height, profile.fps, profile.sharpen
        )
        _run(
            [
                *BASE_ARGUMENTS,
                "-hwaccel",
                "auto",
                "-ss",
                f"{segment.src_in:.4f}",
                "-i",
                str(source),
                "-map",
                "0:v:0",
                "-an",
                "-vf",
                video_filter,
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
