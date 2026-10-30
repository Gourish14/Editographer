"""Proxies and thumbnails through FFmpeg. Spec: specs/04-pipeline.md#stages (1)"""

from __future__ import annotations

import shutil
from pathlib import Path

from app.adapters.ffmpeg_runner import FfmpegError, run_tool
from app.domain.errors import AnalysisError

PROXY_HEIGHT = 720
THUMBNAIL_HEIGHT = 360
BASE_ARGUMENTS = ("ffmpeg", "-hide_banner", "-loglevel", "error", "-y")


class FfmpegMediaTools:
    def make_proxy(self, source: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        self._run(
            [
                *BASE_ARGUMENTS,
                "-hwaccel",
                "auto",
                "-i",
                str(source),
                "-map",
                "0:v:0",
                "-an",
                "-vf",
                f"scale=-2:'min({PROXY_HEIGHT},ih)',format=yuv420p",
                "-c:v",
                "h264_nvenc",
                "-preset",
                "p1",
                str(target),
            ]
        )

    def adopt_proxy(self, source: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    def make_thumbnail(self, source: Path, target: Path, at_sec: float) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        self._run(
            [
                *BASE_ARGUMENTS,
                "-ss",
                f"{at_sec:.3f}",
                "-i",
                str(source),
                "-frames:v",
                "1",
                "-vf",
                f"scale=-2:'min({THUMBNAIL_HEIGHT},ih)',format=yuvj420p",
                "-update",
                "1",
                str(target),
            ]
        )

    @staticmethod
    def _run(arguments: list[str]) -> None:
        try:
            run_tool(arguments)
        except FfmpegError as error:
            raise AnalysisError(str(error)) from error
