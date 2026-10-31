"""Real renders with photos, speech and text on generated media.

Spec: specs/05-editing-brain.md#b4, #b8, specs/06-edit-plan-schema.md [T-404]

Photo analysis (OpenCV, Depth Anything) and speech (faster-whisper) run for real and are stored
the way AnalyzeAsset stores them; the render then goes through the plan, NVENC and the joiner.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TypeVar

import pytest
from pydantic import BaseModel

from app.adapters.depth_anything import DepthAnythingEstimator
from app.adapters.ffmpeg_audio_finisher import FfmpegAudioFinisher
from app.adapters.ffmpeg_compositor import FfmpegCompositor
from app.adapters.ffmpeg_probe import FfmpegProbe
from app.adapters.file_cache import FileCache
from app.adapters.nvml_gpu_guard import NvmlGpuGuard
from app.adapters.opencv_photo import OpenCvImageSizer, OpenCvSubjectLocator
from app.adapters.skia_text_layer import SkiaTextLayer
from app.adapters.whisper_speech_detector import WhisperSpeechDetector
from app.application.analyze_asset import _stored_speech
from app.application.analyze_photo import AnalyzePhoto
from app.application.direct_edit import DirectEdit
from app.application.job_runner import CancellationToken
from app.application.render_job import RenderEdit
from app.domain.errors import LlmUnavailableError
from app.domain.models import AssetInput, AssetType, RenderJob, RenderSettings
from tests.integration.test_render_edit import (
    Recorder,
    base_analysis,
    clip_analysis,
    generate,
    music_analysis,
)

pytestmark = [
    pytest.mark.gpu,
    pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs FFmpeg"),
]

M = TypeVar("M", bound=BaseModel)
ROOT = Path(__file__).parents[3]
MODELS = ROOT / "models"
FIXTURES = Path(__file__).parent.parent / "fixtures"
FPS = 30


class UnavailableLlm:
    """A prompt asks the director first; without Ollama the keyword rules decide."""

    def complete_json(
        self, system: str, user: str, schema: type[M], examples: Sequence[tuple[str, str]] = ()
    ) -> M:
        raise LlmUnavailableError("not running in tests")


def frame_count(path: Path) -> int:
    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
            "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout  # fmt: skip
    return int(out.strip().rstrip(","))


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("wired")
    gpu = NvmlGpuGuard()
    cache = FileCache(root)
    for name, source in (("a", "testsrc2"), ("b", "smptebars")):
        generate(
            root / "uploads" / f"{name}.mp4",
            "-f", "lavfi", "-i", f"{source}=size=1920x1080:rate=30:duration=6",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
        )  # fmt: skip
    # a clip with real speech muxed on
    generate(
        root / "uploads" / "talk.mp4",
        "-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=30:duration=6",
        "-i", str(FIXTURES / "speech_hello.wav"),
        "-af", "apad", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-t", "6",
    )  # fmt: skip
    generate(root / "uploads" / "song.wav", "-f", "lavfi", "-i", "sine=frequency=330:duration=10")
    shutil.copyfile(FIXTURES / "astronaut.jpg", root / "uploads" / "p1.jpg")
    generate(
        root / "uploads" / "p2.jpg",
        "-f", "lavfi", "-i", "mandelbrot=size=1600x1200", "-frames:v", "1",
    )  # fmt: skip

    photos = AnalyzePhoto(
        OpenCvImageSizer(),
        OpenCvSubjectLocator(MODELS / "mediapipe" / "blaze_face_short_range.tflite"),
        DepthAnythingEstimator(MODELS / "depth_anything_v2_small", gpu),
    )
    for name in ("p1", "p2"):
        found = photos.run(root / "uploads" / f"{name}.jpg", root / "cache" / name / "depth.png")
        cache.save(base_analysis(name, photo=found))
    speech = WhisperSpeechDetector(MODELS / "faster-whisper-small", gpu).detect(
        root / "uploads" / "talk.mp4"
    )
    assert speech.has_speech
    talk = clip_analysis("talk", 1.0).model_copy(update={"speech": _stored_speech(speech)})
    cache.save(talk)
    cache.save(clip_analysis("a", 2.0))
    cache.save(clip_analysis("b", 1.0))
    cache.save(music_analysis())
    return root


def asset(asset_id: str, kind: AssetType, path: str, file_hash: str) -> AssetInput:
    return AssetInput(
        asset_id, kind, path, f"cache/{file_hash}/analysis.json", None, None, 6.0, None, None, None
    )


def render(
    root: Path, render_id: str, assets: Sequence[AssetInput], prompt: str | None = None
) -> Any:
    settings = RenderSettings("16:9", "4K", FPS, "velocity", "preview", 8, prompt, False, 42)
    job = RenderJob("j1", render_id, "p1", settings, (*assets, song()))
    recorder = Recorder()
    cache = FileCache(root)
    compositor = FfmpegCompositor(text_layer=SkiaTextLayer())
    RenderEdit(
        root, cache, cache, compositor, FfmpegAudioFinisher(), recorder,
        DirectEdit(UnavailableLlm(), NvmlGpuGuard()), text=compositor,
    ).run(job, CancellationToken())  # fmt: skip
    final = root / "renders" / render_id / "final.mp4"
    plan = json.loads((root / "renders" / render_id / "plan.json").read_text())
    return final, plan


def song() -> AssetInput:
    return asset("m1", AssetType.MUSIC, "uploads/song.wav", "song")


def video(name: str) -> AssetInput:
    return asset(name, AssetType.VIDEO, f"uploads/{name}.mp4", name)


def photo(name: str) -> AssetInput:
    return asset(name, AssetType.PHOTO, f"uploads/{name}.jpg", name)


def assert_exact_frames(final: Path, plan: dict[str, Any]) -> None:
    window = plan["music"]["end"] - plan["music"]["start"]
    assert frame_count(final) == round(window * FPS)
    assert FfmpegProbe().probe(final).bit_depth == 10
    assert FfmpegProbe().probe(final).codec == "hevc"


def test_a_mixed_clip_and_photo_edit_has_exact_frames(media: Path) -> None:
    final, plan = render(media, "mix", [video("a"), video("b"), photo("p1"), photo("p2")])

    kinds = [segment["type"] for segment in plan["segments"]]
    assert "photo" in kinds
    assert kinds.count("photo") <= len(kinds) * 0.3
    assert_exact_frames(final, plan)


def test_a_photos_only_edit_renders(media: Path) -> None:
    final, plan = render(media, "photos", [photo("p1"), photo("p2")])

    assert {segment["type"] for segment in plan["segments"]} == {"photo"}
    assert_exact_frames(final, plan)


def test_a_prompt_with_text_draws_it_on_the_joined_video(media: Path) -> None:
    final, plan = render(media, "text", [video("a"), video("b")], "add text GOA 2026")

    assert [item["content"] for item in plan["text"]] == ["GOA 2026"]
    assert_exact_frames(final, plan)


def test_a_clip_with_speech_keeps_its_audio_and_gets_captions(media: Path) -> None:
    final, plan = render(media, "speech", [video("talk")])

    assert any(segment["keepAudio"] for segment in plan["segments"])
    assert any(item["anim"] == "caption" for item in plan["text"])
    assert_exact_frames(final, plan)
