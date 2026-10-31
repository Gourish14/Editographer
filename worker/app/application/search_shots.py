"""CLIP shot search. Spec: specs/05-editing-brain.md#b4-shot-assignment-assignpy

Support data for the planner's prompt fit: it ranks and marks shots but never picks them.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.domain.brain.shot_tags import ShotMatch, TagSupport, rank_shots, tag_phrase
from app.domain.shots import ShotMeasure
from app.ports.shots import TextEncoder


class SearchShots:
    def __init__(self, encoder: TextEncoder) -> None:
        self._encoder = encoder

    def rank(self, text: str, shots: Sequence[ShotMeasure]) -> tuple[ShotMatch, ...]:
        """Every shot, closest to the text first."""
        return self.support((text,), (), shots).included[text]

    def support(
        self, include: Sequence[str], exclude: Sequence[str], shots: Sequence[ShotMeasure]
    ) -> TagSupport:
        """Ranks the shots against each prompt tag, encoding all the tags in one GPU session."""
        tags = tuple(dict.fromkeys((*include, *exclude)))
        if not tags:
            return TagSupport({}, {})
        encoded = self._encoder.encode_texts(tuple(tag_phrase(tag) for tag in tags))
        ranked = {tag: rank_shots(query, shots) for tag, query in zip(tags, encoded, strict=True)}
        return TagSupport(
            {tag: ranked[tag] for tag in include}, {tag: ranked[tag] for tag in exclude}
        )
