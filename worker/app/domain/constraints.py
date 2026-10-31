"""What a prompt asks for. Spec: specs/06-edit-plan-schema.md#prompt-constraint-json"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

from app.domain.music import SectionKind

StyleId = Literal["velocity", "hype", "cinematic", "anime", "travel", "car", "sports"]
ShotOrder = Literal["chronological", "energy"]


class _Model(BaseModel):
    """Unknown fields are refused: an LLM echoing its input must not pass as an empty answer."""

    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, frozen=True, extra="forbid"
    )


class Constraints(_Model):
    """Every field is optional; an empty model changes nothing."""

    style: StyleId | None = None
    include_tags: tuple[str, ...] = ()
    exclude_tags: tuple[str, ...] = ()
    slowmo_at: tuple[SectionKind, ...] = ()
    fx_intensity: float | None = Field(default=None, ge=0.0, le=1.0)
    effects_on: tuple[str, ...] = ()
    effects_off: tuple[str, ...] = ()
    duration_sec: float | None = Field(default=None, gt=0.0)
    text: tuple[str, ...] = ()
    order: ShotOrder | None = None
    unmapped: tuple[str, ...] = ()

    @field_validator("include_tags", "exclude_tags", "effects_on", "effects_off")
    @classmethod
    def _lower_case(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(value.strip().lower() for value in values if value.strip())


class DirectorDecision(_Model):
    """The director's reply, B10 in specs/05-editing-brain.md."""

    style: StyleId | None = None
    story_hints: tuple[str, ...] = ()
    constraints: Constraints = Constraints()


NO_CONSTRAINTS = Constraints()


@dataclass(frozen=True)
class Direction:
    """What planning follows: the decision, and notes the user should see in the plan log."""

    decision: DirectorDecision = DirectorDecision()
    notes: tuple[str, ...] = field(default=())
