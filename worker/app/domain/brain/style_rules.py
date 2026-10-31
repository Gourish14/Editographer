"""Style presets and the rule-based style pick.

Spec: specs/05-editing-brain.md#b3-pacing-and-style-presets-pacingpy and
#b10-llm-director-and-fallback-directorpy

New styles are added here and nothing else changes. Grades are data until the look stage reads them.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.domain.brain.tags import tag_matches
from app.domain.constraints import ShotOrder
from app.domain.music import MusicMap, SectionKind
from app.domain.plan import Grade

HALF_BEAT = 0.5
HYPE_BPM = 140.0
FAST_BPM = 120.0
SLOW_BPM = 100.0
DROP_ENERGY = 0.75
MAJORITY_SHARE = 0.5
CAR_TAGS = ("car", "vehicle")
TRAVEL_TAGS = ("outdoor", "landscape", "beach", "mountain")
AUTO = "auto"


@dataclass(frozen=True)
class StylePreset:
    id: str
    cut_beats: dict[SectionKind, tuple[float, ...]]
    fx_intensity: float
    grade: Grade
    order: ShotOrder = "energy"

    def cut_length(self, section: SectionKind, nth_cut: int) -> float:
        """Beats until the next cut. Several values alternate, as in Velocity's drop."""
        lengths = self.cut_beats[section]
        return lengths[nth_cut % len(lengths)]


def _cuts(
    intro: float,
    build: float,
    drop: tuple[float, ...],
    break_: float,
    outro: float,
) -> dict[SectionKind, tuple[float, ...]]:
    """One row of the B3 table. Verse paces like Build."""
    return {
        SectionKind.INTRO: (intro,),
        SectionKind.BUILD: (build,),
        SectionKind.VERSE: (build,),
        SectionKind.DROP: drop,
        SectionKind.BREAK: (break_,),
        SectionKind.OUTRO: (outro,),
    }


VELOCITY = StylePreset(
    id="velocity",
    cut_beats=_cuts(2, 1, (HALF_BEAT, 1), 2, 4),
    fx_intensity=0.9,
    grade=Grade(lut="teal_orange", intensity=0.8, grain=0.0),
)

HYPE = StylePreset(
    id="hype",
    cut_beats=_cuts(1, HALF_BEAT, (HALF_BEAT,), 1, 2),
    fx_intensity=1.0,
    grade=Grade(lut="vibrant", intensity=0.8, grain=0.0),
)

CINEMATIC = StylePreset(
    id="cinematic",
    cut_beats=_cuts(4, 2, (2,), 4, 8),
    fx_intensity=0.3,
    grade=Grade(lut="film", intensity=0.7, grain=0.15),
)

ANIME = StylePreset(
    id="anime",
    cut_beats=_cuts(2, 1, (HALF_BEAT,), 2, 4),
    fx_intensity=0.9,
    grade=Grade(lut="saturated", intensity=0.8, grain=0.0),
)

TRAVEL = StylePreset(
    id="travel",
    cut_beats=_cuts(4, 2, (1,), 4, 4),
    fx_intensity=0.5,
    grade=Grade(lut="warm", intensity=0.7, grain=0.0),
    order="chronological",
)

CAR = StylePreset(
    id="car",
    cut_beats=_cuts(2, 1, (HALF_BEAT,), 2, 4),
    fx_intensity=0.8,
    grade=Grade(lut="moody", intensity=0.8, grain=0.0),
)

SPORTS = StylePreset(
    id="sports",
    cut_beats=_cuts(2, 1, (HALF_BEAT,), 2, 4),
    fx_intensity=0.8,
    grade=Grade(lut="punchy", intensity=0.8, grain=0.0),
)

STYLES = {preset.id: preset for preset in (VELOCITY, HYPE, CINEMATIC, ANIME, TRAVEL, CAR, SPORTS)}


def pick_style(
    requested: str, music: MusicMap, shot_tags: Sequence[Iterable[str]]
) -> tuple[StylePreset, str | None]:
    """The preset to use, and a log line when the request could not be honored."""
    if requested in STYLES:
        return STYLES[requested], None
    fallback = fallback_style(music, shot_tags)
    if requested == AUTO:
        return fallback, None
    return fallback, f"Style '{requested}' does not exist; used {fallback.id}"


def fallback_style(music: MusicMap, shot_tags: Sequence[Iterable[str]]) -> StylePreset:
    """The B10 rules, first match wins."""
    drops = [s.mean_energy for s in music.sections if s.kind is SectionKind.DROP]
    if music.bpm >= HYPE_BPM:
        return HYPE
    if music.bpm >= FAST_BPM and max(drops, default=0.0) >= DROP_ENERGY:
        return VELOCITY
    if _most_tagged(shot_tags, CAR_TAGS):
        return CAR
    if _most_tagged(shot_tags, TRAVEL_TAGS):
        return TRAVEL
    if music.bpm < SLOW_BPM:
        return CINEMATIC
    return VELOCITY


def _most_tagged(shot_tags: Sequence[Iterable[str]], wanted: Sequence[str]) -> bool:
    tagged = sum(1 for tags in shot_tags if _has_any(tuple(tags), wanted))
    return tagged > len(shot_tags) * MAJORITY_SHARE


def _has_any(tags: tuple[str, ...], wanted: Sequence[str]) -> bool:
    return any(tag_matches(tags, word) for word in wanted)
