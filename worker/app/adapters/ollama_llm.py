"""Talks to the local Ollama server. Spec: specs/02-architecture.md#how-the-processes-talk

`format: json` and `keep_alive: 0`, so the model leaves the GPU after each call. One retry on
invalid output. Spec: specs/05-editing-brain.md#b10-llm-director-and-fallback-directorpy
"""

from __future__ import annotations

from typing import Any, TypeVar

import httpx
import structlog
from pydantic import BaseModel, ValidationError

from app.domain.errors import LlmInvalidOutputError, LlmUnavailableError

M = TypeVar("M", bound=BaseModel)

log = structlog.get_logger()

DIRECTOR_MODEL = "qwen3:4b"
CONNECT_TIMEOUT_SEC = 2.0
ANSWER_TIMEOUT_SEC = 120.0
ATTEMPTS = 2
CONTEXT_TOKENS = 4096
FIXED_SEED = 1
RETRY_NOTE = "Your last reply was not valid: {error}. Reply with the JSON object only."
MAX_ERROR_CHARS = 300


class _ChatMessage(BaseModel):
    content: str


class _ChatResponse(BaseModel):
    message: _ChatMessage


class OllamaLlmClient:
    """Temperature 0 and a fixed seed keep the same prompt giving the same answer."""

    def __init__(self, client: httpx.Client, model: str = DIRECTOR_MODEL) -> None:
        self._client = client
        self._model = model

    @classmethod
    def create(cls, url: str, model: str = DIRECTOR_MODEL) -> OllamaLlmClient:
        timeout = httpx.Timeout(ANSWER_TIMEOUT_SEC, connect=CONNECT_TIMEOUT_SEC)
        return cls(httpx.Client(base_url=url, timeout=timeout), model)

    def complete_json(self, system: str, user: str, schema: type[M]) -> M:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        problem = ""
        for attempt in range(1, ATTEMPTS + 1):
            content = self._chat(messages)
            try:
                return schema.model_validate_json(content)
            except ValidationError as error:
                problem = str(error)[:MAX_ERROR_CHARS]
                log.warning("llm.invalid_output", attempt=attempt, message=problem)
                messages = [
                    *messages[:2],
                    {"role": "assistant", "content": content},
                    {"role": "user", "content": RETRY_NOTE.format(error=problem)},
                ]
        raise LlmInvalidOutputError(f"The LLM gave no valid answer: {problem}")

    def _chat(self, messages: list[dict[str, str]]) -> str:
        body: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "format": "json",
            "stream": False,
            "think": False,
            "keep_alive": 0,
            "options": {"temperature": 0, "seed": FIXED_SEED, "num_ctx": CONTEXT_TOKENS},
        }
        try:
            response = self._client.post("/api/chat", json=body)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise LlmUnavailableError(f"Ollama did not answer: {error}") from error
        try:
            return _ChatResponse.model_validate_json(response.content).message.content
        except ValidationError as error:
            raise LlmInvalidOutputError("Ollama sent an unreadable reply") from error
