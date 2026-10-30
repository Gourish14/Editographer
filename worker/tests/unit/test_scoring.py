"""Tests for shot scoring. Spec: specs/05-editing-brain.md#b2-shot-scoring-scoringpy [T-111]"""

from __future__ import annotations

import pytest

from app.domain.brain.scoring import (
    MIN_LUMA,
    RejectReason,
    measure_shot,
    score_shots,
)
from app.domain.shots import FrameSample, ShotMeasure, TimeWindow


def frame(
    time: float = 0.0,
    motion: float = 1.0,
    camera: float = 1.0,
    sharp: float = 100.0,
    luma: float = 0.5,
    area: float = 0.0,
) -> FrameSample:
    return FrameSample(time, motion, camera, sharp, luma, area)


def shot(
    motion: float = 1.0,
    subject: float = 0.5,
    sharpness: float = 100.0,
    stability: float = 0.5,
    luma: float = 0.5,
) -> ShotMeasure:
    return ShotMeasure(
        start=0.0,
        end=2.0,
        motion=motion,
        subject=subject,
        sharpness=sharpness,
        stability=stability,
        luma=luma,
        peak_time=1.0,
        usable=(TimeWindow(start=0.0, end=2.0),),
    )


def test_b2_measures_are_means_of_the_sampled_frames() -> None:
    measured = measure_shot(
        [frame(0.0, motion=1.0, luma=0.2), frame(0.25, motion=3.0, luma=0.4)], 0.0, 0.5
    )

    assert measured.motion == pytest.approx(2.0)
    assert measured.luma == pytest.approx(0.3)


def test_b2_a_subject_filling_a_quarter_of_the_frame_is_a_full_score() -> None:
    assert measure_shot([frame(area=0.25)], 0, 1).subject == 1.0
    assert measure_shot([frame(area=0.9)], 0, 1).subject == 1.0
    assert measure_shot([frame(area=0.0)], 0, 1).subject == 0.0
    assert measure_shot([frame(area=0.125)], 0, 1).subject == pytest.approx(0.5)


def test_b2_a_steady_camera_is_fully_stable_and_a_shaky_one_is_not() -> None:
    steady = measure_shot([frame(camera=2.0), frame(0.25, camera=2.0)], 0, 1)
    shaky = measure_shot([frame(camera=0.0), frame(0.25, camera=8.0)], 0, 1)

    assert steady.stability == 1.0
    assert shaky.stability < 0.2


def test_b2_the_peak_is_highest_motion_times_subject() -> None:
    measured = measure_shot(
        [
            frame(0.0, motion=9.0, area=0.0),
            frame(0.25, motion=5.0, area=0.5),
            frame(0.5, motion=1.0, area=0.5),
        ],
        0,
        1,
    )

    assert measured.peak_time == 0.25


def test_b2_without_a_subject_the_peak_is_the_most_motion() -> None:
    measured = measure_shot([frame(0.0, motion=1.0), frame(0.25, motion=4.0)], 0, 1)

    assert measured.peak_time == 0.25


def test_b2_usable_windows_skip_blurry_and_dark_frames() -> None:
    frames = [frame(index * 0.25) for index in range(12)]
    frames[4] = frame(1.0, sharp=10.0)
    frames[8] = frame(2.0, luma=MIN_LUMA / 2)

    windows = measure_shot(frames, 0, 3).usable

    assert windows == (
        TimeWindow(start=0.0, end=1.0),
        TimeWindow(start=1.25, end=2.0),
        TimeWindow(start=2.25, end=3.0),
    )


def test_b2_a_stretch_under_half_a_second_is_not_usable() -> None:
    frames = [frame(0.0), frame(0.25, luma=0.0), frame(0.5, luma=0.0), frame(0.75)]

    assert measure_shot(frames, 0, 1).usable == ()


def test_b2_a_shot_needs_frames() -> None:
    with pytest.raises(ValueError, match="sampled frame"):
        measure_shot([], 0, 1)


def test_b2_the_best_shot_in_every_term_scores_one() -> None:
    best, worst = score_shots([shot(9.0, 1.0, 900.0, 1.0), shot(1.0, 0.0, 10.0, 0.0)])

    assert best.score == 1.0
    assert worst.score == 0.0


def test_b2_weights_are_renormalized_for_phase_1_terms() -> None:
    only_motion, _ = score_shots([shot(9.0, 0.0, 10.0, 0.0), shot(1.0, 0.0, 10.0, 0.0)])

    assert only_motion.score == pytest.approx(0.25 / 0.70, abs=0.001)


def test_b2_motion_rank_is_relative_to_the_whole_project() -> None:
    scored = score_shots([shot(motion=value) for value in (1.0, 2.0, 3.0)])

    assert scored[0].score < scored[1].score < scored[2].score


def test_b2_a_single_shot_ranks_at_the_top() -> None:
    assert score_shots([shot(subject=0.0, stability=0.0)])[0].score == pytest.approx(0.40 / 0.70, abs=0.001)


def test_b2_a_low_score_is_rejected() -> None:
    _, worst = score_shots([shot(9.0, 1.0, 900.0, 1.0), shot(1.0, 0.0, 10.0, 0.0)])

    assert worst.reject_reason is RejectReason.LOW_SCORE
    assert worst.is_usable is False


def test_b2_a_dark_shot_is_rejected_whatever_its_score() -> None:
    scored = score_shots([shot(9.0, 1.0, 900.0, 1.0, luma=0.01)])[0]

    assert scored.reject_reason is RejectReason.TOO_DARK


def test_b2_a_good_shot_is_kept() -> None:
    assert score_shots([shot()])[0].is_usable is True


def test_b2_an_empty_project_has_no_scores() -> None:
    assert score_shots([]) == ()
