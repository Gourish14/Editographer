"""Port for reports to the backend.

Spec: specs/07-api-and-data.md#internal-worker--backend-header-x-worker-token
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class AssetAnalysis:
    asset_id: str
    analysis_path: str
    file_hash: str
    camera_mode: str | None
    log_profile: str | None
    duration_sec: float | None
    width: int | None
    height: int | None
    fps: float | None


class BackendNotifier(Protocol):
    def progress(
        self, job_id: str, stage: str, percent: int, message: str | None = None
    ) -> None: ...

    def asset_analyzed(self, analysis: AssetAnalysis) -> None: ...

    def preview_ready(self, job_id: str, path: str) -> None: ...

    def job_done(
        self, job_id: str, output_path: str | None = None, plan: dict[str, Any] | None = None
    ) -> None: ...

    def job_failed(self, job_id: str, error: str) -> None: ...
