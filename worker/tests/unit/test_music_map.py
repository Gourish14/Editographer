"""Tests for the music map. Spec: specs/05-editing-brain.md#b1-music-map-music_mappy [T-110]"""

from __future__ import annotations

import pytest

from app.domain.brain.music_map import MusicFeatures, build_music_map, choose_edit_window
from app.domain.music import MusicMap, SectionKind

HOP = 0.05
BEAT = 0.5
BEATS_PER_BAR = 4
BAR = BEAT * BEATS_PER_BAR


def song(levels: list[tuple[int, float]], onset: float = 1.0) -> MusicFeatures:
    """A 120 BPM song from (bars, loudness) parts, with a level jump at each part."""
    rms: list[float] = []
    for bars, level in levels:
        rms.extend([level] * round(bars * BAR / HOP))
    duration = len(rms) * HOP
    beats = tuple(i * BEAT for i in range(int(duration / BEAT)))
    downbeats = beats[::BEATS_PER_BAR]
    strength = [0.0] * len(rms)
    for index, beat in enumerate(beats):
        frame = round(beat / HOP)
        if frame < len(strength):
            strength[frame] = onset if index % BEATS_PER_BAR == 0 else onset / 2
    return MusicFeatures(duration, beats, downbeats, tuple(rms), tuple(strength), HOP)


def kinds(music: MusicMap) -> list[SectionKind]:
    return [section.kind for section in music.sections]


TYPICAL = [(8, 0.2), (8, 1.0), (8, 0.25), (8, 1.0), (8, 0.3)]


def test_b1_bpm_comes_from_the_beat_spacing() -> None:
    assert build_music_map(song(TYPICAL)).bpm == 120.0


def test_b1_energy_is_relative_to_the_loudest_moment() -> None:
    energy = build_music_map(song(TYPICAL)).energy

    assert min(energy) == pytest.approx(0.2)
    assert max(energy) == 1.0


def test_b1_energy_is_smoothed_over_half_a_second() -> None:
    music = build_music_map(song([(4, 0.0), (4, 1.0)]))

    jump = round(4 * BAR / HOP)
    assert 0.0 < music.energy[jump] < 1.0


def test_b1_silence_has_zero_energy_rather_than_failing() -> None:
    assert set(build_music_map(song([(16, 0.0)])).energy) == {0.0}


def test_b1_beat_strength_comes_from_the_onset_at_the_beat() -> None:
    music = build_music_map(song(TYPICAL))

    assert music.beats[0].strength == 1.0
    assert music.beats[1].strength == 0.5


def test_b1_accents_are_the_top_15_percent_of_beats() -> None:
    features = song([(20, 0.5)])
    strength = list(features.onset_strength)
    for index in range(0, 12):
        strength[round(index * BEAT / HOP)] = 2.0 + index
    music = build_music_map(
        MusicFeatures(
            features.duration_sec,
            features.beats,
            features.downbeats,
            features.rms,
            tuple(strength),
            HOP,
        )
    )

    assert len(music.accent_beats) == 12
    assert music.accent_beats[0] == 0.0


def test_b1_section_boundaries_land_only_on_downbeats() -> None:
    music = build_music_map(song(TYPICAL))

    for section in music.sections[1:]:
        assert section.start in music.downbeats


def test_b1_sections_cover_the_whole_song_without_gaps() -> None:
    music = build_music_map(song(TYPICAL))

    assert music.sections[0].start == 0.0
    assert music.sections[-1].end == music.duration_sec
    for earlier, later in zip(music.sections, music.sections[1:], strict=False):
        assert earlier.end == later.start


def test_b1_a_typical_song_gets_intro_drop_break_drop_outro() -> None:
    assert kinds(build_music_map(song(TYPICAL))) == [
        SectionKind.INTRO,
        SectionKind.DROP,
        SectionKind.BREAK,
        SectionKind.DROP,
        SectionKind.OUTRO,
    ]


def test_b1_small_energy_changes_make_no_boundary() -> None:
    music = build_music_map(song([(8, 0.5), (8, 0.55), (8, 0.5)]))

    assert len(music.sections) == 1


