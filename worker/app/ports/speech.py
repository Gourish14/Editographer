"""Ports for speech detection and text layers. Spec: specs/05-editing-brain.md#b8-text-and-audio"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.domain.brain.text_rules import TextItem


@dataclass(frozen=True)
class SpeechSpan:
    start: float
    end: float


@dataclass(frozen=True)
class SpokenWord:
    text: str
    start: float
    end: float


@dataclass(frozen=True)
class SpeechResult:
    spans: tuple[SpeechSpan, ...]
    words: tuple[SpokenWord, ...]

    @property
    def has_speech(self) -> bool:
        return bool(self.spans)


class SpeechDetector(Protocol):
    def detect(self, media: Path) -> SpeechResult: ...


class TextLayerRenderer(Protocol):
    def render(self, item: TextItem, width: int, height: int, out: Path) -> Path:
        """Writes a transparent PNG of the item and returns its path."""
        ...
