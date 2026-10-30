"""Tests for filter building. Spec: specs/04-pipeline.md#stages (6) [T-113]"""

from __future__ import annotations

from app.adapters.ffmpeg_filters import segment_filter
from app.domain.plan import Effect

SHAKE = Effect(type="shake", at=0.0, duration=0.25, strength=0.8)
ZOOM = Effect(type="zoomPunch", at=0.5, duration=0.25, strength=0.15)
FLASH = Effect(type="flash", at=0.0, duration=0.08)


def test_a_plain_segment_stays_on_the_fast_path() -> None:
    chain = segment_filter((), 2160, 3840, 30, sharpen=False)

    assert chain.startswith("fps=30,format=yuv420p10le,crop=")
    assert "scale=2160:3840:flags=lanczos" in chain
    assert "eval=frame" not in chain


def test_every_chain_crops_to_the_output_ratio() -> None:
    chain = segment_filter((), 3840, 2160, 30, sharpen=False)

    assert "ih*1.777778" in chain
    assert "iw/1.777778" in chain


def test_a_zoom_scales_per_frame_then_crops_back_to_size() -> None:
    chain = segment_filter((ZOOM,), 2160, 3840, 30, sharpen=False)

    assert "eval=frame" in chain
    assert "crop=2160:3840" in chain
    assert "between(t,0.5000,0.7500)" in chain


def test_a_shake_overscans_so_no_edge_shows() -> None:
    chain = segment_filter((SHAKE,), 2160, 3840, 30, sharpen=False)

    assert "1.040" in chain
    assert "sin(t*71)" in chain
    assert "sin(t*53)" in chain


def test_a_flash_is_a_full_frame_box_while_it_lasts() -> None:
    chain = segment_filter((FLASH,), 2160, 3840, 30, sharpen=False)

    assert "drawbox=" in chain
    assert "enable='between(t,0.0000,0.0800)'" in chain


def test_sharpening_is_only_added_when_asked() -> None:
    assert "unsharp" in segment_filter((), 2160, 3840, 30, sharpen=True)
    assert "unsharp" not in segment_filter((), 2160, 3840, 30, sharpen=False)


def test_all_effects_combine() -> None:
    chain = segment_filter((SHAKE, ZOOM, FLASH), 1080, 1920, 60, sharpen=True)

    assert chain.startswith("fps=60")
    assert "1.040+0.150*" in chain
    assert "drawbox" in chain
