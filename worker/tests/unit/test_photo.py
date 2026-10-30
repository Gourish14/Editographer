"""Photo rules. Spec: specs/05-editing-brain.md#b4 and #b7, specs/04-pipeline.md (4) [T-403]"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.adapters.ffmpeg_photo import photo_command, photo_filter
from app.application.analyze_photo import AnalyzePhoto
from app.domain.errors import AnalysisError
from app.domain.photo import (
    DepthSummary,
    FocusBox,
    FocusSource,
    PhotoAnalysis,
    PhotoMotion,
    choose_motion,
    photo_allowed,
    photo_slot_budget,
)

FOCUS = FocusBox(0.6, 0.2, 0.2, 0.2, FocusSource.FACE)


def depth(contrast: float) -> DepthSummary:
    return DepthSummary(contrast=contrast, near_threshold=120, map_file="depth.png")


def analysis(motion: PhotoMotion) -> PhotoAnalysis:
    return PhotoAnalysis(4000, 3000, FOCUS, motion, depth(0.8))


def test_b4_photos_fill_at_most_thirty_percent_of_slots() -> None:
    assert photo_slot_budget(10, photos_only=False) == 3
    assert photo_slot_budget(9, photos_only=False) == 2
    assert photo_allowed(2, 10, is_drop=False, photos_only=False)
    assert not photo_allowed(3, 10, is_drop=False, photos_only=False)


def test_b4_a_photo_never_takes_a_drop_slot() -> None:
    assert not photo_allowed(0, 10, is_drop=True, photos_only=False)


def test_b4_photos_only_input_has_no_cap_and_drops_are_allowed() -> None:
    assert photo_slot_budget(10, photos_only=True) == 10
    assert photo_allowed(9, 10, is_drop=True, photos_only=True)


def test_b7_high_depth_contrast_chooses_parallax_else_ken_burns() -> None:
    assert choose_motion(depth(0.8)) is PhotoMotion.PARALLAX
    assert choose_motion(depth(0.79)) is PhotoMotion.KEN_BURNS
    assert choose_motion(None) is PhotoMotion.KEN_BURNS


def test_b7_ken_burns_filter_zooms_to_1_12_with_exact_frame_count() -> None:
    text = photo_filter(analysis(PhotoMotion.KEN_BURNS), 1080, 1920, 30, 45)

    assert "z='1+0.1200*" in text
    assert "d=45" in text
    assert "trim=end_frame=45" in text
    assert "s=1080x1920" in text and "fps=30" in text
    assert "[1:v]" not in text


def test_b7_ken_burns_pans_toward_the_subject_center() -> None:
    text = photo_filter(analysis(PhotoMotion.KEN_BURNS), 1920, 1080, 30, 30)

    assert "x='(iw-iw/zoom)*0.7000'" in text
    assert "y='(ih-ih/zoom)*0.3000'" in text


def test_b7_parallax_moves_the_near_layer_more_than_the_background() -> None:
    text = photo_filter(analysis(PhotoMotion.PARALLAX), 1080, 1920, 30, 60)

    assert "1+0.0400*" in text and "1+0.1200*" in text
    assert "alphamerge" in text and "[1:v]" in text
    assert text.endswith("[v]") and "trim=end_frame=60" in text


def test_b7_parallax_without_a_depth_map_falls_back_to_ken_burns() -> None:
    bare = PhotoAnalysis(4000, 3000, FOCUS, PhotoMotion.PARALLAX, None)

    assert "alphamerge" not in photo_filter(bare, 1080, 1920, 30, 30)


def test_a_photo_clip_needs_at_least_one_frame() -> None:
    with pytest.raises(ValueError, match="at least one frame"):
        photo_filter(analysis(PhotoMotion.KEN_BURNS), 1080, 1920, 30, 0)


def test_photo_command_adds_the_depth_map_as_second_input_and_limits_frames() -> None:
    command = photo_command(
        analysis(PhotoMotion.PARALLAX), Path("p.jpg"), Path("o.mp4"), 1080, 1920, 30, 60
    )

    assert command.count("-i") == 2 and "depth.png" in command
    assert command[command.index("-frames:v") + 1] == "60"


class FakeSizer:
    def size(self, image: Path) -> tuple[int, int]:
        return 400, 300


class FakeLocator:
    def locate(self, image: Path) -> FocusBox:
        return FOCUS


class FakeDepth:
    def __init__(self, contrast: float) -> None:
        self._contrast = contrast

    def estimate(self, image: Path, map_file: Path) -> DepthSummary:
        return depth(self._contrast)


def test_analyze_photo_returns_size_focus_depth_and_motion(tmp_path: Path) -> None:
    image = tmp_path / "a.jpg"
    image.write_bytes(b"x")

    result = AnalyzePhoto(FakeSizer(), FakeLocator(), FakeDepth(0.9)).run(image, tmp_path / "d.png")

    assert (result.width, result.height) == (400, 300)
    assert result.focus is FOCUS
    assert result.motion is PhotoMotion.PARALLAX


def test_analyze_photo_rejects_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(AnalysisError):
        AnalyzePhoto(FakeSizer(), FakeLocator(), FakeDepth(0.1)).run(
            tmp_path / "none.jpg", tmp_path / "d.png"
        )
