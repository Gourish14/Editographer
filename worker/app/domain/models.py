"""Data shared across the worker.

Spec: specs/07-api-and-data.md#worker-api-fastapi-port-8090-localhost-only
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class JobKind(StrEnum):
    ANALYZE = "ANALYZE"
    RENDER = "RENDER"


class AssetType(StrEnum):
    VIDEO = "VIDEO"
    PHOTO = "PHOTO"
    MUSIC = "MUSIC"


@dataclass(frozen=True)
class GpuStatus:
    name: str
    vram_free_mb: int
    temp_c: int


@dataclass(frozen=True)
class AnalyzeJob:
    job_id: str
    asset_id: str
    path: str
    type: AssetType
    proxy_source: str | None = None


@dataclass(frozen=True)
class FollowPoint:
    """The subject to follow in 360 clips: a tap on the equirect frame, as shares 0..1."""

    x: float
    y: float
    time_sec: float


@dataclass(frozen=True)
class RenderSettings:
    ratio: str
    quality: str
    fps: int
    style: str
    mode: str
    length_sec: int | None
    prompt: str | None
    cool_mode: bool
    seed: int
    follow_point: FollowPoint | None = None


@dataclass(frozen=True)
class AssetInput:
    id: str
    type: AssetType
    path: str
    analysis_path: str | None
    camera_mode: str | None
    log_profile: str | None
    duration_sec: float | None
    width: int | None
    height: int | None
    fps: float | None


@dataclass(frozen=True)
class RenderJob:
    job_id: str
    render_id: str
    project_id: str
    settings: RenderSettings
    assets: tuple[AssetInput, ...]
