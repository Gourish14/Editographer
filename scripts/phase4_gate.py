"""Runs the Phase 4 gate end to end on real media: a full Max render, kept cool, that plays smoothly.

Spec: specs/10-roadmap.md#phase-4--ultra-quality [T-412]

Gate text: 8K 9:16 export plays smoothly; cool mode keeps the GPU under 85 C for a full Max quality
render.

Reuses scripts/phase1_gate.py to start the apps, upload, wait for analysis and check the frame
count. One real project goes through the real app: Max quality, 8K, 9:16, cool mode ON, 60 s. While
it renders, nvidia-smi is sampled about every 5 s into thermal.csv in the run folder, from before
the render starts to after it ends. The render passes the thermal line only when its status is DONE,
the frame count is exact, every temperature sample is under 85 C and no gap between samples is
longer than 30 s, so the claim covers the whole render.

If the first 10 % of progress projects a render longer than 8 hours, the render is cancelled and
started again with a shorter edit, and the report says so (lengthSec and shortened).

"Plays smoothly" is measured on the finished file: an FFmpeg hardware decode speed test, and a
play-through to the end in real Chrome (scripts/phase4_playback.mjs, Playwright with the installed
Chrome) reading getVideoPlaybackQuality(), once on the download URL and once on the app's own
render page.

Usage, from worker/:
    uv run python ..\\scripts\\phase4_gate.py --inputs ..\\media\\gate-inputs\\clips [--skip-build]
    uv run python ..\\scripts\\phase4_gate.py --postcheck ..\\media\\phase4_gate\\runs\\<run>
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import signal
import statistics
import subprocess
import sys
import threading
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import phase1_gate as gate  # noqa: E402

ROOT = gate.ROOT
GATE_FOLDER = Path("media") / "phase4_gate"
REPORT_FILE = "phase4_report.json"
THERMAL_FILE = "thermal.csv"
RATIO = "9:16"
QUALITY = "8K"
MODE = "max"
FPS = 30
LENGTH_SEC = 60
SHORT_LENGTH_SEC = 30
SEED = 2412
STYLE = "auto"
EXPECTED_SIZE = (4320, 7680)
LIMIT_C = 85.0
MAX_GAP_SEC = 30.0
SAMPLE_EVERY_SEC = 5.0
LIMIT_HOURS = 8.0
PROJECT_AT_PERCENT = 10
POLL_SEC = 3.0
RENDER_TIMEOUT_SEC = 14 * 3600
VRAM_LIMIT_MB = 6.1 * 1024
PLAYBACK_TIMEOUT_FACTOR = 4
DECODERS = ("d3d11va", "cuda")
MIN_REALTIME_SPEED = 1.0
MAX_DROPPED_SHARE = 0.01

SMI_FIELDS = (
    "temperature.gpu,power.draw,clocks.sm,clocks.mem,memory.used,utilization.gpu,"
    "utilization.encoder,clocks_throttle_reasons.active"
)
CSV_HEADER = (
    "wall_time,elapsed_sec,temp_c,power_w,sm_mhz,mem_mhz,mem_used_mb,gpu_util,enc_util,throttle"
)
SPEED = re.compile(r"speed=\s*([\d.]+)x")
FRAMES = re.compile(r"frame=\s*(\d+)")
FPS_LINE = re.compile(r"fps=\s*([\d.]+)")


@dataclass(frozen=True)
class Sample:
    """One nvidia-smi reading. Fields are None when the card reported [N/A]."""

    at: float
    temp_c: float | None
    power_w: float | None
    sm_mhz: float | None
    mem_mhz: float | None
    mem_used_mb: float | None
    gpu_util: float | None
    enc_util: float | None
    throttle: str


@dataclass
class ThermalSummary:
    samples: int
    seconds: float
    max_temp_c: float | None
    mean_temp_c: float | None
    over_limit: int
    seconds_at_or_above_pause: float
    longest_gap_sec: float
    peak_power_w: float | None
    min_sm_mhz: float | None
    max_sm_mhz: float | None
    peak_mem_used_mb: float | None
    throttle_seen: dict[str, int] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return (
            self.samples > 1
            and self.over_limit == 0
            and self.max_temp_c is not None
            and self.longest_gap_sec <= MAX_GAP_SEC
        )


# Pure helpers, covered by test_phase4_gate.py


def _number(text: str) -> float | None:
    try:
        return float(text)
    except ValueError:
        return None


def parse_smi_line(line: str, at: float) -> Sample | None:
    """A Sample from one line of `nvidia-smi --format=csv,noheader,nounits`, None if malformed."""
    parts = [part.strip() for part in line.split(",")]
    if len(parts) != len(SMI_FIELDS.split(",")):
        return None
    numbers = [_number(part) for part in parts[:7]]
    return Sample(at, *numbers, throttle=parts[7])  # type: ignore[arg-type]


def sample_gaps(times: Sequence[float]) -> list[float]:
    return [later - earlier for earlier, later in zip(times, times[1:], strict=False)]


def summarize_thermal(samples: Sequence[Sample], pause_at_c: float = 83.0) -> ThermalSummary:
    """The numbers a thermal verdict is judged by. A sample without a temperature is not data."""
    times = [item.at for item in samples]
    temps = [item for item in samples if item.temp_c is not None]
    gaps = sample_gaps(times)
    # Readings that failed count as missing time, so a dead sampler cannot pass the gate.
    longest = max(gaps, default=float("inf"))
    seen: dict[str, int] = {}
    for item in samples:
        seen[item.throttle] = seen.get(item.throttle, 0) + 1
    above = sum(
        later.at - earlier.at
        for earlier, later in zip(temps, temps[1:], strict=False)
        if earlier.temp_c is not None and earlier.temp_c >= pause_at_c
    )

    def peak(values: list[float | None]) -> float | None:
        found = [value for value in values if value is not None]
        return max(found) if found else None

    def low(values: list[float | None]) -> float | None:
        found = [value for value in values if value is not None]
        return min(found) if found else None

    return ThermalSummary(
        samples=len(samples),
        seconds=round(times[-1] - times[0], 1) if len(times) > 1 else 0.0,
        max_temp_c=peak([item.temp_c for item in temps]),
        mean_temp_c=round(statistics.fmean(item.temp_c for item in temps if item.temp_c), 1)
        if temps
        else None,
        over_limit=sum(item.temp_c is not None and item.temp_c >= LIMIT_C for item in samples),
        seconds_at_or_above_pause=round(above, 1),
        longest_gap_sec=round(longest, 1),
        peak_power_w=peak([item.power_w for item in samples]),
        min_sm_mhz=low([item.sm_mhz for item in samples]),
        max_sm_mhz=peak([item.sm_mhz for item in samples]),
        peak_mem_used_mb=peak([item.mem_used_mb for item in samples]),
        throttle_seen=seen,
    )


def projected_total_sec(elapsed_sec: float, percent: float) -> float | None:
    """The whole render's length if the rest goes as fast as the part done so far."""
    return elapsed_sec * 100.0 / percent if percent > 0 else None


