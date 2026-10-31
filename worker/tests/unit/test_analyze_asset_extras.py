"""Photo analysis and speech detection inside AnalyzeAsset. Spec: specs/04-pipeline.md [T-404]"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from app.application.analyze_asset import AnalyzeAsset
from app.application.analyze_music import AnalyzeMusic
from app.application.analyze_photo import AnalyzePhoto
from app.application.analyze_shots import AnalyzeShots
from app.application.job_runner import CancellationToken
from app.domain.media import MediaInfo
from app.domain.models import AssetType
from app.domain.photo import DepthSummary, FocusBox, FocusSource, PhotoMotion
from app.ports.speech import SpeechResult, SpeechSpan, SpokenWord
from tests.unit.shot_fakes import FakeEncoder, FakeObjects
from tests.unit.test_analyze_asset import (
    Curves,
    Decoder,
    Fixture,
    Frames,
    Hasher,
    Scenes,
    Tracker,
)


class FakePhotos:
    """One object standing in for the sizer, locator and depth estimator."""

    def __init__(self) -> None:
        self.maps: list[Path] = []

    def size(self, image: Path) -> tuple[int, int]:
        return 400, 300

    def locate(self, image: Path) -> FocusBox:
        return FocusBox(0.4, 0.4, 0.2, 0.2, FocusSource.CENTER)

    def estimate(self, image: Path, map_file: Path) -> DepthSummary:
        self.maps.append(map_file)
        return DepthSummary(0.5, 100, str(map_file))


class SilentProbe:
    def __init__(self, base: MediaInfo, silent: bool) -> None:
        self._info = dataclasses.replace(base, has_audio=not silent)

    def probe(self, path: Path) -> MediaInfo:
        return self._info


class FakeSpeech:
    def __init__(self) -> None:
        self.heard: list[Path] = []

    def detect(self, media: Path) -> SpeechResult:
        self.heard.append(media)
        return SpeechResult((SpeechSpan(1.0, 2.0),), (SpokenWord("hi", 1.0, 1.5),))


@pytest.fixture
def fx(tmp_path: Path) -> Fixture:
    return Fixture(tmp_path)


def build(fx: Fixture, silent: bool = False) -> tuple[AnalyzeAsset, FakePhotos, FakeSpeech]:
    photos, speech = FakePhotos(), FakeSpeech()
    use_case = AnalyzeAsset(
        fx.root,
        SilentProbe(fx.probe.probe(fx.root), silent),
        Hasher(),
        fx.cache,
        fx.tools,
        fx.tools,
        fx.notifier,
        AnalyzeMusic(Decoder(), Tracker(), Curves()),
        AnalyzeShots(Scenes(), Frames(), FakeObjects(), FakeEncoder()),
        AnalyzePhoto(photos, photos, photos),
        speech,
    )
    return use_case, photos, speech


def test_t404_a_video_stores_its_speech_spans_and_words(fx: Fixture) -> None:
    use_case, _, speech = build(fx)

    use_case.run(fx.job(), CancellationToken())

    assert speech.heard == [fx.root / "uploads/a.mp4"]
    assert fx.cache.stored is not None
    assert fx.cache.stored.speech is not None
    assert fx.cache.stored.speech.spans == ((1.0, 2.0),)
    assert fx.cache.stored.speech.words == (("hi", 1.0, 1.5),)


def test_t404_a_silent_video_is_not_sent_to_speech_detection(fx: Fixture) -> None:
    use_case, _, speech = build(fx, silent=True)

    use_case.run(fx.job(), CancellationToken())

    assert speech.heard == []
    assert fx.cache.stored is not None
    assert fx.cache.stored.speech is None


def test_t404_a_photo_stores_its_photo_analysis(fx: Fixture) -> None:
    use_case, photos, speech = build(fx)

    use_case.run(fx.job(AssetType.PHOTO), CancellationToken())

    assert fx.cache.stored is not None
    photo = fx.cache.stored.photo
    assert photo is not None
    assert (photo.width, photo.height, photo.motion) == (400, 300, PhotoMotion.KEN_BURNS)
    assert photo.depth == DepthSummary(0.5, 100, str(fx.root / "cache/abc/depth.png"))
    assert photos.maps == [fx.root / "cache/abc/depth.png"]
    assert speech.heard == []
