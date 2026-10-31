"""Raw .OSV stitching on a generated dual-fisheye clip. Spec: specs/08-osmo360.md (rule 3) [T-409]

No real .OSV exists on the build machine. The clips here are made by FFmpeg itself, projecting an
equirect clip to two fisheye circles with the same lens FOV as `osmo_calibration.json`, so these
tests prove the plumbing and the v360 round trip, not the calibration against a real camera.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from app.adapters.ffmpeg_osv import FfmpegOsvStitcher, load_calibration, stitch_graph
from app.adapters.ffmpeg_probe import FfmpegProbe

pytestmark = [
    pytest.mark.gpu,
    pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs FFmpeg"),
]

WIDTH, HEIGHT = 1024, 512
BOX = 90
BOX_AT = (700, 256)  # equirect pixels, left of the back lens seam and off the poles


def ffmpeg(*arguments: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *arguments], check=True)


@pytest.fixture(scope="module")
def equirect(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("osv") / "equirect.mp4"
    graph = (
        f"color=c=black:size={WIDTH}x{HEIGHT}:rate=30:duration=1[bg];"
        f"color=c=red:size={BOX}x{BOX}:rate=30:duration=1[box];"
        f"[bg][box]overlay=x={BOX_AT[0] - BOX // 2}:y={BOX_AT[1] - BOX // 2},format=yuv420p"
    )
    ffmpeg("-filter_complex", graph, "-c:v", "libx264", "-crf", "10", str(path))
    return path


def fisheye(calibration: dict[str, Any]) -> str:
    fov = calibration["fov_degrees"]
    return f"v360=input=equirect:output=dfisheye:h_fov={fov}:v_fov={fov}:w={WIDTH}:h={HEIGHT}"


def red_center(video: Path, width: int, height: int) -> tuple[float, float]:
    raw = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(video)]
        + ["-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True,
        check=True,
    ).stdout
    frame = np.frombuffer(raw, np.uint8).reshape(height, width, 3)
    mask = (frame[:, :, 0] > 150) & (frame[:, :, 1] < 90) & (frame[:, :, 2] < 90)
    ys, xs = np.nonzero(mask)
    assert len(xs) > 50, "the red box is not in the stitched frame"
    return float(xs.mean()), float(ys.mean())


def test_rule_3_one_frame_with_both_lenses_stitches_back_to_equirect(
    equirect: Path, tmp_path: Path
) -> None:
    calibration = load_calibration()
    raw = tmp_path / "CAM_0001.osv.mp4"
    ffmpeg("-i", str(equirect), "-vf", fisheye(calibration), "-c:v", "libx264", str(raw))
    stitched = tmp_path / "stitched.mp4"

    FfmpegOsvStitcher().stitch(raw, stitched)

    info = FfmpegProbe().probe(stitched)
    assert (info.width, info.height) == (WIDTH, HEIGHT)
    x, y = red_center(stitched, WIDTH, HEIGHT)
    assert abs(x - BOX_AT[0]) < 10
    assert abs(y - BOX_AT[1]) < 10


def test_rule_3_two_lens_streams_are_joined_before_the_stitch(
    equirect: Path, tmp_path: Path
) -> None:
    calibration = load_calibration()
    both = tmp_path / "both.mp4"
    ffmpeg("-i", str(equirect), "-vf", fisheye(calibration), "-c:v", "libx264", str(both))
    half = HEIGHT
    raw = tmp_path / "CAM_0002.osv"
    graph = (
        f"[0:v]split[a][b];[a]crop={half}:{half}:0:0[left];[b]crop={half}:{half}:{half}:0[right]"
    )
    ffmpeg(
        *["-i", str(both), "-filter_complex", graph, "-map", "[left]", "-map", "[right]"],
        *["-c:v", "libx264", "-f", "mp4", str(raw)],
    )
    stitched = tmp_path / "stitched2.mp4"

    FfmpegOsvStitcher().stitch(raw, stitched)

    x, y = red_center(stitched, WIDTH, HEIGHT)
    assert abs(x - BOX_AT[0]) < 10
    assert abs(y - BOX_AT[1]) < 10


def test_rule_3_the_graph_joins_two_streams_and_names_the_calibration() -> None:
    calibration = load_calibration()

    two = stitch_graph(calibration, 2, 3840)
    one = stitch_graph(calibration, 1, 3840)

    assert two.startswith("[0:v:0][0:v:1]hstack=inputs=2")
    assert one.startswith("[0:v:0]format")
    assert "input=dfisheye:output=equirect" in two
    assert "w=7680:h=3840" in two
    assert f"ih_fov={calibration['fov_degrees']:g}" in two
    assert calibration["proven_on_real_files"] is False