def exceeds_limit(projected_sec: float | None, limit_hours: float = LIMIT_HOURS) -> bool:
    return projected_sec is not None and projected_sec > limit_hours * 3600


def parse_cool_pauses(log_text: str) -> dict[str, Any]:
    """Time spent holding for the GPU to cool, from the worker's cool_mode.paused/resumed lines.

    The 10 s rests before each GPU stage are not logged, so they are not in this number.
    """
    holds: list[float] = []
    started: datetime | None = None
    for line in log_text.splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        event = entry.get("event")
        if event not in ("cool_mode.paused", "cool_mode.resumed"):
            continue
        moment = datetime.fromisoformat(str(entry["ts"]).replace("Z", "+00:00"))
        if event == "cool_mode.paused":
            started = moment
        elif started is not None:
            holds.append((moment - started).total_seconds())
            started = None
    return {
        "holds": len(holds),
        "holdSeconds": round(sum(holds), 1),
        "longestHoldSeconds": round(max(holds, default=0.0), 1),
        "unfinishedHold": started is not None,
    }


def parse_decode_speed(stderr: str) -> dict[str, float | None]:
    """Frames, fps and speed from the last stats line FFmpeg printed."""
    last = stderr.replace("\r", "\n").splitlines()
    stats = [line for line in last if SPEED.search(line) and FRAMES.search(line)]
    if not stats:
        return {"frames": None, "fps": None, "speed": None}
    line = stats[-1]
    fps = FPS_LINE.search(line)
    frames = FRAMES.search(line)
    speed = SPEED.search(line)
    return {
        "frames": int(frames.group(1)) if frames else None,
        "fps": float(fps.group(1)) if fps else None,
        "speed": float(speed.group(1)) if speed else None,
    }


