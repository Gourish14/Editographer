"""Real depth model, face model and FFmpeg on a generated photo.

Spec: specs/04-pipeline.md#stages (4), specs/05-editing-brain.md#b7 [T-403]
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.adapters.depth_anything import DepthAnythingEstimator
from app.adapters.ffmpeg_photo import photo_command
from app.adapters.nvml_gpu_guard import NvmlGpuGuard
from app.adapters.opencv_photo import OpenCvImageSizer, OpenCvSubjectLocator
from app.application.analyze_photo import AnalyzePhoto
from app.domain.photo import PhotoMotion

MODELS = Path(__file__).resolve().parents[3] / "models"
FACE_MODEL = MODELS / "mediapipe" / "blaze_face_short_range.tflite"
DEPTH_DIR = MODELS / "depth_anything_v2_small"
OUT_W, OUT_H, FPS, FRAMES = 540, 960, 30, 45

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None
    or not FACE_MODEL.exists()
    or not (DEPTH_DIR / "model.safetensors").exists(),
    reason="needs FFmpeg and the face and depth models from setup.bat",
)


@pytest.fixture(scope="module")
def scene(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A road receding to a horizon with a bright near box on the right: strong depth."""
    height, width = 900, 1200
    rows = np.linspace(0, 1, height)[:, None, None]
    sky = np.array([200, 160, 90], dtype=np.float32)
    ground = np.array([60, 90, 70], dtype=np.float32)
    image = np.where(rows < 0.45, sky, ground) * np.ones((height, width, 3), dtype=np.float32)
    cv2.line(image, (600, 405), (100, 900), (150, 150, 150), 40)
    cv2.line(image, (600, 405), (1100, 900), (150, 150, 150), 40)
    cv2.rectangle(image, (800, 450), (1100, 880), (30, 30, 220), -1)
    rng = np.random.default_rng(1)
    noisy = image + rng.normal(0, 6, image.shape)
    target = tmp_path_factory.mktemp("photo") / "scene.jpg"
    cv2.imwrite(str(target), np.clip(noisy, 0, 255).astype(np.uint8))
    return target


def frame_count(clip: Path) -> int:
    probe = subprocess.run(
        [
            "ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
            "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(clip),
        ],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    return int(probe.stdout.strip())


def test_analysis_runs_depth_and_subject_on_a_generated_photo(scene: Path, tmp_path: Path) -> None:
    use_case = AnalyzePhoto(
        OpenCvImageSizer(),
        OpenCvSubjectLocator(FACE_MODEL),
        DepthAnythingEstimator(DEPTH_DIR, NvmlGpuGuard()),
    )

    result = use_case.run(scene, tmp_path / "depth.png")

    assert (result.width, result.height) == (1200, 900)
    assert 0.0 <= result.focus.center_x <= 1.0
    assert result.depth is not None and result.depth.contrast > 0.0
    depth_map = cv2.imread(result.depth.map_file, cv2.IMREAD_GRAYSCALE)
    assert depth_map is not None and depth_map.shape == (900, 1200)

    for motion in (PhotoMotion.KEN_BURNS, PhotoMotion.PARALLAX):
        clip = tmp_path / f"{motion.value}.mp4"
        subprocess.run(
            photo_command(replace(result, motion=motion), scene, clip, OUT_W, OUT_H, FPS, FRAMES),
            check=True,
        )
        assert frame_count(clip) == FRAMES
