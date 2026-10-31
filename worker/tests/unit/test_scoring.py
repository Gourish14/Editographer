"""Tests for shot scoring. [T-111] [T-201]

Spec: specs/05-editing-brain.md#b2-shot-scoring-scoringpy
"""

from __future__ import annotations

import pytest

from app.domain.brain.scoring import (
    MIN_LUMA,
    RejectReason,
    describe_shot,
    measure_shot,
    object_velocity_peak,
    score_shots,
)
from app.domain.shots import (
    DetectedObject,
    Embedding,
    FrameObjects,
    FrameSample,
    MotionDirection,
    ShotMeasure,
    ShotVision,
    TimeWindow,
)


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
    action: float = 0.0,
    aesthetics: float = 0.5,
    embedding: Embedding = (),
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
        action=action,
        aesthetics=aesthetics,
        embedding=embedding,
    )


def test_b2_measures_are_means_of_the_sampled_frames() -> None:
    measured = measure_shot(
        [
            frame(0.0, luma=0.2),
            frame(0.25, motion=1.0, luma=0.4),
            frame(0.5, motion=3.0, luma=0.3),
        ],
        0.0,
        0.75,
    )

    assert measured.motion == pytest.approx(2.0)
    assert measured.luma == pytest.approx(0.3)


def test_b2_a_subject_filling_a_quarter_of_the_frame_is_a_full_score() -> None:
    assert measure_shot([frame(area=0.25)], 0, 1).subject == 1.0
    assert measure_shot([frame(area=0.9)], 0, 1).subject == 1.0
    assert measure_shot([frame(area=0.0)], 0, 1).subject == 0.0
    assert measure_shot([frame(area=0.125)], 0, 1).subject == pytest.approx(0.5)


def test_b2_a_steady_camera_is_fully_stable_and_a_shaky_one_is_not() -> None:
    steady = measure_shot([frame(), frame(0.25, camera=2.0), frame(0.5, camera=2.0)], 0, 1)
    shaky = measure_shot([frame(), frame(0.25, camera=0.0), frame(0.5, camera=8.0)], 0, 1)

    assert steady.stability == 1.0
    assert shaky.stability < 0.2


def test_b2_the_peak_is_highest_motion_times_subject() -> None:
    measured = measure_shot(
        [
            frame(0.0),
            frame(0.25, motion=9.0, area=0.0),
            frame(0.5, motion=5.0, area=0.5),
            frame(0.75, motion=1.0, area=0.5),
        ],
        0,
        1,
    )

    assert measured.peak_time == 0.5


def test_b2_without_a_subject_the_peak_is_the_most_motion() -> None:
    measured = measure_shot([frame(0.0), frame(0.25, motion=1.0), frame(0.5, motion=4.0)], 0, 1)

    assert measured.peak_time == 0.5


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
    best, worst = score_shots(
        [
            shot(9.0, 1.0, 900.0, 1.0, action=2.0, aesthetics=1.0),
            shot(1.0, 0.0, 10.0, 0.0, action=0.0, aesthetics=0.0),
        ]
    )

    assert best.score == 1.0
    assert worst.score == 0.0


@pytest.mark.parametrize(
    ("better", "weight"),
    [
        ({"motion": 2.0}, 0.25),
        ({"subject": 1.0}, 0.20),
        ({"sharpness": 2.0}, 0.15),
        ({"action": 2.0}, 0.15),
        ({"aesthetics": 1.0}, 0.15),
        ({"stability": 1.0}, 0.10),
    ],
)
def test_b2_each_term_carries_its_weight(better: dict[str, float], weight: float) -> None:
    flat: dict[str, float] = {
        "motion": 1.0,
        "subject": 0.0,
        "sharpness": 1.0,
        "stability": 0.0,
        "action": 1.0,
        "aesthetics": 0.0,
    }

    scored = score_shots([shot(**{**flat, **better}), shot(**flat)])  # type: ignore[arg-type]

    assert scored[0].score - scored[1].score == pytest.approx(weight, abs=0.001)


def test_b2_motion_rank_is_relative_to_the_whole_project() -> None:
    scored = score_shots([shot(motion=value) for value in (1.0, 2.0, 3.0)])

    assert scored[0].score < scored[1].score < scored[2].score


def test_b2_a_single_shot_ranks_at_the_top() -> None:
    alone = shot(subject=0.0, stability=0.0, aesthetics=0.0)

    assert score_shots([alone])[0].score == pytest.approx(0.25 + 0.15 + 0.15, abs=0.001)


