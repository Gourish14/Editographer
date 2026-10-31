"""Tests for the shot-cut threshold. Spec: specs/05-editing-brain.md#b2-shot-scoring-scoringpy"""

from __future__ import annotations

from app.adapters.scenedetect_shots import cut_threshold, real_cuts

BASE = 27.0


def test_b2_a_steady_clip_keeps_the_detectors_own_threshold() -> None:
    assert cut_threshold([2.0, 3.0, 4.0, 5.0], BASE) == BASE


def test_b2_a_shaky_clip_needs_a_cut_to_stand_out_from_its_own_shake() -> None:
    assert cut_threshold([19.0, 20.0, 21.0], BASE) == 50.0


def test_b2_a_clip_with_no_measurements_keeps_the_base_threshold() -> None:
    assert cut_threshold([], BASE) == BASE


def test_b2_in_a_shaky_clip_only_the_big_change_is_a_cut() -> None:
    changes = dict.fromkeys(range(100), 20.0) | {30: 29.0, 60: 58.0}

    assert real_cuts(changes, [30, 60], BASE) == [60]


def test_b2_in_a_steady_clip_every_detected_cut_stays() -> None:
    changes = dict.fromkeys(range(100), 3.0) | {30: 29.0, 60: 58.0}

    assert real_cuts(changes, [30, 60], BASE) == [30, 60]
