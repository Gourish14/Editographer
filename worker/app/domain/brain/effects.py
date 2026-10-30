"""Beat effects. Spec: specs/05-editing-brain.md#b5-effect-rules-effectspy

Phase 1 has flash, shake and zoom punch with hard cuts. Effect times are relative to the segment.
A prompt can switch effects off or replace the style's FX intensity.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.domain.brain.assign import Assignment
from app.domain.brain.style_rules import StylePreset
from app.domain.constraints import NO_CONSTRAINTS, Constraints
from app.domain.music import MusicMap, SectionKind
from app.domain.plan import Effect

FLASH = "flash"
SHAKE = "shake"
ZOOM_PUNCH = "zoomPunch"
FLASH_SEC = 0.08
HIT_SEC = 0.25
ZOOM_PUNCH_STRENGTH = 0.15
SHAKE_CAP_SHARE = 0.4
EFFECT_NAMES = {
    "shake": SHAKE,
    "shakes": SHAKE,
    "camera shake": SHAKE,
    "flash": FLASH,
    "flashes": FLASH,
    "white flash": FLASH,
    "zoom": ZOOM_PUNCH,
    "zooms": ZOOM_PUNCH,
    "zoompunch": ZOOM_PUNCH,
    "zoom punch": ZOOM_PUNCH,
}


def effects_turned_off(names: Sequence[str]) -> frozenset[str]:
    """The effect types a prompt switched off, whichever way it spelled them."""
    return frozenset(EFFECT_NAMES[name.lower()] for name in names if name.lower() in EFFECT_NAMES)


def plan_effects(
    assignments: Sequence[Assignment],
    music: MusicMap,
    style: StylePreset,
    constraints: Constraints = NO_CONSTRAINTS,
) -> tuple[tuple[Effect, ...], ...]:
    """One tuple of effects per assignment, with the B5 caps applied."""
    intensity = style.fx_intensity if constraints.fx_intensity is None else constraints.fx_intensity
    if intensity <= 0:
        return tuple(() for _ in assignments)
    off = effects_turned_off(constraints.effects_off)

    window_start = assignments[0].slot.start
    window_end = assignments[-1].slot.end
    beats_in_window = [b for b in music.beats if window_start <= b.time < window_end]
    allowed_shakes = 0 if SHAKE in off else int(len(beats_in_window) * SHAKE_CAP_SHARE)
    strengths = {beat.time: beat.strength for beat in music.beats}
    accents = [time for time in music.accent_beats if window_start <= time < window_end]

    shakes = 0
    use_shake_next = True
    first_drop_beats = _first_beats_of_drops(assignments)
    planned: list[tuple[Effect, ...]] = []
    for assignment in assignments:
        slot = assignment.slot
        effects: list[Effect] = []
        if slot.start in first_drop_beats:
            effects.append(Effect(type=FLASH, at=0.0, duration=FLASH_SEC))
            effects.append(_zoom(0.0, intensity))
            if shakes < allowed_shakes:
                effects.append(_shake(0.0, 1.0, intensity))
                shakes += 1
        for accent in (t for t in accents if slot.start <= t < slot.end):
            if accent == slot.start and slot.start in first_drop_beats:
                continue
            offset = round(accent - slot.start, 4)
            if use_shake_next and shakes < allowed_shakes:
                effects.append(_shake(offset, strengths.get(accent, 1.0), intensity))
                shakes += 1
            else:
                effects.append(_zoom(offset, intensity))
            use_shake_next = not use_shake_next
        kept = [effect for effect in effects if effect.type not in off]
        planned.append(tuple(_inside_segment(kept, slot.duration)))
    return tuple(planned)


def _first_beats_of_drops(assignments: Sequence[Assignment]) -> set[float]:
    firsts: set[float] = set()
    previous: SectionKind | None = None
    for assignment in assignments:
        if assignment.slot.section is SectionKind.DROP and previous is not SectionKind.DROP:
            firsts.add(assignment.slot.start)
        previous = assignment.slot.section
    return firsts


def _shake(at: float, strength: float, intensity: float) -> Effect:
    scaled = round(strength * intensity, 3)
    return Effect(type=SHAKE, at=at, duration=HIT_SEC, strength=scaled)


def _zoom(at: float, intensity: float) -> Effect:
    scaled = round(ZOOM_PUNCH_STRENGTH * intensity, 3)
    return Effect(type=ZOOM_PUNCH, at=at, duration=HIT_SEC, strength=scaled)


def _inside_segment(effects: Sequence[Effect], duration: float) -> list[Effect]:
    """Trims an effect that would run past its segment, so it never spills across a cut."""
    trimmed = []
    for effect in effects:
        length = min(effect.duration, round(duration - effect.at, 4))
        trimmed.append(effect.model_copy(update={"duration": length}))
    return trimmed
