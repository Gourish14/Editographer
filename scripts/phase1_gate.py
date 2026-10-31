"""Runs the Phase 1 gate end to end on generated media. A rehearsal, not the real gate.

Spec: specs/10-roadmap.md#phase-1--core-engine [T-118]

Builds the backend jar, starts the real worker and backend on private ports with a private media
folder and database, uploads 10 clips and a song through the tus API, waits for analysis, renders a
60 s Fast edit at 4K in all 6 ratios and checks every render. Then it renders the slowest ratio
again with shake, zoom and flash covering every segment, which the planner never does by itself.

Everything it starts is stopped by PID with taskkill /T, also on failure. It never touches anything
else: when a port is taken it stops instead.

Usage, from worker/:
    uv run python ..\\scripts\\phase1_gate.py [--skip-build] [--shared-gpu] [--ratios 16:9 1:1]

--shared-gpu: other work is using this machine, so the 15 minute limit is reported, not judged.
"""

from __future__ import annotations

import argparse
import base64
import ctypes
import json
import os
import re
import secrets
import signal
import socket
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import check_beats  # noqa: E402
import phase1_media  # noqa: E402

ROOT = SCRIPTS.parent
GATE_FOLDER = Path("media") / "phase1_gate"
RATIOS = ("16:9", "9:16", "1:1", "4:5", "4:3", "21:9")
LENGTH_SEC = 60
FPS = 30
SEED = 1118
STYLE = "velocity"
LIMIT_MINUTES = 15.0
BACKEND_PORT = 18080
WORKER_PORT = 18090
START_TIMEOUT_SEC = 180
ANALYSIS_TIMEOUT_SEC = 3600
RENDER_TIMEOUT_SEC = 3600
POLL_SEC = 3.0
SAMPLE_SEC = 5.0
UPLOAD_CHUNK_BYTES = 32 * 1024 * 1024
TUS_VERSION = "1.0.0"
PEAK_REACH_FRAMES = 3
PEAK_FACTOR = 3.0
MIN_SHARE_WITHIN_ONE_FRAME = 0.95
MIN_CUT_SCORE = 0.01
STRESS_FLASH_SEC = 0.08
STRESS_ZOOM = 0.15
STRESS_SHAKE = 1.0
REPORT_FILE = "gate_report.json"

BEATS_LINE = re.compile(r"cuts: (\d+), worst offset from the grid: ([\d.]+) ms")
FRAMES_LINE = re.compile(r"one frame is ([\d.]+) ms; frames expected (\d+), got (\d+)")
SCENE_FRAME = re.compile(r"frame:(\d+)\s+pts:\S+\s+pts_time:(\S+)")
SCENE_SCORE = re.compile(r"lavfi\.scene_score=([\d.]+)")


class GateError(Exception):
    """The gate could not run. Failed checks are results, not errors."""


@dataclass(frozen=True)
class BeatCheck:
    cuts: int
    worst_ms: float
    frame_ms: float
    frames_expected: int
    frames_actual: int
    passed: bool


@dataclass(frozen=True)
class FrameScore:
    time: float
    score: float


@dataclass
class Load:
    """How busy the machine was during a render. None when a tool could not say."""

    gpu_percent_mean: float | None = None
    gpu_percent_peak: float | None = None
    encoder_percent_mean: float | None = None
    cpu_percent_mean: float | None = None
    vram_mb_peak: float | None = None
    temp_c_peak: float | None = None


@dataclass
class RenderResult:
    label: str
    ratio: str
    status: str
    seconds: float
    error: str | None = None
    render_id: str | None = None
    beat_check: BeatCheck | None = None
    true_grid_worst_ms: float | None = None
    cuts_measured: int = 0
    worst_measured_frames: int | None = None
    share_within_one: float = 0.0
    worst_pts_drift_ms: float | None = None
    codec: str | None = None
    profile: str | None = None
    pix_fmt: str | None = None
    width: int | None = None
    height: int | None = None
    size_mb: float | None = None
    download_ok: bool | None = None
    coverage: dict[str, dict[str, int]] = field(default_factory=dict)
    load: Load = field(default_factory=Load)

    @property
    def passed(self) -> bool:
        return (
            self.status == "DONE"
            and self.beat_check is not None
            and self.beat_check.passed
            and self.share_within_one >= MIN_SHARE_WITHIN_ONE_FRAME
        )


