"""The analysis document cached per file. Spec: specs/02-architecture.md#storage-replaces-minio"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.domain.music import MusicMap
from app.domain.shots import ShotMeasure

ANALYSIS_VERSION = 2


class StoredAnalysis(BaseModel):
    """Written once per content hash, so an identical file is never analyzed twice."""

    model_config = ConfigDict(frozen=True)

    version: int = ANALYSIS_VERSION
    file_hash: str
    codec: str | None
    width: int | None
    height: int | None
    fps: float | None
    rotation: int
    duration_sec: float | None
    transfer: str | None
    bit_depth: int | None
    camera_mode: str | None
    log_profile: str | None
    native_slow_mo: bool
    music: MusicMap | None = None
    shots: tuple[ShotMeasure, ...] = ()
