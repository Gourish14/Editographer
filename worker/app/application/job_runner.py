"""Runs one job at a time. Spec: specs/02-architecture.md#job-queue-replaces-rabbitmq"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass

import structlog

from app.domain.errors import ErrorCode, JobCancelledError, WorkerError
from app.ports.backend_notifier import BackendNotifier

log = structlog.get_logger()


class CancellationToken:
    """Checked by long-running work between stages and segments."""

    def __init__(self) -> None:
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    def raise_if_cancelled(self) -> None:
        if self._cancelled.is_set():
            raise JobCancelledError


JobWork = Callable[[CancellationToken], None]


class WorkerBusyError(Exception):
    """A job is already running."""


@dataclass(frozen=True)
class _RunningJob:
    job_id: str
    token: CancellationToken


class JobRunner:
    """Accepts a job only while idle and reports how it ended to the backend."""

    def __init__(self, notifier: BackendNotifier) -> None:
        self._notifier = notifier
        self._lock = threading.Lock()
        self._current: _RunningJob | None = None
        self._thread: threading.Thread | None = None

    @property
    def current_job_id(self) -> str | None:
        with self._lock:
            return self._current.job_id if self._current else None

    def start(self, job_id: str, request_id: str | None, work: JobWork) -> None:
        """Starts the work on its own thread. Raises WorkerBusyError when a job is running."""
        token = CancellationToken()
        with self._lock:
            if self._current is not None:
                raise WorkerBusyError
            self._current = _RunningJob(job_id, token)
            self._thread = threading.Thread(
                target=self._run, args=(job_id, request_id, work, token), daemon=True
            )
            self._thread.start()

    def cancel(self, job_id: str) -> bool:
        """Asks the job to stop at its next check. False when that job is not running."""
        with self._lock:
            if self._current is None or self._current.job_id != job_id:
                return False
            self._current.token.cancel()
            return True

    def wait(self, timeout_sec: float) -> None:
        """Waits for the running job. Used at shutdown and in tests."""
        thread = self._thread
        if thread is not None:
            thread.join(timeout_sec)

    def _run(
        self, job_id: str, request_id: str | None, work: JobWork, token: CancellationToken
    ) -> None:
        structlog.contextvars.bind_contextvars(jobId=job_id, requestId=request_id)
        log.info("job.started")
        try:
            work(token)
            log.info("job.finished")
        except WorkerError as error:
            log.warning("job.failed", errorCode=error.code.value, message=str(error))
            self._report_failure(job_id, error.code)
        except Exception:  # noqa: BLE001 - a job must never take the worker down
            log.exception("job.crashed", errorCode=ErrorCode.INTERNAL_ERROR.value)
            self._report_failure(job_id, ErrorCode.INTERNAL_ERROR)
        finally:
            with self._lock:
                self._current = None
            structlog.contextvars.clear_contextvars()

    def _report_failure(self, job_id: str, code: ErrorCode) -> None:
        self._notifier.job_failed(job_id, code.value)
