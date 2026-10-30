"""Analysis cache in media/cache/{hash}/. Spec: specs/02-architecture.md#storage-replaces-minio"""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from app.domain.analysis import ANALYSIS_VERSION, StoredAnalysis

CACHE_FOLDER = "cache"
ANALYSIS_FILE = "analysis.json"
THUMBNAIL_FILE = "thumbnail.jpg"


class FileCache:
    def __init__(self, media_root: Path) -> None:
        self._media_root = media_root

    def load(self, file_hash: str) -> StoredAnalysis | None:
        """The stored analysis. A damaged or outdated document counts as no analysis."""
        path = self._folder(file_hash) / ANALYSIS_FILE
        if not path.exists():
            return None
        try:
            analysis = StoredAnalysis.model_validate_json(path.read_text(encoding="utf-8"))
        except ValidationError:
            return None
        return analysis if analysis.version == ANALYSIS_VERSION else None

    def save(self, analysis: StoredAnalysis) -> None:
        folder = self._folder(analysis.file_hash)
        folder.mkdir(parents=True, exist_ok=True)
        temporary = folder / (ANALYSIS_FILE + ".tmp")
        temporary.write_text(analysis.model_dump_json(), encoding="utf-8")
        temporary.replace(folder / ANALYSIS_FILE)

    def analysis_path(self, file_hash: str) -> str:
        return f"{CACHE_FOLDER}/{file_hash}/{ANALYSIS_FILE}"

    def thumbnail_file(self, file_hash: str) -> Path:
        return self._folder(file_hash) / THUMBNAIL_FILE

    def _folder(self, file_hash: str) -> Path:
        return self._media_root / CACHE_FOLDER / file_hash
