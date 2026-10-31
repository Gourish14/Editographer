"""Phase 2 gate on generated media, with nothing listening where Ollama should be.

Spec: specs/10-roadmap.md#phase-2--ai-director [T-202]
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from app.adapters.ffmpeg_audio_finisher import FfmpegAudioFinisher
from app.adapters.ffmpeg_compositor import FfmpegCompositor
from app.adapters.ffmpeg_probe import FfmpegProbe
from app.adapters.file_cache import FileCache
from app.adapters.nvml_gpu_guard import NvmlGpuGuard
from app.adapters.ollama_llm import OllamaLlmClient
from app.application.direct_edit import FALLBACK_NOTE, DirectEdit
from app.application.job_runner import CancellationToken
from app.application.render_job import RenderEdit
from app.domain.models import AssetType, RenderJob, RenderSettings
from tests.integration.test_render_edit import (
    CLIP_SEC,
    Recorder,
    asset,
    clip_analysis,
    generate,
    music_analysis,
)

pytestmark = [
    pytest.mark.gpu,
    pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs FFmpeg"),
]

NOTHING_LISTENS_HERE = "http://127.0.0.1:9"
SONG_WITH_A_DROP = (0.2,) * 80 + (1.0,) * 120
CAR_CLIPS = {"c1", "c2"}
SOURCES = {"c1": "testsrc2", "c2": "smptebars", "b1": "testsrc", "b2": "rgbtestsrc"}
TAGS = {"c1": ("car",), "c2": ("car", "road"), "b1": ("beach",), "b2": ("beach", "sea")}


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_media(tmp_path_factory.mktemp("media"))


def build_media(root: Path) -> Path:
    cache = FileCache(root)
    for index, (name, source) in enumerate(SOURCES.items()):
        generate(
            root / "uploads" / f"{name}.mp4",
            "-f",
            "lavfi",
            "-i",
            f"{source}=size=1280x720:rate=30:duration={CLIP_SEC}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
        )
        clip = clip_analysis(name, 1.0 + index)
        shots = tuple(shot.model_copy(update={"tags": TAGS[name]}) for shot in clip.shots)
        cache.save(clip.model_copy(update={"shots": shots}))
    generate(root / "uploads" / "song.wav", "-f", "lavfi", "-i", "sine=frequency=330:duration=10")
    cache.save(music_analysis(rms=SONG_WITH_A_DROP))
    return root


def render(
    media: Path, render_id: str, prompt: str | None, ollama_url: str = NOTHING_LISTENS_HERE
) -> tuple[Recorder, dict[str, Any]]:
    settings = RenderSettings("16:9", "4K", 30, "auto", "preview", 8, prompt, False, 42)
    clips = tuple(asset(name, AssetType.VIDEO, f"uploads/{name}.mp4", name) for name in SOURCES)
    song = asset("m1", AssetType.MUSIC, "uploads/song.wav", "song")
    cache = FileCache(media)
    recorder = Recorder()
    director = DirectEdit(OllamaLlmClient.create(ollama_url), NvmlGpuGuard())
    RenderEdit(
        media, cache, cache, FfmpegCompositor(), FfmpegAudioFinisher(), recorder, director
    ).run(RenderJob("j1", render_id, "p1", settings, (*clips, song)), CancellationToken())
    plan = recorder.done[0][1]
    assert plan is not None
    return recorder, plan


def assets_of(plan: dict[str, Any]) -> set[str]:
    return {segment["assetId"] for segment in plan["segments"]}


def effects_of(plan: dict[str, Any]) -> set[str]:
    return {effect["type"] for segment in plan["segments"] for effect in segment["effects"]}


def rendered_seconds(media: Path, render_id: str) -> float:
    duration = FfmpegProbe().probe(media / "renders" / render_id / "final.mp4").duration_sec
    assert duration is not None
    return duration


def test_gate_with_ollama_stopped_an_edit_is_still_produced(media: Path) -> None:
    recorder, plan = render(media, "stopped", None)

    assert FALLBACK_NOTE in plan["log"]
    assert rendered_seconds(media, "stopped") > 0
    assert ("PLANNING", 2) in recorder.stages
    assert plan["style"] == "velocity"


def test_gate_only_car_shots_changes_the_edit(media: Path) -> None:
    _, before = render(media, "plain-car", None)
    _, after = render(media, "car", "only car shots")

    assert assets_of(before) - CAR_CLIPS
    assert assets_of(after) == CAR_CLIPS
    assert rendered_seconds(media, "car") > 0


def test_gate_slow_mo_on_the_drop_changes_the_edit(media: Path) -> None:
    _, plain = render(media, "plain-slow", None)
    _, plan = render(media, "slow", "slow-mo on the drop")

    def ramped(edit: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            segment
            for segment in edit["segments"]
            if {speed for _, speed in segment["speed"]["curve"]} != {1.0}
        ]

    assert any(note.startswith("Slow motion on: drop") for note in plan["log"])
    assert len(ramped(plan)) > len(ramped(plain))
    assert rendered_seconds(media, "slow") > 0


def test_gate_cinematic_no_shakes_changes_the_edit(media: Path) -> None:
    _, before = render(media, "plain-cine", None)
    _, after = render(media, "cine", "cinematic no shakes")

    assert "shake" in effects_of(before)
    assert after["style"] == "cinematic"
    assert after["grade"]["lut"] == "film"
    assert "shake" not in effects_of(after)
    assert len(after["segments"]) < len(before["segments"])
    assert rendered_seconds(media, "cine") > 0


def test_gate_a_request_nothing_understands_is_logged_and_the_edit_is_made(media: Path) -> None:
    _, plan = render(media, "sky", "make the sky purple")

    assert "Prompt request 'make the sky purple' skipped: nothing maps to it" in plan["log"]
