"""Shot assignment. Spec: specs/05-editing-brain.md#b4-shot-assignment

Only picks shots for slots. Randomness comes from the injected generator, for ties only.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.brain.pacing import MIN_SEGMENT_SEC, Slot
from app.domain.brain.scoring import ScoredShot
from app.domain.brain.tags import tag_matches
from app.domain.constraints import NO_CONSTRAINTS, Constraints, ShotOrder
from app.domain.errors import ErrorCode, RenderError
from app.domain.music import MusicMap, SectionKind
from app.domain.shots import TimeWindow

SECTION_WEIGHTS = {
    SectionKind.DROP: 1.0,
    SectionKind.BUILD: 0.7,
    SectionKind.VERSE: 0.6,
    SectionKind.INTRO: 0.5,
    SectionKind.OUTRO: 0.5,
    SectionKind.BREAK: 0.4,
}
TIE_BREAK_SIZE = 1e-6
PROMPT_FIT_PER_TAG = 1.5
CHRONOLOGICAL: ShotOrder = "chronological"


@dataclass(frozen=True)
class Candidate:
    """A usable shot, its clip, and how its motion ranks in the project (0..1)."""

    asset_id: str
    shot: ScoredShot
    motion_rank: float

    @property
    def key(self) -> tuple[str, float]:
        return self.asset_id, self.shot.measure.start


@dataclass(frozen=True)
class Assignment:
    slot: Slot
    candidate: Candidate
    src_in: float
    src_out: float


@dataclass(frozen=True)
class _Rules:
    """What stays the same for every slot of one assignment."""

    constraints: Constraints
    order: ShotOrder
    can_vary_clips: bool
    positions: dict[tuple[str, float], int]


def prompt_fit(tags: Sequence[str], include: Sequence[str], exclude: Sequence[str]) -> float:
    """1.5 for each included tag matched, 0 if an excluded tag matches."""
    if any(tag_matches(tags, word) for word in exclude):
        return 0.0
    matched = sum(1 for word in include if tag_matches(tags, word))
    return float(PROMPT_FIT_PER_TAG**matched)


def select_candidates(
    candidates: Sequence[Candidate], constraints: Constraints, needed_sec: float
) -> tuple[list[Candidate], tuple[str, ...]]:
    """Shots the prompt allows, and notes for the plan log.

    Other shots are excluded unless too few: when the matches hold less usable footage than the
    edit needs, the best other shots top them up until it is covered.
    """
    include, exclude = constraints.include_tags, constraints.exclude_tags
    notes = [
        f"Prompt request '{word}' skipped: no matching footage"
        for word in (*include, *exclude)
        if not any(tag_matches(c.shot.measure.tags, word) for c in candidates)
    ]
    allowed = [c for c in candidates if prompt_fit(c.shot.measure.tags, (), exclude) > 0]
    if not allowed:
        notes.append(f"Every shot is excluded by {', '.join(exclude)}; ignored that request")
        allowed = list(candidates)
    matched = [c for c in allowed if _matches_any(c, include)]
    if not matched:
        return allowed, tuple(notes)

    others = sorted(
        (c for c in allowed if c not in matched), key=lambda c: c.shot.score, reverse=True
    )
    kept = list(matched)
    covered = sum(_usable_sec(c) for c in kept)
    added = 0
    for other in others:
        if covered >= needed_sec:
            break
        kept.append(other)
        covered += _usable_sec(other)
        added += 1
    if added:
        wanted = ", ".join(include)
        notes.append(f"Too little '{wanted}' footage for this length; added {added} other shots")
    return [c for c in allowed if c in kept], tuple(notes)


def _matches_any(candidate: Candidate, words: Sequence[str]) -> bool:
    return any(tag_matches(candidate.shot.measure.tags, word) for word in words)


def _usable_sec(candidate: Candidate) -> float:
    return sum(window.end - window.start for window in candidate.shot.measure.usable)


def split_long_slots(slots: Sequence[Slot], grid: Sequence[float], longest: float) -> list[Slot]:
    """Halves any slot no shot can fill, cutting on the grid, so length fit can always be met."""
    result: list[Slot] = []
    for slot in slots:
        pending = [slot]
        while pending:
            current = pending.pop(0)
            middle = _middle_cut(current, grid)
            if current.duration <= longest or middle is None:
                result.append(current)
            else:
                pending[:0] = [
                    _part(current, current.start, middle),
                    _part(current, middle, current.end),
                ]
    return result


def assign_shots(
    slots: Sequence[Slot],
    candidates: Sequence[Candidate],
    music: MusicMap,
    rng: random.Random,
    constraints: Constraints = NO_CONSTRAINTS,
    order: ShotOrder = "energy",
) -> tuple[Assignment, ...]:
    """Fills slots, honoring the B4 constraints.

    Energy order fills from the most important slot down and takes the best match. Chronological
    order walks the timeline and takes the earliest allowed shot, with `candidates` in capture
    order.
    """
    if not candidates:
        raise RenderError("No usable shots to edit with", ErrorCode.PLAN_INVALID)
    if order == CHRONOLOGICAL:
        turns = list(range(len(slots)))
    else:
        turns = sorted(
            range(len(slots)),
            key=lambda i: (-_importance(slots[i]), slots[i].start, rng.random()),
        )
    filled: dict[int, Assignment] = {}
    used: dict[tuple[str, float], list[TimeWindow]] = {}
    rules = _Rules(
        constraints,
        order,
        len({candidate.asset_id for candidate in candidates}) > 1,
        {candidate.key: position for position, candidate in enumerate(candidates)},
    )
    for index in turns:
        filled[index] = _fill(index, slots, candidates, music, rng, filled, used, rules)
    return tuple(filled[index] for index in range(len(slots)))


def _importance(slot: Slot) -> float:
    return SECTION_WEIGHTS[slot.section] * max(slot.beat_strength, TIE_BREAK_SIZE)


def _fill(
    index: int,
    slots: Sequence[Slot],
    candidates: Sequence[Candidate],
    music: MusicMap,
    rng: random.Random,
    filled: dict[int, Assignment],
    used: dict[tuple[str, float], list[TimeWindow]],
    rules: _Rules,
) -> Assignment:
    slot = slots[index]
    neighbours = {
        filled[other].candidate.asset_id for other in (index - 1, index + 1) if other in filled
    }
    pool = [
        candidate
        for candidate in candidates
        if _fits(candidate, slot)
        and not (rules.can_vary_clips and candidate.asset_id in neighbours)
    ]
    if not pool:
        pool = [candidate for candidate in candidates if _fits(candidate, slot)]
    if not pool:
        raise RenderError(f"No shot fits the {slot.duration:.2f} s slot", ErrorCode.PLAN_INVALID)

    pool = [candidate for candidate in pool if candidate.key not in used] or pool
    if slot.section is SectionKind.DROP:
        energetic = [candidate for candidate in pool if candidate.motion_rank >= 0.5]
        pool = energetic or pool

    if rules.order == CHRONOLOGICAL:
        best = min(pool, key=lambda c: (len(used.get(c.key, ())), rules.positions[c.key]))
    else:
        energy = _slot_energy(slot, music)
        best = max(pool, key=lambda c: (_match(c, energy, rules.constraints), rng.random()))
    src_in = _place(best, slot, used.get(best.key, []))
    used.setdefault(best.key, []).append(TimeWindow(start=src_in, end=src_in + slot.duration))
    return Assignment(slot, best, round(src_in, 4), round(src_in + slot.duration, 4))


def _match(candidate: Candidate, energy: float, constraints: Constraints) -> float:
    """match = S × fit. Length fit is settled by the pool, slow-mo fit comes with ramps."""
    energy_fit = 1.0 - abs(candidate.motion_rank - energy)
    fit = prompt_fit(
        candidate.shot.measure.tags, constraints.include_tags, constraints.exclude_tags
    )
    return candidate.shot.score * energy_fit * fit


def _fits(candidate: Candidate, slot: Slot) -> bool:
    return any(
        window.end - window.start >= slot.duration for window in candidate.shot.measure.usable
    )


def _slot_energy(slot: Slot, music: MusicMap) -> float:
    first = round(slot.start / music.energy_hop_sec)
    last = max(first + 1, round(slot.end / music.energy_hop_sec))
    window = music.energy[first:last]
    return sum(window) / len(window) if window else 0.0


def _place(candidate: Candidate, slot: Slot, taken: Sequence[TimeWindow]) -> float:
    """Puts the peak on the slot's beat, moving only as far as the usable window requires."""
    measure = candidate.shot.measure
    windows = [w for w in measure.usable if w.end - w.start >= slot.duration]
    best_window = min(
        windows,
        key=lambda w: abs(_clamped(measure.peak_time, w, slot.duration) - measure.peak_time),
    )
    start = _clamped(measure.peak_time, best_window, slot.duration)
    if not _overlaps(start, slot.duration, taken):
        return start
    for window in windows:
        position = window.start
        while position + slot.duration <= window.end:
            if not _overlaps(position, slot.duration, taken):
                return position
            position += MIN_SEGMENT_SEC
    return start


def _clamped(time: float, window: TimeWindow, duration: float) -> float:
    return min(max(time, window.start), window.end - duration)


def _overlaps(start: float, duration: float, taken: Sequence[TimeWindow]) -> bool:
    return any(start < window.end and window.start < start + duration for window in taken)


def _middle_cut(slot: Slot, grid: Sequence[float]) -> float | None:
    inside = [time for time in grid if slot.start < time < slot.end]
    return inside[len(inside) // 2] if inside else None


def _part(slot: Slot, start: float, end: float) -> Slot:
    return Slot(
        start, end, slot.section, slot.beat_strength, slot.is_downbeat and start == slot.start
    )
