"""Ports for video analysis. Spec: specs/04-pipeline.md#stages (3)"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.domain.shots import FrameSample


class ShotDetector(Protocol):
    def detect(self, path: Path) -> tuple[tuple[float, float], ...]:
        """Start and end of each shot in seconds. Empty when the clip has no cuts."""
        ...


class FrameSampler(Protocol):
    def sample(self, path: Path) -> tuple[FrameSample, ...]:
        """Measures frames at 4 fps."""
        ...