def test_b1_rising_energy_over_four_bars_is_a_build() -> None:
    parts = [(8, 0.1), (2, 0.35), (2, 0.45), (2, 0.55), (2, 0.65), (8, 0.15), (8, 0.1)]

    assert SectionKind.BUILD in kinds(build_music_map(song(parts)))


def test_b1_a_quiet_part_with_no_drop_before_it_is_not_a_break() -> None:
    parts = [(8, 0.9), (8, 0.3), (8, 0.7), (8, 0.3)]

    assert SectionKind.BREAK not in kinds(build_music_map(song(parts)))


def test_b1_a_middle_part_that_fits_nothing_is_a_verse() -> None:
    parts = [(8, 0.1), (8, 0.55), (8, 0.1), (8, 1.0), (8, 0.1)]

    assert SectionKind.VERSE in kinds(build_music_map(song(parts)))


def test_b1_window_starts_8_bars_before_the_first_drop_on_a_downbeat() -> None:
    music = build_music_map(song([(16, 0.2), (32, 1.0), (16, 0.3)]))

    drop = next(s for s in music.sections if s.kind is SectionKind.DROP)
    assert music.edit_window.start == pytest.approx(drop.start - 8 * BAR)
    assert music.edit_window.start in music.downbeats


def test_b1_window_clamps_to_the_first_bar_when_the_drop_comes_early() -> None:
    music = build_music_map(song([(4, 0.2), (32, 1.0), (8, 0.3)]))

    assert music.edit_window.start == 0.0


def test_b1_window_ends_on_a_downbeat_within_the_length() -> None:
    music = build_music_map(song([(16, 0.2), (64, 1.0), (16, 0.3)]), length_sec=30.0)

    window = music.edit_window
    assert window.end in music.downbeats
    assert 28.0 <= window.end - window.start <= 30.0


def test_b1_a_short_song_uses_what_there_is() -> None:
    music = build_music_map(song([(8, 0.2), (8, 1.0), (8, 0.3)]))

    assert music.edit_window.end <= music.duration_sec
    assert music.edit_window.end > music.edit_window.start


def test_b1_a_song_with_no_drop_uses_its_loudest_stretch() -> None:
    music = build_music_map(song([(8, 0.6), (8, 1.0), (24, 0.6)]), length_sec=16.0)

    music_without_drop = music.model_copy(
        update={
            "sections": tuple(
                section.model_copy(update={"kind": SectionKind.VERSE})
                for section in music.sections
            )
        }
    )
    window = choose_edit_window(
        music_without_drop.downbeats,
        music_without_drop.sections,
        music_without_drop.energy,
        HOP,
        music_without_drop.duration_sec,
        16.0,
    )

    assert window.start == pytest.approx(16.0)
    assert window.end == pytest.approx(32.0)


def test_b1_downbeats_are_guessed_every_four_beats_when_none_were_found() -> None:
    features = song(TYPICAL)
    music = build_music_map(
        MusicFeatures(
            features.duration_sec,
            features.beats,
            (),
            features.rms,
            features.onset_strength,
            HOP,
        )
    )

    assert music.downbeats == features.downbeats


def test_b1_a_song_with_no_rhythm_cannot_be_mapped() -> None:
    with pytest.raises(ValueError, match="two beats"):
        build_music_map(MusicFeatures(10.0, (1.0,), (), (0.1,) * 200, (0.0,) * 200, HOP))


def test_b1_same_input_gives_the_same_map() -> None:
    assert build_music_map(song(TYPICAL)) == build_music_map(song(TYPICAL))


def test_b1_a_user_length_can_recompute_the_window() -> None:
    music = build_music_map(song([(16, 0.2), (64, 1.0), (16, 0.3)]))

    window = choose_edit_window(
        music.downbeats,
        music.sections,
        music.energy,
        music.energy_hop_sec,
        music.duration_sec,
        16.0,
    )

    assert window.end - window.start == pytest.approx(16.0)
