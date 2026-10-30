"""Tests for one-at-a-time job running.

Spec: specs/02-architecture.md#job-queue-replaces-rabbitmq [T-108]
"""

from __future__ import annotations

import threading
from typing import Any

import pytest

from app.application.job_runner import CancellationToken, JobRunner, WorkerBusyError
from app.domain.errors import AnalysisError, ErrorCode
from app.ports.backend_notifier import AssetAnalysis

WAIT_SEC = 5.0


class FakeNotifier:
    def __init__(self) -> None:
        self.failed: list[tuple[str, str]] = []

    def progress(self, job_id: str, stage: str, percent: int, message: str | None = None) -> None:
        pass

    def asset_analyzed(self, analysis: AssetAnalysis) -> None:
        pass

    def preview_ready(self, job_id: str, path: str) -> None:
        pass

    def job_done(
        self, job_id: str, output_path: str | None = None, plan: dict[str, Any] | None = None
    ) -> None:
        pass

    def job_failed(self, job_id: str, error: str) -> None:
        self.failed.append((job_id, error))


@pytest.fixture
def notifier() -> FakeNotifier:
    return FakeNotifier()


@pytest.fixture
def runner(notifier: FakeNotifier) -> JobRunner:
    return JobRunner(notifier)


def test_a_finished_job_frees_the_worker(runner: JobRunner, notifier: FakeNotifier) -> None:
    ran = threading.Event()

    runner.start("j1", None, lambda _: ran.set())
    runner.wait(WAIT_SEC)

    assert ran.is_set()
    assert runner.current_job_id is None
    assert notifier.failed == []


def test_a_second_job_is_refused_while_one_runs(runner: JobRunner) -> None:
    release = threading.Event()

    def hold(_: CancellationToken) -> None:
        release.wait(WAIT_SEC)

    runner.start("j1", None, hold)
    try:
        assert runner.current_job_id == "j1"
        with pytest.raises(WorkerBusyError):
            runner.start("j2", None, lambda _: None)
    finally:
        release.set()
        runner.wait(WAIT_SEC)


def test_a_known_failure_reports_its_code(runner: JobRunner, notifier: FakeNotifier) -> None:
    def fail(_: CancellationToken) -> None:
        raise AnalysisError("bad file")

    runner.start("j1", None, fail)
    runner.wait(WAIT_SEC)

    assert notifier.failed == [("j1", ErrorCode.ANALYSIS_FAILED.value)]
    assert runner.current_job_id is None


def test_a_crash_is_reported_and_does_not_stop_the_worker(
    runner: JobRunner, notifier: FakeNotifier
) -> None:
    def crash(_: CancellationToken) -> None:
        raise ValueError("bug")

    runner.start("j1", None, crash)
    runner.wait(WAIT_SEC)
    runner.start("j2", None, lambda _: None)
    runner.wait(WAIT_SEC)

    assert notifier.failed == [("j1", ErrorCode.INTERNAL_ERROR.value)]


def test_cancel_stops_the_job_at_its_next_check(runner: JobRunner, notifier: FakeNotifier) -> None:
    started = threading.Event()
    stop = threading.Event()

    def work(token: CancellationToken) -> None:
        started.set()
        stop.wait(WAIT_SEC)
        token.raise_if_cancelled()

    runner.start("j1", None, work)
    started.wait(WAIT_SEC)

    assert runner.cancel("j1") is True
    stop.set()
    runner.wait(WAIT_SEC)

    assert notifier.failed == [("j1", ErrorCode.RENDER_CANCELLED.value)]


def test_cancelling_another_job_does_nothing(runner: JobRunner) -> None:
    assert runner.cancel("nope") is False


def test_a_token_only_raises_after_cancel() -> None:
    token = CancellationToken()

    token.raise_if_cancelled()
    token.cancel()

    with pytest.raises(Exception, match="cancelled"):
        token.raise_if_cancelled()
