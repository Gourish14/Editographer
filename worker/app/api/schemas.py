"""Request and response bodies.

Spec: specs/07-api-and-data.md#worker-api-fastapi-port-8090-localhost-only
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.domain.models import (
    AnalyzeJob,
    AssetInput,
    AssetType,
    GpuStatus,
    RenderJob,
    RenderSettings,
)


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, frozen=True)


class GpuResponse(ApiModel):
    name: str
    vram_free_mb: int
    temp_c: int

    @classmethod
    def of(cls, status: GpuStatus | None) -> GpuResponse | None:
        if status is None:
            return None
        return cls(name=status.name, vram_free_mb=status.vram_free_mb, temp_c=status.temp_c)


class HealthResponse(ApiModel):
    busy: bool
    current_job_id: str | None
    gpu: GpuResponse | None


class AnalyzeRequest(ApiModel):
    job_id: str
    asset_id: str
    path: str
    type: AssetType
    proxy_source: str | None = None

    def to_job(self) -> AnalyzeJob:
        return AnalyzeJob(self.job_id, self.asset_id, self.path, self.type, self.proxy_source)


class RenderSettingsBody(ApiModel):
    ratio: str
    quality: str
    fps: int
    style: str
    mode: str
    length_sec: int | None = None
    prompt: str | None = None
    cool_mode: bool = False
    seed: int

    def to_settings(self) -> RenderSettings:
        return RenderSettings(
            self.ratio,
            self.quality,
            self.fps,
            self.style,
            self.mode,
            self.length_sec,
            self.prompt,
            self.cool_mode,
            self.seed,
        )


class AssetBody(ApiModel):
    id: str
    type: AssetType
    path: str
    analysis_path: str | None = None
    camera_mode: str | None = None
    log_profile: str | None = None
    duration_sec: float | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None

    def to_input(self) -> AssetInput:
        return AssetInput(
            self.id,
            self.type,
            self.path,
            self.analysis_path,
            self.camera_mode,
            self.log_profile,
            self.duration_sec,
            self.width,
            self.height,
            self.fps,
        )


class RenderRequest(ApiModel):
    job_id: str
    render_id: str
    project_id: str
    settings: RenderSettingsBody
    assets: list[AssetBody]

    def to_job(self) -> RenderJob:
        return RenderJob(
            self.job_id,
            self.render_id,
            self.project_id,
            self.settings.to_settings(),
            tuple(asset.to_input() for asset in self.assets),
        )
