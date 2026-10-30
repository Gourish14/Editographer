"""Reports to the backend over HTTP.

Spec: specs/07-api-and-data.md#internal-worker--backend-header-x-worker-token
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from app.ports.backend_notifier import AssetAnalysis

log = structlog.get_logger()
TIMEOUT_SEC = 10.0


class HttpBackendNotifier:
    """A lost report is logged, not raised: the job's outcome must not depend on it."""

    def __init__(self, client: httpx.Client) -> None:
        self._client = client

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
        )

    def preview_ready(self, job_id: str, path: str) -> None:
        self._post("/internal/preview-ready", {"jobId": job_id, "path": path})

    def job_done(
        self, job_id: str, output_path: str | None = None, plan: dict[str, Any] | None = None
    ) -> None:
        self._post(
            "/internal/complete",
            {"jobId": job_id, "status": "DONE", "outputPath": output_path, "plan": plan},
        )

    def job_failed(self, job_id: str, error: str) -> None:
        self._post("/internal/complete", {"jobId": job_id, "status": "FAILED", "error": error})

    def _post(self, path: str, body: dict[str, Any]) -> None:
        try:
            self._client.post(path, json=body).raise_for_status()
        except httpx.HTTPError as error:
            log.error("backend.report_failed", path=path, message=str(error))