def test_b2_a_low_score_is_rejected() -> None:
    _, worst = score_shots([shot(9.0, 1.0, 900.0, 1.0), shot(1.0, 0.0, 10.0, 0.0, aesthetics=0.0)])

    assert worst.reject_reason is RejectReason.LOW_SCORE
    assert worst.is_usable is False


def test_b2_a_dark_shot_is_rejected_whatever_its_score() -> None:
    scored = score_shots([shot(9.0, 1.0, 900.0, 1.0, luma=0.01)])[0]

    assert scored.reject_reason is RejectReason.TOO_DARK


def test_b2_a_good_shot_is_kept() -> None:
    assert score_shots([shot()])[0].is_usable is True


def test_b2_an_empty_project_has_no_scores() -> None:
    assert score_shots([]) == ()


def test_b2_a_near_copy_of_a_better_shot_is_rejected() -> None:
    worse, better = score_shots([shot(1.0, embedding=(1.0, 0.0)), shot(9.0, embedding=(1.0, 0.01))])

    assert worse.reject_reason is RejectReason.DUPLICATE
    assert better.is_usable is True


def test_b2_similarity_of_exactly_the_limit_is_not_a_duplicate() -> None:
    # cos = 0.95 exactly: the rule is strictly greater than.
    near = (0.95, (1 - 0.95**2) ** 0.5)

    scored = score_shots([shot(1.0, embedding=(1.0, 0.0)), shot(9.0, embedding=near)])

    assert all(item.reject_reason is not RejectReason.DUPLICATE for item in scored)


def test_b2_different_shots_are_not_duplicates() -> None:
    scored = score_shots([shot(1.0, embedding=(1.0, 0.0)), shot(9.0, embedding=(0.0, 1.0))])

    assert all(item.is_usable for item in scored)


def test_b2_shots_with_no_embedding_are_never_duplicates() -> None:
    assert all(item.is_usable for item in score_shots([shot(), shot()]))


def test_b2_a_shot_is_not_a_duplicate_of_one_that_was_itself_rejected() -> None:
    dark = shot(9.0, 1.0, 900.0, 1.0, luma=0.01, embedding=(1.0, 0.0))
    good = shot(1.0, embedding=(1.0, 0.0))

    scored_dark, scored_good = score_shots([dark, good])

    assert scored_dark.reject_reason is RejectReason.TOO_DARK
    assert scored_good.is_usable is True


def test_b2_duplicates_keep_the_input_order_for_the_planner() -> None:
    first, second, third = (
        shot(1.0),
        shot(2.0, embedding=(1.0, 0.0)),
        shot(3.0, embedding=(1.0, 0.0)),
    )

    scored = score_shots([first, second, third])

    assert [item.measure for item in scored] == [first, second, third]


def box(x: float, y: float = 0.5, label: str = "car", size: float = 0.1) -> DetectedObject:
    return DetectedObject(label, 0.9, x, y, size, size)


def seen(time: float, *boxes: DetectedObject) -> FrameObjects:
    return FrameObjects(time, boxes)


def test_b2_action_is_object_speed_in_frame_widths_per_second() -> None:
    assert object_velocity_peak([seen(0.0, box(0.2)), seen(0.25, box(0.3))]) == pytest.approx(0.4)


def test_b2_action_takes_the_fastest_object() -> None:
    slow_and_fast = [
        seen(0.0, box(0.1, label="person"), box(0.5)),
        seen(0.25, box(0.11, label="person"), box(0.7)),
    ]

    assert object_velocity_peak(slow_and_fast) == pytest.approx(0.8)


def test_b2_action_is_zero_for_still_objects_and_for_no_objects() -> None:
    assert object_velocity_peak([seen(0.0, box(0.5)), seen(0.25, box(0.5))]) == 0.0
    assert object_velocity_peak([seen(0.0), seen(0.25)]) == 0.0
    assert object_velocity_peak([]) == 0.0


def test_b2_action_does_not_pair_different_labels() -> None:
    assert object_velocity_peak([seen(0.0, box(0.2)), seen(0.25, box(0.3, label="dog"))]) == 0.0


def test_b2_a_jump_too_far_is_a_different_object_not_speed() -> None:
    assert object_velocity_peak([seen(0.0, box(0.1)), seen(0.25, box(0.9))]) == 0.0


