"""Tests for reports to the backend.

Spec: specs/07-api-and-data.md#internal-worker--backend-header-x-worker-token [T-108]
"""

from __future__ import annotations

import json

import httpx

from app.adapters.http_backend_notifier import HttpBackendNotifier
from app.ports.backend_notifier import AssetAnalysis


class Recorder:
    def __init__(self, status: int = 204) -> None:
        self.requests: list[httpx.Request] = []
        self.status = status

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status)

    def notifier(self) -> HttpBackendNotifier:
        client = httpx.Client(base_url="http://backend", transport=httpx.MockTransport(self))
        return HttpBackendNotifier(client)

    def last_json(self) -> dict[str, object]:
        body: dict[str, object] = json.loads(self.requests[-1].content)
        return body


def test_progress_uses_the_spec_fields() -> None:
    recorder = Recorder()

    recorder.notifier().progress("j1", "COMPOSING", 40, "segment 3")

    assert recorder.requests[0].url.path == "/internal/progress"
    assert recorder.last_json() == {
        "jobId": "j1",
        "stage": "COMPOSING",
        "percent": 40,
        "message": "segment 3",
    }


def test_asset_analyzed_uses_camel_case() -> None:
    recorder = Recorder()

    recorder.notifier().asset_analyzed(
        AssetAnalysis("a1", "cache/h/analysis.json", "h", "FLAT", None, 12.5, 3840, 2160, 29.97)
    )

    body = recorder.last_json()
    assert body["assetId"] == "a1"
    assert body["analysisPath"] == "cache/h/analysis.json"
    assert body["fileHash"] == "h"
    assert body["durationSec"] == 12.5


def test_preview_ready() -> None:
    recorder = Recorder()

    recorder.notifier().preview_ready("j1", "renders/r/preview.mp4")

    assert recorder.requests[0].url.path == "/internal/preview-ready"
    assert recorder.last_json() == {"jobId": "j1", "path": "renders/r/preview.mp4"}


def test_a_finished_job_reports_output_and_plan() -> None:
    recorder = Recorder()

    recorder.notifier().job_done("j1", "renders/r/final.mp4", {"version": 1})

    assert recorder.last_json() == {
        "jobId": "j1",
        "status": "DONE",
        "outputPath": "renders/r/final.mp4",
        "plan": {"version": 1},
    }


def test_a_failed_job_reports_its_error() -> None:
    recorder = Recorder()

    recorder.notifier().job_failed("j1", "RENDER_FAILED")

    assert recorder.last_json() == {"jobId": "j1", "status": "FAILED", "error": "RENDER_FAILED"}


def test_a_lost_report_does_not_raise() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("backend down", request=request)

    client = httpx.Client(base_url="http://backend", transport=httpx.MockTransport(refuse))

    HttpBackendNotifier(client).job_failed("j1", "RENDER_FAILED")


def test_an_error_status_does_not_raise() -> None:
    Recorder(status=500).notifier().job_failed("j1", "RENDER_FAILED")
