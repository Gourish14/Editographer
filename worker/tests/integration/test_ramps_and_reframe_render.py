"""Real renders of speed ramps, subject crops, 360 follow and Max quality on generated media.

Spec: specs/04-pipeline.md#stages (6, 7), specs/05-editing-brain.md#b6, #b7, specs/08-osmo360.md
[T-405]. A red box crosses black frames at a known speed, so where it is in an output frame shows
which source frame was used and where the camera pointed.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TypeVar

import numpy as np
import pytest
from numpy.typing import NDArray
from pydantic import BaseModel

from app.adapters.ffmpeg_audio_finisher import FfmpegAudioFinisher
from app.adapters.ffmpeg_compositor import FfmpegCompositor
from app.adapters.ffmpeg_frame_media import FfmpegFrameMedia, FfmpegVideoUpscaler
from app.adapters.ffmpeg_probe import FfmpegProbe
from app.adapters.file_cache import FileCache
from app.adapters.nvml_gpu_guard import NvmlGpuGuard
from app.adapters.realesrgan_upscaler import RealEsrganUpscaler
from app.adapters.rife_interpolator import RifeInterpolator
from app.adapters.torch_enhance import read_frame
from app.application.direct_edit import DirectEdit
from app.application.enhance_stages import RetimeStage
from app.application.job_runner import CancellationToken
from app.application.render_job import RenderEdit
from app.domain.analysis import StoredAnalysis
from app.domain.brain.music_map import MusicFeatures, build_music_map
from app.domain.brain.ramps import RAMP_CURVE, ramp_speed, source_length, source_time_at
from app.domain.brain.reframe import SubjectBearing, follow_camera
from app.domain.constraints import Constraints, DirectorDecision
from app.domain.models import AssetInput, AssetType, FollowPoint, RenderJob, RenderSettings
from app.domain.music import SectionKind
from app.domain.photo import FocusBox, FocusSource, PhotoAnalysis, PhotoMotion
from app.domain.plan import Reframe, ReframePoint, Segment, Source, Transition
from app.domain.shots import ShotMeasure, SubjectSample, TimeWindow
from app.ports.backend_notifier import AssetAnalysis
from app.ports.render import EncodeProfile, NextClip, SegmentLook

pytestmark = [
    pytest.mark.gpu,
    pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs FFmpeg"),
]

M = TypeVar("M", bound=BaseModel)
Image = NDArray[np.uint8]

ROOT = Path(__file__).resolve().parents[3]
MODELS = ROOT / "models"
RIFE_WEIGHTS = MODELS / "rife" / "flownet_v4.25.pkl"
ESRGAN_WEIGHTS = MODELS / "realesrgan" / "realesr-general-x4v3.pth"
FPS = 30
DURATION = 2.0
SOURCE_SEC = 8
BOX_SPEED = 250.0
BOX_START = 100.0
BOX_SIZE = 160
FLAT = (1920, 1080)
EQUIRECT = (4096, 2048)
YAW_RATE = 20.0
PROFILE = EncodeProfile(960, 540, FPS, 28, "p2", False)
TALL = EncodeProfile(540, 960, FPS, 28, "p2", False)
BEAT = 0.5
HOP = 0.05
needs_models = pytest.mark.skipif(
    not RIFE_WEIGHTS.exists() or not ESRGAN_WEIGHTS.exists(), reason="needs RIFE and ESRGAN"
)


def generate(target: Path, *arguments: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *arguments, str(target)],
        check=True,
    )


def box_clip(target: Path, size: tuple[int, int], rate: int, x: str, y: str) -> None:
    width, height = size
    graph = (
        f"color=c=black:size={width}x{height}:rate={rate}:duration={SOURCE_SEC}[bg];"
        f"color=c=red:size={BOX_SIZE}x{BOX_SIZE}:rate={rate}:duration={SOURCE_SEC}[box];"
        f"[bg][box]overlay=x='{x}':y='{y}':eval=frame,format=yuv420p"
    )
    generate(target, "-filter_complex", graph, "-c:v", "libx264", "-crf", "12")


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("media")
    box_clip(root / "uploads/flat30.mp4", FLAT, 30, f"{BOX_START}+{BOX_SPEED}*t", "460")
    box_clip(root / "uploads/flat120.mp4", FLAT, 120, f"{BOX_START}+{BOX_SPEED}*t", "460")
    box_clip(
        root / "uploads/pano.mp4",
        EQUIRECT,
        30,
        f"2048+4096*{YAW_RATE}*t/360-{BOX_SIZE // 2}",
        f"1024-{BOX_SIZE // 2}",
    )
    generate(root / "uploads/song.wav", "-f", "lavfi", "-i", "sine=frequency=330:duration=12")
    return root


def frames_of(video: Path, width: int, height: int) -> list[Image]:
    raw = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(video)]
        + ["-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True,
        check=True,
    ).stdout
    size = width * height * 3
    return [
        np.frombuffer(raw[i : i + size], np.uint8).reshape(height, width, 3)
        for i in range(0, len(raw), size)
    ]


def box_center(frame: Any) -> tuple[float, float] | None:
    mask = (frame[:, :, 0] > 150) & (frame[:, :, 1] < 90) & (frame[:, :, 2] < 90)
    ys, xs = np.nonzero(mask)
    if len(xs) < 20:
        return None
    return float(xs.mean()), float(ys.mean())


def segment(**fields: Any) -> Segment:
    base: dict[str, Any] = {
        "id": "s1",
        "asset_id": "v1",
        "type": "video",
        "src_in": 1.0,
        "src_out": 1.0 + DURATION,
        "at": 0.0,
        "duration": DURATION,
        "source": Source(camera_mode="FLAT", log_profile=None, native_fps=30.0, width=FLAT[0]),
    }
    return Segment(**{**base, **fields})


def ramped(native_fps: float) -> Segment:
    speed = ramp_speed(native_fps)
    return segment(
        src_out=1.0 + source_length(DURATION),
        speed=speed,
        source=Source(camera_mode="FLAT", log_profile=None, native_fps=native_fps, width=1920),
    )


def expected_box_x(src_in: float, offset: float, scale: float) -> float:
    return (BOX_START + BOX_SIZE / 2 + BOX_SPEED * (src_in + offset)) * scale


def check_follows_the_curve(centers: list[tuple[float, float] | None], scale: float) -> float:
    errors = []
    for index, center in enumerate(centers):
        offset = source_time_at(RAMP_CURVE, DURATION, index / FPS)
        assert center is not None, f"no box in frame {index}"
        errors.append(abs(center[0] - expected_box_x(1.0, offset, scale)))
    return max(errors)


def test_b6_native_120_fps_footage_ramps_with_its_own_frames(media: Path, tmp_path: Path) -> None:
    target = tmp_path / "native.mp4"

    FfmpegCompositor().render_segment(
        media / "uploads/flat120.mp4", ramped(120.0), 60, PROFILE, target
    )

    info = FfmpegProbe().probe(target)
    centers = [box_center(frame) for frame in frames_of(target, 960, 540)]
    assert len(centers) == 60
    assert info.fps == pytest.approx(30.0)
    # A native frame is 1 px here; the fps filter picks the nearest slot, so a few px of jitter.
    assert check_follows_the_curve(centers, 0.5) < 6.0
    speeds = [b[0] - a[0] for a, b in zip(centers, centers[1:], strict=False) if a and b]
    assert max(speeds) > 8 * min(speeds) > 0 or min(speeds) <= 1.0  # fast part vs slow hold


@needs_models
def test_b6_rife_ramp_has_the_exact_frames_and_follows_the_curve(
    media: Path, tmp_path: Path
) -> None:
    gpu = NvmlGpuGuard()
    stage = RetimeStage(RifeInterpolator(gpu, RIFE_WEIGHTS), FfmpegFrameMedia())
    clip = ramped(30.0)

    patterns = stage.run(
        [(clip, media / "uploads/flat30.mp4", 60)], FPS, tmp_path, CancellationToken()
    )

    pattern = patterns["s1"]
    files = sorted(pattern.parent.glob("*.png"))
    assert len(files) == 60
    centers = [box_center(read_frame(f)) for f in files]
    assert check_follows_the_curve(centers, 1.0) < 12.0

    target = tmp_path / "rife.mp4"
    FfmpegCompositor().render_segment(
        media / "uploads/flat30.mp4", clip, 60, PROFILE, target, SegmentLook(retimed=pattern)
    )
    rendered = [box_center(frame) for frame in frames_of(target, 960, 540)]
    assert len(rendered) == 60
    assert check_follows_the_curve(rendered, 0.5) < 8.0


def test_b7_a_crop_path_keeps_the_subject_near_the_middle_of_a_tall_frame(
    media: Path, tmp_path: Path
) -> None:
    times = [i * 0.25 for i in range(9)]
    path = tuple(
        ReframePoint(t=t, x=(BOX_START + BOX_SIZE / 2 + BOX_SPEED * (1.0 + t)) / 1920, y=0.5)
        for t in times
    )
    follow = segment(reframe=Reframe(mode="track", path=path))
    centered = segment()
    target = tmp_path / "crop.mp4"
    plain = tmp_path / "plain.mp4"

    FfmpegCompositor().render_segment(media / "uploads/flat30.mp4", follow, 60, TALL, target)
    FfmpegCompositor().render_segment(media / "uploads/flat30.mp4", centered, 60, TALL, plain)

    followed = [box_center(frame) for frame in frames_of(target, 540, 960)]
    fixed = [box_center(frame) for frame in frames_of(plain, 540, 960)]
    assert len(followed) == 60
    assert all(c is not None and abs(c[0] - 270) < 80 for c in followed)
    assert sum(1 for c in fixed if c is None) > 10  # the center crop loses the subject


@pytest.mark.parametrize(("profile", "ratio"), [(TALL, "9:16"), (PROFILE, "16:9")])
def test_b7_a_360_camera_follows_the_subject_in_both_ratios(
    media: Path, tmp_path: Path, profile: EncodeProfile, ratio: str
) -> None:
    bearings = [SubjectBearing(i * 0.25, YAW_RATE * (1.0 + i * 0.25)) for i in range(9)]
    keys = [0.0, 0.5, 1.0, 1.5, DURATION]
    camera = follow_camera(bearings, keys, ratio)
    clip = segment(
        type="video360",
        camera360=camera,
        source=Source(camera_mode="OSMO360_PANO_8K", log_profile=None, native_fps=30.0, width=4096),
    )
    target = tmp_path / f"pano_{profile.width}.mp4"

    FfmpegCompositor().render_segment(media / "uploads/pano.mp4", clip, 60, profile, target)

    centers = [box_center(frame) for frame in frames_of(target, profile.width, profile.height)]
    assert len(centers) == 60
    # Pitch is -5 and the box sits on the horizon, so it should stay near the middle.
    for center in centers:
        assert center is not None
        assert abs(center[0] - profile.width / 2) < profile.width * 0.2
    # Without the follow a 20 deg/s subject drifts out of a 90 degree view within seconds.
    assert len({round(c[1] / 10) for c in centers if c}) <= 6


# A full edit through the worker, with the GPU stages


def audio_analysis() -> StoredAnalysis:
    rms = (0.2,) * 80 + (1.0,) * 80 + (0.25,) * 80
    beats = tuple(i * BEAT for i in range(24))
    onset = [0.0] * len(rms)
    for index, beat in enumerate(beats):
        onset[round(beat / HOP)] = 1.0 if index % 4 == 0 else 0.5
    music = build_music_map(
        MusicFeatures(12.0, beats, beats[::4], rms, tuple(onset), HOP), length_sec=8.0
    )
    return base("song", None, 30.0, music=music)


def base(file_hash: str, size: tuple[int, int] | None, fps: float, **fields: Any) -> StoredAnalysis:
    return StoredAnalysis(
        file_hash=file_hash,
        codec="h264",
        width=size[0] if size else None,
        height=size[1] if size else None,
        fps=fps,
        rotation=0,
        duration_sec=float(SOURCE_SEC),
        transfer=None,
        bit_depth=8,
        camera_mode=fields.pop("camera_mode", "FLAT"),
        log_profile=None,
        native_slow_mo=False,
        **fields,
    )


def clip_analysis(
    file_hash: str,
    size: tuple[int, int],
    fps: float,
    track: tuple[SubjectSample, ...],
    **fields: Any,
) -> StoredAnalysis:
    shot = ShotMeasure(
        start=0.0,
        end=float(SOURCE_SEC),
        motion=1.0,
        subject=0.5,
        sharpness=100.0,
        stability=0.8,
        luma=0.5,
        peak_time=1.0,
        usable=(TimeWindow(start=0.0, end=float(SOURCE_SEC)),),
        action=0.5,
        aesthetics=0.6,
        subject_track=track,
    )
    return base(file_hash, size, fps, shots=(shot,), **fields)


class Slowmo:
    """Stands in for the director: slow motion everywhere, nothing else."""

    def complete_json(
        self, system: str, user: str, schema: type[M], examples: Sequence[tuple[str, str]] = ()
    ) -> M:
        decision = DirectorDecision(
            constraints=Constraints(slowmo_at=tuple(SectionKind), style="velocity")
        )
        return schema.model_validate(decision.model_dump())


class Recorder:
    def __init__(self) -> None:
        self.stages: list[tuple[str, int]] = []
        self.done: list[dict[str, Any] | None] = []

    def progress(self, job_id: str, stage: str, percent: int, message: str | None = None) -> None:
        self.stages.append((stage, percent))

    def asset_analyzed(self, analysis: AssetAnalysis) -> None:
        pass

    def preview_ready(self, job_id: str, path: str) -> None:
        pass

    def job_done(
        self, job_id: str, output_path: str | None = None, plan: dict[str, Any] | None = None
    ) -> None:
        self.done.append(plan)

    def job_failed(self, job_id: str, error: str) -> None:
        pass


def asset(
    asset_id: str, kind: AssetType, path: str, file_hash: str, size: Any, fps: Any
) -> AssetInput:
    width, height = size or (None, None)
    return AssetInput(
        asset_id,
        kind,
        path,
        f"cache/{file_hash}/analysis.json",
        None,
        None,
        8.0,
        width,
        height,
        fps,
    )


@needs_models
@pytest.mark.parametrize(("ratio", "size"), [("9:16", (2160, 3840)), ("16:9", (3840, 2160))])
def test_max_quality_edit_of_flat_native_and_360_clips(
    media: Path, ratio: str, size: tuple[int, int]
) -> None:
    track = tuple(
        SubjectSample(
            time=i * 0.25, x=(BOX_START + BOX_SIZE / 2 + BOX_SPEED * i * 0.25) / 1920, y=0.43
        )
        for i in range(32)
    )
    pano_track = tuple(
        SubjectSample(time=i * 0.25, x=0.5 + YAW_RATE * i * 0.25 / 360, y=0.5) for i in range(32)
    )
    cache = FileCache(media)
    cache.save(audio_analysis())
    cache.save(clip_analysis("flat30", FLAT, 30.0, track))
    cache.save(clip_analysis("flat120", FLAT, 120.0, track))
    cache.save(clip_analysis("pano", EQUIRECT, 30.0, pano_track, camera_mode="OSMO360_PANO_8K"))
    gpu = NvmlGpuGuard()
    recorder = Recorder()
    renderer = RenderEdit(
        media,
        cache,
        cache,
        FfmpegCompositor(),
        FfmpegAudioFinisher(),
        recorder,
        DirectEdit(Slowmo(), gpu),
        interpolator=RifeInterpolator(gpu, RIFE_WEIGHTS),
        frames=FfmpegFrameMedia(),
        upscaler=FfmpegVideoUpscaler(RealEsrganUpscaler(gpu, ESRGAN_WEIGHTS)),
    )
    job = RenderJob(
        "j1",
        f"max{ratio[0]}",
        "p1",
        RenderSettings(
            ratio, "4K", 30, "auto", "max", 8, "slow motion", False, 5, FollowPoint(0.5, 0.5, 0.0)
        ),
        (
            asset("v1", AssetType.VIDEO, "uploads/flat30.mp4", "flat30", FLAT, 30.0),
            asset("v2", AssetType.VIDEO, "uploads/flat120.mp4", "flat120", FLAT, 120.0),
            asset("v3", AssetType.VIDEO, "uploads/pano.mp4", "pano", EQUIRECT, 30.0),
            asset("m1", AssetType.MUSIC, "uploads/song.wav", "song", None, None),
        ),
    )

    renderer.run(job, CancellationToken())

    final = media / "renders" / job.render_id / "final.mp4"
    info = FfmpegProbe().probe(final)
    plan = recorder.done[0]
    assert plan is not None
    window = plan["music"]["end"] - plan["music"]["start"]
    assert (info.width, info.height) == size
    assert info.duration_sec == pytest.approx(window, abs=0.1)
    count = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0"]
        + ["-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(final)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert int(count) == round(window * FPS)
    kinds = {s["type"] for s in plan["segments"]}
    modes = {s["speed"]["interpolate"] for s in plan["segments"]}
    assert "video360" in kinds
    assert {"rife", "native"} <= modes
    assert "UPSCALING" in {stage for stage, _ in recorder.stages}
    percents = [percent for _, percent in recorder.stages]
    assert max(percents) <= 100


def test_a_photo_beside_a_ramp_and_a_360_clip_keeps_every_frame_count(
    media: Path, tmp_path: Path
) -> None:
    photo = ROOT / "worker/tests/fixtures/astronaut.jpg"
    analysis = PhotoAnalysis(
        512, 512, FocusBox(0.4, 0.2, 0.2, 0.2, FocusSource.FACE), PhotoMotion.KEN_BURNS, None
    )
    pano_segment = segment(
        id="s3",
        type="video360",
        at=2.0 + 0.8,
        duration=1.1,
        camera360=follow_camera([SubjectBearing(0.0, 0.0)], [0.0, 1.1], "9:16"),
        source=Source(camera_mode="OSMO360_PANO_8K", log_profile=None, native_fps=30.0, width=4096),
    )
    ramp = ramped(120.0).model_copy(
        update={"transition_out": Transition(type="whip_left", duration=0.18)}
    )
    still = segment(id="s2", type="photo", duration=0.8, at=2.0)
    pano = media / "uploads/pano.mp4"
    plan = [
        (
            ramp,
            media / "uploads/flat120.mp4",
            60,
            SegmentLook(next_clip=NextClip(pano, 1.0, None, pano_segment)),
        ),
        (still, photo, 24, SegmentLook(photo=analysis)),
        (pano_segment, pano, 33, SegmentLook()),
        (still.model_copy(update={"id": "s4"}), photo, 17, SegmentLook(photo=analysis)),
    ]
    compositor = FfmpegCompositor()
    parts = []
    for part_segment, source, frames, look in plan:
        part = tmp_path / f"{part_segment.id}.mp4"
        compositor.render_segment(source, part_segment, frames, TALL, part, look)
        assert len(frames_of(part, TALL.width, TALL.height)) == frames
        parts.append(part)

    joined = tmp_path / "joined.mp4"
    compositor.join(parts, joined, [item[2] for item in plan], TALL.fps)

    assert len(frames_of(joined, TALL.width, TALL.height)) == 60 + 24 + 33 + 17
