"""Tests for CLIP tags and shot search. Spec: specs/05-editing-brain.md#b2 and #b4 [T-201]"""

from __future__ import annotations

import pytest

from app.application.search_shots import SearchShots
from app.domain.brain.shot_tags import (
    MAX_CLIP_TAGS,
    TAG_MATCH_SIMILARITY,
    clip_tags,
    object_tags,
    rank_shots,
    tag_phrase,
)
from app.domain.shots import (
    DetectedObject,
    Embedding,
    FrameObjects,
    ShotMeasure,
    cosine_similarity,
)
from tests.unit.shot_fakes import BEACH_VECTOR, CAR_VECTOR, FakeEncoder


def shot(embedding: Embedding = ()) -> ShotMeasure:
    return ShotMeasure(
        start=0.0,
        end=1.0,
        motion=1.0,
        subject=0.0,
        sharpness=1.0,
        stability=1.0,
        luma=0.5,
        peak_time=0.5,
        usable=(),
        embedding=embedding,
    )


def seen(*labels: str) -> FrameObjects:
    return FrameObjects(
        0.0, tuple(DetectedObject(label, 0.9, 0.5, 0.5, 0.1, 0.1) for label in labels)
    )


def test_cosine_is_one_for_the_same_direction_and_zero_at_a_right_angle() -> None:
    assert cosine_similarity((2.0, 0.0), (5.0, 0.0)) == pytest.approx(1.0)
    assert cosine_similarity((1.0, 0.0), (0.0, 1.0)) == 0.0


def test_a_missing_or_zero_embedding_resembles_nothing() -> None:
    assert cosine_similarity((), (1.0,)) == 0.0
    assert cosine_similarity((0.0, 0.0), (1.0, 0.0)) == 0.0


def test_b2_clip_tags_are_the_close_phrases_closest_first() -> None:
    vocabulary = {"near": (0.9, 0.1), "nearest": (1.0, 0.0), "far": (0.0, 1.0)}

    assert clip_tags((1.0, 0.0), vocabulary) == ("nearest", "near")


def test_b2_clip_tags_are_capped() -> None:
    vocabulary = {f"tag{index}": (1.0, 0.0) for index in range(MAX_CLIP_TAGS + 3)}

    assert len(clip_tags((1.0, 0.0), vocabulary)) == MAX_CLIP_TAGS


def test_b2_an_object_seen_in_one_frame_of_many_is_no_tag() -> None:
    frames = [seen("car"), *[seen("person") for _ in range(9)]]

    assert object_tags(frames) == ("person",)


def test_b2_a_shot_with_no_frames_has_no_object_tags() -> None:
    assert object_tags([]) == ()


def test_b4_search_ranks_the_closest_shot_first() -> None:
    near, far = shot(CAR_VECTOR), shot(BEACH_VECTOR)

    ranked = rank_shots(CAR_VECTOR, [far, near])

    assert [match.shot for match in ranked] == [near, far]


def test_b4_a_shot_matches_only_above_the_similarity_threshold() -> None:
    assert rank_shots(CAR_VECTOR, [shot(CAR_VECTOR)])[0].matched is True
    assert rank_shots(CAR_VECTOR, [shot(BEACH_VECTOR)])[0].matched is False
    assert TAG_MATCH_SIMILARITY == 0.25


def test_b4_a_shot_without_an_embedding_never_matches() -> None:
    match = rank_shots(CAR_VECTOR, [shot()])[0]

    assert match.similarity == 0.0
    assert match.matched is False


def test_b4_search_phrases_the_text_like_the_tags() -> None:
    encoder = FakeEncoder()
    car = shot(CAR_VECTOR)

    ranked = SearchShots(encoder).rank("car", [car])

    assert encoder.texts == [(tag_phrase("car"),)]
    assert ranked[0].matched is True


def test_b4_support_gives_each_include_and_exclude_tag_its_ranking() -> None:
    car, beach = shot(CAR_VECTOR), shot(BEACH_VECTOR)

    support = SearchShots(FakeEncoder()).support(["car"], ["sea"], [car, beach])

    assert [match.shot for match in support.included["car"] if match.matched] == [car]
    assert [match.shot for match in support.excluded["sea"] if match.matched] == [beach]


def test_b4_support_encodes_all_tags_in_one_call_and_each_tag_once() -> None:
    encoder = FakeEncoder()

    SearchShots(encoder).support(["car", "sea"], ["car"], [shot()])

    assert len(encoder.texts) == 1
    assert len(encoder.texts[0]) == 2


def test_b4_no_prompt_tags_never_touch_the_gpu() -> None:
    encoder = FakeEncoder()

    support = SearchShots(encoder).support([], [], [shot()])

    assert (support.included, support.excluded) == ({}, {})
    assert encoder.texts == []
