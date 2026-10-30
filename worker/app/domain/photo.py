"""What photo analysis finds. Spec: specs/04-pipeline.md#stages (4), specs/05-editing-brain.md#b7

All coordinates are fractions of the image (0 to 1), so they survive any resize.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

KEN_BURNS_MAX_SCALE = 1.12
PARALLAX_BACKGROUND_SCALE = 1.04
PARALLAX_MIN_CONTRAST = 0.8  # flat wall measured 0.67, receding road 0.9+
PHOTO_MAX_SHARE = 0.30


class PhotoMotion(StrEnum):
    KEN_BURNS = "KEN_BURNS"
    PARALLAX = "PARALLAX"


class FocusSource(StrEnum):
    FACE = "FACE"
    SALIENCY = "SALIENCY"
    CENTER = "CENTER"


@dataclass(frozen=True)
class FocusBox:
    """The subject's box, used to aim the Ken Burns move."""

    x: float
    y: float
    width: float
    height: float
    source: FocusSource

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2


@dataclass(frozen=True)
class DepthSummary:
    """Relative depth, near is bright. Contrast is (p95 - p5) / p95 of the raw map."""

    contrast: float
    near_threshold: int
    map_file: str


@dataclass(frozen=True)
class PhotoAnalysis:
    width: int
    height: int
    focus: FocusBox
    motion: PhotoMotion
    depth: DepthSummary | None


def choose_motion(depth: DepthSummary | None) -> PhotoMotion:
    """Depth parallax only when the scene has strong depth contrast, else Ken Burns (B7)."""
    if depth is not None and depth.contrast >= PARALLAX_MIN_CONTRAST:
        return PhotoMotion.PARALLAX
    return PhotoMotion.KEN_BURNS


def photo_slot_budget(total_slots: int, photos_only: bool) -> int:
    """How many slots photos may fill (B4): at most 30% of them, or all if the input is photos."""
    if photos_only:
        return total_slots
    return int(total_slots * PHOTO_MAX_SHARE)


def photo_allowed(
    photo_slots_used: int, total_slots: int, is_drop: bool, photos_only: bool
) -> bool:
    """True when one more photo fits: under the 30% cap and not on a drop (B4)."""
    if photos_only:
        return True
    return not is_drop and photo_slots_used < photo_slot_budget(total_slots, photos_only)
