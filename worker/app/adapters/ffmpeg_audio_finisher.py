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
LIMIT = 0.97
LEVELING_PASSES = 3
CLOSE_ENOUGH_LU = 0.2
BASE_ARGUMENTS = ("ffmpeg", "-hide_banner", "-loglevel", "error")


class FfmpegAudioFinisher:
    def add_music(
        self, video: Path, music: Path, start: float, duration: float, target: Path
    ) -> None:
        window = ["-ss", f"{start:.4f}", "-t", f"{duration:.4f}", "-i", str(music)]
        try:
            gain_db = _gain_to_target(window)
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
                    _level_filter(gain_db),
                    "-ac",
                    str(CHANNELS),
                    "-ar",
                    str(SAMPLE_RATE),
                    "-c:v",
                    "copy",
                    "-c:a",
                    "aac",
                    "-b:a",
                    AUDIO_BITRATE,
                    "-movflags",
                    "+faststart",
                    str(target),
                ]
            )
        except FfmpegError as error:
            raise RenderError(str(error)) from error


def _level_filter(gain_db: float) -> str:
    return f"volume={gain_db:.2f}dB,alimiter=limit={LIMIT}:level=disabled"


def _gain_to_target(window: list[str]) -> float:
    """The limiter takes back some of any boost, so measure after it and correct."""
    gain_db = 0.0
    for _ in range(LEVELING_PASSES):
        loudness = _measure(window, gain_db)
        if not math.isfinite(loudness):
            return gain_db
        difference = TARGET_LUFS - loudness
        gain_db += difference
        if abs(difference) <= CLOSE_ENOUGH_LU:
            break
    return gain_db


def _measure(window: list[str], gain_db: float) -> float:
    raw = run_tool_for_bytes(
        [
            *BASE_ARGUMENTS,
            *window,
            "-map",
            "0:a:0",
            "-af",
            _level_filter(gain_db),
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
    return float(pyloudnorm.Meter(SAMPLE_RATE).integrated_loudness(samples))
