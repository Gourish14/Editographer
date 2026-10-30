"""Look and sound rules for a plan. Spec: specs/05-editing-brain.md#b5-effect-rules-effectspy

Also B8 (SFX and ducking). A plan that lists its own SFX is rendered as written; otherwise the
cues are read off its transitions and drop hits, so plans from the rules engine get the full mix.
"""

from __future__ import annotations

from app.domain.plan import EditPlan, Segment, SfxCue, Transition

CUT = "cut"
FLASH = "flash"
ZOOM_PUNCH = "zoomPunch"
MOTION_BLUR = "motionBlur"
BLURRED_TRANSITIONS = frozenset({"zoom_whip", "whip_left", "whip_right", "spin", "zoom_through"})
MOTION_BLUR_SHARE = 0.7

WHOOSH = "whoosh"
IMPACT = "impact"
SFX_GAIN_DB = -18.0
WHOOSH_PEAK_SEC = 0.25
SPEECH_DUCK_DB = 8.0


def transition_frames(transition: Transition, fps: int, frames: int) -> int:
    """Frames of the outgoing transition. At least one frame of the segment stays clean."""
    if transition.type == CUT or transition.duration <= 0 or frames < 2:
        return 0
    return max(1, min(round(transition.duration * fps), frames - 1))


def motion_blur_amount(segment: Segment, fx_intensity: float) -> float:
    """B5: every segment with zoom, spin or whip, unless the plan names its own amount."""
    for effect in segment.effects:
        if effect.type == MOTION_BLUR and effect.amount is not None:
            return effect.amount
    zooms = any(effect.type == ZOOM_PUNCH for effect in segment.effects)
    if zooms or segment.transition_out.type in BLURRED_TRANSITIONS:
        return round(fx_intensity * MOTION_BLUR_SHARE, 3)
    return 0.0


def planned_sfx(plan: EditPlan) -> tuple[SfxCue, ...]:
    """B8: a whoosh peaking on each transition's cut and an impact on each drop hit.

    Phase 1 flashes only on the first beat of a drop, so a flash at a segment start marks one.
    """
    if plan.sfx:
        return plan.sfx
    cues: list[SfxCue] = []
    for segment, following in zip(plan.segments, plan.segments[1:], strict=False):
        if segment.transition_out.type != CUT:
            whoosh_at = round(following.at - WHOOSH_PEAK_SEC, 4)
            cues.append(SfxCue(type=WHOOSH, at=whoosh_at, gain_db=SFX_GAIN_DB))
    for segment in plan.segments:
        if any(effect.type == FLASH and effect.at == 0.0 for effect in segment.effects):
            cues.append(SfxCue(type=IMPACT, at=segment.at, gain_db=SFX_GAIN_DB))
    return tuple(sorted(cues, key=lambda cue: cue.at))
