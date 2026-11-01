"""Runs the Phase 3 gate on real Osmo 360 footage, through the real app. [T-416]

Spec: specs/10-roadmap.md#phase-3--360--osmo, specs/08-osmo360.md, specs/05-editing-brain.md#b7

Gate text: an Osmo 360 8K clip produces a subject-following reframe with a beat spin on the drop and
a tiny planet at a section change, in 9:16 and 16:9.

Reuses scripts/phase1_gate.py (apps, tus upload, beat check, probing) and scripts/phase2_gate.py
(private Ollama server) and starts only what it stops by PID. The work is split in phases so a
person can look at the footage in between, as the follow point must be chosen by looking:

    analyze   starts the apps, uploads the .OSV files and the song, waits for the stitch and the
              analysis, then checks each stitched file (size, frame count, audio, process end)
    frames    writes equirect frames of a stitched clip so the subject can be found by eye
    render    renders the ratios with the real `followPoint` and measures every gate line
    measure   judges finished renders again from plan.json and the files on disk

Usage, from worker/ (see --help of each phase):
    uv run python ..\\scripts\\phase3_gate.py analyze --osmo <folder> --song <wav>
    uv run python ..\\scripts\\phase3_gate.py frames --run <run folder> --clip <osv> --times 1 5
    uv run python ..\\scripts\\phase3_gate.py render --run <run folder> --follow 0.5 0.5 2.0
"""

from __future__ import annotations

import argparse
import json
import math
import os
import signal
import subprocess
import sys
import time
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import phase1_gate as gate  # noqa: E402
import phase2_gate as phase2  # noqa: E402

ROOT = gate.ROOT
GATE_FOLDER = Path("media") / "phase3_gate"
STATE_FILE = "state.json"
STITCH_WIDTH = 7680
STITCH_HEIGHT = 3840
OLLAMA_PORT = 18434
FPS = 30
SPIN_MIN_DEGREES = 330.0
SPIN_MAX_BEATS = 1.5
TINY_PLANET = "tinyplanet"
WHIP_DEGREES_PER_FRAME = 12.0
LENGTH_SEC = 40
MODE = "fast"
STYLE = "auto"
SEED = 3416
RATIOS = ("9:16", "16:9")
EPSILON = 1e-6

# Pure helpers, covered by test_phase3_gate.py


def parse_follow(values: Sequence[float]) -> dict[str, float]:
    """The API's followPoint: x and y as shares of the equirect frame, timeSec in the clip."""
    x, y, time_sec = values
    if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0) or time_sec < 0.0:
        raise gate.GateError(f"followPoint {values} needs x and y in 0..1 and a time of 0 or more")
    return {"x": x, "y": y, "timeSec": time_sec}


def section_kind(time_sec: float, sections: Sequence[dict[str, Any]]) -> str:
    for section in sections:
        if section["start"] <= time_sec < section["end"]:
            return section["kind"].lower()
    return "unknown"


def is_section_change(time_sec: float, sections: Sequence[dict[str, Any]], slack: float) -> bool:
    """True when `time_sec` is within `slack` of a boundary between two sections."""
    return any(abs(time_sec - section["start"]) <= slack for section in sections[1:])


def nearest_beat_offset(time_sec: float, beats: Sequence[float]) -> float:
    return min((abs(time_sec - beat) for beat in beats), default=math.inf)


def stitch_facts(
    stitched: dict[str, Any], source_frames: int, audio_streams: int
) -> dict[str, Any]:
    """The stitch criteria of one clip: 7680x3840, the source's frame count, audio kept."""
    size_ok = (stitched["width"], stitched["height"]) == (STITCH_WIDTH, STITCH_HEIGHT)
    frames_ok = stitched["frames"] == source_frames
    return {
        "size": f"{stitched['width']}x{stitched['height']}",
        "sizeOk": size_ok,
        "frames": stitched["frames"],
        "sourceFrames": source_frames,
        "framesOk": frames_ok,
        "audioKept": audio_streams > 0,
        "pixFmt": stitched.get("pix_fmt"),
        "codec": stitched.get("codec_name"),
        "passed": size_ok and frames_ok and audio_streams > 0,
    }


