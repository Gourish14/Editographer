"""Tests for the worker API.

Spec: specs/07-api-and-data.md#worker-api-fastapi-port-8090-localhost-only [T-108]
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, nullcontext
from typing import TypeVar

import pytest
from fastapi.testclient import TestClient

from app.api.routes import create_api
from app.application.job_runner import CancellationToken, JobRunner
from app.domain.models import AnalyzeJob, GpuStatus, RenderJob
from tests.unit.test_job_runner import FakeNotifier

T = TypeVar("T")
TOKEN = "secret"
AUTH = {"X-Worker-Token": TOKEN}
WAIT_SEC = 5.0
RTX_3050 = GpuStatus("RTX 3050", 5000, 55)
ANALYZE_BODY = {"jobId": "j1", "assetId": "a1", "path": "uploads/p/a.mp4", "type": "VIDEO"}
RENDER_BODY = {
    "jobId": "j2",
    "renderId": "r1",
    "projectId": "p1",
    "settings": {
        "ratio": "9:16",
        "quality": "4K",
        "fps": 30,
        "style": "auto",
        "mode": "fast",
        "lengthSec": None,
        "prompt": None,
        "coolMode": False,
        "seed": 7,
    },
    "assets": [
        {
            "id": "a1",
            "type": "VIDEO",
            "path": "uploads/p/a.mp4",
            "analysisPath": "cache/h/analysis.json",
            "cameraMode": "FLAT",
            "logProfile": None,
            "durationSec": 12.5,
            "width": 3840,
            "height": 2160,
            "fps": 29.97,
        }
    ],
}


class FakeGpu:
    def __init__(self, status: GpuStatus | None) -> None:
        self._status = status

    def status(self) -> GpuStatus | None:
        return self._status

    def loaded(self, load: Callable[[], T]) -> AbstractContextManager[T]:
        return nullcontext(load())


class Fixture:
    def __init__(self, gpu: GpuStatus | None = RTX_3050) -> None:
        self.analyzed: list[AnalyzeJob] = []
        self.rendered: list[RenderJob] = []
        self.release = threading.Event()
        self.release.set()
        self.runner = JobRunner(FakeNotifier())
        self.client = TestClient(
            create_api(self.runner, FakeGpu(gpu), self._analyze, self._render, TOKEN)
        )

    def _analyze(self, job: AnalyzeJob, _: CancellationToken) -> None:
        self.analyzed.append(job)
        self.release.wait(WAIT_SEC)

    def _render(self, job: RenderJob, _: CancellationToken) -> None:
        self.rendered.append(job)
        self.release.wait(WAIT_SEC)


@pytest.fixture
def api() -> Iterator[Fixture]:
    fixture = Fixture()
    yield fixture
    fixture.release.set()
    fixture.runner.wait(WAIT_SEC)


def test_health_reports_an_idle_worker_with_its_gpu(api: Fixture) -> None:
    assert api.client.get("/health").json() == {
        "busy": False,
        "currentJobId": None,
        "gpu": {"name": "RTX 3050", "vramFreeMb": 5000, "tempC": 55},
    }


def test_health_needs_no_token_and_survives_a_missing_gpu() -> None:
    assert Fixture(gpu=None).client.get("/health").json()["gpu"] is None


def test_analyze_is_accepted_and_runs(api: Fixture) -> None:
    response = api.client.post("/jobs/analyze", json=ANALYZE_BODY, headers=AUTH)
    api.runner.wait(WAIT_SEC)

    assert response.status_code == 202
    assert api.analyzed[0].asset_id == "a1"
    assert api.analyzed[0].path == "uploads/p/a.mp4"


def test_render_is_accepted_with_camel_case_settings(api: Fixture) -> None:
    response = api.client.post("/jobs/render", json=RENDER_BODY, headers=AUTH)
    api.runner.wait(WAIT_SEC)

    assert response.status_code == 202
    job = api.rendered[0]
    assert job.settings.seed == 7
    assert job.settings.cool_mode is False
    assert job.assets[0].analysis_path == "cache/h/analysis.json"
    assert job.assets[0].duration_sec == 12.5


def test_health_shows_the_running_job(api: Fixture) -> None:
    api.release.clear()

    api.client.post("/jobs/analyze", json=ANALYZE_BODY, headers=AUTH)

    health = api.client.get("/health").json()
    assert health["busy"] is True
    assert health["currentJobId"] == "j1"


def test_a_second_job_gets_409_so_the_backend_keeps_it_queued(api: Fixture) -> None:
    api.release.clear()
    api.client.post("/jobs/analyze", json=ANALYZE_BODY, headers=AUTH)

    response = api.client.post("/jobs/render", json=RENDER_BODY, headers=AUTH)

    assert response.status_code == 409
    assert response.json() == {"errorCode": "WORKER_UNAVAILABLE"}


def test_jobs_need_the_token(api: Fixture) -> None:
    for headers in ({}, {"X-Worker-Token": "wrong"}):
        response = api.client.post("/jobs/analyze", json=ANALYZE_BODY, headers=headers)
        assert response.status_code == 401
    assert api.analyzed == []


def test_cancel_reaches_the_running_job(api: Fixture) -> None:
    api.release.clear()
    api.client.post("/jobs/analyze", json=ANALYZE_BODY, headers=AUTH)

    assert api.client.post("/jobs/j1/cancel", headers=AUTH).status_code == 202


def test_cancelling_an_unknown_job_is_404(api: Fixture) -> None:
    assert api.client.post("/jobs/nope/cancel", headers=AUTH).status_code == 404


def test_a_malformed_job_is_refused(api: Fixture) -> None:
    response = api.client.post("/jobs/analyze", json={"jobId": "j1"}, headers=AUTH)

    assert response.status_code == 422
