"""The edit plan. Spec: specs/06-edit-plan-schema.md#edit-plan"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

PLAN_VERSION = 1


class _PlanModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, frozen=True)


class Output(_PlanModel):
    ratio: str
    quality: str
    width: int
    height: int
    fps: int
    mode: str


class MusicWindow(_PlanModel):
    asset_id: str
    start: float
    end: float
    bpm: float


class Grade(_PlanModel):
    lut: str
    intensity: float
    grain: float


class Speed(_PlanModel):
    curve: tuple[tuple[float, float], ...] = ((0.0, 1.0), (1.0, 1.0))
    interpolate: str = "none"


class Reframe(_PlanModel):
    mode: str = "center"
    subject: str | None = None


class Effect(_PlanModel):
    type: str
    at: float = 0.0
    duration: float = 0.0
    strength: float | None = None
    amount: float | None = None


class Transition(_PlanModel):
    type: str = "cut"
    duration: float = 0.0


class Source(_PlanModel):
    camera_mode: str | None
    log_profile: str | None
    native_fps: float | None


class Segment(_PlanModel):
    id: str
    asset_id: str
    type: str
    src_in: float
    src_out: float
    at: float
    duration: float
    speed: Speed = Speed()
    reframe: Reframe = Reframe()
    effects: tuple[Effect, ...] = ()
    transition_out: Transition = Transition()
    source: Source
    keep_audio: bool = False


class SfxCue(_PlanModel):
    type: str
    at: float
    gain_db: float


class EditPlan(_PlanModel):
    version: int = PLAN_VERSION
    seed: int
    style: str
    output: Output
    music: MusicWindow
    grade: Grade
    segments: tuple[Segment, ...]
    sfx: tuple[SfxCue, ...] = ()
    log: tuple[str, ...] = ()
