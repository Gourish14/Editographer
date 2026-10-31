"""Text, captions and kept speech in the plan. Spec: specs/05-editing-brain.md#b8-text-and-audio

Prompt text pops on downbeats. Captions come from the words said in segments that keep their
audio. All times are on the music timeline, like a segment's `at`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from app.domain.analysis import StoredAnalysis
from app.domain.brain.text_rules import (
    CaptionWord,
    caption_items,
    captions_enabled,
    schedule_text,
)
from app.domain.brain.text_rules import TextItem as RuleItem
from app.domain.music import EditWindow
from app.domain.plan import Segment, TextItem


def has_speech(analysis: StoredAnalysis, src_in: float, src_out: float) -> bool:
    return analysis.speech is not None and analysis.speech.overlaps(src_in, src_out)


def plan_text(
    contents: Sequence[str],
    downbeats: Sequence[float],
    window: EditWindow,
    style: str,
    segments: Sequence[Segment],
    analyses: Mapping[str, StoredAnalysis],
) -> tuple[tuple[TextItem, ...], tuple[str, ...]]:
    """Prompt text plus captions, and plan-log lines for text that did not fit."""
    items, notes = schedule_text(contents, downbeats, window.start, window.end)
    spoken = [segment for segment in segments if segment.keep_audio]
    captions: tuple[RuleItem, ...] = ()
    if captions_enabled(style, bool(spoken)):
        words = _words(spoken, analyses)
        captions = tuple(
            RuleItem(item.content, item.at + window.start, item.duration, item.anim)
            for item in caption_items(words, window.start, window.end)
        )
    return tuple(_clipped(item, window.end) for item in (*items, *captions)), notes


def _words(spoken: Sequence[Segment], analyses: Mapping[str, StoredAnalysis]) -> list[CaptionWord]:
    words: list[CaptionWord] = []
    for segment in spoken:
        speech = analyses[segment.asset_id].speech
        if speech is None:
            continue
        for text, start, end in speech.words:
            if segment.src_in <= start and end <= segment.src_out:
                shift = segment.at - segment.src_in
                words.append(CaptionWord(text, round(start + shift, 4), round(end + shift, 4)))
    return sorted(words, key=lambda word: word.start)


def _clipped(item: RuleItem, window_end: float) -> TextItem:
    return TextItem(
        content=item.content,
        at=round(item.at, 4),
        duration=round(min(item.duration, window_end - item.at), 4),
        anim=item.anim,
        behind_subject=item.behind_subject,
    )