def judge_decode(result: dict[str, Any], frames_expected: int) -> bool:
    speed = result.get("speed")
    return (
        result.get("exitCode") == 0
        and result.get("frames") == frames_expected
        and speed is not None
        and speed >= MIN_REALTIME_SPEED
    )


def judge_playback(result: dict[str, Any], frames_expected: int) -> bool:
    """Played to the end, every frame decoded, no more than 1 % dropped."""
    total = result.get("totalFrames") or 0
    dropped = result.get("droppedFrames")
    return (
        bool(result.get("ended"))
        and result.get("error") is None
        and total >= frames_expected
        and dropped is not None
        and dropped <= total * MAX_DROPPED_SHARE
    )


def smooth_verdict(
    decode: dict[str, dict[str, Any]], playback: dict[str, dict[str, Any]], frames_expected: int
) -> dict[str, Any]:
    decoded = {name: judge_decode(item, frames_expected) for name, item in decode.items()}
    played = {name: judge_playback(item, frames_expected) for name, item in playback.items()}
    return {
        "decodeOk": decoded,
        "playbackOk": played,
        "passed": bool(decoded) and any(decoded.values()) and bool(played) and all(played.values()),
    }


def covers(samples: Sequence[Sample], started_at: float, ended_at: float) -> bool:
    """The samples start before the render does and end after it ends."""
    return bool(samples) and samples[0].at <= started_at and samples[-1].at >= ended_at


def thermal_verdict(
    status: str,
    frames: tuple[int, int] | None,
    summary: ThermalSummary | None,
    covered: bool = True,
) -> dict[str, Any]:
    exact = frames is not None and frames[0] == frames[1]
    return {
        "samplesCoverRender": covered,
        "statusDone": status == "DONE",
        "frameCountExact": exact,
        "allSamplesUnderLimit": bool(summary and summary.over_limit == 0 and summary.samples > 1),
        "noGapOverLimit": bool(summary and summary.longest_gap_sec <= MAX_GAP_SEC),
        "passed": status == "DONE" and exact and covered and bool(summary and summary.passed),
    }


def per_frame_ms(seconds: float, frames: int) -> float:
    return round(seconds * 1000.0 / frames, 1) if frames else 0.0


# Sampling


