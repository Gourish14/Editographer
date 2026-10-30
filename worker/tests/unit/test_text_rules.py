"""Text and captions rules. Spec: specs/05-editing-brain.md#b8-text-and-audio [T-402]"""

from __future__ import annotations

from app.adapters.ffmpeg_text_overlay import overlay_chain
from app.domain.brain.text_rules import (
    CaptionWord,
    TextItem,
    caption_items,
    captions_enabled,
    next_downbeat,
    schedule_text,
)

DOWNBEATS = [0.0, 2.0, 4.0, 6.0, 8.0]


def test_b8_text_pops_on_the_next_downbeat() -> None:
    assert next_downbeat(2.1, DOWNBEATS) == 4.0
    assert next_downbeat(2.0, DOWNBEATS) == 2.0
    assert next_downbeat(9.0, DOWNBEATS) is None


def test_b8_every_text_item_lands_on_a_downbeat_without_overlap() -> None:
    items, log = schedule_text(["A", "B", "C"], DOWNBEATS, 1.0, 9.0)
    assert [i.at for i in items] == [2.0, 4.0, 6.0] or all(i.at in DOWNBEATS for i in items)
    assert len({i.at for i in items}) == 3
    assert log == ()


def test_b8_text_that_finds_no_downbeat_is_logged_not_dropped_silently() -> None:
    items, log = schedule_text(["A", "B", "C"], [4.0], 0.0, 6.0)
    assert len(items) == 1
    assert len(log) == 2 and "skipped" in log[0]


def test_b8_text_duration_is_clipped_to_the_window() -> None:
    items, _ = schedule_text(["A"], [5.5], 0.0, 6.0)
    assert items[0].duration == 0.5


def test_b8_captions_need_speech_and_a_non_cinematic_style() -> None:
    assert captions_enabled("velocity", True)
    assert not captions_enabled("velocity", False)
    assert not captions_enabled("Cinematic", True)


def test_b8_captions_group_words_and_shift_to_the_window() -> None:
    words = [
        CaptionWord("a", 10.0, 10.2),
        CaptionWord("b", 10.3, 10.5),
        CaptionWord("c", 12.0, 12.3),
        CaptionWord("early", 1.0, 1.2),
    ]
    items = caption_items(words, window_start=10.0, window_end=13.0)
    assert [(i.content, i.at) for i in items] == [("a b", 0.0), ("c", 2.0)]
    assert all(i.anim == "caption" for i in items)


def test_b8_overlay_chain_enables_each_layer_only_during_its_time() -> None:
    chain = overlay_chain("v", [TextItem("HI", 2.0, 1.4)], first_input=1)
    assert "between(t,2.000,3.400)" in chain
    assert chain.endswith("[vtext]")
    assert overlay_chain("v", [], 1) == "[v]null[vtext]"
