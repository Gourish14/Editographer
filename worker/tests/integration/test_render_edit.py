"""A real render through FFmpeg and NVENC on generated media.

Spec: specs/04-pipeline.md#stages [T-113]
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import pyloudnorm
import pytest

from app.adapters.ffmpeg_audio_finisher import FfmpegAudioFinisher
from app.adapters.ffmpeg_compositor import FfmpegCompositor
from app.adapters.ffmpeg_probe import FfmpegProbe
from app.adapters.file_cache import FileCache
from app.application.job_runner import CancellationToken
from app.application.render_job import RenderEdit
from app.domain.analysis import StoredAnalysis
from app.domain.brain.music_map import MusicFeatures, build_music_map
from app.domain.errors import JobCancelledError, RenderError
from app.domain.models import AssetInput, AssetType, RenderJob, RenderSettings
from app.domain.shots import ShotMeasure, TimeWindow
from app.ports.backend_notifier import AssetAnalysis

pytestmark = [
    pytest.mark.gpu,
    pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs FFmpeg"),
]

BEAT = 0.5
HOP = 0.05
CLIP_SEC = 6


class Recorder:
    def __init__(self) -> None:
        self.stages: list[tuple[str, int]] = []
        self.previews: list[str] = []
        self.done: list[tuple[str | None, dict[str, Any] | None]] = []

    def progress(self, job_id: str, stage: str, percent: int, message: str | None = None) -> None:
        self.stages.append((stage, percent))

    def asset_analyzed(self, analysis: AssetAnalysis) -> None:
        pass

    def preview_ready(self, job_id: str, path: str) -> None:
        self.previews.append(path)

    def job_done(
        self, job_id: str, output_path: str | None = None, plan: dict[str, Any] | None = None
    ) -> None:
        self.done.append((output_path, plan))

    def job_failed(self, job_id: str, error: str) -> None:
        pass


def generate(target: Path, *arguments: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *arguments, str(target)],
        check=True,
    )


def base_analysis(file_hash: str, **fields: Any) -> StoredAnalysis:
    return StoredAnalysis(
        file_hash=file_hash,
        codec="h264",
        width=1920,
        height=1080,
        fps=30.0,
        rotation=0,
        duration_sec=float(CLIP_SEC),
        transfer=None,
        bit_depth=8,
        camera_mode="FLAT",
        log_profile=None,
        native_slow_mo=False,
        **fields,
    )


def clip_analysis(file_hash: str, motion: float) -> StoredAnalysis:
    shot = ShotMeasure(
        start=0.0,
        end=float(CLIP_SEC),
        motion=motion,
        subject=0.5,
        sharpness=100.0,
        stability=0.8,
        luma=0.5,
        peak_time=1.0,
        usable=(TimeWindow(start=0.0, end=float(CLIP_SEC)),),
    )
    return base_analysis(file_hash, shots=(shot,))


def music_analysis() -> StoredAnalysis:
    rms = (0.2,) * 80 + (1.0,) * 80 + (0.25,) * 40
    beats = tuple(i * BEAT for i in range(20))
    onset = [0.0] * len(rms)
    for index, beat in enumerate(beats):
        onset[round(beat / HOP)] = 1.0 if index % 4 == 0 else 0.5
    music = build_music_map(
        MusicFeatures(10.0, beats, beats[::4], rms, tuple(onset), HOP), length_sec=8.0
    )
    return base_analysis("song", music=music)


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("media")
    for name, source in (("a", "testsrc2"), ("b", "smptebars")):
        generate(
            root / "uploads" / f"{name}.mp4",
            "-f",
            "lavfi",
            "-i",
            f"{source}=size=1920x1080:rate=30:duration={CLIP_SEC}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
        )
    generate(root / "uploads" / "song.wav", "-f", "lavfi", "-i", "sine=frequency=330:duration=10")
    cache = FileCache(root)
    cache.save(clip_analysis("a", 2.0))
    cache.save(clip_analysis("b", 1.0))
    cache.save(music_analysis())
    return root


def asset(asset_id: str, kind: AssetType, path: str, file_hash: str) -> AssetInput:
    return AssetInput(
        asset_id, kind, path, f"cache/{file_hash}/analysis.json", None, None, 6.0, None, None, None
    )


def job(render_id: str, ratio: str = "9:16", mode: str = "fast") -> RenderJob:
    return RenderJob(
        "j1",
        render_id,
        "p1",
        RenderSettings(ratio, "4K", 30, "velocity", mode, 8, None, False, 42),
        (
            asset("v1", AssetType.VIDEO, "uploads/a.mp4", "a"),
            asset("v2", AssetType.VIDEO, "uploads/b.mp4", "b"),
            asset("m1", AssetType.MUSIC, "uploads/song.wav", "song"),
        ),
    )


def renderer(root: Path, recorder: Recorder) -> RenderEdit:
    cache = FileCache(root)
    return RenderEdit(root, cache, cache, FfmpegCompositor(), FfmpegAudioFinisher(), recorder)


@pytest.fixture(scope="module")
def finished(media: Path) -> Recorder:
    recorder = Recorder()
    renderer(media, recorder).run(job("r1"), CancellationToken())
    return recorder


def test_the_final_file_is_4k_hevc_10_bit_with_aac(media: Path, finished: Recorder) -> None:
    info = FfmpegProbe().probe(media / "renders/r1/final.mp4")

    assert info.codec == "hevc"
    assert (info.width, info.height) == (2160, 3840)
    assert info.bit_depth == 10
    assert info.fps == pytest.approx(30.0)
    plan = finished.done[0][1]
    assert plan is not None
    window = plan["music"]["end"] - plan["music"]["start"]
    assert info.duration_sec == pytest.approx(window, abs=0.1)


def test_the_audio_is_stereo_at_minus_14_lufs(media: Path, finished: Recorder) -> None:
    raw = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(media / "renders/r1/final.mp4"),
            "-map",
            "0:a:0",
            "-f",
            "f32le",
            "-",
        ],
        capture_output=True,
        check=True,
    ).stdout
    channels = int(
        subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=channels",
                "-of",
                "csv=p=0",
                str(media / "renders/r1/final.mp4"),
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    )
    samples = np.frombuffer(raw, dtype=np.float32).reshape(-1, channels)

    assert channels == 2
    assert pyloudnorm.Meter(48000).integrated_loudness(samples) == pytest.approx(-14.0, abs=0.5)


def test_the_preview_is_1080p_and_reported_before_the_final(
    media: Path, finished: Recorder
) -> None:
    info = FfmpegProbe().probe(media / "renders/r1/preview.mp4")

    assert (info.width, info.height) == (1080, 1920)
    assert finished.previews == ["renders/r1/preview.mp4"]


def test_the_plan_is_saved_and_reported(media: Path, finished: Recorder) -> None:
    assert (media / "renders/r1/plan.json").exists()
    output, plan = finished.done[0]
    assert output == "renders/r1/final.mp4"
    assert plan is not None
    assert plan["segments"][0]["srcIn"] >= 0


def test_progress_only_moves_forward(finished: Recorder) -> None:
    percents = [percent for _, percent in finished.stages]

    assert percents == sorted(percents)
    assert {stage for stage, _ in finished.stages} >= {"PLANNING", "COMPOSING", "ENCODING"}


def test_the_work_folder_is_cleaned_up(media: Path, finished: Recorder) -> None:
    assert not (media / "renders/r1/work").exists()


def test_preview_mode_stops_at_the_preview(media: Path) -> None:
    recorder = Recorder()

    renderer(media, recorder).run(job("r2", mode="preview"), CancellationToken())

    info = FfmpegProbe().probe(media / "renders/r2/final.mp4")
    assert (info.width, info.height) == (1080, 1920)
    assert recorder.done[0][0] == "renders/r2/final.mp4"


@pytest.mark.parametrize(
    ("ratio", "size"),
    [
        ("16:9", (1920, 1080)),
        ("1:1", (1920, 1920)),
        ("4:5", (1536, 1920)),
        ("4:3", (1920, 1440)),
        ("21:9", (1920, 824)),
    ],
)
def test_every_other_ratio_renders(media: Path, ratio: str, size: tuple[int, int]) -> None:
    render_id = "r-" + ratio.replace(":", "-")

    renderer(media, Recorder()).run(job(render_id, ratio, "preview"), CancellationToken())

    info = FfmpegProbe().probe(media / "renders" / render_id / "final.mp4")
    assert (info.width, info.height) == size


def test_a_cancelled_render_stops(media: Path) -> None:
    token = CancellationToken()
    token.cancel()

    with pytest.raises(JobCancelledError):
        renderer(media, Recorder()).run(job("r3"), token)


def test_a_render_without_music_fails_clearly(media: Path) -> None:
    source = job("r4")
    no_song = RenderJob(
        source.job_id, source.render_id, source.project_id, source.settings, source.assets[:2]
    )

    with pytest.raises(RenderError, match="song"):
        renderer(media, Recorder()).run(no_song, CancellationToken())
