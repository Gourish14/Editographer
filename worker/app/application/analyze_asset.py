"""Analyzes one uploaded asset. Spec: specs/04-pipeline.md#stages (1)"""

from __future__ import annotations

from pathlib import Path

import structlog

from app.application.job_runner import CancellationToken
from app.domain.analysis import StoredAnalysis
from app.domain.errors import AnalysisError, ErrorCode
from app.domain.media import (
    MediaInfo,
    detect_camera_mode,
    detect_log_profile,
    is_native_slow_mo,
)
from app.domain.models import AnalyzeJob, AssetType
from app.ports.backend_notifier import AssetAnalysis, BackendNotifier
from app.ports.media import (
    AnalysisCache,
    ContentHasher,
    MediaProbe,
    ProxyMaker,
    ThumbnailMaker,
)

log = structlog.get_logger()
PROXIES_FOLDER = "proxies"
THUMBNAIL_POSITION = 0.1


class AnalyzeAsset:
    def __init__(
        self,
        media_root: Path,
        probe: MediaProbe,
        hasher: ContentHasher,
        cache: AnalysisCache,
        proxies: ProxyMaker,
        thumbnails: ThumbnailMaker,
        notifier: BackendNotifier,
    ) -> None:
        self._media_root = media_root
        self._probe = probe
        self._hasher = hasher
        self._cache = cache
        self._proxies = proxies
        self._thumbnails = thumbnails
        self._notifier = notifier

    def run(self, job: AnalyzeJob, token: CancellationToken) -> None:
        source = self._media_root / job.path
        if not source.exists():
            raise AnalysisError(f"Missing file: {job.path}", ErrorCode.ASSET_NOT_FOUND)

        file_hash = self._hasher.hash_file(source)
        token.raise_if_cancelled()
        analysis = self._cache.load(file_hash)
        if analysis is None:
            extension = source.suffix.removeprefix(".")
            analysis = self._document(self._probe.probe(source), file_hash, extension)
            self._cache.save(analysis)
        else:
            log.info("analysis.cache_hit", fileHash=file_hash)
        token.raise_if_cancelled()

        if job.type is AssetType.VIDEO:
            self._ensure_proxy(source, job)
        token.raise_if_cancelled()
        self._ensure_thumbnail(source, job, analysis)

        self._notifier.asset_analyzed(self._report(job, analysis))
        self._notifier.job_done(job.job_id)

    @staticmethod
    def _document(info: MediaInfo, file_hash: str, extension: str) -> StoredAnalysis:
        camera_mode = detect_camera_mode(info, extension)
        log_profile = detect_log_profile(info)
        return StoredAnalysis(
            file_hash=file_hash,
            codec=info.codec,
            width=info.width,
            height=info.height,
            fps=info.fps,
            rotation=info.rotation,
            duration_sec=info.duration_sec,
            transfer=info.transfer,
            bit_depth=info.bit_depth,
            camera_mode=camera_mode.value,
            log_profile=log_profile.value if log_profile else None,
            native_slow_mo=is_native_slow_mo(info),
        )

    def _ensure_proxy(self, source: Path, job: AnalyzeJob) -> None:
        target = self._media_root / PROXIES_FOLDER / f"{job.asset_id}.mp4"
        if target.exists():
            return
        if job.proxy_source is not None:
            self._proxies.adopt_proxy(self._media_root / job.proxy_source, target)
        else:
            self._proxies.make_proxy(source, target)

    def _ensure_thumbnail(self, source: Path, job: AnalyzeJob, analysis: StoredAnalysis) -> None:
        target = self._cache.thumbnail_file(analysis.file_hash)
        if job.type is AssetType.MUSIC or target.exists():
            return
        position = (analysis.duration_sec or 0.0) * THUMBNAIL_POSITION
        self._thumbnails.make_thumbnail(source, target, position)

    def _report(self, job: AnalyzeJob, analysis: StoredAnalysis) -> AssetAnalysis:
        return AssetAnalysis(
            asset_id=job.asset_id,
            analysis_path=self._cache.analysis_path(analysis.file_hash),
            file_hash=analysis.file_hash,
            camera_mode=analysis.camera_mode,
            log_profile=analysis.log_profile,
            duration_sec=analysis.duration_sec,
            width=analysis.width,
            height=analysis.height,
            fps=analysis.fps,
        )
