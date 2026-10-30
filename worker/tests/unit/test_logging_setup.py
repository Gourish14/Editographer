"""Tests for worker logging. Spec: specs/11-coding-standards.md#6-logging-all-three-apps [T-108]"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
import structlog

from app.logging_setup import configure_logging


@pytest.fixture
def logs_dir(tmp_path: Path) -> Iterator[Path]:
    configure_logging(tmp_path)
    yield tmp_path
    for handler in logging.getLogger().handlers:
        handler.close()
    logging.getLogger().handlers.clear()
    structlog.reset_defaults()
    structlog.contextvars.clear_contextvars()


def lines(logs_dir: Path) -> list[dict[str, object]]:
    text = (logs_dir / "worker.log").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines()]


def test_every_line_is_json_with_the_spec_fields(logs_dir: Path) -> None:
    structlog.contextvars.bind_contextvars(requestId="r1", jobId="j1")

    structlog.get_logger("test").info("stage.finished", message="done", durationMs=42)

    entry = lines(logs_dir)[0]
    assert entry["event"] == "stage.finished"
    assert entry["level"] == "INFO"
    assert entry["service"] == "worker"
    assert entry["requestId"] == "r1"
    assert entry["jobId"] == "j1"
    assert entry["message"] == "done"
    assert entry["durationMs"] == 42
    assert "ts" in entry


def test_http_client_chatter_stays_out_of_the_json_log(logs_dir: Path) -> None:
    logging.getLogger("httpx").info("HTTP Request: POST http://backend")

    structlog.get_logger("test").info("after")

    assert [entry["event"] for entry in lines(logs_dir)] == ["after"]