class ThermalRecorder:
    """Samples nvidia-smi into a CSV while the render runs, from before it starts to after it ends."""

    def __init__(self, path: Path, every_sec: float = SAMPLE_EVERY_SEC) -> None:
        self._path = path
        self._every = every_sec
        self._samples: list[Sample] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._origin = 0.0
        self.failures = 0

    def __enter__(self) -> ThermalRecorder:
        self._origin = time.time()
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(self._every * 3)

    @property
    def samples(self) -> list[Sample]:
        return list(self._samples)

    def _read(self) -> Sample | None:
        try:
            output = subprocess.run(
                ["nvidia-smi", f"--query-gpu={SMI_FIELDS}", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, check=True, timeout=20,
            ).stdout  # fmt: skip
        except (OSError, subprocess.SubprocessError):
            return None
        return (
            parse_smi_line(output.strip().splitlines()[0], time.time()) if output.strip() else None
        )

    def _run(self) -> None:
        with self._path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(CSV_HEADER.split(","))
            while True:
                started = time.monotonic()
                sample = self._read()
                if sample is None:
                    self.failures += 1
                else:
                    self._samples.append(sample)
                    writer.writerow(
                        [
                            datetime.fromtimestamp(sample.at).isoformat(timespec="seconds"),
                            round(sample.at - self._origin, 1), sample.temp_c, sample.power_w,
                            sample.sm_mhz, sample.mem_mhz, sample.mem_used_mb, sample.gpu_util,
                            sample.enc_util, sample.throttle,
                        ]
                    )  # fmt: skip
                    handle.flush()
                if self._stop.wait(max(0.0, self._every - (time.monotonic() - started))):
                    return


# Render and measure


@dataclass
class RenderFacts:
    render_id: str | None = None
    status: str = "NOT_RUN"
    error: str | None = None
    length_sec: int = LENGTH_SEC
    shortened: bool = False
    projected_hours: float | None = None
    projected_at_percent: float | None = None
    seconds: float = 0.0
    frames: tuple[int, int] | None = None
    width: int | None = None
    height: int | None = None
    codec: str | None = None
    pix_fmt: str | None = None
    size_mb: float | None = None
    progress_log: list[tuple[float, int, str]] = field(default_factory=list)


def wait_with_projection(
    api: gate.Api, render_id: str, started: float, services: gate.Services, allow_cancel: bool
) -> tuple[RenderFacts, bool]:
    """Polls to the end. Returns the facts and True when the 8 h projection cancelled it."""
    facts = RenderFacts(render_id=render_id)
    projected = False
    last_percent = -1
    while time.monotonic() - started < RENDER_TIMEOUT_SEC:
        services.require_running()
        render = api.get(f"/api/renders/{render_id}")
        elapsed = time.monotonic() - started
        percent = int(render.get("progress") or 0)
        if percent != last_percent:
            last_percent = percent
            facts.progress_log.append((round(elapsed, 1), percent, str(render.get("stage"))))
            print(f"[{elapsed / 60:7.1f} min] {percent}% {render.get('stage')}", flush=True)
        if render["status"] in ("DONE", "FAILED", "CANCELLED"):
            facts.status, facts.error = render["status"], render.get("error")
            return facts, False
        if not projected and percent >= PROJECT_AT_PERCENT:
            projected = True
            total = projected_total_sec(elapsed, percent)
            facts.projected_at_percent = percent
            facts.projected_hours = round(total / 3600, 2) if total else None
            print(f"Projection at {percent}%: {facts.projected_hours} h", flush=True)
            if allow_cancel and exceeds_limit(total):
                api.post(f"/api/renders/{render_id}/cancel", {})
                print("Projected beyond 8 h: cancelled", flush=True)
                time.sleep(POLL_SEC * 2)
                facts.status = "CANCELLED_BY_GATE"
                return facts, True
        time.sleep(POLL_SEC)
    facts.status, facts.error = "TIMED_OUT", f"Not finished after {RENDER_TIMEOUT_SEC} s"
    return facts, False


def run_one_render(
    api: gate.Api, project_id: str, length_sec: int, services: gate.Services, allow_cancel: bool
) -> tuple[RenderFacts, bool]:
    settings = {
        "ratio": RATIO, "quality": QUALITY, "fps": FPS, "style": STYLE, "mode": MODE,
        "lengthSec": length_sec, "seed": SEED, "coolMode": True,
    }  # fmt: skip
    started = time.monotonic()
    render_id = api.post(f"/api/projects/{project_id}/renders", settings)["id"]
    print(f"Render {render_id}: {settings}", flush=True)
    facts, cancelled = wait_with_projection(api, render_id, started, services, allow_cancel)
    facts.seconds = round(time.monotonic() - started, 1)
    facts.length_sec = length_sec
    return facts, cancelled


def inspect_final(
    facts: RenderFacts, media_root: Path, analysis: Path, env: dict[str, str]
) -> None:
    folder = media_root / "renders" / str(facts.render_id)
    check = gate.run_beat_check(folder, analysis, env)
    facts.frames = (check.frames_actual, check.frames_expected)
    stream = gate.probe_summary(folder / "final.mp4", env)
    facts.width, facts.height = stream.get("width"), stream.get("height")
    facts.codec, facts.pix_fmt = stream.get("codec_name"), stream.get("pix_fmt")
    facts.size_mb = round((folder / "final.mp4").stat().st_size / 2**20, 1)


def worker_log_text(logs: Path) -> str:
    return "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in sorted(logs.glob("worker.log*"))
    )


# Smoothness


def decode_test(video: Path, decoder: str, env: dict[str, str]) -> dict[str, Any]:
    """Decodes the whole file with hardware acceleration and throws the pictures away."""
    started = time.monotonic()
    finished = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-stats", "-hwaccel", decoder, "-i", str(video),
         "-map", "0:v:0", "-f", "null", "-"],
        capture_output=True, text=True, env=env, check=False,
    )  # fmt: skip
    result: dict[str, Any] = {
        "decoder": decoder,
        "exitCode": finished.returncode,
        "wallSeconds": round(time.monotonic() - started, 1),
        **parse_decode_speed(finished.stderr),
    }
    if finished.returncode != 0:
        result["stderrTail"] = finished.stderr.strip()[-400:]
    return result


