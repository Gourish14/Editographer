"""Ports for rendering. Spec: specs/04-pipeline.md#stages (6, 8)"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.domain.brain.text_rules import TextItem
from app.domain.photo import PhotoAnalysis
from app.domain.plan import EditPlan, Grade, Segment


@dataclass(frozen=True)
class EncodeProfile:
    """How to encode one pass of a render."""

    width: int
    height: int
    fps: int
    quality: int
    preset: str
    sharpen: bool


@dataclass(frozen=True)
class NextClip:
    """Where the following segment comes from, for a transition into it."""

    source: Path
    src_in: float
    log_profile: str | None = None
    segment: Segment | None = None


@dataclass(frozen=True)
class SegmentLook:
    """Plan-wide look for one segment. The default renders the segment plain."""

    grade: Grade | None = None
    motion_blur: float = 0.0
    next_clip: NextClip | None = None
    retimed: Path | None = None
    """Frames already on the segment's timeline, a pattern like `folder/%06d.png` (RIFE)."""
    photo: PhotoAnalysis | None = None


@dataclass(frozen=True)
class SfxPlacement:
    """One sound effect on the edit timeline, in seconds from the first frame."""

    type: str
    at: float
    gain_db: float


@dataclass(frozen=True)
class KeptClipAudio:
    """Clip audio kept under the music, in seconds from the first frame."""

    source: Path
    src_in: float
    at: float
    duration: float


@dataclass(frozen=True)
class AudioMix:
    """Everything mixed with the music. The default is music alone."""

    sfx: tuple[SfxPlacement, ...] = ()
    speech: tuple[KeptClipAudio, ...] = ()


NO_LOOK = SegmentLook()
MUSIC_ONLY = AudioMix()


class Compositor(Protocol):
    def render_segment(
        self,
        source: Path,
        segment: Segment,
        frames: int,
        profile: EncodeProfile,
        target: Path,
        look: SegmentLook = NO_LOOK,
    ) -> None:
        """Writes one segment with exactly this many frames.

        A transition into the next clip happens inside these frames and ends on the last one,
        so the next segment still starts on its beat and the join stays a plain copy.
        """
        ...

    def join(self, parts: Sequence[Path], target: Path) -> None:
        """Puts segments together without re-encoding."""
        ...


class TextOverlay(Protocol):
    def overlay_text(
        self,
        video: Path,
        items: Sequence[TextItem],
        profile: EncodeProfile,
        frames: int,
        target: Path,
    ) -> None:
        """Draws the items on the joined video, times from its first frame, same frame count."""
        ...


class AudioFinisher(Protocol):
    def add_music(
        self,
        video: Path,
        music: Path,
        start: float,
        duration: float,
        target: Path,
        mix: AudioMix = MUSIC_ONLY,
    ) -> None:
        """Cuts the music to the window, mixes in the rest, levels the whole mix to -14 LUFS."""
        ...


class PlanStore(Protocol):
    def save_plan(self, render_id: str, plan: EditPlan) -> None: ...
