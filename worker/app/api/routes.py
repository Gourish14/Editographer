"""HTTP routes. Spec: specs/07-api-and-data.md#worker-api-fastapi-port-8090-localhost-only"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.api.schemas import AnalyzeRequest, GpuResponse, HealthResponse, RenderRequest
from app.application.job_runner import CancellationToken, JobRunner, WorkerBusyError
from app.domain.errors import ErrorCode
from app.domain.models import AnalyzeJob, RenderJob
from app.ports.gpu_guard import GpuGuard

AnalyzeWork = Callable[[AnalyzeJob, CancellationToken], None]
RenderWork = Callable[[RenderJob, CancellationToken], None]


def create_api(
    runner: JobRunner,
    gpu: GpuGuard,
    analyze: AnalyzeWork,
    render: RenderWork,
    token: str,
) -> FastAPI:
    """Builds the app from its collaborators, which main.py creates."""
    api = FastAPI(title="Editographer worker")

    def require_token(x_worker_token: Annotated[str | None, Header()] = None) -> None:
        if x_worker_token is None or not secrets.compare_digest(x_worker_token, token):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, ErrorCode.WORKER_TOKEN_INVALID.value)

    guarded = [Depends(require_token)]

    @api.exception_handler(WorkerBusyError)
    async def worker_busy(_: Request, __: WorkerBusyError) -> JSONResponse:
        return JSONResponse(
            {"errorCode": ErrorCode.WORKER_UNAVAILABLE.value},
            status_code=status.HTTP_409_CONFLICT,
        )

    @api.get("/health", response_model=HealthResponse, response_model_by_alias=True)
    def health() -> HealthResponse:
        job_id = runner.current_job_id
        return HealthResponse(
            busy=job_id is not None, current_job_id=job_id, gpu=GpuResponse.of(gpu.status())
        )

    @api.post("/jobs/analyze", status_code=status.HTTP_202_ACCEPTED, dependencies=guarded)
    def start_analyze(
        body: AnalyzeRequest, x_request_id: Annotated[str | None, Header()] = None
    ) -> None:
        job = body.to_job()
        runner.start(job.job_id, x_request_id, lambda cancel: analyze(job, cancel))

    @api.post("/jobs/render", status_code=status.HTTP_202_ACCEPTED, dependencies=guarded)
    def start_render(
        body: RenderRequest, x_request_id: Annotated[str | None, Header()] = None
    ) -> None:
        job = body.to_job()
        runner.start(job.job_id, x_request_id, lambda cancel: render(job, cancel))

    @api.post("/jobs/{job_id}/cancel", status_code=status.HTTP_202_ACCEPTED, dependencies=guarded)
    def cancel_job(job_id: str) -> None:
        if not runner.cancel(job_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, ErrorCode.JOB_NOT_FOUND.value)

    return api
