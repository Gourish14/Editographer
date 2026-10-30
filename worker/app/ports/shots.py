"""Ports for video analysis. Spec: specs/04-pipeline.md#stages (3)"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from app.domain.shots import Embedding, FrameObjects, FrameSample, ShotVision


class ShotDetector(Protocol):
    def detect(self, path: Path) -> tuple[tuple[float, float], ...]:
        """Start and end of each shot in seconds. Empty when the clip has no cuts."""
        ...


class FrameSampler(Protocol):
    def sample(self, path: Path) -> tuple[FrameSample, ...]:
        """Measures frames at 4 fps."""
        ...


class ObjectDetector(Protocol):
    def detect_objects(self, path: Path) -> tuple[FrameObjects, ...]:
        """Objects in the same 4 fps frames FrameSampler measures, with identical times."""
        ...


class TextEncoder(Protocol):
    def encode_texts(self, texts: Sequence[str]) -> tuple[Embedding, ...]:
        """One unit vector per text, in order, comparable with ShotEncoder embeddings."""
        ...


class ShotEncoder(TextEncoder, Protocol):
    def encode_shots(
        self, path: Path, spans: Sequence[tuple[float, float]]
    ) -> tuple[ShotVision, ...]:
        """One unit embedding and a 0..1 aesthetic score per span, in order."""
        ...