def play_in_chrome(
    base_url: str, render_id: str, duration_sec: float, headless: bool, out: Path
) -> dict[str, Any]:
    """Runs phase4_playback.mjs: plays the file to the end in the installed Chrome."""
    timeout = duration_sec * PLAYBACK_TIMEOUT_FACTOR + 120
    command = [
        "node", str(SCRIPTS / "phase4_playback.mjs"), base_url, render_id, str(duration_sec),
        str(int(timeout)), "headless" if headless else "headed", str(out),
    ]  # fmt: skip
    finished = subprocess.run(
        command, capture_output=True, text=True, check=False, timeout=timeout * 2 + 300
    )
    print(finished.stdout[-1500:], flush=True)
    if not out.is_file():
        return {"error": f"playback script failed: {finished.stderr[-600:]}"}
    return json.loads(out.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def smoothness(
    video: Path, base_url: str, render_id: str, frames_expected: int, fps: int,
    run_folder: Path, env: dict[str, str], headless: bool,
) -> dict[str, Any]:  # fmt: skip
    decode = {name: decode_test(video, name, env) for name in DECODERS}
    for item in decode.values():
        print(f"Decode {item['decoder']}: {item}", flush=True)
    playback = play_in_chrome(
        base_url, render_id, frames_expected / fps, headless, run_folder / "playback.json"
    )
    pages = {name: page for name, page in playback.get("pages", {}).items()}
    verdict = smooth_verdict(decode, pages, frames_expected)
    return {"decode": decode, "playback": playback, "verdict": verdict}


# The gate


def finish_report(
    report: dict[str, Any], facts: RenderFacts, summary: ThermalSummary | None, covered: bool
) -> None:
    pauses = report.get("coolPauses", {})
    frames = facts.frames[0] if facts.frames else 0
    peak = summary.peak_mem_used_mb if summary else None
    report["render"] = asdict(facts)
    report["thermal"] = asdict(summary) if summary else None
    report["perFrameMs"] = per_frame_ms(facts.seconds, frames)
    report["perFrameMsWithoutHolds"] = per_frame_ms(
        max(0.0, facts.seconds - pauses.get("holdSeconds", 0.0)), frames
    )
    report["peakVramMb"] = peak
    report["peakVramGb"] = round(peak / 1024, 2) if peak else None
    report["vramLimitGb"] = round(VRAM_LIMIT_MB / 1024, 2)
    report["vramUnderLimit"] = peak is not None and peak <= VRAM_LIMIT_MB
    report["thermalVerdict"] = thermal_verdict(facts.status, facts.frames, summary, covered)


def run_gate(args: argparse.Namespace, run_folder: Path, tools: dict[str, str]) -> dict[str, Any]:
    clips, song = gate.input_files(args.inputs)
    if not args.skip_build:
        gate.build_backend(tools)
    for port in (args.backend_port, args.worker_port):
        if gate.port_in_use(port):
            raise gate.GateError(f"Port {port} is in use. The gate touches nothing running.")
    relative = run_folder.relative_to(ROOT)
    env = gate.service_environment(tools, relative, args.backend_port, args.worker_port)
    media_root = run_folder / "media"
    for folder in (media_root, run_folder / "data", run_folder / "logs"):
        folder.mkdir(parents=True, exist_ok=True)

    services = gate.Services(run_folder / "logs")
    report: dict[str, Any] = {"started": datetime.now().isoformat(), "inputs": str(args.inputs)}
    facts = RenderFacts()
    summary: ThermalSummary | None = None
    covered = False
    try:
        gate.start_services(services, env, args.backend_port)
        api = gate.Api(args.backend_port)
        project_id = api.post("/api/projects", {"name": "Phase 4 gate"})["id"]
        for path in [*clips, song]:
            api.upload(project_id, path)
            print(f"Uploaded {path.name}", flush=True)
        started = time.monotonic()
        gate.wait_for_analysis(api, project_id, len(clips) + 1, services)
        report["analysisSeconds"] = round(time.monotonic() - started, 1)
        analysis = gate.song_analysis_file(media_root)
        music = json.loads(analysis.read_text(encoding="utf-8"))["music"]
        report["bpm"], report["editWindow"] = music["bpm"], music.get("edit_window")

        with ThermalRecorder(run_folder / THERMAL_FILE) as recorder:
            time.sleep(SAMPLE_EVERY_SEC * 2)  # a baseline before the render starts
            render_start = time.time()
            facts, cancelled = run_one_render(api, project_id, args.length_sec, services, True)
            report["firstAttempt"] = asdict(facts) if cancelled else None
            if cancelled:
                print(f"Restarting with a {SHORT_LENGTH_SEC} s edit", flush=True)
                time.sleep(15)
                first = facts
                facts, _ = run_one_render(api, project_id, SHORT_LENGTH_SEC, services, False)
                facts.shortened = True
                facts.projected_hours = first.projected_hours
                facts.projected_at_percent = first.projected_at_percent
            render_end = time.time()
            time.sleep(SAMPLE_EVERY_SEC * 2)  # and after it ends
            recorder.stop()
            covered = covers(recorder.samples, render_start, render_end)
            summary = summarize_thermal(recorder.samples)
            report["samplerFailures"] = recorder.failures

        report["coolPauses"] = parse_cool_pauses(worker_log_text(run_folder / "logs"))
        if facts.status == "DONE":
            inspect_final(facts, media_root, analysis, env)
            report["smoothness"] = smoothness(
                media_root / "renders" / str(facts.render_id) / "final.mp4",
                f"http://127.0.0.1:{args.backend_port}", str(facts.render_id),
                facts.frames[1] if facts.frames else 0, FPS, run_folder, env, args.headless,
            )  # fmt: skip
    finally:
        services.stop_all()
    finish_report(report, facts, summary, covered)
    return report


def postcheck(args: argparse.Namespace, tools: dict[str, str]) -> dict[str, Any]:
    """Runs the smoothness checks again on a finished run folder, starting its apps again."""
    run_folder = args.postcheck.resolve()
    report = json.loads((run_folder / REPORT_FILE).read_text(encoding="utf-8"))
    relative = run_folder.relative_to(ROOT)
    env = gate.service_environment(tools, relative, args.backend_port, args.worker_port)
    services = gate.Services(run_folder / "logs")
    render_id = report["render"]["render_id"]
    frames = report["render"]["frames"][1]
    try:
        gate.start_services(services, env, args.backend_port)
        report["smoothness"] = smoothness(
            run_folder / "media" / "renders" / render_id / "final.mp4",
            f"http://127.0.0.1:{args.backend_port}", render_id, frames, FPS, run_folder, env,
            args.headless,
        )  # fmt: skip
    finally:
        services.stop_all()
    return report


def overall(report: dict[str, Any]) -> dict[str, Any]:
    smooth = report.get("smoothness", {}).get("verdict", {})
    thermal = report.get("thermalVerdict", {})
    return {
        "smoothPassed": bool(smooth.get("passed")),
        "thermalPassed": bool(thermal.get("passed")),
        "passed": bool(smooth.get("passed")) and bool(thermal.get("passed")),
    }


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, help="Folder of *.mp4 and song.wav")
    parser.add_argument("--postcheck", type=Path, help="A finished run folder: smoothness again")
    parser.add_argument("--length-sec", type=int, default=LENGTH_SEC)
    parser.add_argument("--headless", action="store_true", help="Chrome without a window")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--backend-port", type=int, default=gate.BACKEND_PORT)
    parser.add_argument("--worker-port", type=int, default=gate.WORKER_PORT)
    return parser.parse_args(argv)


def _raise_exit(signal_number: int, _: object) -> None:
    raise SystemExit(128 + signal_number)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_arguments(argv)
    for name in ("SIGTERM", "SIGBREAK"):
        signal.signal(getattr(signal, name), _raise_exit)
    tools = gate.tool_environment()
    os.environ.update(tools)
    if args.postcheck is not None:
        report = postcheck(args, tools)
        run_folder = args.postcheck.resolve()
    else:
        if args.inputs is None:
            raise SystemExit("--inputs is required for a run")
        run_folder = ROOT / GATE_FOLDER / "runs" / datetime.now().strftime("%Y%m%d-%H%M%S")
        run_folder.mkdir(parents=True)
        report = run_gate(args, run_folder, tools)
    report["verdict"] = overall(report)
    (run_folder / REPORT_FILE).write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps({k: report.get(k) for k in ("thermalVerdict", "verdict")}, indent=1))
    print(f"Report: {run_folder / REPORT_FILE}")
    return 0 if report["verdict"]["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
