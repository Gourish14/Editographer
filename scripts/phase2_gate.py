"""Runs the Phase 2 gate end to end on real media: do prompts visibly change the edit?

Spec: specs/10-roadmap.md#phase-2--ai-director [T-411]

Gate text: the prompts "only car shots", "slow-mo on the drop" and "cinematic no shakes" each
visibly change the edit, and with Ollama stopped an edit is still produced by the fallback.

Reuses scripts/phase1_gate.py to start the apps, upload, wait and inspect. Starts a private Ollama
server of its own on a free port (never touches another one), renders a baseline with no prompt and
one render per prompt, then restarts the worker with Ollama pointed at a closed port and renders
once more. "Visibly" is measured from each plan.json against the baseline, and the frame-accurate
facts are checked again in the finished file. Everything it starts is stopped by PID.

Usage, from worker/:
    uv run python ..\\scripts\\phase2_gate.py --inputs ..\\media\\gate-inputs\\clips \\
        --ollama-models <folder with qwen3:4b and qwen2.5vl:3b> [--skip-build]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import statistics
import subprocess
import sys
import time
import urllib.request
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import phase1_gate as gate  # noqa: E402

ROOT = gate.ROOT
GATE_FOLDER = Path("media") / "phase2_gate"
REPORT_FILE = "phase2_report.json"
RATIO = "9:16"
MODE = "preview"
QUALITY = "4K"
FPS = 30
LENGTH_SEC = 40
SEED = 2411
STYLE = "auto"
OLLAMA_PORT = 18434
CLOSED_PORT = 1
OLLAMA_START_SEC = 60
FALLBACK_NOTE = "AI director unavailable; used the rule fallback"
RUNS: tuple[tuple[str, str | None], ...] = (
    ("baseline", None),
    ("only car shots", "only car shots"),
    ("slow-mo on the drop", "slow-mo on the drop"),
    ("cinematic no shakes", "cinematic no shakes"),
)
DOWN_LABEL = "ollama down"
DOWN_PROMPT = "cinematic no shakes"
CAR_TAG = "car"
RAMP_FAST_END = 0.4
HOLD_START = 0.5
HOLD_END = 0.8
MIN_FRAMES_FOR_RAMP_CHECK = 3
EPSILON = 1e-6

DECIDED = re.compile(r"director\.decided")
FELL_BACK = re.compile(r"director\.fallback")


@dataclass
class PlanFacts:
    """What one plan.json says, in numbers a gate line can be judged by."""

    style: str
    segments: int
    car_segments: int
    ramps: int
    ramps_in_drop: int
    drop_segments: int
    shakes: int
    flashes: int
    zooms: int
    fallback_note: bool
    notes: list[str] = field(default_factory=list)
    ramp_segments: list[str] = field(default_factory=list)

    @property
    def car_share(self) -> float:
        return self.car_segments / self.segments if self.segments else 0.0


@dataclass
class RampCheck:
    """A ramped segment as it sits in the file: the slow hold must move less than the fast start."""

    segment: str
    fast_mean: float
    hold_mean: float

    @property
    def slower(self) -> bool:
        return self.hold_mean < self.fast_mean


@dataclass
class RunResult:
    label: str
    prompt: str | None
    status: str
    seconds: float
    render_id: str | None = None
    error: str | None = None
    director: str = "unknown"
    facts: PlanFacts | None = None
    beats_ok: bool | None = None
    cuts: int | None = None
    worst_ms: float | None = None
    frames: str | None = None
    ramp_checks: list[RampCheck] = field(default_factory=list)
    width: int | None = None
    height: int | None = None


# Pure helpers, covered by test_phase2_gate.py


def shot_tags(segment: dict[str, Any], shots: Sequence[dict[str, Any]]) -> list[str]:
    """Tags of the shot the segment's source window overlaps most."""
    start, end = segment["srcIn"], segment["srcOut"]

    def overlap(shot: dict[str, Any]) -> float:
        return min(end, shot["end"]) - max(start, shot["start"])

    best = max(shots, key=overlap, default=None)
    return list(best["tags"]) if best is not None and overlap(best) > 0 else []


