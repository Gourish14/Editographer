"""Text and captions rules. Spec: specs/05-editing-brain.md#b8-text-and-audio

Text pops on the next downbeat. Captions only when speech exists and the style is not cinematic.
SAM 2 text-behind-subject is out of scope: `behind_subject` is carried but never set here.
"""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Sequence
from dataclasses import dataclass

POP_ANIM = "pop_on_beat"
CAPTION_ANIM = "caption"
NO_CAPTION_STYLES = frozenset({"cinematic"})
DEFAULT_TEXT_DURATION = 1.4
CAPTION_MAX_WORDS = 4
CAPTION_MAX_GAP = 0.6
CAPTION_MIN_DURATION = 0.4
EPSILON = 1e-6


@dataclass(frozen=True)
class TextItem:
    content: str
    at: float
    duration: float
    anim: str = POP_ANIM
    behind_subject: bool = False


@dataclass(frozen=True)
class CaptionWord:
    text: str
    start: float
    end: float


def next_downbeat(time: float, downbeats: Sequence[float]) -> float | None:
    """First downbeat at or after `time`, or None when there is none."""
    index = bisect_left(downbeats, time - EPSILON)
    return downbeats[index] if index < len(downbeats) else None


def schedule_text(
    contents: Sequence[str],
    downbeats: Sequence[float],
    window_start: float,
    window_end: float,
    duration: float = DEFAULT_TEXT_DURATION,
) -> tuple[tuple[TextItem, ...], tuple[str, ...]]:
    """Spreads prompt text evenly over the window; each item pops on the next downbeat.

    Returns the items and log lines for text that could not be placed.
    """
    texts = [text.strip() for text in contents if text.strip()]
    span = window_end - window_start
    usable = [d for d in downbeats if window_start - EPSILON <= d < window_end]
    items: list[TextItem] = []
    log: list[str] = []
    used: set[float] = set()
    for index, text in enumerate(texts):
        at = next_downbeat(window_start + span * index / len(texts), usable)
        while at is not None and at in used:
            at = next_downbeat(at + 1e-3, usable)
        if at is None:
            log.append(f"Text '{text}' skipped: no downbeat left in the edit window")
            continue
        used.add(at)
        items.append(TextItem(text, at, min(duration, window_end - at)))
    return tuple(items), tuple(log)


def captions_enabled(style: str, has_speech: bool) -> bool:
    return has_speech and style.lower() not in NO_CAPTION_STYLES


def caption_items(
    words: Sequence[CaptionWord],
    window_start: float = 0.0,
    window_end: float | None = None,
) -> tuple[TextItem, ...]:
    """Groups words into short caption lines, shifted to the timeline of the window."""
    kept = [
        w for w in words if w.start >= window_start and (window_end is None or w.end <= window_end)
    ]
    groups: list[list[CaptionWord]] = []
    for word in kept:
        if (
            groups
            and len(groups[-1]) < CAPTION_MAX_WORDS
            and word.start - groups[-1][-1].end <= CAPTION_MAX_GAP
        ):
            groups[-1].append(word)
        else:
            groups.append([word])
    return tuple(
        TextItem(
            " ".join(w.text.strip() for w in group),
            group[0].start - window_start,
            max(group[-1].end - group[0].start, CAPTION_MIN_DURATION),
            CAPTION_ANIM,
        )
        for group in groups
    )
