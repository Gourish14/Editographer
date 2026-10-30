"""Ports for inspecting and converting media. Spec: specs/04-pipeline.md#stages"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.domain.analysis import StoredAnalysis
from app.domain.media import MediaInfo


class MediaProbe(Protocol):
    def probe(self, path: Path) -> MediaInfo:
        """Reads the file's facts. Raises AnalysisError when it is not readable media."""
        ...


class ContentHasher(Protocol):
    def hash_file(self, path: Path) -> str:
        """A cache key from the first and last 16 MB plus the size."""
        ...


class ProxyMaker(Protocol):
    def make_proxy(self, source: Path, target: Path) -> None:
        """Writes a 720p H.264 video with no audio."""
        ...

    def adopt_proxy(self, source: Path, target: Path) -> None:
        """Uses a file the camera already made, such as an Osmo .LRF."""
        ...


class ThumbnailMaker(Protocol):
    def make_thumbnail(self, source: Path, target: Path, at_sec: float) -> None:
        """Writes a JPEG of the frame at the given time."""
        ...


class AnalysisCache(Protocol):
    def load(self, file_hash: str) -> StoredAnalysis | None: ...

    def save(self, analysis: StoredAnalysis) -> None: ...

    def analysis_path(self, file_hash: str) -> str:
        """The document's path relative to the media folder."""
        ...

    def thumbnail_file(self, file_hash: str) -> Path: ...
