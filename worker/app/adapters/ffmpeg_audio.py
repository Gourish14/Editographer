"""Decodes any audio file to samples. Spec: specs/04-pipeline.md#stages (2)"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from app.adapters.ffmpeg_runner import FfmpegError, run_tool_for_bytes
from app.domain.errors import AnalysisError, ErrorCode
from app.ports.music import AudioSamples


class FfmpegAudioDecoder:
    def decode_mono(self, path: Path, sample_rate: int) -> AudioSamples:
        try:
            raw = run_tool_for_bytes(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    str(path),
                    "-map",
                    "0:a:0",
                    "-ac",
                    "1",
                    "-ar",
                    str(sample_rate),
                    "-f",
                    "f32le",
                    "-",
                ]
            )
        except FfmpegError as error:
            raise AnalysisError(str(error), ErrorCode.ASSET_UNSUPPORTED) from error
        return np.frombuffer(raw, dtype=np.float32)
