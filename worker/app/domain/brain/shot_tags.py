"""CLIP tags and text search over shots.

Spec: specs/05-editing-brain.md#b2-shot-scoring-scoringpy and #b4-shot-assignment-assignpy
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.domain.shots import Embedding, FrameObjects, ShotMeasure, cosine_similarity

TAG_MATCH_SIMILARITY = 0.25
MAX_CLIP_TAGS = 5
OBJECT_TAG_MIN_FRAME_SHARE = 0.25
TAG_PHRASE = "a photo of {}"

TAG_VOCABULARY: tuple[str, ...] = (
    "person",
    "people",
    "face",
    "car",
    "vehicle",
    "motorcycle",
    "bicycle",
    "truck",
    "bus",
    "boat",
    "airplane",
    "train",
    "road",
    "street",
    "city",
    "building",
    "indoor",
    "outdoor",
    "landscape",
    "beach",
    "sea",
    "mountain",
    "forest",
    "snow",
    "sky",
    "sunset",
    "night",
    "food",
    "animal",
    "dog",
    "cat",
    "sports",
    "dancing",
)


@dataclass(frozen=True)
class ShotMatch:
    """How close one shot is to a piece of text. `matched` is the B4 prompt-fit test."""

    shot: ShotMeasure
    similarity: float
    matched: bool


@dataclass(frozen=True)
class TagSupport:
    """For the planner's B4 prompt fit: per tag, the shots ranked by similarity."""

    included: Mapping[str, tuple[ShotMatch, ...]]
    excluded: Mapping[str, tuple[ShotMatch, ...]]


def tag_phrase(tag: str) -> str:
    """The sentence CLIP compares images with; it does better on a phrase than a bare word."""
    return TAG_PHRASE.format(tag)


def clip_tags(embedding: Embedding, vocabulary: Mapping[str, Embedding]) -> tuple[str, ...]:
    """The vocabulary tags this shot resembles, closest first."""
    similarities = [
        (cosine_similarity(embedding, phrase), tag) for tag, phrase in vocabulary.items()
    ]
    close = [item for item in similarities if item[0] > TAG_MATCH_SIMILARITY]
    close.sort(key=lambda item: (-item[0], item[1]))
    return tuple(tag for _, tag in close[:MAX_CLIP_TAGS])


def object_tags(frames: Sequence[FrameObjects]) -> tuple[str, ...]:
    """Detector labels seen in enough of a shot's frames, so one false box adds no tag."""
    if not frames:
        return ()
    seen = Counter(label for frame in frames for label in {box.label for box in frame.objects})
    enough = len(frames) * OBJECT_TAG_MIN_FRAME_SHARE
    return tuple(sorted(label for label, count in seen.items() if count >= enough))


def rank_shots(query: Embedding, shots: Sequence[ShotMeasure]) -> tuple[ShotMatch, ...]:
    """Every shot, closest to the text first. Ties keep their input order."""
    matches = [_match(query, shot) for shot in shots]
    return tuple(sorted(matches, key=lambda match: -match.similarity))


def _match(query: Embedding, shot: ShotMeasure) -> ShotMatch:
    similarity = cosine_similarity(query, shot.embedding)
    return ShotMatch(shot, round(similarity, 4), similarity > TAG_MATCH_SIMILARITY)
