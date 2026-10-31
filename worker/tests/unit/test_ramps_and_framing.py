"""Ramps, reframing and 360 moves reaching the plan.

Spec: specs/05-editing-brain.md#b4-shot-assignment, #b5-effect-rules-effectspy,
#b6-speed-ramp-curve-rampspy, #b7-reframing-rules [T-405]
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from app.domain.brain.effects import WHIPS, plan_transitions, with_fov_punch
from app.domain.brain.pacing import beat_grid
from app.domain.brain.planner import ClipInput, build_edit_plan
from app.domain.brain.ramps import (
    RAMP_CURVE,
    curve_source_length,
    ramp_slot_starts,
    retime_expression,
    source_length,
    source_time_at,
    timeline_time_at,
)
from app.domain.brain.reframe import camera_at
from app.domain.brain.style_rules import VELOCITY
from app.domain.constraints import NO_CONSTRAINTS, Constraints, Direction, DirectorDecision
from app.domain.models import FollowPoint, RenderSettings
from app.domain.music import SectionKind
from app.domain.plan import Camera360, CameraKeyframe, EditPlan
from app.domain.shots import SubjectSample
from tests.unit.test_planner import analysis, measure, music_map

SETTINGS = RenderSettings("9:16", "4K", 30, "velocity", "fast", 40, None, False, 7)


def plan_of(
    clips: list[ClipInput], constraints: Constraints = NO_CONSTRAINTS, **changes: Any
) -> EditPlan:
    settings = dataclasses.replace(SETTINGS, **changes)
    direction = Direction(DirectorDecision(constraints=constraints))
    return build_edit_plan("m1", music_map(), clips, settings, direction)


def with_track(track: tuple[SubjectSample, ...], **fields: object) -> ClipInput:
    shot = measure(0.0, 30.0).model_copy(update={"subject_track": track})
    return ClipInput("v0", analysis(shot).model_copy(update=fields))


def drifting_subject() -> tuple[SubjectSample, ...]:
    return tuple(SubjectSample(time=i * 0.25, x=0.3 + 0.01 * i, y=0.5) for i in range(120))


def test_b6_source_time_adds_up_to_the_curve_length() -> None:
    assert source_time_at(RAMP_CURVE, 2.0, 2.0) == pytest.approx(source_length(2.0), rel=1e-3)
    assert source_time_at(RAMP_CURVE, 2.0, 0.0) == 0.0


def test_b6_timeline_time_inverts_source_time() -> None:
    for time in (0.3, 0.9, 1.2, 1.7):
        source = source_time_at(RAMP_CURVE, 2.0, time)
        assert timeline_time_at(RAMP_CURVE, 2.0, source) == pytest.approx(time, abs=1e-3)


def test_b6_retime_expression_is_a_closed_setpts_expression() -> None:
    expression = retime_expression(RAMP_CURVE, 2.0)

    assert "SRC" not in expression
    assert expression.count("(") == expression.count(")")
    assert expression.endswith("/TB")


def test_b6_a_ramp_needs_its_hold_start_on_the_grid_and_a_long_enough_slot() -> None:
    music = music_map()
    from app.domain.brain.pacing import Slot

    grid = beat_grid(music)
    good = Slot(0.0, 1.0, SectionKind.BREAK, 1.0, True)
    off_grid = Slot(0.0, 0.9, SectionKind.BREAK, 1.0, True)
    short = Slot(0.0, 0.25, SectionKind.BREAK, 1.0, True)

    chosen = ramp_slot_starts([good], (SectionKind.BREAK,), False, grid, 1 / 30)

    assert chosen == {0.0}
    assert ramp_slot_starts([off_grid], (SectionKind.BREAK,), False, grid, 1 / 30) == frozenset()
    assert ramp_slot_starts([short], (SectionKind.BREAK,), False, grid, 1 / 30) == frozenset()


def test_b4_a_ramped_slot_takes_the_extra_source_the_curve_needs() -> None:
    clip = ClipInput("v0", analysis(measure(0.0, 30.0)))
    plan = plan_of([clip], Constraints(slowmo_at=tuple(SectionKind)))

    ramped = [segment for segment in plan.segments if len(segment.speed.curve) > 2]

    assert ramped
    for segment in ramped:
        needed = curve_source_length(segment.speed.curve, segment.duration)
        assert segment.src_out - segment.src_in == pytest.approx(needed, abs=1e-3)
        assert segment.speed.interpolate == "rife"
        hold = segment.at + 0.5 * segment.duration
        assert min(abs(hold - time) for time in beat_grid(music_map())) < 1 / 30
    assert not any("Phase 3" in line for line in plan.log)


def test_b6_native_high_fps_footage_ramps_with_its_own_frames() -> None:
    clip = ClipInput("v0", analysis(measure(0.0, 30.0)).model_copy(update={"fps": 120.0}))

    plan = plan_of([clip], Constraints(slowmo_at=tuple(SectionKind)))

    assert {s.speed.interpolate for s in plan.segments if len(s.speed.curve) > 2} == {"native"}


def test_b6_velocity_ramps_its_drop_without_being_asked() -> None:
    clip = ClipInput("v0", analysis(measure(0.0, 30.0)))

    plan = plan_of([clip], style="velocity", length_sec=60)

    assert VELOCITY.id == plan.style
    assert plan.segments


def test_b7_a_flat_clip_with_a_subject_gets_a_crop_path() -> None:
    plan = plan_of([with_track(drifting_subject())])

    tracked = [segment for segment in plan.segments if segment.reframe.path]

    assert tracked
    segment = tracked[0]
    assert segment.type == "video"
    assert segment.reframe.mode == "track"
    assert all(0.0 <= point.x <= 1.0 and 0.0 <= point.y <= 1.0 for point in segment.reframe.path)


def test_b7_a_flat_clip_without_a_subject_stays_centered() -> None:
    plan = plan_of([with_track(())])

    assert all(not s.reframe.path and s.reframe.mode == "center" for s in plan.segments)


def pano(track: tuple[SubjectSample, ...] = ()) -> ClipInput:
    return with_track(track, camera_mode="OSMO360_PANO_8K", width=7680, height=3840)


def test_b7_a_360_clip_gets_a_camera_path_with_pitch_limited() -> None:
    plan = plan_of([pano(drifting_subject())])

    assert {segment.type for segment in plan.segments} == {"video360"}
    for segment in plan.segments:
        assert segment.camera360 is not None
        assert segment.source.width == 7680
        for key in segment.camera360.keyframes:
            if key.projection != "tinyplanet":
                assert key.pitch >= -60.0
    assert not any("center-cropped" in line for line in plan.log)


def test_b7_a_360_drop_spins_a_full_turn_on_its_first_beat() -> None:
    plan = plan_of([pano()])

    spins = [
        s
        for s in plan.segments
        if s.camera360 and max(k.yaw for k in s.camera360.keyframes) >= 360 - 1e-6
    ]

    assert spins
    assert all(any(e.type == "flash" for e in s.effects) for s in spins)


def test_b7_a_360_section_change_curls_into_a_tiny_planet() -> None:
    plan = plan_of([pano()])

    planets = [
        s
        for s in plan.segments
        if s.camera360 and any(k.projection == "tinyplanet" for k in s.camera360.keyframes)
    ]

    assert planets
    assert all(s.transition_out.type == "cut" for s in planets)


def test_b7_a_picked_follow_point_starts_every_360_camera_on_it() -> None:
    plan = plan_of([pano()], follow_point=FollowPoint(0.75, 0.5, 0.0))

    assert plan.segments[0].camera360 is not None
    assert camera_at(plan.segments[0].camera360, 0.0).yaw == pytest.approx(90.0, abs=1.0)
    assert plan.segments[0].camera360.follow == "picked"


def test_b5_a_360_zoom_punch_becomes_a_fov_punch() -> None:
    plan = plan_of([pano()])

    assert not any(e.type == "zoomPunch" for s in plan.segments for e in s.effects)
    fovs = {round(key.fov) for s in plan.segments if s.camera360 for key in s.camera360.keyframes}
    assert {140, 70} <= fovs


def test_b5_fov_punch_snaps_wide_to_tight_and_settles_on_the_view() -> None:
    camera = Camera360(
        keyframes=(
            CameraKeyframe(t=0.0, yaw=0, pitch=-5, fov=90),
            CameraKeyframe(t=1.0, yaw=0, pitch=-5, fov=90),
        )
    )

    punched = with_fov_punch(camera, 0.25, 0.25)

    assert camera_at(punched, 0.25).fov == pytest.approx(140.0)
    assert camera_at(punched, 0.35).fov < 90.0
    assert camera_at(punched, 0.5).fov == pytest.approx(90.0)
    assert camera_at(punched, 1.0).fov == pytest.approx(90.0)


def test_b5_transitions_alternate_whips_and_stay_under_half_the_cuts() -> None:
    plan = plan_of([ClipInput("v0", analysis(measure(0.0, 30.0)))])
    kinds = [s.transition_out.type for s in plan.segments]
    moving = [kind for kind in kinds if kind != "cut"]

    assert moving
    assert len(moving) <= (len(kinds) - 1) // 2
    assert kinds[-1] == "cut"
    whips = [kind for kind in moving if kind in WHIPS]
    assert all(a != b for a, b in zip(whips, whips[1:], strict=False))


def test_b5_a_section_change_gets_a_signature_transition() -> None:
    plan = plan_of([ClipInput("v0", analysis(measure(0.0, 30.0)))], length_sec=60)

    assert {s.transition_out.type for s in plan.segments} & {"zoom_through", "spin", "glitch"}


def test_b5_no_effects_means_no_transitions() -> None:
    plan = plan_of([ClipInput("v0", analysis(measure(0.0, 30.0)))], Constraints(fx_intensity=0.0))

    assert all(s.transition_out.type == "cut" for s in plan.segments)
    assert plan_transitions([], VELOCITY) == ()