def tag_matches(tags: Sequence[str], wanted: str) -> bool:
    """The planner's own rule: "car" matches "sports car" and "cars", not "carpet"."""

    def stem(word: str) -> str:
        return (
            word[:-1] if word.endswith("s") and not word.endswith("ss") and len(word) > 3 else word
        )

    words = {stem(part) for tag in tags for part in tag.lower().replace("-", " ").split()}
    return stem(wanted.lower()) in words


def section_kind(time_sec: float, sections: Sequence[dict[str, Any]]) -> str:
    for section in sections:
        if section["start"] <= time_sec < section["end"]:
            return section["kind"].lower()
    return "unknown"


def is_ramp(segment: dict[str, Any]) -> bool:
    return any(abs(speed - 1.0) > EPSILON for _, speed in segment["speed"]["curve"])


def count_effects(plan: dict[str, Any], kind: str) -> int:
    return sum(effect["type"] == kind for item in plan["segments"] for effect in item["effects"])


def plan_facts(
    plan: dict[str, Any],
    shots_by_asset: dict[str, list[dict[str, Any]]],
    sections: Sequence[dict[str, Any]],
) -> PlanFacts:
    segments = plan["segments"]
    kinds = [section_kind(item["at"], sections) for item in segments]
    ramped = [item for item in segments if is_ramp(item)]
    car = [
        item
        for item in segments
        if tag_matches(shot_tags(item, shots_by_asset.get(item["assetId"], [])), CAR_TAG)
    ]
    ramps_in_drop = [
        item for item, kind in zip(segments, kinds, strict=True) if kind == "drop" and is_ramp(item)
    ]
    notes = list(plan.get("log", []))
    return PlanFacts(
        style=plan["style"],
        segments=len(segments),
        car_segments=len(car),
        ramps=len(ramped),
        ramps_in_drop=len(ramps_in_drop),
        drop_segments=kinds.count("drop"),
        shakes=count_effects(plan, "shake"),
        flashes=count_effects(plan, "flash"),
        zooms=count_effects(plan, "zoomPunch"),
        fallback_note=FALLBACK_NOTE in notes,
        notes=notes,
        ramp_segments=[item["id"] for item in ramped],
    )


def director_source(log_text: str) -> str:
    """Who decided, from the worker's log lines of one render: llm, fallback or none."""
    if FELL_BACK.search(log_text):
        return "fallback"
    return "llm" if DECIDED.search(log_text) else "none"


def ramp_checks(plan: dict[str, Any], scores: Sequence[gate.FrameScore]) -> list[RampCheck]:
    """Mean frame-to-frame change in the fast start and the slow hold of each ramped segment."""
    fps = plan["output"]["fps"]
    origin = plan["music"]["start"]
    checks = []
    for item in plan["segments"]:
        if not is_ramp(item):
            continue
        first = round((item["at"] - origin) * fps)
        length = round(item["duration"] * fps)
        fast = _window(scores, first, length, 0.0, RAMP_FAST_END)
        hold = _window(scores, first, length, HOLD_START, HOLD_END)
        if len(fast) >= MIN_FRAMES_FOR_RAMP_CHECK and len(hold) >= MIN_FRAMES_FOR_RAMP_CHECK:
            checks.append(RampCheck(item["id"], statistics.fmean(fast), statistics.fmean(hold)))
    return checks


def _window(
    scores: Sequence[gate.FrameScore], first: int, length: int, low: float, high: float
) -> list[float]:
    start = first + round(length * low)
    stop = first + round(length * high)
    return [item.score for item in scores[start:stop]]


