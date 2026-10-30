"""Pacing. Spec: specs/05-editing-brain.md#b3-pacing-and-style-presets-pacingpy

Cuts land on the beat grid: every beat plus the midpoint between beats, which half-beat cuts need
(ADR-011). This module only builds slots; it never picks shots.
"""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.brain.style_rules import StylePreset
from app.domain.music import Beat, EditWindow, MusicMap, Section, SectionKind

MIN_SEGMENT_SEC = 0.25
UNITS_PER_BEAT = 2
OFF_BEAT_STRENGTH_SHARE = 0.5


@dataclass(frozen=True)
class Slot:
    start: float
    end: float
    section: SectionKind
    beat_strength: float
    is_downbeat: bool

    @property
    def duration(self) -> float:
        return self.end - self.start


def beat_grid(music: MusicMap) -> tuple[float, ...]:
    """Every time a cut may land: the beats and the midpoints between them."""
    grid: list[float] = []
    for earlier, later in zip(music.beats, music.beats[1:], strict=False):
        grid.extend((earlier.time, round((earlier.time + later.time) / 2, 4)))
    grid.append(music.beats[-1].time)
    return tuple(grid)


def build_slots(music: MusicMap, window: EditWindow, style: StylePreset) -> tuple[Slot, ...]:
    """Slots covering the window exactly, each starting and ending on the grid."""
    grid = _grid_within(music, window)
    section_starts = {section.start for section in music.sections}
    downbeats = set(music.downbeats)
    strengths = _strengths(music.beats)

    slots: list[Slot] = []
    index = 0
    nth_cut = 0
    while index < len(grid) - 1:
        start = grid[index]
        section = _section_at(music.sections, start)
        beats = style.cut_length(section.kind, nth_cut)
        end_index = _next_cut(grid, index, beats, section_starts)
        slots.append(
            Slot(
                start=start,
                end=grid[end_index],
                section=section.kind,
                beat_strength=strengths.get(start, 0.0),
                is_downbeat=start in downbeats,
            )
        )
        index = end_index
        nth_cut += 1
    return tuple(slots)


def _grid_within(music: MusicMap, window: EditWindow) -> list[float]:
    grid = beat_grid(music)
    return list(grid[bisect_left(grid, window.start) : bisect_left(grid, window.end) + 1])


def _strengths(beats: Sequence[Beat]) -> dict[float, float]:
    strengths = {beat.time: beat.strength for beat in beats}
    for earlier, later in zip(beats, beats[1:], strict=False):
        midpoint = round((earlier.time + later.time) / 2, 4)
        strengths[midpoint] = earlier.strength * OFF_BEAT_STRENGTH_SHARE
    return strengths


def _section_at(sections: Sequence[Section], time: float) -> Section:
    for section in sections:
        if section.start <= time < section.end:
            return section
    return sections[-1]


def _next_cut(grid: Sequence[float], index: int, beats: float, section_starts: set[float]) -> int:
    """Where this slot ends: at its length, doubled while too short, and never past a section."""
    last = len(grid) - 1
    units = max(1, round(beats * UNITS_PER_BEAT))
    while index + units < last and grid[index + units] - grid[index] < MIN_SEGMENT_SEC:
        units *= 2
    end = min(last, index + units)
    for candidate in range(index + 1, end):
        if grid[candidate] in section_starts and grid[candidate] - grid[index] >= MIN_SEGMENT_SEC:
            end = candidate
            break
    if last - end > 0 and grid[last] - grid[end] < MIN_SEGMENT_SEC:
        end = last
    return end
