"""Beat effects. Spec: specs/05-editing-brain.md#b5-effect-rules-effectspy

Phase 1 has flash, shake and zoom punch with hard cuts. Effect times are relative to the segment.
A prompt can switch effects off or replace the style's FX intensity.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.domain.brain.assign import Assignment
from app.domain.brain.ramps import EASE_IN_OUT_CUBIC, EASE_OUT_EXPO
from app.domain.brain.reframe import CameraPose, camera_at, replace_span
from app.domain.brain.style_rules import StylePreset
from app.domain.constraints import NO_CONSTRAINTS, Constraints
from app.domain.look import BLURRED_TRANSITIONS, MOTION_BLUR, MOTION_BLUR_SHARE
from app.domain.music import MusicMap, SectionKind
from app.domain.plan import Camera360, CameraKeyframe, Effect, Transition

FOV_PUNCH_WIDE = 140.0
FOV_PUNCH_TIGHT = 70.0
FOV_PUNCH_PEAK_SHARE = 0.4
MIN_PUNCH_SEC = 0.04
SIGNATURE_TRANSITIONS = ("zoom_through", "spin", "glitch")
WHIPS = ("whip_left", "whip_right")
TRANSITION_SEC = 0.18
TRANSITION_CAP_DIVISOR = 2
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
    first_drop_beats = first_beats_of_drops(assignments)
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


def with_fov_punch(camera: Camera360, at: float, duration: float) -> Camera360:
    """Spec 08 FOV punch: the FOV snaps 140 to 70 and settles back to the view's own FOV."""
    end = min(at + duration, camera.keyframes[-1].t)
    if end - at < MIN_PUNCH_SEC:
        return camera
    settled = camera_at(camera, end)
    pose = camera_at(camera, at)
    peak = at + (end - at) * FOV_PUNCH_PEAK_SHARE
    return replace_span(
        camera,
        at,
        end,
        (
            _key(pose, at, FOV_PUNCH_WIDE, EASE_OUT_EXPO),
            _key(pose, peak, FOV_PUNCH_TIGHT, EASE_IN_OUT_CUBIC),
            _key(settled, end, settled.fov),
        ),
    )


def _key(pose: CameraPose, time: float, fov: float, ease: str = "linear") -> CameraKeyframe:
    return CameraKeyframe(
        t=time, yaw=pose.yaw, pitch=pose.pitch, roll=pose.roll, fov=fov, ease=ease
    )


def plan_transitions(
    assignments: Sequence[Assignment],
    style: StylePreset,
    constraints: Constraints = NO_CONSTRAINTS,
    panoramic: frozenset[str] = frozenset(),
) -> tuple[Transition, ...]:
    """B5: a signature transition at each section change, a whip on every other regular cut.

    Capped at half of all cuts, the section changes first. A 360 section change gets its tiny
    planet from the camera path instead, so its transition stays a cut.
    """
    intensity = style.fx_intensity if constraints.fx_intensity is None else constraints.fx_intensity
    cuts = len(assignments) - 1
    chosen: dict[int, str] = {}
    signature = 0
    regular = 0
    for index, (current, following) in enumerate(zip(assignments, assignments[1:], strict=False)):
        if current.slot.section is not following.slot.section:
            if current.candidate.asset_id not in panoramic:
                chosen[index] = SIGNATURE_TRANSITIONS[signature % len(SIGNATURE_TRANSITIONS)]
                signature += 1
        else:
            if regular % 2 == 1:
                chosen[index] = WHIPS[(regular // 2) % len(WHIPS)]
            regular += 1
    if intensity <= 0:
        chosen = {}
    allowed = sorted(chosen, key=lambda index: (chosen[index] in WHIPS, index))
    kept = set(allowed[: cuts // TRANSITION_CAP_DIVISOR])
    return tuple(
        _transition(chosen[index], assignment.slot.duration) if index in kept else Transition()
        for index, assignment in enumerate(assignments)
    )


def _transition(kind: str, duration: float) -> Transition:
    return Transition(type=kind, duration=round(min(TRANSITION_SEC, duration * 0.4), 4))


def with_motion_blur(
    effects: tuple[Effect, ...], transition: Transition, intensity: float
) -> tuple[Effect, ...]:
    """Motion blur on every segment with a zoom punch or a spin or whip out, intensity x 0.7."""
    moving = any(effect.type == ZOOM_PUNCH for effect in effects) or (
        transition.type in BLURRED_TRANSITIONS
    )
    if not moving or intensity <= 0:
        return effects
    return (*effects, Effect(type=MOTION_BLUR, amount=round(intensity * MOTION_BLUR_SHARE, 3)))


def first_beats_of_drops(assignments: Sequence[Assignment]) -> set[float]:
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
