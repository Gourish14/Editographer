"""Ports for music analysis. Spec: specs/04-pipeline.md#stages (2)"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

AudioSamples = NDArray[np.float32]


@dataclass(frozen=True)
class BeatGrid:
    beats: tuple[float, ...]
    downbeats: tuple[float, ...]


@dataclass(frozen=True)
class AudioCurves:
    rms: tuple[float, ...]
    onset_strength: tuple[float, ...]
    hop_sec: float
    brightness: tuple[float, ...] = ()


class AudioDecoder(Protocol):
    def decode_mono(self, path: Path, sample_rate: int) -> AudioSamples: ...


class BeatTracker(Protocol):
    def track(self, samples: AudioSamples, sample_rate: int) -> BeatGrid: ...


class AudioCurveExtractor(Protocol):
    def extract(self, samples: AudioSamples, sample_rate: int) -> AudioCurves: ...
