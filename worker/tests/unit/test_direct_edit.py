"""Tests for the director: the brief, the guard and the fallback.

Spec: specs/05-editing-brain.md#b10-llm-director-and-fallback-directorpy [T-202]
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Sequence
from typing import TypeVar

import pytest
from pydantic import BaseModel

from app.adapters.nvml_gpu_guard import NvmlGpuGuard
from app.application.direct_edit import FALLBACK_NOTE, DirectEdit
from app.domain.brain.director import (
    EXAMPLES,
    MAX_SHOTS,
    NO_PROMPT,
    director_brief,
    director_request,
)
from app.domain.brain.planner import ClipInput
from app.domain.constraints import Constraints, DirectorDecision
from app.domain.errors import LlmInvalidOutputError, LlmUnavailableError
from app.domain.models import RenderSettings
from app.domain.shots import ShotMeasure, TimeWindow
from tests.unit.test_planner import analysis, music_map

M = TypeVar("M", bound=BaseModel)
AUTO = RenderSettings("9:16", "4K", 30, "auto", "fast", 30, None, False, 42)
TOKEN_BUDGET = 3000
CHARS_PER_TOKEN = 4


class FakeLlm:
    def __init__(self, answer: DirectorDecision | Exception) -> None:
        self.answer = answer
        self.calls: list[str] = []
        self.systems: list[str] = []
        self.examples: tuple[tuple[str, str], ...] = ()
        self.guard: NvmlGpuGuard | None = None
        self.held_guard = False

    def complete_json(
        self,
        system: str,
        user: str,
        schema: type[M],
        examples: Sequence[tuple[str, str]] = (),
    ) -> M:
        self.calls.append(user)
        self.systems.append(system)
        self.examples = tuple(examples)
        if self.guard is not None:
            self.held_guard = self.guard._lock.locked()
        if isinstance(self.answer, Exception):
            raise self.answer
        return schema.model_validate(self.answer.model_dump())


def shot(*tags: str, motion: float = 1.0) -> ShotMeasure:
    return ShotMeasure(
        start=0.0,
        end=10.0,
        motion=motion,
        subject=0.6,
        sharpness=100.0,
        stability=0.8,
        luma=0.5,
        peak_time=1.0,
        usable=(TimeWindow(start=0.0, end=10.0),),
        tags=tags,
    )


def clips(count: int = 3) -> list[ClipInput]:
    return [ClipInput(f"v{i}", analysis(shot("car", motion=i + 1.0))) for i in range(count)]


def director(llm: FakeLlm) -> DirectEdit:
    guard = NvmlGpuGuard(empty_cache=lambda: None)
    llm.guard = guard
    return DirectEdit(llm, guard)


def test_b10_the_brief_has_sections_shots_and_settings() -> None:
    brief = json.loads(director_brief(music_map(), clips(), AUTO))

    assert {"type", "start", "end", "energy"} == set(brief["sections"][0])
    assert {"id", "tags", "score", "cameraMode"} == set(brief["shots"][0])
    assert brief["shots"][0]["tags"] == ["car"]
    assert brief["settings"]["ratio"] == "9:16"


def test_b10_the_project_is_in_the_system_message_and_the_prompt_is_the_question() -> None:
    settings = dataclasses.replace(AUTO, prompt="  only car shots ")

    request = director_request(music_map(), clips(), settings)

    assert director_brief(music_map(), clips(), settings) in request.system
    assert request.user == "only car shots"
    assert request.examples == EXAMPLES


def test_b10_every_worked_example_is_a_valid_decision() -> None:
    for _, answer in EXAMPLES:
        DirectorDecision.model_validate_json(answer)


def test_b10_an_empty_prompt_asks_only_for_a_style() -> None:
    assert director_request(music_map(), clips(), AUTO).user == NO_PROMPT


def test_b10_the_brief_has_only_the_top_40_shots_in_score_order() -> None:
    many = [ClipInput(f"v{i}", analysis(shot(motion=float(i)))) for i in range(60)]

    shots = json.loads(director_brief(music_map(), many, AUTO))["shots"]

    assert len(shots) == MAX_SHOTS
    assert [s["score"] for s in shots] == sorted((s["score"] for s in shots), reverse=True)


def test_b10_the_brief_stays_inside_the_token_budget_at_its_largest() -> None:
    wordy = tuple(f"very long tag number {n}" for n in range(30))
    many = [ClipInput(f"asset-{i:032}", analysis(shot(*wordy))) for i in range(60)]
    settings = dataclasses.replace(AUTO, prompt="x" * 20000)

    request = director_request(music_map(), many, settings)
    examples = sum(len(question) + len(answer) for question, answer in request.examples)

    assert (len(request.system) + len(request.user) + examples) / CHARS_PER_TOKEN <= TOKEN_BUDGET


def test_b10_the_decision_is_followed() -> None:
    answer = DirectorDecision(style="hype", constraints=Constraints(include_tags=("car",)))
    llm = FakeLlm(answer)

    direction = director(llm).decide(
        music_map(), clips(), dataclasses.replace(AUTO, prompt="only car shots")
    )

    assert direction.decision == answer
    assert direction.notes == ()


def test_b10_the_gpu_guard_is_held_during_the_call() -> None:
    llm = FakeLlm(DirectorDecision())

    director(llm).decide(music_map(), clips(), AUTO)

    assert llm.held_guard


def test_b10_the_gpu_guard_is_released_when_ollama_is_down() -> None:
    llm = FakeLlm(LlmUnavailableError("down"))
    edit = director(llm)

    edit.decide(music_map(), clips(), AUTO)

    assert llm.guard is not None
    assert not llm.guard._lock.locked()


@pytest.mark.parametrize(
    "failure", [LlmUnavailableError("Ollama did not answer"), LlmInvalidOutputError("bad")]
)
def test_b10_a_failed_llm_falls_back_to_the_keyword_rules(failure: Exception) -> None:
    settings = dataclasses.replace(AUTO, prompt="cinematic, no shakes")

    direction = director(FakeLlm(failure)).decide(music_map(), clips(), settings)

    assert direction.decision.constraints.style == "cinematic"
    assert direction.decision.constraints.effects_off == ("shake",)
    assert direction.notes == (FALLBACK_NOTE,)


def test_b10_with_no_prompt_and_a_chosen_style_the_llm_is_not_called() -> None:
    llm = FakeLlm(DirectorDecision())
    settings = dataclasses.replace(AUTO, style="velocity")

    direction = director(llm).decide(music_map(), clips(), settings)

    assert llm.calls == []
    assert direction.notes == ()


def test_b10_with_auto_style_the_llm_picks_even_without_a_prompt() -> None:
    llm = FakeLlm(DirectorDecision(style="sports"))

    direction = director(llm).decide(music_map(), clips(), AUTO)

    assert len(llm.calls) == 1
    assert direction.decision.style == "sports"


def test_b10_a_style_the_prompt_names_counts_as_the_prompts_own() -> None:
    llm = FakeLlm(DirectorDecision(style="cinematic"))
    settings = dataclasses.replace(AUTO, style="velocity", prompt="cinematic no shakes")

    direction = director(llm).decide(music_map(), clips(), settings)

    assert direction.decision.constraints.style == "cinematic"


def test_b10_the_directors_own_pick_is_not_mistaken_for_the_prompts() -> None:
    llm = FakeLlm(DirectorDecision(style="hype"))
    settings = dataclasses.replace(AUTO, style="velocity", prompt="only car shots")

    direction = director(llm).decide(music_map(), clips(), settings)

    assert direction.decision.constraints.style is None


def test_b9_an_empty_prompt_never_gets_constraints_from_the_llm() -> None:
    invented = Constraints(include_tags=("car",), duration_sec=10.0)
    llm = FakeLlm(DirectorDecision(style="sports", constraints=invented))

    direction = director(llm).decide(music_map(), clips(), AUTO)

    assert direction.decision.constraints == Constraints()
    assert direction.decision.style == "sports"
