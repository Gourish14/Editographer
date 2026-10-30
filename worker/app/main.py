"""Composition root: builds adapters and hands them to the app.

Spec: specs/11-coding-standards.md#4
"""

from __future__ import annotations

from fastapi import FastAPI

from app.adapters.http_backend_notifier import HttpBackendNotifier
from app.adapters.nvml_gpu_guard import NvmlGpuGuard
from app.api.routes import create_api
from app.application.job_runner import CancellationToken, JobRunner
from app.config import Settings
from app.domain.errors import AnalysisError, RenderError
from app.domain.models import AnalyzeJob, RenderJob
from app.logging_setup import configure_logging


def _analysis_not_built(_: AnalyzeJob, __: CancellationToken) -> None:
    raise AnalysisError("Analysis arrives with T-109")


def _render_not_built(_: RenderJob, __: CancellationToken) -> None:
    raise RenderError("Rendering arrives with T-113")


def build_app() -> FastAPI:
    settings = Settings()  # type: ignore[call-arg]  # values come from config/local.env
    configure_logging(settings.resolved(settings.logs_dir))
    notifier = HttpBackendNotifier.create(settings.backend_url, settings.worker_token)
    return create_api(
        runner=JobRunner(notifier),
        gpu=NvmlGpuGuard(),
        analyze=_analysis_not_built,
        render=_render_not_built,
        token=settings.worker_token,
    )


app = build_app()
