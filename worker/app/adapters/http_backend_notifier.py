"""Reports to the backend over HTTP.

Spec: specs/07-api-and-data.md#internal-worker--backend-header-x-worker-token
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx
import structlog

from app.ports.backend_notifier import AssetAnalysis

log = structlog.get_logger()
TIMEOUT_SEC = 10.0
MAX_ATTEMPTS = 6
BACKOFF_BASE_SEC = 1.0
BACKOFF_MAX_SEC = 10.0


class HttpBackendNotifier:
    """A lost report is logged, not raised: the job's outcome must not depend on it.

    Reports that decide a job's fate (done, failed, asset analyzed) are retried with
    exponential backoff on connection errors and 5xx, at most MAX_ATTEMPTS times (about 25 s),
    so the job runner is never blocked for long. Progress and preview stay best-effort.
    """

    def __init__(
        self,
        client: httpx.Client,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = MAX_ATTEMPTS,
    ) -> None:
        self._client = client
        self._sleep = sleep
        self._max_attempts = max_attempts

    @classmethod
    def create(cls, backend_url: str, token: str) -> HttpBackendNotifier:
        return cls(
            httpx.Client(
                base_url=backend_url,
                headers={"X-Worker-Token": token},
                timeout=TIMEOUT_SEC,
            )
        )

    def progress(self, job_id: str, stage: str, percent: int, message: str | None = None) -> None:
        self._post(
            "/internal/progress",
            {"jobId": job_id, "stage": stage, "percent": percent, "message": message},
        )

    def asset_analyzed(self, analysis: AssetAnalysis) -> None:
        self._post(
            "/internal/asset-analyzed",
            {
                "assetId": analysis.asset_id,
                "analysisPath": analysis.analysis_path,
                "fileHash": analysis.file_hash,
                "cameraMode": analysis.camera_mode,
                "logProfile": analysis.log_profile,
                "durationSec": analysis.duration_sec,
                "width": analysis.width,
                "height": analysis.height,
                "fps": analysis.fps,
            },
            retry=True,
        )

    def preview_ready(self, job_id: str, path: str) -> None:
        self._post("/internal/preview-ready", {"jobId": job_id, "path": path})

    def job_done(
        self, job_id: str, output_path: str | None = None, plan: dict[str, Any] | None = None
    ) -> None:
        self._post(
            "/internal/complete",
            {"jobId": job_id, "status": "DONE", "outputPath": output_path, "plan": plan},
            retry=True,
        )

    def job_failed(self, job_id: str, error: str) -> None:
        self._post(
            "/internal/complete",
            {"jobId": job_id, "status": "FAILED", "error": error},
            retry=True,
        )

    def _post(self, path: str, body: dict[str, Any], retry: bool = False) -> None:
        attempts = self._max_attempts if retry else 1
        for attempt in range(1, attempts + 1):
            try:
                self._client.post(path, json=body).raise_for_status()
                return
            except httpx.HTTPStatusError as error:
                transient = error.response.status_code >= 500
                self._lost(path, attempt, attempts, error, transient)
                if not transient:
                    return
            except httpx.HTTPError as error:
                self._lost(path, attempt, attempts, error, True)
            if attempt < attempts:
                self._sleep(min(BACKOFF_BASE_SEC * 2 ** (attempt - 1), BACKOFF_MAX_SEC))

    @staticmethod
    def _lost(
        path: str, attempt: int, attempts: int, error: httpx.HTTPError, transient: bool
    ) -> None:
        log.error(
            "backend.report_failed",
            path=path,
            attempt=attempt,
            attempts=attempts,
            willRetry=transient and attempt < attempts,
            message=str(error),
        )