# Pure helpers, covered by test_phase1_gate.py


def tus_metadata(project_id: str, filename: str) -> str:
    def encoded(value: str) -> str:
        return base64.b64encode(value.encode("utf-8")).decode("ascii")

    return f"projectId {encoded(project_id)},filename {encoded(filename)}"


def parse_beat_check(output: str, exit_code: int) -> BeatCheck:
    beats = BEATS_LINE.search(output)
    frames = FRAMES_LINE.search(output)
    if beats is None or frames is None:
        raise GateError(f"check_beats printed something unexpected: {output[-300:]}")
    return BeatCheck(
        cuts=int(beats.group(1)),
        worst_ms=float(beats.group(2)),
        frame_ms=float(frames.group(1)),
        frames_expected=int(frames.group(2)),
        frames_actual=int(frames.group(3)),
        passed=exit_code == 0,
    )


def parse_scene_scores(output: str) -> list[FrameScore]:
    """Scores in frame order from FFmpeg's metadata=print output."""
    scores: list[FrameScore] = []
    current_time: float | None = None
    for line in output.splitlines():
        frame = SCENE_FRAME.search(line)
        if frame is not None:
            current_time = float(frame.group(2))
            continue
        score = SCENE_SCORE.search(line)
        if score is not None and current_time is not None:
            scores.append(FrameScore(current_time, float(score.group(1))))
            current_time = None
    return scores


def planned_cut_frames(plan: dict[str, Any]) -> list[int]:
    """Frame of every cut in the file. The first segment starts the file, so it is no cut."""
    fps = plan["output"]["fps"]
    start = plan["music"]["start"]
    return [round((segment["at"] - start) * fps) for segment in plan["segments"][1:]]


def cut_offsets(scores: Sequence[FrameScore], cuts: Iterable[int]) -> list[int]:
    """How many frames each visible cut sits from its planned frame.

    Takes the frame closest to the plan that stands out from its neighbours, because a flash that
    ends after a cut, or a sudden jump inside a clip, can score higher than the cut. Cuts between
    two look-alike frames score too low to see and are left out.
    """
    offsets = []
    for cut in cuts:
        first = max(0, cut - PEAK_REACH_FRAMES)
        near = scores[first : cut + PEAK_REACH_FRAMES + 1]
        if not near:
            continue
        floor = max(MIN_CUT_SCORE, statistics.median(item.score for item in near) * PEAK_FACTOR)
        hits = [first + i - cut for i, item in enumerate(near) if item.score >= floor]
        if hits:
            offsets.append(min(hits, key=abs))
    return offsets


def share_within_one_frame(offsets: Sequence[int]) -> float:
    return sum(abs(offset) <= 1 for offset in offsets) / len(offsets) if offsets else 0.0


def worst_pts_drift(scores: Sequence[FrameScore], fps: int) -> float:
    """Seconds between where any frame is and where its index says it should be."""
    return max((abs(item.time - index / fps) for index, item in enumerate(scores)), default=0.0)


def saturated_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """The plan with shake and zoom covering all of every segment and a flash on each cut.

    A zoom that lasts the whole segment changes the frame size on every frame, the slowest thing
    the filter chain can be asked to do. This breaks the B5 caps on purpose: it measures the worst
    case and does not pass validation, so it never goes through the planner.
    """
    segments = []
    for segment in plan["segments"]:
        length = segment["duration"]
        effects = [
            {"type": "flash", "at": 0.0, "duration": min(STRESS_FLASH_SEC, length)},
            {"type": "zoomPunch", "at": 0.0, "duration": length, "strength": STRESS_ZOOM},
            {"type": "shake", "at": 0.0, "duration": length, "strength": STRESS_SHAKE},
        ]
        segments.append({**segment, "effects": effects})
    return {**plan, "segments": segments}


