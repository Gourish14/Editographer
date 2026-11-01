"""A follow point names its 360 clip, and the drop spin lands on that clip.

Spec: specs/08-osmo360.md rule 5, specs/05-editing-brain.md#b4-shot-assignment and #b7 [CR-014]
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import pytest

from app.application.render_job import RenderEdit
from app.domain.brain.framing import follows, resolve_follow_point
from app.domain.brain.pacing import beat_grid
from app.domain.brain.planner import ClipInput
from app.domain.models import AssetInput, AssetType, FollowPoint, RenderJob
from app.domain.plan import EditPlan, Segment
from tests.unit.test_planner import analysis, measure, music_map
from tests.unit.test_ramps_and_framing import SETTINGS, pano, plan_of

TAP = FollowPoint(0.75, 0.5, 2.0)


def named(asset_id: str | None) -> FollowPoint:
    return dataclasses.replace(TAP, asset_id=asset_id)


def two_panos() -> list[ClipInput]:
    return [dataclasses.replace(pano(), asset_id="v0"), dataclasses.replace(pano(), asset_id="v1")]


def spun(plan: EditPlan) -> list[Segment]:
    """The drop's first segments: the beat spin always comes with the white flash."""
    return [s for s in plan.segments if any(e.type == "flash" for e in s.effects)]


def test_08_rule5_a_point_without_an_asset_id_belongs_to_the_first_360_clip() -> None:
    point, note = resolve_follow_point(named(None), ["v3", "v5"])

    assert point is not None
    assert point.asset_id == "v3"
    assert note is None


def test_08_rule5_a_point_for_a_clip_that_is_not_360_is_dropped_with_a_note() -> None:
    for id_ in ("flat-clip", "gone"):
        point, note = resolve_follow_point(named(id_), ["v3"])

        assert point is None
        assert note is not None
        assert "not a 360 clip" in note


def test_08_rule5_a_named_360_clip_keeps_its_point_and_no_point_stays_none() -> None:
    assert resolve_follow_point(named("v5"), ["v3", "v5"]) == (named("v5"), None)
    assert resolve_follow_point(None, ["v3"]) == (None, None)
    assert resolve_follow_point(named(None), []) == (None, None)


def test_08_rule5_a_point_is_for_its_own_clip_only() -> None:
    assert follows(named("v1"), "v1") == named("v1")
    assert follows(named("v1"), "v0") is None
    assert follows(named(None), "v0") == named(None)


def test_08_rule5_only_the_tapped_360_clip_starts_on_the_picked_subject() -> None:
    plan = plan_of(two_panos(), follow_point=named("v1"))

    for segment in plan.segments:
        assert segment.camera360 is not None
        picked = segment.camera360.follow == "picked"
        assert picked == (segment.asset_id == "v1")
    assert {s.asset_id for s in plan.segments} == {"v0", "v1"}


@pytest.mark.parametrize("followed", ["v0", "v1"])
def test_b4_the_drop_spin_lands_on_the_followed_360_clip(followed: str) -> None:
    plan = plan_of(two_panos(), follow_point=named(followed))

    drops = spun(plan)
    assert drops
    assert {s.asset_id for s in drops} == {followed}


def test_b4_every_cut_stays_on_the_beat_grid_when_the_drop_prefers_a_clip() -> None:
    grid = beat_grid(music_map())
    plan = plan_of(two_panos(), follow_point=named("v1"))

    for segment in plan.segments:
        window = 0.0
        assert any(abs(window + segment.at - beat) < 1e-3 for beat in grid)
        end = window + segment.at + segment.duration
        assert any(abs(end - beat) < 1e-3 for beat in grid)


def test_b4_a_followed_clip_that_has_no_shot_for_the_drop_changes_nothing() -> None:
    flat = ClipInput("v0", analysis(measure(0.0, 30.0)))
    other = dataclasses.replace(pano(), asset_id="v1")

    plain = plan_of([flat, other])
    asked = plan_of([flat, other], follow_point=named("nope"))

    assert [s.asset_id for s in asked.segments] == [s.asset_id for s in plain.segments]


def edit_for(assets: list[AssetInput], inputs: list[ClipInput], point: FollowPoint | None) -> Any:
    nothing: Any = None
    edit = RenderEdit(Path(), nothing, nothing, nothing, nothing, nothing, nothing)
    job = RenderJob("j", "r", "p", dataclasses.replace(SETTINGS, follow_point=point), tuple(assets))
    return edit._with_resolved_follow(job, assets, inputs)


def clip_asset(asset_id: str) -> AssetInput:
    return AssetInput(
        asset_id,
        AssetType.VIDEO,
        f"uploads/{asset_id}.mp4",
        None,
        None,
        None,
        30.0,
        7680,
        3840,
        30.0,
    )


def test_08_rule5_the_render_ties_an_untagged_point_to_the_first_360_clip() -> None:
    flat = ClipInput("a0", analysis(measure(0.0, 30.0)))
    other = dataclasses.replace(pano(), asset_id="a1")
    assets = [clip_asset("a0"), clip_asset("a1")]

    job, note = edit_for(assets, [flat, other], named(None))

    assert job.settings.follow_point == named("a1")
    assert note is None


def test_08_rule5_the_render_refuses_a_point_on_a_flat_clip_and_says_so() -> None:
    flat = ClipInput("a0", analysis(measure(0.0, 30.0)))
    other = dataclasses.replace(pano(), asset_id="a1")
    assets = [clip_asset("a0"), clip_asset("a1")]

    job, note = edit_for(assets, [flat, other], named("a0"))

    assert job.settings.follow_point is None
    assert note is not None
