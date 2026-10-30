"""Music for the final file. Spec: specs/04-pipeline.md#stages (8)"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pyloudnorm

from app.adapters.ffmpeg_runner import FfmpegError, run_tool, run_tool_for_bytes
from app.domain.errors import RenderError

TARGET_LUFS = -14.0
SAMPLE_RATE = 48000
CHANNELS = 2
AUDIO_BITRATE = "320k"
BASE_ARGUMENTS = ("ffmpeg", "-hide_banner", "-loglevel", "error")


class FfmpegAudioFinisher:
    def add_music(
        self, video: Path, music: Path, start: float, duration: float, target: Path
    ) -> None:
        window = ["-ss", f"{start:.4f}", "-t", f"{duration:.4f}", "-i", str(music)]
        try:
            gain_db = self._gain_to_target(window)
            run_tool(
                [
                    *BASE_ARGUMENTS,
                    "-y",
                    "-i",
                    str(video),
                    *window,
                    "-map",
                    "0:v:0",
                    "-map",
                    "1:a:0",
                    "-af",
                    f"volume={gain_db:.2f}dB,alimiter=limit=0.97",
                    "-c:v",
                    "copy",
                    "-c:a",
                    "aac",
                    "-b:a",
                    AUDIO_BITRATE,
                    "-ar",
                    str(SAMPLE_RATE),
                    "-movflags",
                    "+faststart",
                    "-shortest",
                    str(target),
                ]
            )
        except FfmpegError as error:
            raise RenderError(str(error)) from error

    @staticmethod
    def _gain_to_target(window: list[str]) -> float:
        raw = run_tool_for_bytes(
            [
                *BASE_ARGUMENTS,
                *window,
                "-map",
                "0:a:0",
                "-ac",
                str(CHANNELS),
                "-ar",
                str(SAMPLE_RATE),
                "-f",
                "f32le",
                "-",
            ]
        )
        samples = np.frombuffer(raw, dtype=np.float32).reshape(-1, CHANNELS)
        loudness = pyloudnorm.Meter(SAMPLE_RATE).integrated_loudness(samples)
        return TARGET_LUFS - loudness if math.isfinite(loudness) else 0.0
