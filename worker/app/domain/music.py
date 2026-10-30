"""The music map every later brain step uses.

Spec: specs/05-editing-brain.md#b1-music-map-music_mappy
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class SectionKind(StrEnum):
    INTRO = "intro"
    BUILD = "build"
    DROP = "drop"
    BREAK = "break"
    VERSE = "verse"
    OUTRO = "outro"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class Beat(_Frozen):
    time: float
    strength: float


class Section(_Frozen):
    kind: SectionKind
    start: float
    end: float
    mean_energy: float


class EditWindow(_Frozen):
    start: float
    end: float


class MusicMap(_Frozen):
    bpm: float
    duration_sec: float
    beats: tuple[Beat, ...]
    downbeats: tuple[float, ...]
    accent_beats: tuple[float, ...]
    energy: tuple[float, ...]
    energy_hop_sec: float
    sections: tuple[Section, ...]
    edit_window: EditWindow
