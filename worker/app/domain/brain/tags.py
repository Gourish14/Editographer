"""Matching a wanted word against shot tags.

Spec: specs/05-editing-brain.md#b4-shot-assignment-assignpy

The similarity threshold is applied when tags are stored, so here a tag either matches or not.
"""

from __future__ import annotations

from collections.abc import Iterable

MIN_STEM_LENGTH = 3


def tag_matches(tags: Iterable[str], wanted: str) -> bool:
    """True when a tag has the wanted word: "car" matches "sports car" and "cars", not "carpet"."""
    word = wanted.strip().lower()
    return any(_stem(word) in _words(tag) for tag in tags)


def _words(tag: str) -> set[str]:
    return {_stem(word) for word in tag.lower().replace("-", " ").split()}


def _stem(word: str) -> str:
    plural = word.endswith("s") and not word.endswith("ss") and len(word) > MIN_STEM_LENGTH
    return word[:-1] if plural else word