def judge_car(baseline: RunResult, run: RunResult) -> dict[str, Any]:
    base, now = _facts(baseline), _facts(run)
    rose = now.car_share > base.car_share
    return {
        "baselineCarShare": round(base.car_share, 3),
        "promptCarShare": round(now.car_share, 3),
        "carSegments": f"{now.car_segments}/{now.segments}",
        "notes": [note for note in now.notes if "car" in note.lower()],
        "director": run.director,
        "visibleChange": rose,
        "passed": rose and run.status == "DONE" and run.director == "llm",
    }


def judge_slowmo(baseline: RunResult, run: RunResult) -> dict[str, Any]:
    base, now = _facts(baseline), _facts(run)
    in_file = bool(run.ramp_checks) and all(check.slower for check in run.ramp_checks)
    rose = now.ramps_in_drop > base.ramps_in_drop
    return {
        "baselineRampsInDrop": base.ramps_in_drop,
        "promptRampsInDrop": now.ramps_in_drop,
        "dropSegments": now.drop_segments,
        "rampsTotal": now.ramps,
        "slowerInFinishedFile": in_file,
        "rampChecks": [asdict(check) for check in run.ramp_checks],
        "notes": [note for note in now.notes if "slow" in note.lower()],
        "director": run.director,
        "visibleChange": rose,
        "passed": rose and in_file and run.status == "DONE" and run.director == "llm",
    }


def judge_cinematic(baseline: RunResult, run: RunResult) -> dict[str, Any]:
    """Cinematic with no shakes, and a change from the baseline: another style or fewer shakes."""
    base, now = _facts(baseline), _facts(run)
    asked = now.style == "cinematic" and now.shakes == 0
    changed = base.style != now.style or base.shakes > now.shakes
    return {
        "baselineStyle": base.style,
        "baselineShakes": base.shakes,
        "promptStyle": now.style,
        "promptShakes": now.shakes,
        "director": run.director,
        "visibleChange": asked and changed,
        "passed": run.status == "DONE" and asked and changed and run.director == "llm",
    }


def judge_down(run: RunResult) -> dict[str, Any]:
    facts = run.facts
    return {
        "status": run.status,
        "director": run.director,
        "fallbackNoteInPlan": bool(facts and facts.fallback_note),
        "style": facts.style if facts else None,
        "shakes": facts.shakes if facts else None,
        "passed": run.status == "DONE"
        and facts is not None
        and facts.fallback_note
        and run.director == "fallback",
    }


def _facts(run: RunResult) -> PlanFacts:
    if run.facts is None:
        raise gate.GateError(f"{run.label} produced no plan, status {run.status}")
    return run.facts


def verdict(results: dict[str, RunResult]) -> dict[str, Any]:
    baseline = results["baseline"]
    lines = {
        "onlyCarShots": judge_car(baseline, results["only car shots"]),
        "slowMoOnTheDrop": judge_slowmo(baseline, results["slow-mo on the drop"]),
        "cinematicNoShakes": judge_cinematic(baseline, results["cinematic no shakes"]),
        "ollamaDown": judge_down(results[DOWN_LABEL]),
    }
    return {"lines": lines, "passed": all(line["passed"] for line in lines.values())}


def report_table(results: Sequence[RunResult]) -> str:
    header = (
        "| Run | Status | Director | Style | Segs | Car | Ramps | Ramps in drop | Drop segs | "
        "Shakes | Flashes | Zooms | Cuts | Worst grid ms | Frames | Seconds |"
    )
    rows = [header, "|" + " --- |" * 16]
    for result in results:
        f = result.facts
        cells = [
            result.label, result.status, result.director,
            f.style if f else "-", f.segments if f else "-",
            f"{f.car_segments} ({f.car_share:.0%})" if f else "-",
            f.ramps if f else "-", f.ramps_in_drop if f else "-", f.drop_segments if f else "-",
            f.shakes if f else "-", f.flashes if f else "-", f.zooms if f else "-",
            result.cuts if result.cuts is not None else "-",
            result.worst_ms if result.worst_ms is not None else "-",
            result.frames or "-", f"{result.seconds:.0f}",
        ]  # fmt: skip
        rows.append("| " + " | ".join(str(cell) for cell in cells) + " |")
    return "\n".join(rows)