def spins(plan: dict[str, Any], beat_sec: float) -> list[dict[str, Any]]:
    """Every full yaw turn in the camera keyframes: where it starts, how long, how far."""
    found = []
    for segment in plan["segments"]:
        keys = (segment.get("camera360") or {}).get("keyframes", [])
        for first, second in zip(keys, keys[1:], strict=False):
            turned = abs(second["yaw"] - first["yaw"])
            span = second["t"] - first["t"]
            if turned >= SPIN_MIN_DEGREES and span <= SPIN_MAX_BEATS * beat_sec + EPSILON:
                found.append(
                    {
                        "segment": segment["id"],
                        "start": round(segment["at"] + first["t"], 4),
                        "seconds": round(span, 4),
                        "degrees": round(turned, 1),
                    }
                )
    return found


def tiny_planets(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Every camera span that touches a tiny planet: where it starts and ends in edit time."""
    found = []
    for segment in plan["segments"]:
        keys = (segment.get("camera360") or {}).get("keyframes", [])
        for first, second in zip(keys, keys[1:], strict=False):
            if TINY_PLANET in (first.get("projection"), second.get("projection")):
                found.append(
                    {
                        "segment": segment["id"],
                        "start": round(segment["at"] + first["t"], 4),
                        "end": round(segment["at"] + second["t"], 4),
                        "segmentEnd": round(segment["at"] + segment["duration"], 4),
                    }
                )
    return found


def yaw_whips(
    yaws: Sequence[float], limit: float, skip: Sequence[tuple[int, int]] = ()
) -> list[tuple[int, float]]:
    """Frames where the wrapped yaw jumps by more than `limit` degrees, outside `skip` spans."""
    whips = []
    for index in range(1, len(yaws)):
        if any(low <= index <= high for low, high in skip):
            continue
        step = (yaws[index] - yaws[index - 1] + 180.0) % 360.0 - 180.0
        if abs(step) > limit:
            whips.append((index, round(step, 1)))
    return whips


def share(flags: Sequence[bool]) -> float:
    return sum(flags) / len(flags) if flags else 0.0


# Processes and API


def stream_counts(path: Path, env: dict[str, str]) -> list[dict[str, Any]]:
    """Streams of a file with their packet counts (a frame count without decoding)."""
    output = subprocess.run(
        [
            "ffprobe", "-v", "error", "-count_packets", "-show_entries",
            "stream=index,codec_type,codec_name,pix_fmt,width,height,nb_read_packets",
            "-of", "json", str(path),
        ],
        capture_output=True, text=True, env=env, check=True,
    ).stdout  # fmt: skip
    return json.loads(output)["streams"]


def lens_frames(source: Path, env: dict[str, str]) -> int:
    """Frames of the first lens stream of an .OSV (the MJPEG cover is not a lens)."""
    for stream in stream_counts(source, env):
        if stream["codec_type"] == "video" and stream["codec_name"] == "hevc":
            return int(stream["nb_read_packets"])
    raise gate.GateError(f"{source} has no lens stream")


def stitched_summary(path: Path, env: dict[str, str]) -> tuple[dict[str, Any], int]:
    streams = stream_counts(path, env)
    video = next(s for s in streams if s["codec_type"] == "video")
    audio = sum(s["codec_type"] == "audio" for s in streams)
    summary = {
        "width": video["width"], "height": video["height"], "pix_fmt": video.get("pix_fmt"),
        "codec_name": video["codec_name"], "frames": int(video["nb_read_packets"]),
    }  # fmt: skip
    return summary, audio


def processes_named(*names: str) -> list[str]:
    """Image names of running processes among `names`, to show a stitch left nothing behind."""
    listing = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True)
    running = {row.split('","')[0].strip('"').lower() for row in listing.stdout.splitlines() if row}
    return sorted(name for name in names if name.lower() in running)


def load_state(run_folder: Path) -> dict[str, Any]:
    return json.loads((run_folder / STATE_FILE).read_text(encoding="utf-8"))


def save_state(run_folder: Path, state: dict[str, Any]) -> None:
    (run_folder / STATE_FILE).write_text(json.dumps(state, indent=1), encoding="utf-8")


class Session:
    """The apps and a private Ollama on private ports, stopped by PID when the block ends."""

    def __init__(self, args: argparse.Namespace, run_folder: Path, tools: dict[str, str]) -> None:
        self.args = args
        self.run_folder = run_folder
        relative = run_folder.relative_to(ROOT)
        self.env = gate.service_environment(tools, relative, args.backend_port, args.worker_port)
        self.env["OLLAMA_URL"] = f"http://127.0.0.1:{args.ollama_port}"
        self.services = gate.Services(run_folder / "logs")
        self.media_root = run_folder / "media"

    def __enter__(self) -> Session:
        for port in (self.args.backend_port, self.args.worker_port, self.args.ollama_port):
            if gate.port_in_use(port):
                raise gate.GateError(f"Port {port} is in use. The gate touches nothing running.")
        for folder in (self.media_root, self.run_folder / "data", self.run_folder / "logs"):
            folder.mkdir(parents=True, exist_ok=True)
        try:
            phase2.start_ollama(
                self.services, self.args.ollama_exe, self.args.ollama_models,
                self.args.ollama_port, self.env,
            )  # fmt: skip
            gate.start_services(self.services, self.env, self.args.backend_port)
        except BaseException:
            self.services.stop_all()
            raise
        return self

    def __exit__(self, *_: object) -> None:
        self.services.stop_all()

    @property
    def log_file(self) -> Path:
        return self.run_folder / "logs" / "worker.log"


# Phases


def phase_analyze(args: argparse.Namespace, tools: dict[str, str]) -> int:
    osmo = sorted(p for p in args.osmo.iterdir() if p.suffix.lower() == ".osv")
    if not osmo:
        raise gate.GateError(f"No .OSV files in {args.osmo}")
    run_folder = ROOT / GATE_FOLDER / "runs" / datetime.now().strftime("%Y%m%d-%H%M%S")
    run_folder.mkdir(parents=True)
    state: dict[str, Any] = {"started": datetime.now().isoformat(), "clips": {}}
    with Session(args, run_folder, tools) as session:
        api = gate.Api(args.backend_port)
        project_id = api.post("/api/projects", {"name": "Phase 3 gate"})["id"]
        state["projectId"] = project_id
        began = time.monotonic()
        for path in [*osmo, args.song]:
            api.upload(project_id, path)
            print(f"Uploaded {path.name} after {time.monotonic() - began:.0f} s", flush=True)
        done_at: dict[str, float] = {}
        expected = len(osmo) + 1
        while time.monotonic() - began < gate.ANALYSIS_TIMEOUT_SEC:
            session.services.require_running()
            assets = api.get(f"/api/projects/{project_id}/assets")
            for asset in assets:
                if asset["analysisStatus"] == "FAILED":
                    raise gate.GateError(f"Analysis failed for {asset['filename']}")
                if asset["analysisStatus"] == "DONE" and asset["id"] not in done_at:
                    done_at[asset["id"]] = round(time.monotonic() - began, 1)
                    print(
                        f"{asset['filename']} analysed after {done_at[asset['id']]} s", flush=True
                    )
            if len(assets) == expected and len(done_at) == expected:
                break
            time.sleep(gate.POLL_SEC)
        else:
            raise gate.GateError("Analysis did not finish in time")
        state["analysisSeconds"] = round(time.monotonic() - began, 1)
        state["doneAt"] = done_at
        assets = api.get(f"/api/projects/{project_id}/assets")
        state["assets"] = assets
        time.sleep(5)
        state["processesAfterAnalysis"] = processes_named("ffmpeg.exe", "ffprobe.exe")
        for asset in assets:
            source = next((p for p in osmo if p.name == asset["filename"]), None)
            if source is None:
                continue
            stitched = session.media_root / "stitched" / f"{asset['id']}.mp4"
            summary, audio = stitched_summary(stitched, session.env)
            facts = stitch_facts(summary, lens_frames(source, session.env), audio)
            facts["stitchedFile"] = str(stitched)
            facts["analysedAtSec"] = done_at[asset["id"]]
            facts["assetId"] = asset["id"]
            state["clips"][asset["filename"]] = facts
            print(json.dumps({asset["filename"]: facts}, indent=1), flush=True)
    state["portsFreeAfterStop"] = not any(
        gate.port_in_use(p) for p in (args.backend_port, args.worker_port, args.ollama_port)
    )
    save_state(run_folder, state)
    print(f"Run folder: {run_folder}")
    return 0 if all(c["passed"] for c in state["clips"].values()) else 1


def phase_frames(args: argparse.Namespace, tools: dict[str, str]) -> int:
    """Equirect frames of one stitched clip, scaled down, for choosing the follow point by eye."""
    clip = load_state(args.run)["clips"][args.clip]
    args.out.mkdir(parents=True, exist_ok=True)
    for moment in args.times:
        target = args.out / f"{Path(args.clip).stem}_{moment:05.2f}.jpg"
        subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", str(moment),
                "-i", clip["stitchedFile"], "-frames:v", "1", "-vf", f"scale={args.width}:-2",
                "-q:v", "3", str(target),
            ],
            env=tools, check=True,
        )  # fmt: skip
        print(target)
    return 0


def yaw_per_frame(segment: dict[str, Any], fps: int) -> list[float]:
    """The planned yaw of every output frame of one 360 segment (linear between keyframes)."""
    keys = (segment.get("camera360") or {}).get("keyframes", [])
    frames = round(segment["duration"] * fps)
    if not keys:
        return [0.0] * frames
    yaws = []
    for frame in range(frames):
        at = frame / fps
        later = next((k for k in keys if k["t"] >= at), keys[-1])
        earlier = next((k for k in reversed(keys) if k["t"] <= at), keys[0])
        if later["t"] - earlier["t"] < EPSILON:
            yaws.append(earlier["yaw"])
        else:
            mix = (at - earlier["t"]) / (later["t"] - earlier["t"])
            yaws.append(earlier["yaw"] + (later["yaw"] - earlier["yaw"]) * mix)
    return yaws


def source_coverage(plan: dict[str, Any], durations: dict[str, float]) -> dict[str, Any]:
    """How much of each clip the edit shows and how much of it repeats (source seconds)."""
    per_asset: dict[str, list[tuple[float, float]]] = {}
    for segment in plan["segments"]:
        per_asset.setdefault(segment["assetId"], []).append((segment["srcIn"], segment["srcOut"]))
    report: dict[str, Any] = {}
    used_total = unique_total = 0.0
    for asset, spans in per_asset.items():
        used = sum(high - low for low, high in spans)
        merged: list[list[float]] = []
        for low, high in sorted(spans):
            if merged and low <= merged[-1][1] + EPSILON:
                merged[-1][1] = max(merged[-1][1], high)
            else:
                merged.append([low, high])
        unique = sum(high - low for low, high in merged)
        used_total += used
        unique_total += unique
        report[asset] = {
            "segments": len(spans), "usedSec": round(used, 2), "uniqueSec": round(unique, 2),
            "clipSec": durations.get(asset),
        }  # fmt: skip
    report["total"] = {
        "usedSec": round(used_total, 2),
        "uniqueSec": round(unique_total, 2),
        "repeatedShare": round(1 - unique_total / used_total, 3) if used_total else 0.0,
    }
    return report


def expected_size(ratio: str) -> tuple[int, int]:
    """4K output: the long side is 3840."""
    wide, high = (int(part) for part in ratio.split(":"))
    return (3840, round(3840 * high / wide)) if wide >= high else (round(3840 * wide / high), 3840)


def follow_lines(log_text: str) -> list[str]:
    """The worker's own lines about the subject track, to say which track the plan used."""
    return [line[:400] for line in log_text.splitlines() if "follow" in line or "sam2" in line]


def run_render(
    session: Session, api: gate.Api, project_id: str, settings: dict[str, Any]
) -> dict[str, Any]:
    offset = session.log_file.stat().st_size if session.log_file.is_file() else 0
    began = time.monotonic()
    with gate.LoadSampler() as sampler:
        render_id = api.post(f"/api/projects/{project_id}/renders", settings)["id"]
        status, error = gate._wait_for_render(api, render_id)
    seconds = round(time.monotonic() - began, 1)
    text, _ = phase2.log_slice(session.log_file, offset)
    load = sampler.load()
    return {
        "renderId": render_id, "status": status, "error": error, "seconds": seconds,
        "settings": settings, "followLog": follow_lines(text),
        "vramMbPeak": load.vram_mb_peak, "gpuPercentMean": load.gpu_percent_mean,
    }  # fmt: skip


def phase_render(args: argparse.Namespace, tools: dict[str, str]) -> int:
    state = load_state(args.run)
    follow = parse_follow(args.follow) if args.follow else None
    runs = state.setdefault("renders", {})
    with Session(args, args.run, tools) as session:
        api = gate.Api(args.backend_port)
        for ratio in args.ratios:
            settings: dict[str, Any] = {
                "ratio": ratio, "quality": "4K", "fps": FPS, "style": args.style,
                "mode": args.mode, "lengthSec": args.length, "seed": args.seed,
            }  # fmt: skip
            if follow:
                settings["followPoint"] = follow
            if args.prompt:
                settings["prompt"] = args.prompt
            print(f"Rendering {ratio}: {settings}", flush=True)
            session.services.require_running()
            result = run_render(session, api, state["projectId"], settings)
            runs[f"{args.tag}-{ratio}"] = result
            print(json.dumps(result, indent=1), flush=True)
            save_state(args.run, state)
    return 0 if all(r["status"] == "DONE" for r in runs.values()) else 1


def read_frames(
    video: Path, width: int, height: int, fps: float | None, env: dict[str, str]
) -> list:
    """Frames of the finished file, scaled to width x height, as numpy arrays (BGR)."""
    import numpy

    filters = f"scale={width}:{height}:flags=fast_bilinear"
    if fps is not None:
        filters = f"fps={fps}," + filters
    process = subprocess.Popen(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(video), "-map", "0:v:0",
         "-vf", filters, "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
        stdout=subprocess.PIPE, env=env,
    )  # fmt: skip
    size = width * height * 3
    frames = []
    assert process.stdout is not None
    while True:
        data = process.stdout.read(size)
        if len(data) < size:
            break
        frames.append(numpy.frombuffer(data, dtype=numpy.uint8).reshape(height, width, 3))
    process.wait()
    return frames


def sheet(frames: list, columns: int, labels: Sequence[str], path: Path) -> None:
    import cv2
    import numpy

    height, width = frames[0].shape[:2]
    rows = math.ceil(len(frames) / columns)
    canvas = numpy.zeros((rows * height, columns * width, 3), dtype=numpy.uint8)
    for index, frame in enumerate(frames):
        row, column = divmod(index, columns)
        tile = frame.copy()
        cv2.putText(tile, labels[index], (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
        canvas[row * height : (row + 1) * height, column * width : (column + 1) * width] = tile
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), canvas, [cv2.IMWRITE_JPEG_QUALITY, 85])


def detect_rider(frames: list, model_path: Path) -> list[dict[str, Any]]:
    """YOLO person, bicycle and motorcycle boxes per frame, as shares of the frame."""
    from ultralytics import YOLO

    model = YOLO(str(model_path))
    found = []
    for frame in frames:
        height, width = frame.shape[:2]
        result = model.predict(frame, classes=[0, 1, 3], conf=0.25, verbose=False, device="cpu")[0]
        boxes = [
            {"cls": int(b.cls), "conf": round(float(b.conf), 2),
             "cx": round(float((b.xyxy[0][0] + b.xyxy[0][2]) / 2 / width), 3),
             "cy": round(float((b.xyxy[0][1] + b.xyxy[0][3]) / 2 / height), 3),
             "h": round(float((b.xyxy[0][3] - b.xyxy[0][1]) / height), 3)}
            for b in result.boxes
        ]  # fmt: skip
        found.append({"boxes": boxes})
    return found


def yaw_steps(plan: dict[str, Any], spin_list: list[dict[str, Any]], fps: int, limit: float):
    """Largest yaw step per frame of the planned camera outside the spins, and the whips."""
    whips, largest = [], 0.0
    for segment in plan["segments"]:
        if segment["type"] != "video360":
            continue
        yaws = yaw_per_frame(segment, fps)
        skip = [
            (
                round((s["start"] - segment["at"]) * fps),
                round((s["start"] - segment["at"] + s["seconds"]) * fps) + 1,
            )
            for s in spin_list
            if s["segment"] == segment["id"]
        ]
        for index in range(1, len(yaws)):
            if any(low <= index <= high for low, high in skip):
                continue
            largest = max(largest, abs((yaws[index] - yaws[index - 1] + 180) % 360 - 180))
        whips += [(segment["id"], i, d) for i, d in yaw_whips(yaws, limit, skip)]
    return largest, whips


def phase_measure(args: argparse.Namespace, tools: dict[str, str]) -> int:
    state = load_state(args.run)
    media_root = args.run / "media"
    analysis = gate.song_analysis_file(media_root)
    music = json.loads(analysis.read_text(encoding="utf-8"))["music"]
    sections, beats = music["sections"], [b["time"] for b in music["beats"]]
    durations = {a["id"]: a.get("durationSec") for a in state.get("assets", [])}
    report: dict[str, Any] = {"bpm": music["bpm"], "sections": sections}
    beat_sec = 60.0 / music["bpm"]
    for key, run in state["renders"].items():
        if (args.only and key not in args.only) or run["status"] != "DONE":
            continue
        folder = media_root / "renders" / run["renderId"]
        plan = json.loads((folder / "plan.json").read_text(encoding="utf-8"))
        fps, origin = plan["output"]["fps"], plan["music"]["start"]
        ratio = run["settings"]["ratio"]
        check = gate.run_beat_check(folder, analysis, tools)
        stream = gate.probe_summary(folder / "final.mp4", tools)
        spin_list, planet_list = spins(plan, beat_sec), tiny_planets(plan)
        for item in spin_list:
            item["sectionKind"] = section_kind(item["start"], sections)
            item["beatOffsetMs"] = round(nearest_beat_offset(item["start"], beats) * 1000, 1)
            item["editSec"] = round(item["start"] - origin, 3)
        for item in planet_list:
            item["sectionKind"] = section_kind(item["start"], sections)
            item["segmentEndIsSectionChange"] = is_section_change(
                item["segmentEnd"], sections, 1.5 * beat_sec
            )
            item["editSec"] = round(item["start"] - origin, 3)
        largest, whips = yaw_steps(plan, spin_list, fps, args.whip)
        entry: dict[str, Any] = {
            "ratio": ratio, "renderId": run["renderId"], "renderSeconds": run["seconds"],
            "size": f"{stream.get('width')}x{stream.get('height')}",
            "sizeOk": (stream.get("width"), stream.get("height")) == expected_size(ratio),
            "codec": stream.get("codec_name"), "profile": stream.get("profile"),
            "pixFmt": stream.get("pix_fmt"),
            "beatCheck": {"cuts": check.cuts, "worstMs": check.worst_ms, "frameMs": check.frame_ms,
                          "frames": f"{check.frames_actual}/{check.frames_expected}",
                          "passed": check.passed},
            "style": plan["style"], "segments": len(plan["segments"]),
            "video360Segments": sum(s["type"] == "video360" for s in plan["segments"]),
            "spins": spin_list, "tinyPlanets": planet_list,
            "planLog": plan.get("log", []), "followLog": run["followLog"],
            "maxYawStepDegPerFrameOutsideSpin": round(largest, 2),
            "yawWhipsOverLimit": whips,
            "sourceCoverage": source_coverage(plan, durations),
        }  # fmt: skip
        report[key] = entry
        print(json.dumps(entry, indent=1), flush=True)
    out = args.run / "measure.json"
    out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"Report: {out}")
    return 0


