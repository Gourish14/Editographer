"""Proves that a 16 GB .OSV goes through the tus upload, across a client kill and a backend restart.

Spec: specs/02-architecture.md#communication, specs/07-api-and-data.md [T-418, FEAT-001]

Builds a 16 GiB file with a known SHA-256 in media/ (git-ignored), starts the real backend with a
small heap (and the worker, for the analysis of the fake .OSV) on private ports, and uploads the
file with tus using the frontend's chunk size. The client is killed part way and started again;
later the backend is killed and started again while the client keeps going. Every byte the client
writes to the socket is counted, so a resend shows up as sent > size. At the end the stored file's
size and SHA-256 are compared with the input, and backend heap and RSS are reported.

Everything it starts is stopped by PID with taskkill /T, also on failure. The 16 GiB files it
creates are deleted at the end (unless --keep).

Usage, from the repository root:
    python scripts\\big_upload_gate.py [--skip-build] [--size-gib 16] [--keep]
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import http.client
import json
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
from collections.abc import Callable
from ctypes import wintypes
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import phase1_gate as p1  # noqa: E402

ROOT = SCRIPTS.parent
GATE_FOLDER = Path("media") / "big_upload_gate"
INPUT_NAME = "input.osv"
BACKEND_PORT = 18280
WORKER_PORT = 18290
GIB = 1024**3
MIB = 1024**2
# Same as frontend/src/app/core/services/upload.service.ts (CHUNK_BYTES).
CHUNK_BYTES = 64 * MIB
SLICE_BYTES = MIB
BLOCK_BYTES = 8 * MIB
SEED = 418
HEAP_LIMIT = "-Xmx256m"
KILL_CLIENT_AT = 0.30
RESTART_BACKEND_AT = 0.65
SAMPLE_SEC = 2.0
RETRY_WAIT_SEC = 2.0
RETRY_LIMIT_SEC = 180.0
REQUEST_TIMEOUT_SEC = 300
PHASE_TIMEOUT_SEC = 3 * 3600
ANALYSIS_WAIT_SEC = 120
REPORT_FILE = "report.json"
TUS_VERSION = p1.TUS_VERSION
HEAP_USED = re.compile(r"used (\d+)K")


class GateError(Exception):
    """The gate could not run. Failed checks are results, not errors."""


# Pure helpers, covered by test_big_upload_gate.py


def make_blocks(size: int, seed: int = SEED, block: int = BLOCK_BYTES):
    """Yields the bytes of the input: seeded pseudo-random, so never all zeros and repeatable."""
    rng = random.Random(seed)
    remaining = size
    while remaining > 0:
        length = min(block, remaining)
        yield rng.randbytes(length)
        remaining -= length


def write_input(
    path: Path, size: int, seed: int = SEED, block: int = BLOCK_BYTES
) -> str:
    """Writes exactly `size` bytes and returns their SHA-256."""
    digest = hashlib.sha256()
    with path.open("wb") as target:
        for part in make_blocks(size, seed, block):
            digest.update(part)
            target.write(part)
    return digest.hexdigest()


def sha256_file(path: Path, block: int = 16 * MIB) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while part := source.read(block):
            digest.update(part)
    return digest.hexdigest()


def parse_heap_used_mb(output: str) -> float | None:
    """Reads 'used 12345K' out of jcmd GC.heap_info."""
    found = HEAP_USED.search(output)
    return int(found.group(1)) / 1024 if found else None


def resent_bytes(sent: int, size: int) -> int:
    return max(0, sent - size)


def judge(
    size: int,
    chunk: int,
    sent: int,
    server_size: int | None,
    server_sha: str | None,
    expected_sha: str,
) -> list[str]:
    """Names every rule the upload broke. An empty list is a pass."""
    failures: list[str] = []
    if server_size != size:
        failures.append(f"stored size {server_size} is not {size}")
    if server_sha != expected_sha:
        failures.append("stored SHA-256 differs from the input")
    if sent < size:
        failures.append(f"client sent {sent}, less than the file size {size}")
    if sent > size + chunk:
        failures.append(
            f"client sent {sent}: {resent_bytes(sent, size)} bytes twice, "
            f"more than one chunk ({chunk})"
        )
    return failures


@dataclass
class Peaks:
    heap_mb: float = 0.0
    heap_mb_first: float | None = None
    rss_mb: float = 0.0
    samples: int = 0
    heap_series: list[float] = field(default_factory=list)


# Windows process memory


class _Counters(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def peak_working_set_mb(pid: int) -> float | None:
    """Peak resident memory of a process, as Windows keeps it."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.OpenProcess.restype = wintypes.HANDLE
    handle = kernel.OpenProcess(0x1000 | 0x0010, False, pid)  # QUERY_LIMITED | VM_READ
    if not handle:
        handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return None
    try:
        counters = _Counters()
        counters.cb = ctypes.sizeof(counters)
        ok = psapi.GetProcessMemoryInfo(
            wintypes.HANDLE(handle), ctypes.byref(counters), counters.cb
        )
        return counters.PeakWorkingSetSize / MIB if ok else None
    finally:
        kernel.CloseHandle(wintypes.HANDLE(handle))