# Processes and renders


def start_ollama(
    services: gate.Services, executable: Path, models: Path, port: int, env: dict[str, str]
) -> None:
    """A private server on its own port. The ones already running are never touched."""
    if gate.port_in_use(port):
        raise gate.GateError(f"Port {port} is in use. The gate touches nothing already running.")
    private = {**env, "OLLAMA_HOST": f"127.0.0.1:{port}", "OLLAMA_MODELS": str(models)}
    services.start("ollama", [str(executable), "serve"], ROOT, private)
    deadline = time.monotonic() + OLLAMA_START_SEC
    while time.monotonic() < deadline:
        services.require_running()
        if gate._answers(f"http://127.0.0.1:{port}/api/tags"):
            return
        time.sleep(1)
    raise gate.GateError("The private Ollama server did not start")


def ollama_models(port: int) -> list[str]:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/tags", timeout=10) as response:
        return [item["name"] for item in json.load(response)["models"]]


def restart_worker(
    services: gate.Services, env: dict[str, str], ollama_url: str, logs: Path, name: str
) -> None:
    """A worker whose Ollama address is `ollama_url`. The backend keeps running."""
    worker_env = {**env, "OLLAMA_URL": ollama_url}
    python = ROOT / "worker" / ".venv" / "Scripts" / "python.exe"
    services.start(
        name,
        [str(python), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
         "--port", env["WORKER_PORT"]],
        ROOT / "worker",
        worker_env,
    )  # fmt: skip
    deadline = time.monotonic() + gate.START_TIMEOUT_SEC
    while time.monotonic() < deadline:
        services.require_running()
        if gate._answers(f"http://127.0.0.1:{env['WORKER_PORT']}/health"):
            return
        time.sleep(1)
    raise gate.GateError("The worker did not start")


def stop_named(services: gate.Services, name: str) -> None:
    """Stops one service by its PID, with its children."""
    for index, (started, process) in enumerate(services._started):
        if started == name:
            if process.poll() is None:
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    check=False,
                )
            services._started.pop(index)
            print(f"Stopped {name} (PID {process.pid})", flush=True)
            return


def log_slice(log_file: Path, offset: int) -> tuple[str, int]:
    if not log_file.is_file():
        return "", offset
    data = log_file.read_bytes()
    return data[offset:].decode("utf-8", errors="replace"), len(data)


def load_shots(media_root: Path) -> dict[str, list[dict[str, Any]]]:
    """Each uploaded video's shots with their tags.

    The backend stores an upload as uploads/<project>/<asset id>.<ext> and the worker keeps its
    analysis under the file's content hash, so the same hash finds the analysis again.
    """
    sys.path.insert(0, str(ROOT / "worker"))
    from app.adapters.xxhash_hasher import XxhashHasher

    hasher = XxhashHasher()
    shots: dict[str, list[dict[str, Any]]] = {}
    for path in sorted((media_root / "uploads").glob("*/*.mp4")):
        document = media_root / "cache" / hasher.hash_file(path) / "analysis.json"
        if not document.is_file():
            continue
        found = json.loads(document.read_text(encoding="utf-8")).get("shots", [])
        shots[path.stem] = [
            {"start": shot["start"], "end": shot["end"], "tags": shot.get("tags", [])}
            for shot in found
        ]
    return shots


