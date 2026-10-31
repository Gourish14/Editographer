"""Fakes for the model ports, shared by the analysis tests. [T-201]"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from app.domain.brain.shot_tags import tag_phrase
from app.domain.shots import Embedding, FrameObjects, ShotVision

CAR_VECTOR: Embedding = (1.0, 0.0)
BEACH_VECTOR: Embedding = (0.0, 1.0)
CAR_VISION = ShotVision(CAR_VECTOR, 0.5)


class FakeObjects:
    def __init__(self, frames: tuple[FrameObjects, ...] = ()) -> None:
        self.frames = frames
        self.calls = 0

    def detect_objects(self, path: Path) -> tuple[FrameObjects, ...]:
        self.calls += 1
        return self.frames


class FakeEncoder:
    """Texts mentioning a car point one way and everything else the other."""

    def __init__(self, vision: ShotVision = CAR_VISION) -> None:
        self.vision = vision
        self.spans: list[tuple[float, float]] = []
        self.texts: list[tuple[str, ...]] = []

    def encode_shots(
        self, path: Path, spans: Sequence[tuple[float, float]]
    ) -> tuple[ShotVision, ...]:
        self.spans.extend(spans)
        return tuple(self.vision for _ in spans)

    def encode_texts(self, texts: Sequence[str]) -> tuple[Embedding, ...]:
        self.texts.append(tuple(texts))
        return tuple(CAR_VECTOR if text == tag_phrase("car") else BEACH_VECTOR for text in texts)
