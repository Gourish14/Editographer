"""Measures the shots of a clip. Spec: specs/04-pipeline.md#stages (3)"""

from __future__ import annotations

from pathlib import Path

from app.domain.brain.scoring import measure_shot
from app.domain.errors import AnalysisError
from app.domain.shots import ShotMeasure
from app.ports.shots import FrameSampler, ShotDetector


class AnalyzeShots:
    def __init__(self, detector: ShotDetector, sampler: FrameSampler) -> None:
        self._detector = detector
        self._sampler = sampler

    def run(self, proxy: Path, duration_sec: float) -> tuple[ShotMeasure, ...]:
        frames = self._sampler.sample(proxy)
        if not frames:
            raise AnalysisError(f"No frames could be read from {proxy.name}")
        spans = self._detector.detect(proxy) or ((0.0, duration_sec),)
        measures = []
        for start, end in spans:
            inside = [frame for frame in frames if start <= frame.time < end]
            if inside:
                measures.append(measure_shot(inside, start, end))
        return tuple(measures)
