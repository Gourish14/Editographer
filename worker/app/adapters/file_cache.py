"""Analysis cache in media/cache/{hash}/. Spec: specs/02-architecture.md#storage-replaces-minio"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from app.domain.analysis import ANALYSIS_VERSION, StoredAnalysis
from app.domain.music import MusicMap
from app.domain.plan import EditPlan

CACHE_FOLDER = "cache"
ANALYSIS_FILE = "analysis.json"
THUMBNAIL_FILE = "thumbnail.jpg"
WAVEFORM_FILE = "waveform.json"
WAVEFORM_PEAKS = 800
RENDERS_FOLDER = "renders"
PLAN_FILE = "plan.json"


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

    def save_waveform(self, file_hash: str, music: MusicMap) -> None:
        folder = self._folder(file_hash)
        folder.mkdir(parents=True, exist_ok=True)
        document = {
            "durationSec": music.duration_sec,
            "peaks": _peaks(music.energy),
            "beats": [beat.time for beat in music.beats],
            "downbeats": list(music.downbeats),
            "sections": [
                {"kind": section.kind.value, "start": section.start, "end": section.end}
                for section in music.sections
            ],
        }
        (folder / WAVEFORM_FILE).write_text(json.dumps(document), encoding="utf-8")

    def save_plan(self, render_id: str, plan: EditPlan) -> None:
        folder = self._media_root / RENDERS_FOLDER / render_id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / PLAN_FILE).write_text(plan.model_dump_json(by_alias=True), encoding="utf-8")

    def _folder(self, file_hash: str) -> Path:
        return self._media_root / CACHE_FOLDER / file_hash


def _peaks(energy: tuple[float, ...]) -> list[float]:
    """Thins the energy curve to a size the browser can draw."""
    step = max(1, len(energy) // WAVEFORM_PEAKS)
    return [round(max(energy[i : i + step]), 3) for i in range(0, len(energy), step)]
