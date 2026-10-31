"""The SAM 2 follower's view, chunking and wrap on a real generated equirect video.

Spec: specs/08-osmo360.md (rule 5, subject follow), specs/05-editing-brain.md#b7 [T-415]

Runs on the CPU with real FFmpeg (libx264, 2 threads) and real OpenCV remapping. The segmenter
is a fake that thresholds the bright subject in the view, so this proves the geometry, the
chunking, the re-centering and the 0/360 wrap, not SAM 2 itself. The SAM 2 run is
tests/integration/test_subject_follow_gpu.py.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest

from app.adapters.ffmpeg_frame_media import FfmpegFrameMedia
from app.adapters.sam2_subject_follower import Sam2SubjectFollower
from app.domain.models import FollowPoint
from app.ports.segmenter import Point

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs FFmpeg on PATH")

WIDTH, HEIGHT = 1024, 512
FPS = 8
SECONDS = 6
START_YAW, SPEED = 160.0, 10.0  # degrees, degrees per second: 160 to 220 crosses the seam
RADIUS = 22


def subject_yaw(time: float) -> float:
    return START_YAW + SPEED * time


def share_x(yaw: float) -> float:
    return ((yaw + 180.0) % 360.0) / 360.0


def make_video(folder: Path) -> Path:
    frames = folder / "png"
    frames.mkdir()
    for index in range(FPS * SECONDS):
        image = np.full((HEIGHT, WIDTH, 3), 40, dtype=np.uint8)
        center_x = share_x(subject_yaw(index / FPS)) * WIDTH
        for shift in (-WIDTH, 0, WIDTH):  # drawn twice when it straddles the seam
            cv2.circle(image, (round(center_x + shift), HEIGHT // 2), RADIUS, (255, 255, 255), -1)
        cv2.imwrite(str(frames / f"{index + 1:06d}.png"), image)
    video = folder / "equirect.mp4"
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-threads", "2",
            "-framerate", str(FPS), "-i", str(frames / "%06d.png"),
            "-c:v", "libx264", "-crf", "10", "-pix_fmt", "yuv420p", str(video),
        ],
        check=True,
    )  # fmt: skip
    return video


class BrightSegmenter:
    """Stands in for SAM 2: the bright blob in each view is the subject."""

    def __init__(self) -> None:
        self.calls = 0

    def track(
        self, frames: Sequence[Path], points: Sequence[Point], folder: Path
    ) -> tuple[Path, ...]:
        self.calls += 1
        folder.mkdir(parents=True, exist_ok=True)
        paths = []
        for index, frame in enumerate(frames, start=1):
            view: Any = cv2.imread(str(frame), cv2.IMREAD_GRAYSCALE)
            path = folder / f"{index:06d}.png"
            cv2.imwrite(str(path), ((view > 200) * 255).astype(np.uint8))
            paths.append(path)
        return tuple(paths)


def seam_distance(x: float, expected: float) -> float:
    return abs((x - expected + 0.5) % 1.0 - 0.5) * 360.0


def test_08_rule5_the_follower_tracks_a_subject_across_the_seam_in_chunks(tmp_path: Path) -> None:
    video = make_video(tmp_path)
    segmenter = BrightSegmenter()
    follower = Sam2SubjectFollower(FfmpegFrameMedia(), segmenter)
    tap = FollowPoint(share_x(START_YAW), 0.5, 0.0)

    track = follower.follow(video, tap, 0.0, 5.0, tmp_path / "work")

    assert track.lost == ()
    assert track.samples[0].time == 0.0
    assert track.samples[-1].time == pytest.approx(5.0, abs=0.3)
    assert segmenter.calls >= 3  # 2 s chunks, re-centered on the subject each time
    for sample in track.samples:
        assert seam_distance(sample.x, share_x(subject_yaw(sample.time))) < 3.0
    xs = [sample.x for sample in track.samples]
    assert min(xs) < 0.1 and max(xs) > 0.9  # it really did cross the 0/360 seam
    steps = [seam_distance(second, first) for first, second in zip(xs, xs[1:], strict=False)]
    assert max(steps) < 5.0  # 2.5 degrees per sample, never a whip


def test_08_rule5_the_follower_tracks_backward_from_a_tap_in_the_middle(tmp_path: Path) -> None:
    video = make_video(tmp_path)
    follower = Sam2SubjectFollower(FfmpegFrameMedia(), BrightSegmenter())
    tap = FollowPoint(share_x(subject_yaw(3.0)), 0.5, 3.0)

    track = follower.follow(video, tap, 0.5, 5.0, tmp_path / "work")

    times = [sample.time for sample in track.samples]
    assert times == sorted(times)
    assert times[0] == pytest.approx(0.5, abs=0.01)
    for sample in track.samples:
        assert seam_distance(sample.x, share_x(subject_yaw(sample.time))) < 3.0


def test_08_rule5_an_empty_mask_ends_the_track_and_reports_where(tmp_path: Path) -> None:
    video = make_video(tmp_path)

    class VanishingSegmenter(BrightSegmenter):
        def track(
            self, frames: Sequence[Path], points: Sequence[Point], folder: Path
        ) -> tuple[Path, ...]:
            paths = super().track(frames, points, folder)
            for path in paths[3:]:  # the subject disappears at the fourth frame of each chunk
                cv2.imwrite(str(path), np.zeros((640, 640), dtype=np.uint8))
            return paths

    follower = Sam2SubjectFollower(FfmpegFrameMedia(), VanishingSegmenter())
    tap = FollowPoint(share_x(START_YAW), 0.5, 0.0)

    track = follower.follow(video, tap, 0.0, 5.0, tmp_path / "work")

    assert [s.time for s in track.samples] == pytest.approx([0.0, 0.25, 0.5])
    assert track.lost == pytest.approx((0.75,))
