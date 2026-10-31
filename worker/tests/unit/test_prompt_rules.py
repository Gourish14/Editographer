"""Tests for the keyword prompt parser and the constraint model.

Spec: specs/05-editing-brain.md#b9-prompt-to-constraints-promptpy [T-202]
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.brain.prompt_rules import parse_prompt
from app.domain.brain.tags import tag_matches
from app.domain.constraints import Constraints, DirectorDecision
from app.domain.music import SectionKind


@pytest.mark.parametrize("prompt", [None, "", "   ", "please"])
def test_b9_an_empty_prompt_asks_for_nothing(prompt: str | None) -> None:
    assert parse_prompt(prompt) == Constraints()


@pytest.mark.parametrize("prompt", ["slow mo", "slow-mo", "slowmo", "slow motion", "SLOW MO"])
def test_b9_slow_mo_defaults_to_the_drop(prompt: str) -> None:
    assert parse_prompt(prompt).slowmo_at == (SectionKind.DROP,)


def test_b9_slow_mo_follows_the_named_section() -> None:
    assert parse_prompt("slow-mo on the break").slowmo_at == (SectionKind.BREAK,)


def test_b9_no_slow_mo_is_understood_and_asks_for_nothing() -> None:
    assert parse_prompt("no slow mo") == Constraints()


@pytest.mark.parametrize(
    "prompt", ["no shake", "no shakes", "without shaking", "no camera shake", "remove the shake"]
)
def test_b9_no_shake_turns_shake_off(prompt: str) -> None:
    result = parse_prompt(prompt)

    assert result.effects_off == ("shake",)
    assert result.exclude_tags == ()
    assert result.unmapped == ()


def test_b9_no_effects_turns_every_effect_off() -> None:
    assert set(parse_prompt("no effects").effects_off) == {"shake", "flash", "zoompunch"}


def test_b9_cinematic_no_shakes() -> None:
    result = parse_prompt("cinematic, no shakes")

    assert result.style == "cinematic"
    assert result.effects_off == ("shake",)


def test_b9_cinematic_no_shakes_without_a_comma() -> None:
    result = parse_prompt("cinematic no shakes")

    assert result.style == "cinematic"
    assert result.effects_off == ("shake",)


def test_b9_not_cinematic_is_no_style() -> None:
    assert parse_prompt("not cinematic").style is None


@pytest.mark.parametrize(
    "prompt",
    [
        "only car",
        "only car shots",
        "use only the car shots",
        "just the car clips",
        "car shots only",
    ],
)
def test_b9_only_car_includes_the_tag(prompt: str) -> None:
    result = parse_prompt(prompt)

    assert result.include_tags == ("car",)
    assert result.style is None
    assert result.unmapped == ()


def test_b9_car_edit_is_a_style_not_a_tag() -> None:
    result = parse_prompt("car edit")

    assert result.style == "car"
    assert result.include_tags == ()


def test_b9_no_people_excludes_the_tag() -> None:
    assert parse_prompt("no people shots").exclude_tags == ("people",)


@pytest.mark.parametrize(
    ("prompt", "seconds"),
    [
        ("30 seconds", 30.0),
        ("30 second edit", 30.0),
        ("30s", 30.0),
        ("45 sec", 45.0),
        ("a 15-second reel", 15.0),
        ("1 minute", 60.0),
        ("2 mins", 120.0),
    ],
)
def test_b9_durations(prompt: str, seconds: float) -> None:
    assert parse_prompt(prompt).duration_sec == seconds


def test_b9_a_shot_count_is_not_a_duration() -> None:
    assert parse_prompt("2 shots").duration_sec is None


def test_b9_duration_and_text_from_the_spec_example() -> None:
    result = parse_prompt("30 seconds, add text GOA 2026")

    assert result.duration_sec == 30.0
    assert result.text == ("GOA 2026",)
    assert result.unmapped == ()


def test_b9_quoted_text_keeps_commas_and_is_not_read_as_requests() -> None:
    result = parse_prompt('add text "no shake, only car" and slow mo')

    assert result.text == ("no shake, only car",)
    assert result.effects_off == ()
    assert result.include_tags == ()
    assert result.slowmo_at == (SectionKind.DROP,)


def test_b9_chronological_order() -> None:
    assert parse_prompt("keep it chronological").order == "chronological"


def test_b9_what_maps_to_nothing_is_kept_in_the_users_words() -> None:
    result = parse_prompt("cinematic, add drone shots, make the sky purple")

    assert result.style == "cinematic"
    assert result.unmapped == ("add drone shots", "make the sky purple")


def test_b9_constraints_read_the_schema_names() -> None:
    result = Constraints.model_validate_json(
        '{"style":"cinematic","includeTags":["Car"],"excludeTags":[],"slowmoAt":["drop"],'
        '"fxIntensity":0.4,"effectsOn":["tinyplanet"],"effectsOff":["shake"],"durationSec":30,'
        '"text":["GOA 2026"],"order":"chronological","unmapped":["add drone shots"]}'
    )

    assert result.include_tags == ("car",)
    assert result.slowmo_at == (SectionKind.DROP,)
    assert result.fx_intensity == 0.4
    assert result.text == ("GOA 2026",)


@pytest.mark.parametrize(
    "document",
    [
        '{"style":"disco"}',
        '{"fxIntensity":1.5}',
        '{"durationSec":0}',
        '{"slowmoAt":["chorus"]}',
        '{"order":"random"}',
    ],
)
def test_b10_values_outside_the_schema_are_refused(document: str) -> None:
    with pytest.raises(ValidationError):
        Constraints.model_validate_json(document)


def test_b10_a_decision_reads_its_schema_names() -> None:
    decision = DirectorDecision.model_validate_json(
        '{"style":"hype","storyHints":["open wide"],"constraints":{"durationSec":20}}'
    )

    assert decision.style == "hype"
    assert decision.story_hints == ("open wide",)
    assert decision.constraints.duration_sec == 20


@pytest.mark.parametrize(
    ("tags", "wanted", "expected"),
    [
        (("car",), "car", True),
        (("Sports Car",), "car", True),
        (("cars",), "car", True),
        (("car",), "cars", True),
        (("carpet",), "car", False),
        (("",), "car", False),
        ((), "car", False),
    ],
)
def test_b4_tag_matching(tags: tuple[str, ...], wanted: str, expected: bool) -> None:
    assert tag_matches(tags, wanted) is expected