def effect_coverage(
    plan: dict[str, Any], sections: Sequence[dict[str, Any]]
) -> dict[str, dict[str, int]]:
    """Segments and effects per song section, to show what a render really exercised."""
    coverage: dict[str, dict[str, int]] = {}
    for segment in plan["segments"]:
        row = coverage.setdefault(_section_kind(segment["at"], sections), {"segments": 0})
        row["segments"] += 1
        for effect in segment["effects"]:
            row[effect["type"]] = row.get(effect["type"], 0) + 1
    return coverage


def _section_kind(time_sec: float, sections: Sequence[dict[str, Any]]) -> str:
    for section in sections:
        if section["start"] <= time_sec < section["end"]:
            return section["kind"].lower()
    return "unknown"


def beat_accuracy(found: Sequence[float], truth: Sequence[float]) -> dict[str, float]:
    """How the tracker's beats compare with the beats the song was built from."""
    inside = [time for time in found if truth[0] - 0.2 <= time <= truth[-1] + 0.2]
    errors = [min((time - true for true in truth), key=abs) for time in inside]
    return {
        "foundBeats": len(inside),
        "trueBeats": len(truth),
        "meanErrorMs": round(statistics.fmean(errors) * 1000, 1),
        "worstErrorMs": round(max(abs(error) for error in errors) * 1000, 1),
    }


def judge(
    results: Sequence[RenderResult], limit_minutes: float, shared_machine: bool
) -> dict[str, Any]:
    """The verdict. Stress renders inform the limit but are no part of the spec's target."""
    edits = [result for result in results if result.label == "edit"]
    slowest = max(edits, key=lambda result: result.seconds, default=None)
    within_limit = slowest is not None and slowest.seconds <= limit_minutes * 60
    beats_ok = bool(edits) and all(result.passed for result in results)
    return {
        "beatsPassed": beats_ok,
        "timePassed": within_limit,
        "timeJudged": not shared_machine,
        "slowestRatio": slowest.ratio if slowest else None,
        "slowestSeconds": round(slowest.seconds, 1) if slowest else None,
        "passed": beats_ok and (within_limit or shared_machine),
    }


def report_table(results: Sequence[RenderResult]) -> str:
    """One line per render, for the console."""
    header = (
        "| Render | Ratio | Size | Status | Time | Cuts | Worst grid ms | True grid ms | "
        "Measured frames | Frames | MB | Codec | GPU % | NVENC % | CPU % |"
    )
    rule = "|" + " --- |" * 15
    return "\n".join([header, rule, *(_table_row(result) for result in results)])


def _table_row(result: RenderResult) -> str:
    check = result.beat_check
    frames = f"{check.frames_actual}/{check.frames_expected}" if check else "-"
    cells = [
        result.label,
        result.ratio,
        f"{result.width}x{result.height}",
        result.status,
        f"{result.seconds / 60:.1f} min",
        check.cuts if check else "-",
        f"{check.worst_ms:.1f}" if check else "-",
        _number(result.true_grid_worst_ms),
        f"{result.share_within_one:.1%} of {result.cuts_measured}, worst "
        f"{result.worst_measured_frames}",
        frames,
        _number(result.size_mb),
        f"{result.codec} {result.pix_fmt}",
        _number(result.load.gpu_percent_mean),
        _number(result.load.encoder_percent_mean),
        _number(result.load.cpu_percent_mean),
    ]
    return "| " + " | ".join(str(cell) for cell in cells) + " |"


def _number(value: float | None) -> str:
    return "-" if value is None else f"{value:.1f}"


# Processes