def test_b2_one_wild_step_does_not_set_the_peak() -> None:
    steady = [seen(index * 0.25, box(0.1 + index * 0.01)) for index in range(20)]
    wild = [*steady, seen(5.0, box(0.1 + 19 * 0.01 + 0.3))]

    assert object_velocity_peak(wild) == pytest.approx(0.04)


def test_b2_two_detections_at_the_same_time_give_no_speed() -> None:
    assert object_velocity_peak([seen(1.0, box(0.2)), seen(1.0, box(0.3))]) == 0.0


def test_b2_a_shot_stores_its_object_velocity_peak() -> None:
    objects = [seen(0.0, box(0.2)), seen(0.25, box(0.3))]

    assert measure_shot([frame()], 0, 1, objects).action == pytest.approx(0.4)


def test_b2_a_person_counts_as_the_subject_when_no_face_was_found() -> None:
    objects = [seen(0.0, box(0.5, label="person", size=0.5))]

    assert measure_shot([frame()], 0, 1, objects).subject == 1.0


def test_b2_the_larger_of_face_and_person_is_the_subject() -> None:
    objects = [seen(0.0, box(0.5, label="person", size=0.1))]

    assert measure_shot([frame(area=0.2)], 0, 1, objects).subject == pytest.approx(0.8)


def test_b2_other_objects_are_not_the_subject() -> None:
    assert measure_shot([frame()], 0, 1, [seen(0.0, box(0.5, size=0.5))]).subject == 0.0


def test_b2_flow_across_the_cut_before_a_shot_is_not_its_motion() -> None:
    measured = measure_shot(
        [frame(0.0, motion=50.0, camera=50.0), frame(0.25, camera=1.0), frame(0.5, camera=1.0)],
        0,
        1,
    )

    assert measured.motion == 1.0
    assert measured.stability == 1.0
    assert measured.peak_time != 0.0


@pytest.mark.parametrize(
    ("flow", "direction"),
    [
        ((2.0, 0.0), MotionDirection.RIGHT),
        ((-2.0, 0.0), MotionDirection.LEFT),
        ((0.0, 2.0), MotionDirection.DOWN),
        ((0.0, -2.0), MotionDirection.UP),
    ],
)
def test_b2_motion_direction_follows_the_flow(
    flow: tuple[float, float], direction: MotionDirection
) -> None:
    frames = [FrameSample(0.0, 2.0, 1.0, 100.0, 0.5, 0.0, flow[0], flow[1])]

    assert measure_shot(frames, 0, 1).motion_direction is direction


def test_b2_shaking_back_and_forth_has_no_direction() -> None:
    frames = [
        FrameSample(index * 0.25, 2.0, 1.0, 100.0, 0.5, 0.0, 2.0 if index % 2 else -2.0, 0.0)
        for index in range(1, 5)
    ]

    assert measure_shot([frame(), *frames], 0, 1).motion_direction is MotionDirection.NONE


def test_b2_a_barely_moving_shot_has_no_direction() -> None:
    frames = [FrameSample(0.0, 0.05, 0.0, 100.0, 0.5, 0.0, 0.05, 0.0)]

    assert measure_shot(frames, 0, 1).motion_direction is MotionDirection.NONE


def test_b2_motion_scattered_in_all_directions_has_no_direction() -> None:
    frames = [FrameSample(0.0, 5.0, 0.0, 100.0, 0.5, 0.0, 0.5, 0.0)]

    assert measure_shot(frames, 0, 1).motion_direction is MotionDirection.NONE


def test_b2_the_dominant_color_is_the_most_common_frame_color() -> None:
    frames = [
        FrameSample(0.0, 1.0, 1.0, 100.0, 0.5, 0.0, color="#105090"),
        FrameSample(0.25, 1.0, 1.0, 100.0, 0.5, 0.0, color="#f01010"),
        FrameSample(0.5, 1.0, 1.0, 100.0, 0.5, 0.0, color="#f01010"),
    ]

    assert measure_shot(frames, 0, 1).dominant_color == "#f01010"


def test_b2_describing_a_shot_merges_clip_and_object_tags_without_repeats() -> None:
    measure = measure_shot([frame()], 0, 1)
    objects = [seen(0.0, box(0.5), box(0.5, label="person"))]

    described = describe_shot(
        measure, ShotVision((1.0, 0.0), 0.6), objects, {"car": (1.0, 0.0), "sea": (0.0, 1.0)}
    )

    assert described.tags == ("car", "person")
    assert described.aesthetics == 0.6
    assert described.embedding == (1.0, 0.0)
