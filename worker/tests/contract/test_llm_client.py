"""Contract of the LlmClient port, run against every adapter.

Spec: specs/05-editing-brain.md#b10-llm-director-and-fallback-directorpy [T-202]
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import httpx
import pytest

from app.adapters.ollama_llm import DIRECTOR_MODEL, OllamaLlmClient
from app.domain.constraints import DirectorDecision
from app.domain.errors import LlmInvalidOutputError, LlmUnavailableError
from app.ports.llm import LlmClient

GOOD = '{"style":"hype","storyHints":[],"constraints":{"includeTags":["car"]}}'


class FakeOllama:
    """Answers each chat call with the next reply."""

    def __init__(self, replies: Sequence[str | int | Exception]) -> None:
        self.replies = list(replies)
        self.bodies: list[dict[str, Any]] = []
        self.paths: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.bodies.append(json.loads(request.content))
        self.paths.append(request.url.path)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, int):
            return httpx.Response(reply)
        return httpx.Response(200, json={"message": {"role": "assistant", "content": reply}})

    def client(self) -> LlmClient:
        http = httpx.Client(base_url="http://ollama", transport=httpx.MockTransport(self))
        return OllamaLlmClient(http)


def ask(ollama: FakeOllama) -> DirectorDecision:
    return ollama.client().complete_json("system", "user", DirectorDecision)


def test_b10_a_valid_answer_comes_back_validated() -> None:
    decision = ask(FakeOllama([GOOD]))

    assert decision.style == "hype"
    assert decision.constraints.include_tags == ("car",)


def test_b10_ollama_is_asked_for_json_and_to_unload_afterwards() -> None:
    ollama = FakeOllama([GOOD])

    ask(ollama)

    body = ollama.bodies[0]
    assert ollama.paths == ["/api/chat"]
    assert body["model"] == DIRECTOR_MODEL == "qwen3:4b"
    assert body["format"] == "json"
    assert body["keep_alive"] == 0
    assert body["stream"] is False
    assert [message["role"] for message in body["messages"]] == ["system", "user"]


def test_b10_one_retry_on_invalid_json() -> None:
    ollama = FakeOllama(["not json at all", GOOD])

    assert ask(ollama).style == "hype"
    assert len(ollama.bodies) == 2
    assert "not valid" in ollama.bodies[1]["messages"][-1]["content"]


def test_b10_one_retry_on_json_outside_the_schema() -> None:
    ollama = FakeOllama(['{"style":"disco"}', GOOD])

    assert ask(ollama).style == "hype"


def test_b10_two_bad_answers_are_invalid_output_and_there_is_no_third_try() -> None:
    ollama = FakeOllama(["nope", '{"style":"disco"}', GOOD])

    with pytest.raises(LlmInvalidOutputError):
        ask(ollama)

    assert len(ollama.bodies) == 2


@pytest.mark.parametrize(
    "failure",
    [httpx.ConnectError("refused"), httpx.ReadTimeout("slow"), 404, 500],
)
def test_b10_no_answer_is_unavailable_and_is_not_retried(failure: Exception | int) -> None:
    ollama = FakeOllama([failure, GOOD])

    with pytest.raises(LlmUnavailableError):
        ask(ollama)

    assert len(ollama.bodies) == 1


def test_b10_an_unreadable_reply_from_ollama_is_invalid_output() -> None:
    def garbage(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>")

    http = httpx.Client(base_url="http://ollama", transport=httpx.MockTransport(garbage))

    with pytest.raises(LlmInvalidOutputError):
        OllamaLlmClient(http).complete_json("system", "user", DirectorDecision)


def test_b10_a_closed_port_is_unavailable() -> None:
    client = OllamaLlmClient.create("http://127.0.0.1:9")

    with pytest.raises(LlmUnavailableError):
        client.complete_json("system", "user", DirectorDecision)
