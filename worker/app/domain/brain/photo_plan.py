"""Photos in the plan. Spec: specs/05-editing-brain.md#b4-shot-assignment, #b7

Photos fill at most 30% of the slots and never a drop, unless the input is only photos, when
every slot is a photo. Pure: it only picks slots and builds segments.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.domain.analysis import StoredAnalysis
from app.domain.brain.pacing import Slot
from app.domain.errors import ErrorCode, RenderError
from app.domain.music import SectionKind
from app.domain.photo import PhotoMotion, photo_allowed, photo_slot_budget
from app.domain.plan import Motion, Segment

PHOTO_SEGMENT = "photo"
PARALLAX = "parallax"
KEN_BURNS = "kenburns"


def photo_slots(slots: Sequence[Slot], photo_count: int, photos_only: bool) -> dict[int, int]:
    """Slot index to photo index. Photos-only fills every slot, round-robin."""
    if photo_count == 0:
        return {}
    if photos_only:
        return {index: index % photo_count for index in range(len(slots))}
    eligible = [i for i, slot in enumerate(slots) if slot.section is not SectionKind.DROP]
    wanted = min(photo_count, photo_slot_budget(len(slots), photos_only), len(eligible))
    chosen: dict[int, int] = {}
    for photo in range(wanted):
        index = eligible[(2 * photo + 1) * len(eligible) // (2 * wanted)]
        if photo_allowed(len(chosen), len(slots), False, False):
            chosen[index] = photo
    return chosen


def photo_segment(segment_id: str, asset_id: str, slot: Slot, analysis: StoredAnalysis) -> Segment:
    photo = analysis.photo
    if photo is None:
        raise RenderError(f"Photo {asset_id} has no photo analysis", ErrorCode.PLAN_INVALID)
    parallax = photo.motion is PhotoMotion.PARALLAX and photo.depth is not None
    return Segment(
        id=segment_id,
        asset_id=asset_id,
        type=PHOTO_SEGMENT,
        at=slot.start,
        duration=round(slot.duration, 4),
        motion=Motion(
            type=PARALLAX if parallax else KEN_BURNS,
            depth=parallax,
            focus_x=round(photo.focus.center_x, 4),
            focus_y=round(photo.focus.center_y, 4),
        ),
    )
