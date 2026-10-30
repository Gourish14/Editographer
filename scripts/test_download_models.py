"""Tests for the model downloader. Spec: specs/09-local-setup.md#setupbat-run-once [T-102]

Run with: python -m unittest discover -s scripts -p "test_*.py"
"""

from __future__ import annotations

import hashlib
import http.server
import tempfile
import threading
import unittest
from pathlib import Path

import download_models
from download_models import DownloadError, ModelSpec, download

PAYLOAD = bytes(range(256)) * 5000
GOOD_SHA = hashlib.sha256(PAYLOAD).hexdigest()


class _Handler(http.server.BaseHTTPRequestHandler):
    """Serves PAYLOAD, honoring Range unless the server is told to ignore it."""

    def do_GET(self) -> None:  # noqa: N802 - name required by BaseHTTPRequestHandler
        server = self.server
        server.requests.append(self.headers.get("Range"))  # type: ignore[attr-defined]
        range_header = self.headers.get("Range")
        if range_header and server.honor_range:  # type: ignore[attr-defined]
            start = int(range_header.removeprefix("bytes=").removesuffix("-"))
            body = PAYLOAD[start:]
            self.send_response(206)
        else:
            body = PAYLOAD
            self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return


class DownloadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.server.requests = []  # type: ignore[attr-defined]
        self.server.honor_range = True  # type: ignore[attr-defined]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.models_dir = Path(temp.name)

    def spec(self, sha256: str = GOOD_SHA) -> ModelSpec:
        port = self.server.server_address[1]
        return ModelSpec(
            name="fake",
            phase=1,
            url=f"http://127.0.0.1:{port}/fake.bin",
            path="fake/fake.bin",
            size=len(PAYLOAD),
            sha256=sha256,
        )

    def test_downloads_and_verifies(self) -> None:
        self.assertEqual(download(self.spec(), self.models_dir, wait_sec=0), "downloaded")
        self.assertEqual((self.models_dir / "fake/fake.bin").read_bytes(), PAYLOAD)
        self.assertFalse((self.models_dir / "fake/fake.bin.part").exists())

    def test_second_run_skips_verified_file(self) -> None:
        download(self.spec(), self.models_dir, wait_sec=0)
        self.server.requests.clear()  # type: ignore[attr-defined]
        self.assertEqual(download(self.spec(), self.models_dir, wait_sec=0), "present")
        self.assertEqual(self.server.requests, [])  # type: ignore[attr-defined]

    def test_resumes_from_partial_file(self) -> None:
        part = self.models_dir / "fake/fake.bin.part"
        part.parent.mkdir(parents=True)
        part.write_bytes(PAYLOAD[:1000])
        self.assertEqual(download(self.spec(), self.models_dir, wait_sec=0), "downloaded")
        self.assertEqual(self.server.requests, ["bytes=1000-"])  # type: ignore[attr-defined]
        self.assertEqual((self.models_dir / "fake/fake.bin").read_bytes(), PAYLOAD)

    def test_restarts_when_server_ignores_range(self) -> None:
        self.server.honor_range = False  # type: ignore[attr-defined]
        part = self.models_dir / "fake/fake.bin.part"
        part.parent.mkdir(parents=True)
        part.write_bytes(b"stale bytes")
        self.assertEqual(download(self.spec(), self.models_dir, wait_sec=0), "downloaded")
        self.assertEqual((self.models_dir / "fake/fake.bin").read_bytes(), PAYLOAD)

    def test_checksum_mismatch_fails_and_leaves_nothing_behind(self) -> None:
        with self.assertRaises(DownloadError):
            download(self.spec(sha256="0" * 64), self.models_dir, wait_sec=0)
        self.assertFalse((self.models_dir / "fake/fake.bin").exists())
        self.assertFalse((self.models_dir / "fake/fake.bin.part").exists())

    def test_redownloads_corrupted_target(self) -> None:
        target = self.models_dir / "fake/fake.bin"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"corrupt")
        self.assertEqual(download(self.spec(), self.models_dir, wait_sec=0), "downloaded")
        self.assertEqual(target.read_bytes(), PAYLOAD)


class ManifestTests(unittest.TestCase):
    def test_every_manifest_entry_is_complete(self) -> None:
        specs = download_models.load_manifest(download_models.MANIFEST)
        self.assertTrue(specs)
        for spec in specs:
            self.assertRegex(spec.sha256, r"^[0-9a-f]{64}$", spec.name)
            self.assertGreater(spec.size, 0, spec.name)
            self.assertTrue(spec.url.startswith("https://"), spec.name)


if __name__ == "__main__":
    unittest.main()