class Services:
    """Starts processes and stops exactly those, with their children."""

    def __init__(self, logs: Path) -> None:
        self._logs = logs
        self._started: list[tuple[str, subprocess.Popen[bytes]]] = []

    def start(self, name: str, arguments: list[str], cwd: Path, env: dict[str, str]) -> None:
        with (self._logs / f"{name}.console.log").open("wb") as output:
            process = subprocess.Popen(
                arguments,
                cwd=cwd,
                env=env,
                stdout=output,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        self._started.append((name, process))
        print(f"Started {name} as PID {process.pid}", flush=True)

    def require_running(self) -> None:
        for name, process in self._started:
            if process.poll() is not None:
                raise GateError(f"{name} exited with {process.returncode}, see {self._logs}")

    def stop_all(self) -> None:
        while self._started:
            name, process = self._started.pop()
            if process.poll() is None:
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    check=False,
                )
            print(f"Stopped {name} (PID {process.pid})", flush=True)


def port_in_use(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(1)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def tool_environment() -> dict[str, str]:
    """The environment scripts\\env.bat builds, so FFmpeg is found the same way as everywhere."""
    listing = subprocess.run(
        f'cmd /c "call "{SCRIPTS / "env.bat"}" && set"',
        capture_output=True,
        text=True,
        check=True,
    )
    pairs = (line.split("=", 1) for line in listing.stdout.splitlines() if "=" in line)
    return {name: value for name, value in pairs}


def service_environment(
    tools: dict[str, str], run_folder: Path, backend_port: int, worker_port: int
) -> dict[str, str]:
    """Environment variables beat config/local.env in both apps, so nothing shared is touched."""
    return {
        **tools,
        "BACKEND_PORT": str(backend_port),
        "WORKER_HOST": "127.0.0.1",
        "WORKER_PORT": str(worker_port),
        "MEDIA_DIR": (run_folder / "media").as_posix(),
        "DATA_DIR": (run_folder / "data").as_posix(),
        "LOGS_DIR": (run_folder / "logs").as_posix(),
        "WORKER_TOKEN": secrets.token_hex(24),
    }


def build_backend(env: dict[str, str]) -> None:
    print("Building the backend jar", flush=True)
    subprocess.run(
        ["cmd", "/c", ".\\mvnw.cmd", "-B", "-ntp", "-q", "-DskipTests", "package"],
        cwd=ROOT / "backend",
        env=env,
        check=True,
    )


def start_services(services: Services, env: dict[str, str], backend_port: int) -> None:
    python = ROOT / "worker" / ".venv" / "Scripts" / "python.exe"
    services.start(
        "worker",
        [
            str(python), "-m", "uvicorn", "app.main:app",
            "--host", "127.0.0.1", "--port", env["WORKER_PORT"],
        ],
        ROOT / "worker",
        env,
    )  # fmt: skip
    jar = ROOT / "backend" / "target" / "editographer.jar"
    services.start("backend", ["java", "-jar", str(jar)], ROOT, env)
    worker_url = f"http://127.0.0.1:{env['WORKER_PORT']}/health"
    backend_url = f"http://127.0.0.1:{backend_port}/api/styles"
    deadline = time.monotonic() + START_TIMEOUT_SEC
    while time.monotonic() < deadline:
        services.require_running()
        if _answers(worker_url) and _answers(backend_url):
            return
        time.sleep(1)
    raise GateError(f"The apps did not start within {START_TIMEOUT_SEC} s")


def _answers(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.status == 200
    except OSError:
        return False


# Backend API


class Api:
    def __init__(self, port: int) -> None:
        self._base = f"http://127.0.0.1:{port}"

    def get(self, path: str) -> Any:
        with urllib.request.urlopen(self._base + path, timeout=60) as response:
            return json.load(response)

    def post(self, path: str, body: dict[str, Any]) -> Any:
        request = urllib.request.Request(
            self._base + path,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)

    def upload(self, project_id: str, path: Path) -> None:
        """A real tus upload: create, then PATCH chunks from the offset the server reports."""
        size = path.stat().st_size
        created = urllib.request.Request(
            self._base + "/api/uploads",
            headers={
                "Tus-Resumable": TUS_VERSION,
                "Upload-Length": str(size),
                "Upload-Metadata": tus_metadata(project_id, path.name),
            },
            method="POST",
        )
        with urllib.request.urlopen(created, timeout=60) as response:
            location = response.headers["Location"]
        url = location if location.startswith("http") else self._base + location
        with path.open("rb") as source:
            offset = 0
            while offset < size:
                source.seek(offset)
                chunk = source.read(UPLOAD_CHUNK_BYTES)
                patch = urllib.request.Request(
                    url,
                    data=chunk,
                    headers={
                        "Tus-Resumable": TUS_VERSION,
                        "Upload-Offset": str(offset),
                        "Content-Type": "application/offset+octet-stream",
                    },
                    method="PATCH",
                )
                with urllib.request.urlopen(patch, timeout=300) as response:
                    offset = int(response.headers["Upload-Offset"])

    def range_of_download(self, render_id: str) -> int:
        request = urllib.request.Request(
            f"{self._base}/api/renders/{render_id}/download", headers={"Range": "bytes=0-1023"}
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            response.read()
            return response.status


def wait_for_analysis(api: Api, project_id: str, expected: int, services: Services) -> None:
    deadline = time.monotonic() + ANALYSIS_TIMEOUT_SEC
    while time.monotonic() < deadline:
        services.require_running()
        assets = api.get(f"/api/projects/{project_id}/assets")
        failed = [asset["filename"] for asset in assets if asset["analysisStatus"] == "FAILED"]
        if failed:
            raise GateError(f"Analysis failed for {failed}")
        done = sum(asset["analysisStatus"] == "DONE" for asset in assets)
        if len(assets) == expected and done == expected:
            return
        time.sleep(POLL_SEC)
    raise GateError("Analysis did not finish in time")


# Load sampling


class LoadSampler:
    """Samples GPU and CPU while a render runs, because a shared machine changes the timings."""

    def __init__(self) -> None:
        self._rows: list[list[float]] = []
        self._cpu: list[float] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def __enter__(self) -> LoadSampler:
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        self._thread.join(SAMPLE_SEC * 2)

    def _run(self) -> None:
        previous = _cpu_times()
        while not self._stop.wait(SAMPLE_SEC):
            current = _cpu_times()
            if previous is not None and current is not None:
                busy, total = current[0] - previous[0], current[1] - previous[1]
                if total > 0:
                    self._cpu.append(100.0 * busy / total)
            previous = current
            row = _gpu_row()
            if row is not None:
                self._rows.append(row)

    def load(self) -> Load:
        result = Load(cpu_percent_mean=_mean(self._cpu))
        if self._rows:
            gpu, encoder, memory, temperature = zip(*self._rows, strict=True)
            result.gpu_percent_mean = _mean(gpu)
            result.gpu_percent_peak = max(gpu)
            result.encoder_percent_mean = _mean(encoder)
            result.vram_mb_peak = max(memory)
            result.temp_c_peak = max(temperature)
        return result


def _mean(values: Sequence[float]) -> float | None:
    return round(statistics.fmean(values), 1) if values else None


def _gpu_row() -> list[float] | None:
    try:
        output = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,utilization.encoder,memory.used,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout
        return [float(part) for part in output.strip().split(",")]
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _cpu_times() -> tuple[int, int] | None:
    """Busy and total CPU time so far, from GetSystemTimes. Kernel time includes idle time."""

    class FileTime(ctypes.Structure):
        _fields_ = [("low", ctypes.c_uint32), ("high", ctypes.c_uint32)]

    idle, kernel, user = FileTime(), FileTime(), FileTime()
    if not ctypes.windll.kernel32.GetSystemTimes(
        ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
    ):
        return None

    def ticks(value: FileTime) -> int:
        return (value.high << 32) | value.low

    total = ticks(kernel) + ticks(user)
    return total - ticks(idle), total


# Checks on a finished render


def run_beat_check(folder: Path, song_analysis: Path, env: dict[str, str]) -> BeatCheck:
    finished = subprocess.run(
        [sys.executable, str(SCRIPTS / "check_beats.py"), str(folder), str(song_analysis)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    return parse_beat_check(finished.stdout, finished.returncode)


def scene_scores(video: Path, env: dict[str, str]) -> list[FrameScore]:
    """A score for every frame of the file itself, independent of the plan's own arithmetic."""
    finished = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(video),
            "-map", "0:v:0",
            "-vf", "scale=320:-2:flags=fast_bilinear,select='gte(scene,0)',"
                   "metadata=print:key=lavfi.scene_score:file=-",
            "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )  # fmt: skip
    return parse_scene_scores(finished.stdout)


def probe_summary(video: Path, env: dict[str, str]) -> dict[str, Any]:
    output = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=codec_name,profile,pix_fmt,width,height",
            "-of", "json", str(video),
        ],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    ).stdout  # fmt: skip
    return json.loads(output)["streams"][0]


def inspect_render(
    result: RenderResult,
    folder: Path,
    song_analysis: Path,
    true_beats: Sequence[float],
    env: dict[str, str],
) -> None:
    """Fills in everything measured from the finished files."""
    video = folder / "final.mp4"
    plan = json.loads((folder / "plan.json").read_text(encoding="utf-8"))
    music = json.loads(song_analysis.read_text(encoding="utf-8"))["music"]
    result.beat_check = run_beat_check(folder, song_analysis, env)
    result.true_grid_worst_ms = round(check_beats.worst_offset(plan, true_beats) * 1000, 1)
    scores = scene_scores(video, env)
    offsets = cut_offsets(scores, planned_cut_frames(plan))
    result.cuts_measured = len(offsets)
    result.worst_measured_frames = max((abs(offset) for offset in offsets), default=None)
    result.share_within_one = round(share_within_one_frame(offsets), 3)
    result.worst_pts_drift_ms = round(worst_pts_drift(scores, plan["output"]["fps"]) * 1000, 2)
    stream = probe_summary(video, env)
    result.codec = stream.get("codec_name")
    result.profile = stream.get("profile")
    result.pix_fmt = stream.get("pix_fmt")
    result.width = stream.get("width")
    result.height = stream.get("height")
    result.size_mb = round(video.stat().st_size / 2**20, 1)
    result.coverage = effect_coverage(plan, music["sections"])


def render_through_api(
    api: Api, project_id: str, ratio: str, media_root: Path, on_done: Callable[[RenderResult], None]
) -> RenderResult:
    settings = {
        "ratio": ratio, "quality": "4K", "fps": FPS, "style": STYLE, "mode": "fast",
        "lengthSec": LENGTH_SEC, "seed": SEED,
    }  # fmt: skip
    started = time.monotonic()
    with LoadSampler() as sampler:
        render_id = api.post(f"/api/projects/{project_id}/renders", settings)["id"]
        status, error = _wait_for_render(api, render_id)
    result = RenderResult(
        "edit", ratio, status, time.monotonic() - started, error, render_id, load=sampler.load()
    )
    if status == "DONE":
        result.download_ok = api.range_of_download(render_id) == 206
        on_done(result)
    return result


def _wait_for_render(api: Api, render_id: str) -> tuple[str, str | None]:
    deadline = time.monotonic() + RENDER_TIMEOUT_SEC
    while time.monotonic() < deadline:
        render = api.get(f"/api/renders/{render_id}")
        if render["status"] in ("DONE", "FAILED", "CANCELLED"):
            return render["status"], render.get("error")
        time.sleep(POLL_SEC)
    return "TIMED_OUT", f"Not finished after {RENDER_TIMEOUT_SEC} s"


def render_saturated(
    source_render: Path, media_root: Path, assets: Sequence[dict[str, Any]], label: str
) -> tuple[Path, float]:
    """Runs the real render use case and adapters on the saturated plan, without the backend."""
    sys.path.insert(0, str(ROOT / "worker"))
    from app.adapters.ffmpeg_audio_finisher import FfmpegAudioFinisher
    from app.adapters.ffmpeg_compositor import FfmpegCompositor
    from app.adapters.file_cache import FileCache
    from app.application.job_runner import CancellationToken
    from app.application.render_job import RenderEdit
    from app.domain.models import AssetInput, AssetType, RenderJob, RenderSettings
    from app.domain.plan import EditPlan

    original = json.loads((source_render / "plan.json").read_text(encoding="utf-8"))
    plan = EditPlan.model_validate(saturated_plan(original))

    class SaturatedEdit(RenderEdit):
        def _plan(self, job: RenderJob) -> EditPlan:
            return plan

    class SilentNotifier:
        def __getattr__(self, _: str) -> Callable[..., None]:
            return lambda *args, **kwargs: None

    inputs = tuple(
        AssetInput(
            asset["id"], AssetType(asset["type"]), asset["path"],
            None, None, None, None, None, None, None,
        )
        for asset in assets
    )  # fmt: skip
    output = plan.output
    settings = RenderSettings(
        output.ratio, output.quality, output.fps, plan.style, output.mode, LENGTH_SEC, None,
        False, plan.seed,
    )  # fmt: skip
    job = RenderJob(label, label, label, settings, inputs)
    cache = FileCache(media_root)
    notifier: Any = SilentNotifier()
    edit = SaturatedEdit(
        media_root, cache, cache, FfmpegCompositor(), FfmpegAudioFinisher(), notifier
    )
    started = time.monotonic()
    edit.run(job, CancellationToken())
    return media_root / "renders" / label, time.monotonic() - started


def render_stress(
    slowest: RenderResult,
    media_root: Path,
    song_analysis: Path,
    true_beats: Sequence[float],
    assets: Sequence[dict[str, Any]],
    env: dict[str, str],
) -> RenderResult:
    source = media_root / "renders" / str(slowest.render_id)
    with LoadSampler() as sampler:
        folder, seconds = render_saturated(source, media_root, assets, "stress")
    result = RenderResult("stress", slowest.ratio, "DONE", seconds, load=sampler.load())
    inspect_render(result, folder, song_analysis, true_beats, env)
    return result


# The gate


def song_analysis_file(media_root: Path) -> Path:
    for candidate in sorted((media_root / "cache").glob("*/analysis.json")):
        if json.loads(candidate.read_text(encoding="utf-8")).get("music"):
            return candidate
    raise GateError("No analysis with a music map was found")


def stored_assets(assets: Sequence[dict[str, Any]], project_id: str) -> list[dict[str, Any]]:
    """Ids and media paths for the stress render. The backend stores uploads under their id."""
    return [
        {
            "id": asset["id"],
            "type": asset["type"],
            "path": f"uploads/{project_id}/{asset['id']}{Path(asset['filename']).suffix}",
        }
        for asset in assets
    ]


def run_gate(args: argparse.Namespace, run_folder: Path, tools: dict[str, str]) -> dict[str, Any]:
    source = ROOT / GATE_FOLDER / "source"
    print("Generating media (kept between runs)", flush=True)
    song = phase1_media.generate_song(source)
    clips = phase1_media.generate_clips(source)
    truth = json.loads((source / phase1_media.TRUTH_FILE).read_text(encoding="utf-8"))

    if not args.skip_build:
        build_backend(tools)
    for port in (args.backend_port, args.worker_port):
        if port_in_use(port):
            raise GateError(f"Port {port} is in use. The gate touches nothing already running.")

    relative_run = run_folder.relative_to(ROOT)
    env = service_environment(tools, relative_run, args.backend_port, args.worker_port)
    media_root = run_folder / "media"
    for folder in (media_root, run_folder / "data", run_folder / "logs"):
        folder.mkdir(parents=True, exist_ok=True)

    services = Services(run_folder / "logs")
    report: dict[str, Any] = {"rehearsal": True, "started": datetime.now().isoformat()}
    results: list[RenderResult] = []
    try:
        start_services(services, env, args.backend_port)
        api = Api(args.backend_port)
        project_id = api.post("/api/projects", {"name": "Phase 1 gate rehearsal"})["id"]

        started = time.monotonic()
        for path in [*clips, song]:
            api.upload(project_id, path)
            print(f"Uploaded {path.name}", flush=True)
        report["uploadSeconds"] = round(time.monotonic() - started, 1)

        started = time.monotonic()
        wait_for_analysis(api, project_id, len(clips) + 1, services)
        report["analysisSeconds"] = round(time.monotonic() - started, 1)
        print(f"Analysis finished in {report['analysisSeconds']} s", flush=True)

        analysis = song_analysis_file(media_root)
        music = json.loads(analysis.read_text(encoding="utf-8"))["music"]
        found = [beat["time"] for beat in music["beats"]]
        report["beatAccuracy"] = beat_accuracy(found, truth["beats"])
        report["bpmFound"] = music["bpm"]
        report["bpmTrue"] = truth["bpm"]
        report["sectionsFound"] = music["sections"]
        report["sectionsTrue"] = truth["sections"]

        def inspected(result: RenderResult) -> None:
            folder = media_root / "renders" / str(result.render_id)
            inspect_render(result, folder, analysis, truth["beats"], env)

        for ratio in args.ratios:
            print(f"Rendering {ratio}", flush=True)
            services.require_running()
            result = render_through_api(api, project_id, ratio, media_root, inspected)
            results.append(result)
            print(report_table([result]), flush=True)

        finished = [item for item in results if item.status == "DONE"]
        if finished and not args.skip_stress:
            slowest = max(finished, key=lambda item: item.seconds)
            print(f"Stress render of {slowest.ratio}", flush=True)
            assets = stored_assets(api.get(f"/api/projects/{project_id}/assets"), project_id)
            results.append(
                render_stress(slowest, media_root, analysis, truth["beats"], assets, env)
            )
            print(report_table(results[-1:]), flush=True)
    finally:
        services.stop_all()

    report["ports_free_after_stop"] = not (
        port_in_use(args.backend_port) or port_in_use(args.worker_port)
    )
    report["verdict"] = judge(results, args.limit_minutes, args.shared_gpu)
    report["renders"] = [asdict(result) | {"passed": result.passed} for result in results]
    return report


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ratios", nargs="+", default=list(RATIOS), choices=RATIOS)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--skip-stress", action="store_true")
    parser.add_argument("--shared-gpu", action="store_true")
    parser.add_argument("--limit-minutes", type=float, default=LIMIT_MINUTES)
    parser.add_argument("--backend-port", type=int, default=BACKEND_PORT)
    parser.add_argument("--worker-port", type=int, default=WORKER_PORT)
    return parser.parse_args(argv)


def _raise_exit(signal_number: int, _: object) -> None:
    raise SystemExit(128 + signal_number)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_arguments(argv)
    for name in ("SIGTERM", "SIGBREAK"):
        signal.signal(getattr(signal, name), _raise_exit)
    tools = tool_environment()
    os.environ.update(tools)
    run_folder = ROOT / GATE_FOLDER / "runs" / datetime.now().strftime("%Y%m%d-%H%M%S")
    run_folder.mkdir(parents=True)
    print("REHEARSAL on generated media: this is not the gate on real footage.", flush=True)

    report = run_gate(args, run_folder, tools)

    (run_folder / REPORT_FILE).write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"\nBeat accuracy against the song's real beats: {report.get('beatAccuracy')}")
    print(report_table([RenderResult(**_row(row)) for row in report["renders"]]))
    print(f"Verdict: {report['verdict']}\nReport: {run_folder / REPORT_FILE}")
    return 0 if report["verdict"]["passed"] else 1


def _row(row: dict[str, Any]) -> dict[str, Any]:
    fields = {key: value for key, value in row.items() if key != "passed"}
    check = fields.get("beat_check")
    fields["beat_check"] = BeatCheck(**check) if check else None
    fields["load"] = Load(**fields["load"])
    return fields


if __name__ == "__main__":
    sys.exit(main())
