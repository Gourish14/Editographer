"""Tests for shot analysis with fake models. Spec: specs/04-pipeline.md#stages (3) [T-201]"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.adapters.model_runtime import pin_model_folders, require_file
from app.application.analyze_shots import AnalyzeShots
from app.domain.errors import AnalysisError
from app.domain.shots import DetectedObject, FrameObjects, FrameSample, ShotVision
from tests.unit.shot_fakes import CAR_VECTOR, FakeEncoder, FakeObjects

PROXY = Path("proxy.mp4")


class Scenes:
    def __init__(self, spans: tuple[tuple[float, float], ...]) -> None:
        self.spans = spans

    def detect(self, path: Path) -> tuple[tuple[float, float], ...]:
        return self.spans


class Frames:
    def sample(self, path: Path) -> tuple[FrameSample, ...]:
        return tuple(FrameSample(i * 0.25, 1.0, 0.5, 100.0, 0.5, 0.0) for i in range(20))


def person(time: float) -> FrameObjects:
    return FrameObjects(time, (DetectedObject("person", 0.9, 0.5, 0.5, 0.5, 0.5),))


def test_b2_a_shot_stores_tags_aesthetics_and_its_embedding() -> None:
    encoder = FakeEncoder(ShotVision(CAR_VECTOR, 0.7))
    objects = FakeObjects(tuple(person(i * 0.25) for i in range(8)))

    measure = AnalyzeShots(Scenes(()), Frames(), objects, encoder).run(PROXY, 5.0)[0]

    assert measure.aesthetics == 0.7
    assert measure.embedding == CAR_VECTOR
    assert measure.tags == ("car", "person")


def test_b2_each_shot_only_counts_its_own_objects() -> None:
    objects = FakeObjects((person(0.0), person(0.25)))
    spans = ((0.0, 1.0), (1.0, 5.0))

    first, second = AnalyzeShots(Scenes(spans), Frames(), objects, FakeEncoder()).run(PROXY, 5.0)

    assert first.subject > 0.0
    assert second.subject == 0.0


def test_b2_clip_is_only_asked_about_spans_that_have_frames() -> None:
    encoder = FakeEncoder()
    spans = ((0.0, 2.0), (30.0, 30.1))

    AnalyzeShots(Scenes(spans), Frames(), FakeObjects(), encoder).run(PROXY, 40.0)

    assert encoder.spans == [(0.0, 2.0)]


def test_b2_with_no_shot_to_measure_no_model_is_loaded() -> None:
    objects, encoder = FakeObjects(), FakeEncoder()

    result = AnalyzeShots(Scenes(((30.0, 31.0),)), Frames(), objects, encoder).run(PROXY, 40.0)

    assert result == ()
    assert objects.calls == 0
    assert encoder.texts == []


def test_rule_3_model_libraries_are_pinned_inside_the_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("TORCH_HOME", "HF_HOME", "YOLO_CONFIG_DIR"):
        monkeypatch.setenv(name, "C:/Users/someone/.cache")

    pin_model_folders(tmp_path)

    for name in ("TORCH_HOME", "HF_HOME", "YOLO_CONFIG_DIR", "MPLCONFIGDIR"):
        assert Path(os.environ[name]).is_relative_to(tmp_path)


def test_rule_2_model_libraries_are_told_to_stay_offline(tmp_path: Path) -> None:
    pin_model_folders(tmp_path)

    assert os.environ["HF_HUB_OFFLINE"] == "1"
    assert os.environ["YOLO_OFFLINE"] == "true"
    assert os.environ["YOLO_AUTOINSTALL"] == "false"


def test_a_missing_model_file_fails_clearly_instead_of_downloading(tmp_path: Path) -> None:
    with pytest.raises(AnalysisError, match="setup.bat"):
        require_file(tmp_path / "yolo11n.pt")