def heap_used_mb(pid: int) -> float | None:
    try:
        finished = subprocess.run(
            ["jcmd", str(pid), "GC.heap_info"],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_heap_used_mb(finished.stdout)


class MemorySampler:
    """Samples the heap through jcmd and RSS through Windows while the backend runs."""

    def __init__(self, pid_of: Callable[[], int | None], peaks: Peaks) -> None:
        self._pid_of = pid_of
        self.peaks = peaks
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def __enter__(self) -> MemorySampler:
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        self._thread.join(timeout=30)

    def _run(self) -> None:
        while not self._stop.wait(SAMPLE_SEC):
            pid = self._pid_of()
            if pid is None:
                continue
            heap = heap_used_mb(pid)
            rss = peak_working_set_mb(pid)
            if heap is not None:
                self.peaks.heap_mb = max(self.peaks.heap_mb, heap)
                if self.peaks.heap_mb_first is None:
                    self.peaks.heap_mb_first = heap
                self.peaks.heap_series.append(round(heap, 1))
            if rss is not None:
                self.peaks.rss_mb = max(self.peaks.rss_mb, rss)
            self.peaks.samples += 1


# The tus client. It runs in its own process so it can be killed.


class _Retry(Exception):
    pass


def _head_offset(host: str, port: int, path: str) -> int:
    connection = http.client.HTTPConnection(host, port, timeout=REQUEST_TIMEOUT_SEC)
    try:
        connection.request("HEAD", path, headers={"Tus-Resumable": TUS_VERSION})
        response = connection.getresponse()
        response.read()
        if response.status not in (200, 204):
            raise _Retry(f"HEAD answered {response.status}")
        return int(response.getheader("Upload-Offset", "-1"))
    finally:
        connection.close()


def _patch_chunk(
    host: str,
    port: int,
    path: str,
    source: Any,
    offset: int,
    length: int,
    on_sent: Callable[[int], None],
) -> int:
    """Sends one chunk in 1 MiB slices, counting each slice before it hits the socket."""
    connection = http.client.HTTPConnection(host, port, timeout=REQUEST_TIMEOUT_SEC)
    try:
        connection.putrequest("PATCH", path)
        connection.putheader("Tus-Resumable", TUS_VERSION)
        connection.putheader("Upload-Offset", str(offset))
        connection.putheader("Content-Type", "application/offset+octet-stream")
        connection.putheader("Content-Length", str(length))
        connection.endheaders()
        source.seek(offset)
        remaining = length
        while remaining > 0:
            part = source.read(min(SLICE_BYTES, remaining))
            on_sent(len(part))
            connection.send(part)
            remaining -= len(part)
        response = connection.getresponse()
        response.read()
        if response.status not in (200, 204):
            raise _Retry(f"PATCH answered {response.status}")
        return int(response.getheader("Upload-Offset", "-1"))
    finally:
        connection.close()


def run_client(url: str, file: Path, progress: Path, chunk: int = CHUNK_BYTES) -> None:
    """Resumes from the server's offset and retries through outages. Progress = bytes sent."""
    parsed = urllib.parse.urlparse(url)
    host, port, path = parsed.hostname or "127.0.0.1", parsed.port or 80, parsed.path
    size = file.stat().st_size
    sent = int(progress.read_text()) if progress.exists() else 0

    def on_sent(count: int) -> None:
        nonlocal sent
        sent += count
        progress.write_text(str(sent))

    failing_since: float | None = None
    with file.open("rb") as source:
        while True:
            try:
                offset = _head_offset(host, port, path)
                while offset < size:
                    offset = _patch_chunk(
                        host,
                        port,
                        path,
                        source,
                        offset,
                        min(chunk, size - offset),
                        on_sent,
                    )
                    failing_since = None
                return
            except (OSError, http.client.HTTPException, _Retry) as problem:
                failing_since = failing_since or time.monotonic()
                if time.monotonic() - failing_since > RETRY_LIMIT_SEC:
                    raise
                print(f"retry after: {problem!r}", flush=True)
                time.sleep(RETRY_WAIT_SEC)


# The gate


class Backend(p1.Services):
    def pid(self) -> int | None:
        return self._started[-1][1].pid if self._started else None

    def alive(self) -> bool:
        return bool(self._started) and self._started[-1][1].poll() is None


def real_java() -> str:
    """The JDK's own java.exe: the shim on PATH starts the real one as a child with another PID."""
    jcmd = shutil.which("jcmd")
    candidate = Path(jcmd).with_name("java.exe") if jcmd else None
    return str(candidate) if candidate and candidate.exists() else "java"


def start_backend(backend: Backend, env: dict[str, str], name: str) -> None:
    jar = ROOT / "backend" / "target" / "editographer.jar"
    backend.start(name, [real_java(), HEAP_LIMIT, "-jar", str(jar)], ROOT, env)
    url = f"http://127.0.0.1:{BACKEND_PORT}/api/styles"
    deadline = time.monotonic() + p1.START_TIMEOUT_SEC
    while time.monotonic() < deadline:
        backend.require_running()
        if p1._answers(url):
            return
        time.sleep(1)
    raise GateError("The backend did not start in time")


def start_client(
    url: str, file: Path, progress: Path, log: Path
) -> subprocess.Popen[bytes]:
    with log.open("ab") as output:
        return subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--client",
                url,
                str(file),
                str(progress),
            ],
            stdout=output,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )


def kill_tree(process: subprocess.Popen[bytes]) -> None:
    subprocess.run(
        ["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False
    )
    process.wait(timeout=30)


def read_sent(progress: Path) -> int:
    try:
        return int(progress.read_text() or 0)
    except (OSError, ValueError):
        return 0


def wait_until(
    condition: Callable[[], bool], client: subprocess.Popen[bytes] | None, label: str
) -> None:
    deadline = time.monotonic() + PHASE_TIMEOUT_SEC
    while time.monotonic() < deadline:
        if condition():
            return
        if client is not None and client.poll() is not None and not condition():
            raise GateError(
                f"The client ended early ({client.returncode}) while waiting: {label}"
            )
        time.sleep(0.5)
    raise GateError(f"Timed out waiting: {label}")


def server_offset(location: str) -> int:
    parsed = urllib.parse.urlparse(location)
    return _head_offset(parsed.hostname or "127.0.0.1", parsed.port or 80, parsed.path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--size-gib", type=float, default=16.0)
    parser.add_argument(
        "--keep", action="store_true", help="keep the big files afterwards"
    )
    parser.add_argument("--client", nargs=3, metavar=("URL", "FILE", "PROGRESS"))
    args = parser.parse_args(argv)
    if args.client:
        run_client(args.client[0], Path(args.client[1]), Path(args.client[2]))
        return 0

    folder = ROOT / GATE_FOLDER
    run_folder = folder / "run"
    input_file = folder / INPUT_NAME
    progress = folder / "progress.txt"
    if p1.port_in_use(BACKEND_PORT) or p1.port_in_use(WORKER_PORT):
        print("A gate port is taken, stopping.")
        return 2
    shutil.rmtree(run_folder, ignore_errors=True)
    for sub in ("media", "data", "logs"):
        (run_folder / sub).mkdir(parents=True)
    progress.write_text("0")
    size = int(args.size_gib * GIB)
    report: dict[str, Any] = {
        "sizeBytes": size,
        "chunkBytes": CHUNK_BYTES,
        "heapLimit": HEAP_LIMIT,
    }
    peaks = Peaks()
    backend = Backend(run_folder / "logs")
    worker = p1.Services(run_folder / "logs")
    started_all = time.monotonic()
    failures: list[str] = []
    try:
        started = time.monotonic()
        print(f"Writing {size} bytes to {input_file}", flush=True)
        expected_sha = write_input(input_file, size)
        report["inputSha256"] = expected_sha
        report["buildInputSeconds"] = round(time.monotonic() - started, 1)
        print(f"Input ready, SHA-256 {expected_sha}", flush=True)

        tools = p1.tool_environment()
        env = p1.service_environment(
            tools, run_folder.relative_to(ROOT), BACKEND_PORT, WORKER_PORT
        )
        if not args.skip_build:
            p1.build_backend(env)
        python = next(
            (
                c
                for c in (
                    ROOT / "worker" / ".venv",
                    ROOT.parents[2] / "worker" / ".venv",
                )
                if (c / "Scripts" / "python.exe").exists()
            ),
            None,
        )
        if python is not None:
            python = python / "Scripts" / "python.exe"
            worker.start(
                "worker",
                [str(python), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                 "--port", str(WORKER_PORT)],
                ROOT / "worker",
                env,
            )  # fmt: skip
        else:
            print("No worker venv found, the analysis check is skipped.")
        start_backend(backend, env, "backend")
        api = p1.Api(BACKEND_PORT)
        project_id = api.post("/api/projects", {"name": "Big upload gate"})["id"]

        created = urllib_create(
            size, project_id, input_file.name.replace("input", "DJI_big")
        )
        location = created
        report["location"] = location
        client_log = run_folder / "logs" / "client.log"

        with MemorySampler(backend.pid, peaks):
            upload_started = time.monotonic()
            # Part 1: kill the client.
            client = start_client(location, input_file, progress, client_log)
            wait_until(
                lambda: read_sent(progress) >= size * KILL_CLIENT_AT,
                client,
                "30 percent",
            )
            kill_tree(client)
            sent_at_kill = read_sent(progress)
            offset_after_kill = server_offset(location)
            report["clientKill"] = {
                "sentBytes": sent_at_kill,
                "serverOffset": offset_after_kill,
            }
            print(
                f"Client killed after {sent_at_kill} sent; server holds {offset_after_kill}",
                flush=True,
            )

            # Part 2: restart the backend while a fresh client runs.
            client = start_client(location, input_file, progress, client_log)
            wait_until(
                lambda: read_sent(progress) >= size * RESTART_BACKEND_AT,
                client,
                "65 percent",
            )
            sent_before_restart = read_sent(progress)
            backend.stop_all()
            time.sleep(3)
            start_backend(backend, env, "backend2")
            report["backendRestart"] = {"sentBytes": sent_before_restart}
            print(f"Backend restarted after {sent_before_restart} sent", flush=True)
            wait_until(lambda: client.poll() is not None, None, "the client to finish")
            if client.returncode != 0:
                raise GateError(
                    f"The client failed with {client.returncode}, see {client_log}"
                )
            upload_seconds = time.monotonic() - upload_started
            # Let the sampler see the end of the upload before it stops.
            time.sleep(SAMPLE_SEC * 2)

        sent = read_sent(progress)
        report["uploadSeconds"] = round(upload_seconds, 1)
        report["sentBytes"] = sent
        report["resentBytes"] = resent_bytes(sent, size)
        report["mbPerSecond"] = round(size / MIB / upload_seconds, 1)
        print(f"Upload finished: sent {sent}, {report['mbPerSecond']} MB/s", flush=True)

        stored = find_stored(run_folder / "media")
        server_size = stored.stat().st_size if stored else None
        started = time.monotonic()
        server_sha = sha256_file(stored) if stored else None
        report["storedFile"] = str(stored)
        report["storedSize"] = server_size
        report["storedSha256"] = server_sha
        report["hashSeconds"] = round(time.monotonic() - started, 1)
        failures = judge(size, CHUNK_BYTES, sent, server_size, server_sha, expected_sha)

        report["analysis"] = check_analysis(api, project_id)
        if report["analysis"]["status"] not in ("FAILED", "PENDING", "RUNNING", "DONE"):
            failures.append("analysis status is unknown")
        report["asset"] = report["analysis"].get("asset")
    except p1.GateError as problem:
        failures.append(str(problem))
    finally:
        backend.stop_all()
        worker.stop_all()
        report["peakHeapMb"] = round(peaks.heap_mb, 1)
        report["firstHeapMb"] = peaks.heap_mb_first
        report["peakRssMb"] = round(peaks.rss_mb, 1)
        report["memorySamples"] = peaks.samples
        report["heapSeries"] = peaks.heap_series[::10]
        report["totalSeconds"] = round(time.monotonic() - started_all, 1)
        report["failures"] = failures
        report["passed"] = not failures
        (folder / REPORT_FILE).write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        if not args.keep:
            input_file.unlink(missing_ok=True)
            shutil.rmtree(run_folder / "media", ignore_errors=True)
    print(json.dumps({k: v for k, v in report.items() if k != "heapSeries"}, indent=2))
    print("PASS" if not failures else "FAIL: " + "; ".join(failures))
    return 0 if not failures else 1


def urllib_create(size: int, project_id: str, filename: str) -> str:
    connection = http.client.HTTPConnection("127.0.0.1", BACKEND_PORT, timeout=60)
    try:
        connection.request(
            "POST",
            "/api/uploads",
            headers={
                "Tus-Resumable": TUS_VERSION,
                "Upload-Length": str(size),
                "Upload-Metadata": p1.tus_metadata(project_id, filename),
            },
        )
        response = connection.getresponse()
        response.read()
        if response.status != 201:
            raise GateError(f"Creating the upload answered {response.status}")
        location = response.getheader("Location") or ""
    finally:
        connection.close()
    return (
        location
        if location.startswith("http")
        else f"http://127.0.0.1:{BACKEND_PORT}{location}"
    )


def find_stored(media: Path) -> Path | None:
    found = [p for p in media.rglob("*.osv") if ".tus" not in p.parts]
    found += [
        p for p in media.rglob("*.OSV") if ".tus" not in p.parts and p not in found
    ]
    return found[0] if found else None


def check_analysis(api: p1.Api, project_id: str) -> dict[str, Any]:
    """The fake .OSV is expected to fail to analyse, cleanly. Reports what the API says."""
    deadline = time.monotonic() + ANALYSIS_WAIT_SEC
    asset: dict[str, Any] = {}
    while time.monotonic() < deadline:
        assets = api.get(f"/api/projects/{project_id}/assets")
        asset = assets[0] if assets else {}
        if asset.get("analysisStatus") in ("FAILED", "DONE"):
            break
        time.sleep(3)
    return {"status": asset.get("analysisStatus", "NONE"), "asset": asset}


if __name__ == "__main__":
    sys.exit(main())
