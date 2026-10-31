"""SAM 2.1 small follows a subject across the 0/360 seam on a generated equirect video.

Spec: specs/08-osmo360.md (rule 5), specs/09-local-setup.md#6-gb-vram-model-profile [T-415]

Needs the GPU, so it is marked `gpu` and is not part of the CPU run. Run it alone, when the GPU
is free:  uv run pytest tests/integration/test_subject_follow_gpu.py -m gpu -q --no-cov
"""

from __future__ import annotations

from pathlib import Path

import pytest
import torch

from app.adapters.ffmpeg_frame_media import FfmpegFrameMedia
from app.adapters.nvml_gpu_guard import NvmlGpuGuard
from app.adapters.sam2_segmenter import Sam2Segmenter
from app.adapters.sam2_subject_follower import Sam2SubjectFollower
from app.domain.models import FollowPoint
from tests.integration.test_subject_follow_view import (
    START_YAW,
    make_video,
    seam_distance,
    share_x,
    subject_yaw,
)

WEIGHTS = Path(__file__).resolve().parents[3] / "models" / "sam2_1_small"

pytestmark = [
    pytest.mark.gpu,
    pytest.mark.skipif(
        not torch.cuda.is_available() or not (WEIGHTS / "model.safetensors").exists(),
        reason="needs CUDA and the SAM 2.1 small weights",
    ),
]


def test_08_rule5_sam2_follows_a_subject_across_the_seam(tmp_path: Path) -> None:
    video = make_video(tmp_path)
    follower = Sam2SubjectFollower(FfmpegFrameMedia(), Sam2Segmenter(WEIGHTS, NvmlGpuGuard()))
    tap = FollowPoint(share_x(START_YAW), 0.5, 0.0)

    track = follower.follow(video, tap, 0.0, 5.0, tmp_path / "work")

    assert track.samples, "SAM 2 found no subject at the tap"
    assert track.lost == ()
    for sample in track.samples:
        assert seam_distance(sample.x, share_x(subject_yaw(sample.time))) < 5.0
    assert torch.cuda.memory_allocated() == 0  # nothing stays on the GPU between chunks