def render_run(
    api: gate.Api,
    project_id: str,
    label: str,
    prompt: str | None,
    media_root: Path,
    analysis: Path,
    shots: dict[str, list[dict[str, Any]]],
    sections: Sequence[dict[str, Any]],
    log_file: Path,
    offset: int,
    env: dict[str, str],
) -> tuple[RunResult, int]:
    settings: dict[str, Any] = {
        "ratio": RATIO, "quality": QUALITY, "fps": FPS, "style": STYLE, "mode": MODE,
        "lengthSec": LENGTH_SEC, "seed": SEED,
    }  # fmt: skip
    if prompt:
        settings["prompt"] = prompt
    started = time.monotonic()
    render_id = api.post(f"/api/projects/{project_id}/renders", settings)["id"]
    status, error = gate._wait_for_render(api, render_id)
    text, offset = log_slice(log_file, offset)
    result = RunResult(
        label, prompt, status, time.monotonic() - started, render_id, error, director_source(text)
    )
    if status == "DONE":
        inspect(result, media_root / "renders" / render_id, analysis, shots, sections, env)
    return result, offset


def inspect(
    result: RunResult,
    folder: Path,
    analysis: Path,
    shots: dict[str, list[dict[str, Any]]],
    sections: Sequence[dict[str, Any]],
    env: dict[str, str],
) -> None:
    plan = json.loads((folder / "plan.json").read_text(encoding="utf-8"))
    result.facts = plan_facts(plan, shots, sections)
    check = gate.run_beat_check(folder, analysis, env)
    result.beats_ok, result.cuts, result.worst_ms = check.passed, check.cuts, check.worst_ms
    result.frames = f"{check.frames_actual}/{check.frames_expected}"
    video = folder / "final.mp4"
    result.ramp_checks = ramp_checks(plan, gate.scene_scores(video, env))
    stream = gate.probe_summary(video, env)
    result.width, result.height = stream.get("width"), stream.get("height")


# The gate


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
    live_url = f"http://127.0.0.1:{args.ollama_port}"
    env["OLLAMA_URL"] = live_url
    log_file = run_folder / "logs" / "worker.log"

    services = gate.Services(run_folder / "logs")
    report: dict[str, Any] = {"started": datetime.now().isoformat(), "inputs": str(args.inputs)}
    results: dict[str, RunResult] = {}
    try:
        start_ollama(services, args.ollama_exe, args.ollama_models, args.ollama_port, env)
        report["ollamaModels"] = ollama_models(args.ollama_port)
        gate.start_services(services, env, args.backend_port)
        api = gate.Api(args.backend_port)
        project_id = api.post("/api/projects", {"name": "Phase 2 gate"})["id"]
        for path in [*clips, song]:
            api.upload(project_id, path)
            print(f"Uploaded {path.name}", flush=True)
        started = time.monotonic()
        gate.wait_for_analysis(api, project_id, len(clips) + 1, services)
        report["analysisSeconds"] = round(time.monotonic() - started, 1)
        analysis = gate.song_analysis_file(media_root)
        music = json.loads(analysis.read_text(encoding="utf-8"))["music"]
        sections = music["sections"]
        report["sections"] = sections
        report["bpm"] = music["bpm"]
        report["editWindow"] = music.get("edit_window")
        assets = api.get(f"/api/projects/{project_id}/assets")
        shots = load_shots(media_root)
        if not shots:
            raise gate.GateError("No analysis with shots was found for the uploaded clips")
        report["fpsPerClip"] = {a["filename"]: a.get("fps") for a in assets}
        report["shotTags"] = {
            key: sorted({tag for shot in found for tag in shot["tags"]})
            for key, found in shots.items()
        }
        offset = log_file.stat().st_size if log_file.is_file() else 0
        for label, prompt in RUNS:
            print(f"Rendering {label!r}", flush=True)
            services.require_running()
            result, offset = render_run(
                api, project_id, label, prompt, media_root, analysis, shots, sections,
                log_file, offset, env,
            )  # fmt: skip
            results[label] = result
            print(report_table([result]), flush=True)

        stop_named(services, "worker")
        closed = f"http://127.0.0.1:{CLOSED_PORT}"
        restart_worker(services, env, closed, run_folder / "logs", "worker-ollama-down")
        offset = log_file.stat().st_size if log_file.is_file() else 0
        print("Rendering with Ollama unreachable", flush=True)
        result, offset = render_run(
            api, project_id, DOWN_LABEL, DOWN_PROMPT, media_root, analysis, shots, sections,
            log_file, offset, env,
        )  # fmt: skip
        results[DOWN_LABEL] = result
        print(report_table([result]), flush=True)
    finally:
        services.stop_all()

    report["portsFreeAfterStop"] = not any(
        gate.port_in_use(port) for port in (args.backend_port, args.worker_port, args.ollama_port)
    )
    report["runs"] = [asdict(item) | {"facts": asdict(item.facts) if item.facts else None}
                      for item in results.values()]  # fmt: skip
    if all(label in results and results[label].facts for label, _ in RUNS) and results.get(
        DOWN_LABEL
    ):
        report["verdict"] = verdict(results)
    else:
        report["verdict"] = {"passed": False, "lines": "a run produced no plan"}
    report["table"] = report_table(list(results.values()))
    return report


