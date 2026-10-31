"""Port for subject masks. Spec: specs/05-editing-brain.md#b8-text-and-audio"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from app.domain.brain.text_rules import TextItem

Point = tuple[float, float]


class Segmenter(Protocol):
    def track(
        self, frames: Sequence[Path], points: Sequence[Point], folder: Path
    ) -> tuple[Path, ...]:
        """Segments the subject marked by `points` (shares of the frame, 0..1) in the first
        frame and follows it through the rest.

        Writes one 8-bit gray PNG per frame (white is subject) into `folder`, same order, and
        returns the paths. Returns an empty tuple when no subject was found.
        """
        ...


class MatteMaker(Protocol):
    def make(self, video: Path, item: TextItem, fps: int, folder: Path) -> Path | None:
        """Subject mattes for the frames of the text item's window on `video`.

        Returns a folder of `%06d.png` gray mattes, exactly `round(duration * fps)` of them, or
        None when no subject mask exists (the text then stays in front).
        """
        ...
