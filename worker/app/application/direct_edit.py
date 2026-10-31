"""Asks the LLM director, or falls back to the rules.

Spec: specs/05-editing-brain.md#b10-llm-director-and-fallback-directorpy
"""

from __future__ import annotations

from collections.abc import Sequence

import structlog

from app.domain.brain.director import director_request
from app.domain.brain.planner import ClipInput, rule_direction
from app.domain.brain.prompt_rules import parse_prompt
from app.domain.brain.style_rules import AUTO
from app.domain.constraints import NO_CONSTRAINTS, Direction, DirectorDecision
from app.domain.errors import LlmInvalidOutputError, LlmUnavailableError
from app.domain.models import RenderSettings
from app.domain.music import MusicMap
from app.ports.gpu_guard import GpuGuard
from app.ports.llm import LlmClient

log = structlog.get_logger()

FALLBACK_NOTE = "AI director unavailable; used the rule fallback"


class DirectEdit:
    def __init__(self, llm: LlmClient, gpu: GpuGuard) -> None:
        self._llm = llm
        self._gpu = gpu

    def has_work(self, settings: RenderSettings) -> bool:
        """With no prompt and a chosen style, the LLM has nothing to decide."""
        return bool(_prompt(settings)) or settings.style == AUTO

    def decide(
        self, music: MusicMap, clips: Sequence[ClipInput], settings: RenderSettings
    ) -> Direction:
        """Never fails: an LLM problem only means the rules decide."""
        if not self.has_work(settings):
            return rule_direction(None)
        request = director_request(music, clips, settings)
        try:
            # Ollama loads its own model, so the guard is held around the call, not around a load.
            with self._gpu.loaded(lambda: self._llm) as llm:
                decision = llm.complete_json(
                    request.system, request.user, DirectorDecision, request.examples
                )
        except (LlmUnavailableError, LlmInvalidOutputError) as error:
            log.warning("director.fallback", errorCode=error.code.value, message=str(error))
            return rule_direction(settings.prompt, (FALLBACK_NOTE,))
        log.info("director.decided", style=decision.style, storyHints=decision.story_hints)
        return Direction(_settled(decision, settings))


def _settled(decision: DirectorDecision, settings: RenderSettings) -> DirectorDecision:
    """An empty prompt has no constraints; a style the prompt names counts as the prompt's.

    The model sometimes reports a named style only as its own pick, which a style setting would
    then outrank, so the keyword rules settle whether the prompt named it.
    """
    if not _prompt(settings):
        return decision.model_copy(update={"constraints": NO_CONSTRAINTS})
    named = parse_prompt(settings.prompt).style
    if named is None or decision.constraints.style is not None:
        return decision
    constraints = decision.constraints.model_copy(update={"style": named})
    return decision.model_copy(update={"constraints": constraints})


def _prompt(settings: RenderSettings) -> str:
    return (settings.prompt or "").strip()
