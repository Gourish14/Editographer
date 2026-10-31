"""The real video stack on generated clips.

Spec: specs/05-editing-brain.md#b2-shot-scoring-scoringpy [T-111]
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from app.adapters.opencv_frame_sampler import OpenCvFrameSampler
from app.adapters.scenedetect_shots import SceneDetectShots
from app.application.analyze_shots import AnalyzeShots
from tests.unit.shot_fakes import FakeEncoder, FakeObjects

FACE_MODEL = (
    Path(__file__).resolve().parents[3] / "models" / "mediapipe" / "blaze_face_short_range.tflite"
)

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or not FACE_MODEL.exists(),
    reason="needs FFmpeg and the face model from setup.bat",
)


def generate(target: Path, *arguments: str) -> Path:
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *arguments, str(target)],
        check=True,
    )
    return target


@pytest.fixture(scope="module")
def two_shots(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Four seconds of moving test pattern, a hard cut, then four seconds of near-black."""
    target = tmp_path_factory.mktemp("clips") / "two_shots.mp4"
    return generate(
        target,
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=1280x720:rate=30:duration=4",
        "-f",
        "lavfi",
        "-i",
        "color=c=0x050505:size=1280x720:rate=30:duration=4",
        "-filter_complex",
        "[0:v][1:v]concat=n=2:v=1",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
    )


@pytest.fixture(scope="module")
def analyzed(two_shots: Path) -> tuple[object, ...]:
    sampler = OpenCvFrameSampler(FACE_MODEL)
    use_case = AnalyzeShots(SceneDetectShots(), sampler, FakeObjects(), FakeEncoder())
    return use_case.run(two_shots, 8.0)


def test_b2_a_hard_cut_splits_the_clip_into_two_shots(analyzed: tuple[object, ...]) -> None:
    assert len(analyzed) == 2
    first, second = analyzed
    assert first.end == pytest.approx(4.0, abs=0.1)  # type: ignore[attr-defined]
    assert second.start == pytest.approx(4.0, abs=0.1)  # type: ignore[attr-defined]


def test_b2_the_moving_shot_has_more_motion_than_the_still_one(
    analyzed: tuple[object, ...],
) -> None:
    first, second = analyzed

    assert first.motion > second.motion  # type: ignore[attr-defined]


def test_b2_the_dark_shot_measures_dark(analyzed: tuple[object, ...]) -> None:
    first, second = analyzed

    assert second.luma < 0.08 < first.luma  # type: ignore[attr-defined]


def test_b2_frames_are_sampled_at_4_fps(two_shots: Path) -> None:
    frames = OpenCvFrameSampler(FACE_MODEL).sample(two_shots)

    assert len(frames) == pytest.approx(8 * 4, abs=2)
    assert frames[1].time == pytest.approx(0.25, abs=0.02)


def test_b2_a_clip_with_no_face_has_no_subject(two_shots: Path) -> None:
    frames = OpenCvFrameSampler(FACE_MODEL).sample(two_shots)

    assert all(frame.subject_area == 0.0 for frame in frames)
