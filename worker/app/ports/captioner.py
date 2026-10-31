"""Port for shot captions. Spec: specs/05-editing-brain.md#b2-shot-scoring-scoringpy"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol


class Captioner(Protocol):
    def caption_frames(self, path: Path, times: Sequence[float]) -> tuple[str, ...]:
        """One short caption per time of the clip, in order.

        A frame that could not be described gives an empty string. Never raises: captions are
        optional, so a failure means no caption, not a failed job.
        """
        ...
