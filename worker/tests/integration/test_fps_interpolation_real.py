"""60 fps from a 30 fps clip with the real RIFE and FFmpeg. Spec: specs/04-pipeline.md#stages (6)

FEAT-021 [T-409]. A red box crosses black frames at a known speed: in a true 60 fps result the box
is where the clock says at every frame, including the frames RIFE made in between.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.adapters.ffmpeg_compositor import FfmpegCompositor
from app.adapters.ffmpeg_frame_media import FfmpegFrameMedia
from app.adapters.nvml_gpu_guard import NvmlGpuGuard
from app.adapters.rife_interpolator import RifeInterpolator
from app.adapters.torch_enhance import read_frame
from app.application.enhance_stages import RetimeStage
from app.application.job_runner import CancellationToken
from app.domain.plan import Segment, Source
from app.ports.render import EncodeProfile, SegmentLook
from tests.integration.test_ramps_and_reframe_render import (
    BOX_SIZE,
    BOX_SPEED,
    BOX_START,
    FLAT,
    RIFE_WEIGHTS,
    box_center,
    box_clip,
    frames_of,
)

pytestmark = [
    pytest.mark.gpu,
    pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs FFmpeg"),
    pytest.mark.skipif(not RIFE_WEIGHTS.exists(), reason="needs the RIFE weights"),
]

OUT_FPS = 60
SECONDS = 1.0
FRAMES = 60
SRC_IN = 1.0
PROFILE = EncodeProfile(960, 540, OUT_FPS, 28, "p2", False)


def test_feat_021_rife_makes_a_30_fps_clip_a_60_fps_clip_with_exact_frames(
    tmp_path: Path,
) -> None:
    source = tmp_path / "flat30.mp4"
    box_clip(source, FLAT, 30, f"{BOX_START}+{BOX_SPEED}*t", "460")
    clip = Segment(
        id="s1",
        asset_id="v1",
        type="video",
        src_in=SRC_IN,
        src_out=SRC_IN + SECONDS,
        at=0.0,
        duration=SECONDS,
        source=Source(camera_mode="FLAT", log_profile=None, native_fps=30.0, width=FLAT[0]),
    )

    patterns = RetimeStage(RifeInterpolator(NvmlGpuGuard(), RIFE_WEIGHTS), FfmpegFrameMedia()).run(
        [(clip, source, FRAMES)], OUT_FPS, tmp_path, CancellationToken()
    )

    files = sorted(patterns["s1"].parent.glob("*.png"))
    assert len(files) == FRAMES
    for index, file in enumerate(files):
        center = box_center(read_frame(file))
        assert center is not None, f"no box in frame {index}"
        expected = BOX_START + BOX_SIZE / 2 + BOX_SPEED * (SRC_IN + index / OUT_FPS)
        assert abs(center[0] - expected) < 6.0, f"frame {index}"

    target = tmp_path / "out.mp4"
    FfmpegCompositor().render_segment(
        source, clip, FRAMES, PROFILE, target, SegmentLook(retimed=patterns["s1"])
    )
    assert len(frames_of(target, PROFILE.width, PROFILE.height)) == FRAMES
