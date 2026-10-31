"""Real-socket check that a failing /internal/complete is retried until it lands.

Spec: specs/07-api-and-data.md#job-flow [T-407, BUG-008]
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from app.adapters.http_backend_notifier import HttpBackendNotifier


class _Flaky(BaseHTTPRequestHandler):
    hits: list[dict[str, Any]] = []
    fail_first = 2

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        length = int(self.headers["Content-Length"])
        type(self).hits.append(json.loads(self.rfile.read(length)))
        status = 500 if len(type(self).hits) <= type(self).fail_first else 204
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *_: object) -> None:
        return


def test_bug008_complete_fails_twice_then_lands_over_real_http() -> None:
    _Flaky.hits = []
    server = HTTPServer(("127.0.0.1", 0), _Flaky)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        notifier = HttpBackendNotifier.create(f"http://127.0.0.1:{server.server_port}", "tok")
        notifier._sleep = lambda _: None  # noqa: SLF001 - keep the test fast
        notifier.job_done("j1", "renders/r/final.mp4")
    finally:
        server.shutdown()
    assert len(_Flaky.hits) == 3
    assert all(hit["jobId"] == "j1" and hit["status"] == "DONE" for hit in _Flaky.hits)