def phase_sheets(args: argparse.Namespace, tools: dict[str, str]) -> int:
    """Contact sheets and rider detection of one finished render, kept outside git."""
    run = load_state(args.run)["renders"][args.key]
    folder = args.run / "media" / "renders" / run["renderId"]
    plan = json.loads((folder / "plan.json").read_text(encoding="utf-8"))
    fps, origin = plan["output"]["fps"], plan["music"]["start"]
    wide, high = expected_size(run["settings"]["ratio"])
    tile_w = 360 if wide > high else 202
    tile_h = round(tile_w * high / wide / 2) * 2
    video = folder / "final.mp4"
    prefix = args.key.replace(":", "x")
    tiles = read_frames(video, tile_w, tile_h, 1.0, tools)
    path = args.out / f"{prefix}_overview.jpg"
    sheet(tiles, 8, [f"{i}s" for i in range(len(tiles))], path)
    print(path)
    every = read_frames(video, tile_w, tile_h, None, tools)
    windows = [
        ("spin", n, i["start"], i["start"] + i["seconds"])
        for n, i in enumerate(spins(plan, 60.0 / args.bpm))
    ] + [("planet", n, i["start"], i["end"]) for n, i in enumerate(tiny_planets(plan))]
    for name, number, begin, end in windows:
        first = max(0, round((begin - origin) * fps) - 3)
        last = min(len(every), round((end - origin) * fps) + 6)
        picks = list(range(first, last, args.step))[:40]
        path = args.out / f"{prefix}_{name}{number}.jpg"
        sheet([every[i] for i in picks], 8, [f"f{i}" for i in picks], path)
        print(path)
    if args.detect:
        size = (960, 540) if wide > high else (540, 960)
        found = detect_rider(read_frames(video, *size, 2.0, tools), ROOT / "models/yolo/yolo11n.pt")
        path = args.out / f"{prefix}_detections.json"
        path.write_text(json.dumps(found), encoding="utf-8")
        print(path)
    return 0


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-port", type=int, default=gate.BACKEND_PORT)
    parser.add_argument("--worker-port", type=int, default=gate.WORKER_PORT)
    parser.add_argument("--ollama-port", type=int, default=OLLAMA_PORT)
    parser.add_argument("--ollama-exe", type=Path)
    parser.add_argument("--ollama-models", type=Path)
    sub = parser.add_subparsers(dest="phase", required=True)
    analyze = sub.add_parser("analyze")
    analyze.add_argument("--osmo", type=Path, required=True)
    analyze.add_argument("--song", type=Path, required=True)
    frames = sub.add_parser("frames")
    frames.add_argument("--run", type=Path, required=True)
    frames.add_argument("--clip", required=True, help="File name of the .OSV")
    frames.add_argument("--times", type=float, nargs="+", required=True)
    frames.add_argument("--out", type=Path, required=True)
    frames.add_argument("--width", type=int, default=2400)
    render = sub.add_parser("render")
    render.add_argument("--run", type=Path, required=True)
    render.add_argument("--follow", type=float, nargs=3, metavar=("X", "Y", "TIME_SEC"))
    render.add_argument("--ratios", nargs="+", default=list(RATIOS))
    render.add_argument("--length", type=int, default=LENGTH_SEC)
    render.add_argument("--mode", default=MODE)
    render.add_argument("--style", default=STYLE)
    render.add_argument("--seed", type=int, default=SEED)
    render.add_argument("--prompt")
    render.add_argument("--tag", default="r1")
    measure = sub.add_parser("measure")
    measure.add_argument("--run", type=Path, required=True)
    measure.add_argument("--only", nargs="*")
    measure.add_argument("--whip", type=float, default=WHIP_DEGREES_PER_FRAME)
    sheets = sub.add_parser("sheets")
    sheets.add_argument("--run", type=Path, required=True)
    sheets.add_argument("--key", required=True)
    sheets.add_argument("--out", type=Path, required=True)
    sheets.add_argument("--bpm", type=float, default=84.96)
    sheets.add_argument("--step", type=int, default=2)
    sheets.add_argument("--detect", action="store_true")
    return parser.parse_args(argv)


def _raise_exit(signal_number: int, _: object) -> None:
    raise SystemExit(128 + signal_number)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_arguments(argv)
    for name in ("SIGTERM", "SIGBREAK"):
        signal.signal(getattr(signal, name), _raise_exit)
    tools = gate.tool_environment()
    os.environ.update(tools)
    if args.ollama_exe is None:
        args.ollama_exe = Path(tools["OLLAMA_DIR"]) / "ollama.exe"
    if args.ollama_models is None:
        args.ollama_models = ROOT / "models" / "ollama"
    phases = {
        "analyze": phase_analyze,
        "frames": phase_frames,
        "render": phase_render,
        "measure": phase_measure,
        "sheets": phase_sheets,
    }
    return phases[args.phase](args, tools)


if __name__ == "__main__":
    sys.exit(main())
