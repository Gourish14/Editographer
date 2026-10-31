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


class CameraKeyframe(_PlanModel):
    """A virtual camera pose. `ease` shapes the span that starts at this keyframe."""

    t: float
    yaw: float
    pitch: float
    roll: float = 0.0
    fov: float
    ease: str = "linear"
    projection: str | None = None


class Camera360(_PlanModel):
    projection: str = "rectilinear"
    follow: str | None = None
    keyframes: tuple[CameraKeyframe, ...] = ()


class Motion(_PlanModel):
    """Photo motion. `focus_x` and `focus_y` are the point it pushes toward, as frame shares."""

    type: str = "kenburns"
    depth: bool = False
    direction: str = "push_in"
    focus_x: float = 0.5
    focus_y: float = 0.5


class Segment(_PlanModel):
    id: str
    asset_id: str
    type: str
    src_in: float = 0.0
    src_out: float = 0.0
    at: float
    duration: float
    speed: Speed = Speed()
    reframe: Reframe = Reframe()
    effects: tuple[Effect, ...] = ()
    transition_out: Transition = Transition()
    source: Source = Source(camera_mode=None, log_profile=None, native_fps=None)
    camera360: Camera360 | None = None
    motion: Motion | None = None
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
