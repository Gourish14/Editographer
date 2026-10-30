"""Ports for rendering. Spec: specs/04-pipeline.md#stages (6, 8)"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.domain.plan import EditPlan, Segment


@dataclass(frozen=True)
class EncodeProfile:
    """How to encode one pass of a render."""

    width: int
    height: int
    fps: int
    quality: int
    preset: str
    sharpen: bool


class Compositor(Protocol):
    def render_segment(
        self, source: Path, segment: Segment, frames: int, profile: EncodeProfile, target: Path
    ) -> None:
        """Writes one segment with exactly this many frames."""
        ...

    def join(self, parts: Sequence[Path], target: Path) -> None:
        """Puts segments together without re-encoding."""
        ...


class AudioFinisher(Protocol):
    def add_music(
        self, video: Path, music: Path, start: float, duration: float, target: Path
    ) -> None:
        """Cuts the music to the window, levels it to -14 LUFS and muxes it with the video."""
        ...


class PlanStore(Protocol):
    def save_plan(self, render_id: str, plan: EditPlan) -> None: ...
