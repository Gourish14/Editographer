"""Asks the LLM director, or falls back to the rules.

Spec: specs/05-editing-brain.md#b10-llm-director-and-fallback-directorpy
"""

from __future__ import annotations

from collections.abc import Sequence

import structlog

from app.domain.brain.director import SYSTEM_PROMPT, director_brief
from app.domain.brain.planner import ClipInput, rule_direction
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
        brief = director_brief(music, clips, settings)
        try:
            # Ollama loads its own model, so the guard is held around the call, not around a load.
            with self._gpu.loaded(lambda: self._llm) as llm:
                decision = llm.complete_json(SYSTEM_PROMPT, brief, DirectorDecision)
        except (LlmUnavailableError, LlmInvalidOutputError) as error:
            log.warning("director.fallback", errorCode=error.code.value, message=str(error))
            return rule_direction(settings.prompt, (FALLBACK_NOTE,))
        log.info("director.decided", style=decision.style, storyHints=decision.story_hints)
        if not _prompt(settings):
            decision = decision.model_copy(update={"constraints": NO_CONSTRAINTS})
        return Direction(decision)


def _prompt(settings: RenderSettings) -> str:
    return (settings.prompt or "").strip()
