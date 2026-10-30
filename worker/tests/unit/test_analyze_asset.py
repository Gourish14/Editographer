"""Tests for the analyze use case. Spec: specs/04-pipeline.md#stages (1) [T-109]"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.application.analyze_asset import AnalyzeAsset
from app.application.job_runner import CancellationToken
from app.domain.analysis import StoredAnalysis
from app.domain.errors import AnalysisError, ErrorCode, JobCancelledError
from app.domain.media import MediaInfo
from app.domain.models import AnalyzeJob, AssetType
from tests.unit.test_job_runner import FakeNotifier

HASH = "abc"
INFO = MediaInfo("hevc", 3840, 1920, 100.0, 0, 20.0, "bt709", 10, ())


class Tools:
    def __init__(self) -> None:
        self.made: list[Path] = []
        self.adopted: list[Path] = []
        self.thumbnails: list[float] = []

    def make_proxy(self, source: Path, target: Path) -> None:
        self.made.append(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("proxy")

    def adopt_proxy(self, source: Path, target: Path) -> None:
        self.adopted.append(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("lrf")

    def make_thumbnail(self, source: Path, target: Path, at_sec: float) -> None:
        self.thumbnails.append(at_sec)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("jpeg")


class Probe:
    def __init__(self) -> None:
        self.calls = 0

    def probe(self, path: Path) -> MediaInfo:
        self.calls += 1
        return INFO


class Hasher:
    def hash_file(self, path: Path) -> str:
        return HASH


class Cache:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.stored: StoredAnalysis | None = None

    def load(self, file_hash: str) -> StoredAnalysis | None:
        return self.stored

    def save(self, analysis: StoredAnalysis) -> None:
        self.stored = analysis

    def analysis_path(self, file_hash: str) -> str:
        return f"cache/{file_hash}/analysis.json"

    def thumbnail_file(self, file_hash: str) -> Path:
        return self.root / "cache" / file_hash / "thumbnail.jpg"


class Reporter(FakeNotifier):
    def __init__(self) -> None:
        super().__init__()
        self.analyses: list[object] = []
        self.done: list[str] = []

    def asset_analyzed(self, analysis: object) -> None:
        self.analyses.append(analysis)

    def job_done(self, job_id: str, output_path: object = None, plan: object = None) -> None:
        self.done.append(job_id)


class Fixture:
    def __init__(self, root: Path) -> None:
        self.root = root
        (root / "uploads").mkdir()
        (root / "uploads/a.mp4").write_text("clip")
        self.probe = Probe()
        self.tools = Tools()
        self.cache = Cache(root)
        self.notifier = Reporter()
        self.use_case = AnalyzeAsset(
            root, self.probe, Hasher(), self.cache, self.tools, self.tools, self.notifier
        )

    def job(self, kind: AssetType = AssetType.VIDEO, proxy_source: str | None = None) -> AnalyzeJob:
        return AnalyzeJob("j1", "a1", "uploads/a.mp4", kind, proxy_source)


@pytest.fixture
def fx(tmp_path: Path) -> Fixture:
    return Fixture(tmp_path)


def test_a_video_gets_analysis_proxy_thumbnail_and_a_report(fx: Fixture) -> None:
    fx.use_case.run(fx.job(), CancellationToken())

    assert fx.cache.stored is not None
    assert fx.cache.stored.camera_mode == "OSMO360_PANO_4K100"
    assert fx.cache.stored.native_slow_mo is True
    assert (fx.root / "proxies/a1.mp4").exists()
    assert fx.tools.thumbnails == [pytest.approx(2.0)]
    assert fx.notifier.done == ["j1"]
    report = fx.notifier.analyses[0]
    assert report.file_hash == HASH  # type: ignore[attr-defined]
    assert report.analysis_path == "cache/abc/analysis.json"  # type: ignore[attr-defined]
    assert report.width == 3840  # type: ignore[attr-defined]


def test_a_matching_lrf_is_used_instead_of_making_a_proxy(fx: Fixture) -> None:
    (fx.root / "uploads/b.lrf").write_text("lrf")

    fx.use_case.run(fx.job(proxy_source="uploads/b.lrf"), CancellationToken())

    assert fx.tools.made == []
    assert fx.tools.adopted == [fx.root / "uploads/b.lrf"]


def test_music_gets_no_proxy_or_thumbnail(fx: Fixture) -> None:
    fx.use_case.run(fx.job(AssetType.MUSIC), CancellationToken())

    assert fx.tools.made == []
    assert fx.tools.thumbnails == []
    assert fx.notifier.done == ["j1"]


def test_a_photo_gets_a_thumbnail_but_no_proxy(fx: Fixture) -> None:
    fx.use_case.run(fx.job(AssetType.PHOTO), CancellationToken())

    assert fx.tools.made == []
    assert len(fx.tools.thumbnails) == 1


def test_identical_content_is_not_analyzed_twice(fx: Fixture) -> None:
    fx.use_case.run(fx.job(), CancellationToken())
    fx.use_case.run(AnalyzeJob("j2", "a2", "uploads/a.mp4", AssetType.VIDEO), CancellationToken())

    assert fx.probe.calls == 1
    assert fx.tools.thumbnails == [pytest.approx(2.0)]
    assert (fx.root / "proxies/a2.mp4").exists()
    assert fx.notifier.done == ["j1", "j2"]


def test_a_missing_file_fails_with_asset_not_found(fx: Fixture) -> None:
    job = AnalyzeJob("j1", "a1", "uploads/gone.mp4", AssetType.VIDEO)

    with pytest.raises(AnalysisError) as failure:
        fx.use_case.run(job, CancellationToken())

    assert failure.value.code is ErrorCode.ASSET_NOT_FOUND


def test_a_cancelled_job_stops_before_any_report(fx: Fixture) -> None:
    token = CancellationToken()
    token.cancel()

    with pytest.raises(JobCancelledError):
        fx.use_case.run(fx.job(), token)

    assert fx.notifier.analyses == []
    assert fx.notifier.done == []
