"""Checks that every cut in a render is within one frame of the beat grid.

Spec: specs/10-roadmap.md#phase-1--core-engine. The grid is the beats plus their midpoints
(ADR-011). Compares the plan's cuts with the frames the file really contains, so a render that
drifted from its plan fails here.

Usage: python scripts/check_beats.py media/renders/<renderId> media/cache/<songHash>/analysis.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from bisect import bisect_left
from collections.abc import Sequence
from pathlib import Path


def beat_grid(beats: Sequence[float]) -> list[float]:
    grid: list[float] = []
    for earlier, later in zip(beats, beats[1:], strict=False):
        grid.extend((earlier, (earlier + later) / 2))
    grid.append(beats[-1])
    return grid


def distance_to_grid(time: float, grid: Sequence[float]) -> float:
    position = bisect_left(grid, time)
    near = grid[max(0, position - 1) : position + 1]
    return min(abs(time - point) for point in near)


def cut_times(plan: dict) -> list[float]:
    """Where each cut really lands: whole frames counted from the start of the edit."""
    fps = plan["output"]["fps"]
    start = plan["music"]["start"]
    return [
        start + round((segment["at"] - start) * fps) / fps for segment in plan["segments"]
    ]


def worst_offset(plan: dict, beats: Sequence[float]) -> float:
    grid = beat_grid(beats)
    return max(distance_to_grid(time, grid) for time in cut_times(plan))


def frame_count(video: Path) -> int:
    output = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-count_packets",
            "-show_entries",
            "stream=nb_read_packets",
            "-of",
            "csv=p=0",
            str(video),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return int(output.stdout.strip().strip(","))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("render_folder", type=Path)
    parser.add_argument("song_analysis", type=Path)
    args = parser.parse_args(argv)

    plan = json.loads((args.render_folder / "plan.json").read_text(encoding="utf-8"))
    song = json.loads(args.song_analysis.read_text(encoding="utf-8"))
    beats = [beat["time"] for beat in song["music"]["beats"]]
    fps = plan["output"]["fps"]
    frame = 1.0 / fps

    worst = worst_offset(plan, beats)
    expected_frames = round((plan["music"]["end"] - plan["music"]["start"]) * fps)
    actual_frames = frame_count(args.render_folder / "final.mp4")

    print(f"cuts: {len(plan['segments'])}, worst offset from the grid: {worst * 1000:.1f} ms")
    print(f"one frame is {frame * 1000:.1f} ms; frames expected {expected_frames}, got {actual_frames}")
    passed = worst <= frame and actual_frames == expected_frames
    print("PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
