"""The real audio stack on a fixture song.

Spec: specs/05-editing-brain.md#b1-music-map-music_mappy [T-110]

Compares against tests/fixtures/expected_music_map.json. Regenerate it only after checking a
change in the output is intended, by running this file with UPDATE_GOLDEN=1 set.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

import pytest

from app.adapters.beat_this_tracker import BeatThisTracker
from app.adapters.ffmpeg_audio import FfmpegAudioDecoder
from app.adapters.file_cache import FileCache
from app.adapters.librosa_curves import LibrosaCurveExtractor
from app.application.analyze_music import AnalyzeMusic
from app.domain.music import MusicMap, SectionKind

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SONG = FIXTURES / "test_song.wav"
GOLDEN = FIXTURES / "expected_music_map.json"
CHECKPOINT = Path(__file__).resolve().parents[3] / "models" / "beat_this" / "small0.ckpt"
BEAT_TOLERANCE_SEC = 0.03

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or not CHECKPOINT.exists(),
    reason="needs FFmpeg and the Beat This! checkpoint from setup.bat",
)


@pytest.fixture(scope="module")
def music() -> MusicMap:
    analyzer = AnalyzeMusic(
        FfmpegAudioDecoder(), BeatThisTracker(CHECKPOINT), LibrosaCurveExtractor()
    )
    return analyzer.run(SONG)


def test_b1_finds_the_tempo_of_the_song(music: MusicMap) -> None:
    assert music.bpm == pytest.approx(120.0, abs=1.0)


def test_b1_beats_fall_on_the_kick_drums(music: MusicMap) -> None:
    for beat in music.beats:
        assert beat.time / 0.5 == pytest.approx(round(beat.time / 0.5), abs=0.1)


def test_b1_the_loud_half_is_found_as_a_drop(music: MusicMap) -> None:
    drop = next(section for section in music.sections if section.kind is SectionKind.DROP)

    assert drop.start == pytest.approx(12.0, abs=0.1)


def test_b1_section_boundaries_are_downbeats(music: MusicMap) -> None:
    for section in music.sections[1:]:
        assert section.start in music.downbeats


def test_b1_the_edit_window_is_on_downbeats(music: MusicMap) -> None:
    assert music.edit_window.start in music.downbeats
    assert music.edit_window.end in music.downbeats


def test_b1_the_fixture_song_matches_the_golden_map(music: MusicMap) -> None:
    actual: dict[str, Any] = {
        "bpm": music.bpm,
        "beats": [beat.time for beat in music.beats],
        "downbeats": list(music.downbeats),
        "sections": [[s.kind.value, s.start, s.end] for s in music.sections],
        "editWindow": [music.edit_window.start, music.edit_window.end],
    }
    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN.write_text(json.dumps(actual, indent=2), encoding="utf-8")
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))

    assert actual["bpm"] == pytest.approx(golden["bpm"], abs=0.5)
    assert actual["beats"] == pytest.approx(golden["beats"], abs=BEAT_TOLERANCE_SEC)
    assert actual["downbeats"] == pytest.approx(golden["downbeats"], abs=BEAT_TOLERANCE_SEC)
    assert [s[0] for s in actual["sections"]] == [s[0] for s in golden["sections"]]


def test_the_waveform_file_has_what_the_ui_draws(music: MusicMap, tmp_path: Path) -> None:
    FileCache(tmp_path).save_waveform("h", music)

    document = json.loads((tmp_path / "cache" / "h" / "waveform.json").read_text("utf-8"))
    assert 0 < len(document["peaks"]) <= 1600
    assert document["beats"] == [beat.time for beat in music.beats]
    assert document["sections"][0]["kind"] == music.sections[0].kind.value
