"""Keyword prompt parser, the fallback when the LLM fails.

Spec: specs/05-editing-brain.md#b9-prompt-to-constraints-promptpy

Works one clause at a time, so a clause nothing understood lands in `unmapped` whole.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import cast, get_args

from app.domain.constraints import Constraints, ShotOrder, StyleId
from app.domain.music import SectionKind

DEFAULT_SLOWMO_SECTION = SectionKind.DROP
SECONDS_PER_MINUTE = 60.0
ALL_EFFECTS = ("shake", "flash", "zoomPunch")
EFFECT_WORDS = {"shake": "shake", "flash": "flash", "zoom": "zoomPunch"}
FILLER = {"please", "make", "it", "the", "a", "an", "thanks", "edit", "video", "me"}

NEGATION = r"(?:no|not|without|remove|disable|avoid|skip|exclude|don'?t\s+use)"
_QUOTED_TEXT = re.compile(
    r"(?:(?:add|put|show)\s+)?(?:the\s+)?(?:text|title|caption)\s*[:=]?\s*"
    r"(?:\"(?P<double>[^\"]+)\"|'(?P<single>[^']+)')",
    re.IGNORECASE,
)
_PLAIN_TEXT = re.compile(
    r"(?:(?:add|put|show)\s+)?(?:the\s+)?(?:text|title|caption)\s*[:=]?\s+(?P<content>\S.*)",
    re.IGNORECASE,
)
_CLAUSE_BREAK = re.compile(r"[,;\n]|\.(?=\s|$)|\s(?:and|then|plus|but|also)\s", re.IGNORECASE)
_SLOWMO = re.compile(r"\bslow[\s-]*mo(?:tion)?\b", re.IGNORECASE)
_NEGATED_SLOWMO = re.compile(rf"\b{NEGATION}\s+slow[\s-]*mo", re.IGNORECASE)
_DURATION = re.compile(
    r"\b(?P<value>\d+(?:\.\d+)?)[\s-]*(?P<unit>seconds?|secs?|s|minutes?|mins?|m)\b",
    re.IGNORECASE,
)
_EFFECT_OFF = re.compile(
    rf"\b{NEGATION}\s+(?:the\s+|any\s+|camera\s+)*(?P<word>shak|flash|zoom)\w*", re.IGNORECASE
)
_ALL_EFFECTS_OFF = re.compile(rf"\b{NEGATION}\s+(?:the\s+|any\s+)*(?:effects?|fx)\b", re.IGNORECASE)
_ONLY_TAG = re.compile(
    r"\b(?:only|just)\s+(?:use\s+)?(?:the\s+|my\s+)?(?P<tag>[a-z][a-z-]*)"
    r"(?:\s+(?:shots?|clips?|footage|scenes?))?\b",
    re.IGNORECASE,
)
_TAG_ONLY = re.compile(
    r"\b(?P<tag>[a-z][a-z-]*)\s+(?:shots?|clips?|footage|scenes?)\s+only\b", re.IGNORECASE
)
_EXCLUDE_TAG = re.compile(
    rf"\b{NEGATION}\s+(?:the\s+|any\s+|my\s+)*(?P<tag>[a-z][a-z-]*)"
    r"(?:\s+(?:shots?|clips?|footage|scenes?))?\b",
    re.IGNORECASE,
)
_CHRONOLOGICAL = re.compile(r"\bchronological(?:ly)?\b|\bin\s+time\s+order\b", re.IGNORECASE)
_NOT_TAGS = {
    "slow", "effect", "effects", "fx", "shake", "shakes", "shaky", "shaking", "flash", "flashes",
    "zoom", "zooms", "camera", "velocity", "hype", "cinematic", "anime",
}  # fmt: skip


@dataclass
class _Found:
    style: StyleId | None = None
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    slowmo: list[SectionKind] = field(default_factory=list)
    off: list[str] = field(default_factory=list)
    duration: float | None = None
    text: list[str] = field(default_factory=list)
    order: ShotOrder | None = None
    unmapped: list[str] = field(default_factory=list)


def parse_prompt(prompt: str | None) -> Constraints:
    """Turns common phrases into constraints; whatever is left is listed in `unmapped`."""
    found = _Found()
    remaining = _take_quoted_text(prompt or "", found)
    for clause in _CLAUSE_BREAK.split(remaining):
        _read_clause(clause.strip(), found)
    return Constraints(
        style=found.style,
        include_tags=tuple(dict.fromkeys(found.include)),
        exclude_tags=tuple(dict.fromkeys(found.exclude)),
        slowmo_at=tuple(dict.fromkeys(found.slowmo)),
        effects_off=tuple(dict.fromkeys(found.off)),
        duration_sec=found.duration,
        text=tuple(found.text),
        order=found.order,
        unmapped=tuple(found.unmapped),
    )


def _take_quoted_text(prompt: str, found: _Found) -> str:
    """Quoted text goes first, so its commas and words are never read as requests."""

    def take(match: re.Match[str]) -> str:
        found.text.append(match["double"] or match["single"])
        return ","

    return _QUOTED_TEXT.sub(take, prompt)


def _read_clause(clause: str, found: _Found) -> None:
    if not clause:
        return
    plain = _PLAIN_TEXT.search(clause)
    if plain:
        found.text.append(plain["content"].strip())
        return
    readers = (_read_slowmo, _read_effects, _read_duration, _read_style, _read_order, _read_tags)
    results = [reader(clause, found) for reader in readers]
    if not any(results) and not _is_filler(clause):
        found.unmapped.append(clause)


def _read_slowmo(clause: str, found: _Found) -> bool:
    if not _SLOWMO.search(clause):
        return False
    if _NEGATED_SLOWMO.search(clause):
        return True
    named = [kind for kind in SectionKind if re.search(rf"\b{kind.value}\b", clause, re.IGNORECASE)]
    found.slowmo.extend(named or [DEFAULT_SLOWMO_SECTION])
    return True


def _read_effects(clause: str, found: _Found) -> bool:
    if _ALL_EFFECTS_OFF.search(clause):
        found.off.extend(ALL_EFFECTS)
        return True
    words = [match["word"].lower() for match in _EFFECT_OFF.finditer(clause)]
    found.off.extend(_effect_name(word) for word in words)
    return bool(words)


def _effect_name(word: str) -> str:
    return EFFECT_WORDS["shake" if word == "shak" else word]


def _read_duration(clause: str, found: _Found) -> bool:
    match = _DURATION.search(clause)
    if match is None:
        return False
    value = float(match["value"])
    if value <= 0:
        return False
    minutes = match["unit"].lower().startswith("m")
    found.duration = value * SECONDS_PER_MINUTE if minutes else value
    return True


def _read_style(clause: str, found: _Found) -> bool:
    """Names a style. "car" and "sports" need "style" or "edit", else they mean footage."""
    for style in get_args(StyleId):
        needs_suffix = style in {"car", "sports", "travel"}
        suffix = r"\s+(?:style|edit|look|vibe)" if needs_suffix else ""
        pattern = rf"(?<!not\s)(?<!no\s)\b{style}{suffix}\b"
        if re.search(pattern, clause, re.IGNORECASE):
            found.style = cast(StyleId, style)
            return True
    return False


def _read_order(clause: str, found: _Found) -> bool:
    if _CHRONOLOGICAL.search(clause):
        found.order = "chronological"
        return True
    return False


def _read_tags(clause: str, found: _Found) -> bool:
    included = [
        match["tag"].lower()
        for pattern in (_ONLY_TAG, _TAG_ONLY)
        for match in pattern.finditer(clause)
    ]
    found.include.extend(tag for tag in included if tag not in _NOT_TAGS)
    excluded = [match["tag"].lower() for match in _EXCLUDE_TAG.finditer(clause)]
    found.exclude.extend(tag for tag in excluded if tag not in _NOT_TAGS)
    return any(tag not in _NOT_TAGS for tag in (*included, *excluded))


def _is_filler(clause: str) -> bool:
    return all(word.lower() in FILLER for word in clause.split())
