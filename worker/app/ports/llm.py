"""Port for the local LLM.

Spec: specs/05-editing-brain.md#b10-llm-director-and-fallback-directorpy
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, TypeVar

from pydantic import BaseModel

M = TypeVar("M", bound=BaseModel)


class LlmClient(Protocol):
    def complete_json(
        self,
        system: str,
        user: str,
        schema: type[M],
        examples: Sequence[tuple[str, str]] = (),
    ) -> M:
        """Asks for JSON and returns it validated against `schema`.

        `examples` are (question, answer) pairs shown to the model before the question.

        Raises LlmUnavailableError when no answer came, LlmInvalidOutputError when the answers
        were unusable. The call unloads the model from the GPU when it ends.
        """
        ...