def reevaluate(run_folder: Path) -> dict[str, Any]:
    """Judges the renders of a finished run again, from the plans and analyses on disk."""
    report = json.loads((run_folder / REPORT_FILE).read_text(encoding="utf-8"))
    media_root = run_folder / "media"
    shots = load_shots(media_root)
    results: dict[str, RunResult] = {}
    for row in report["runs"]:
        plan_file = media_root / "renders" / str(row["render_id"]) / "plan.json"
        plan = json.loads(plan_file.read_text(encoding="utf-8"))
        checks = [RampCheck(**check) for check in row["ramp_checks"]]
        fields = {
            **row,
            "facts": plan_facts(plan, shots, report["sections"]),
            "ramp_checks": checks,
        }
        results[row["label"]] = RunResult(**fields)
    report["runs"] = [asdict(item) for item in results.values()]
    report["verdict"] = verdict(results)
    report["table"] = report_table(list(results.values()))
    report["shotTags"] = {
        key: sorted({tag for shot in found for tag in shot["tags"]}) for key, found in shots.items()
    }
    return report


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, help="Folder of *.mp4 and song.wav")
    parser.add_argument("--ollama-exe", type=Path)
    parser.add_argument("--ollama-models", type=Path)
    parser.add_argument("--reevaluate", type=Path, help="A finished run folder to judge again")
    parser.add_argument("--ollama-port", type=int, default=OLLAMA_PORT)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--backend-port", type=int, default=gate.BACKEND_PORT)
    parser.add_argument("--worker-port", type=int, default=gate.WORKER_PORT)
    return parser.parse_args(argv)


def _raise_exit(signal_number: int, _: object) -> None:
    raise SystemExit(128 + signal_number)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_arguments(argv)
    if args.reevaluate is not None:
        report = reevaluate(args.reevaluate)
        (args.reevaluate / REPORT_FILE).write_text(json.dumps(report, indent=1), encoding="utf-8")
        print(report["table"])
        print(json.dumps(report["verdict"], indent=1))
        return 0 if report["verdict"]["passed"] else 1
    if args.inputs is None or args.ollama_exe is None or args.ollama_models is None:
        raise SystemExit("--inputs, --ollama-exe and --ollama-models are required for a run")
    for name in ("SIGTERM", "SIGBREAK"):
        signal.signal(getattr(signal, name), _raise_exit)
    tools = gate.tool_environment()
    os.environ.update(tools)
    run_folder = ROOT / GATE_FOLDER / "runs" / datetime.now().strftime("%Y%m%d-%H%M%S")
    run_folder.mkdir(parents=True)
    report = run_gate(args, run_folder, tools)
    (run_folder / REPORT_FILE).write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(report["table"])
    print(json.dumps(report["verdict"], indent=1))
    print(f"Report: {run_folder / REPORT_FILE}")
    return 0 if report["verdict"]["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
