"""Real faster-whisper, skia and FFmpeg on generated media.

Spec: specs/05-editing-brain.md#b8-text-and-audio [T-402]
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from app.adapters.ffmpeg_text_overlay import input_args, overlay_chain
from app.adapters.skia_text_layer import SkiaTextLayer
from app.adapters.whisper_speech_detector import WhisperSpeechDetector
from app.domain.brain.text_rules import TextItem

FIXTURES = Path(__file__).parent.parent / "fixtures"
MODEL_DIR = Path(__file__).parents[3] / "models" / "faster-whisper-small"


@pytest.mark.skipif(not (MODEL_DIR / "model.bin").exists(), reason="needs faster-whisper weights")
def test_b8_whisper_finds_speech_and_words_in_spoken_audio() -> None:
    result = WhisperSpeechDetector(MODEL_DIR).detect(FIXTURES / "speech_hello.wav")
    assert result.has_speech
    text = " ".join(w.text.lower() for w in result.words)
    assert "goa" in text or "trip" in text
    assert all(w.end >= w.start for w in result.words)


@pytest.mark.skipif(not (MODEL_DIR / "model.bin").exists(), reason="needs faster-whisper weights")
def test_b8_whisper_finds_no_speech_in_music() -> None:
    result = WhisperSpeechDetector(MODEL_DIR).detect(FIXTURES / "test_song.wav")
    assert not result.has_speech


def test_b8_skia_layer_is_a_transparent_png_with_text_pixels(tmp_path: Path) -> None:
    png = SkiaTextLayer().render(TextItem("GOA 2026", 0, 1.4), 640, 360, tmp_path / "t.png")
    import skia

    image = skia.Image.open(str(png))
    assert (image.width(), image.height()) == (640, 360)
    pixels = image.toarray()
    assert pixels[0, 0, 3] == 0
    assert pixels[..., 3].max() == 255


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs FFmpeg")
def test_b8_ffmpeg_overlays_text_only_during_its_window(tmp_path: Path) -> None:
    item = TextItem("GOA", 1.0, 1.0)
    png = SkiaTextLayer().render(item, 320, 180, tmp_path / "t.png")
    out = tmp_path / "out.mp4"
    graph = overlay_chain("0:v", [item], first_input=1)
    command = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-t", "3", "-i", "color=c=black:s=320x180:r=25",
        *input_args(png, item, 25),
        "-filter_complex", graph, "-map", "[vtext]", "-t", "3", "-pix_fmt", "yuv420p", str(out),
    ]  # fmt: skip
    subprocess.run(command, check=True)  # noqa: S603

    def brightness(second: float) -> float:
        raw = subprocess.run(  # noqa: S603
            ["ffmpeg", "-v", "error", "-ss", str(second), "-i", str(out), "-frames:v", "1",
             "-f", "rawvideo", "-pix_fmt", "gray", "-"],
            check=True, capture_output=True,
        ).stdout  # fmt: skip
        return float(max(raw))

    before = brightness(0.5)
    assert brightness(1.5) > before
    assert brightness(2.6) == before
