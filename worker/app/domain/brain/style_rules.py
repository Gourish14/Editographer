"""Style presets. Spec: specs/05-editing-brain.md#b3-pacing-and-style-presets-pacingpy

Phase 1 ships Velocity and Cinematic. New styles are added here and nothing else changes.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.music import SectionKind
from app.domain.plan import Grade

HALF_BEAT = 0.5
FAST_BPM = 120.0
SLOW_BPM = 100.0


@dataclass(frozen=True)
class StylePreset:
    id: str
    cut_beats: dict[SectionKind, tuple[float, ...]]
    fx_intensity: float
    grade: Grade

    def cut_length(self, section: SectionKind, nth_cut: int) -> float:
        """Beats until the next cut. Several values alternate, as in Velocity's drop."""
        lengths = self.cut_beats[section]
        return lengths[nth_cut % len(lengths)]


VELOCITY = StylePreset(
    id="velocity",
    cut_beats={
        SectionKind.INTRO: (2,),
        SectionKind.BUILD: (1,),
        SectionKind.VERSE: (1,),
        SectionKind.DROP: (HALF_BEAT, 1),
        SectionKind.BREAK: (2,),
        SectionKind.OUTRO: (4,),
    },
    fx_intensity=0.9,
    grade=Grade(lut="teal_orange", intensity=0.8, grain=0.0),
)

CINEMATIC = StylePreset(
    id="cinematic",
    cut_beats={
        SectionKind.INTRO: (4,),
        SectionKind.BUILD: (2,),
        SectionKind.VERSE: (2,),
        SectionKind.DROP: (2,),
        SectionKind.BREAK: (4,),
        SectionKind.OUTRO: (8,),
    },
    fx_intensity=0.3,
    grade=Grade(lut="film", intensity=0.7, grain=0.15),
)

STYLES = {preset.id: preset for preset in (VELOCITY, CINEMATIC)}
AUTO = "auto"


def pick_style(requested: str, bpm: float) -> tuple[StylePreset, str | None]:
    """The preset to use, and a log line when the request could not be honored."""
    if requested in STYLES:
        return STYLES[requested], None
    fallback = CINEMATIC if bpm < SLOW_BPM else VELOCITY
    if requested == AUTO:
        return fallback, None
    return fallback, f"Style '{requested}' arrives in Phase 2; used {fallback.id}"
