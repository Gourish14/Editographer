"""B6 speed ramp rules. Spec: specs/05-editing-brain.md#b6-speed-ramp-curve-rampspy [T-302]"""

from __future__ import annotations

import pytest

from app.domain.brain.ramps import (
    EASE_BEZIER,
    EASE_IN_EXPO,
    EASE_IN_OUT_CUBIC,
    EASE_LINEAR,
    EASE_OUT_EXPO,
    FAST_SPEED,
    RAMP_CURVE,
    SLOW_SPEED,
    cubic_bezier,
    curve_source_length,
    eased,
    ramp_speed,
    slow_hold_start,
    source_length,
    speed_at,
)
from app.domain.errors import ErrorCode, RenderError
from app.domain.plan import Speed

STEPS = 20_000


def midpoint_integral(duration: float) -> float:
    """An independent check of the integral: sums the speed function itself."""
    return sum(speed_at(RAMP_CURVE, (i + 0.5) / STEPS) for i in range(STEPS)) * duration / STEPS


def test_b6_curve_matches_the_spec_table() -> None:
    assert RAMP_CURVE == ((0.0, 2.5), (0.4, 2.5), (0.5, 0.25), (0.8, 0.25), (1.0, 1.0))


@pytest.mark.parametrize(
    ("share", "speed"),
    [(0.0, 2.5), (0.2, 2.5), (0.4, 2.5), (0.5, 0.25), (0.65, 0.25), (0.8, 0.25), (1.0, 1.0)],
)
def test_b6_speed_at_each_phase(share: float, speed: float) -> None:
    assert speed_at(RAMP_CURVE, share) == pytest.approx(speed)


def test_b6_ease_down_stays_between_fast_and_slow_and_never_rises() -> None:
    speeds = [speed_at(RAMP_CURVE, 0.4 + 0.1 * i / 50) for i in range(51)]

    assert all(after <= before for before, after in zip(speeds, speeds[1:], strict=False))
    assert min(speeds) >= SLOW_SPEED - 1e-9
    assert max(speeds) <= FAST_SPEED + 1e-9


def test_b6_ease_up_ends_at_normal_speed_and_never_falls() -> None:
    speeds = [speed_at(RAMP_CURVE, 0.8 + 0.2 * i / 50) for i in range(51)]

    assert all(after >= before for before, after in zip(speeds, speeds[1:], strict=False))
    assert speeds[-1] == pytest.approx(1.0)


def test_b6_easing_is_the_cubic_bezier_0_7_0_0_3_1() -> None:
    assert cubic_bezier(0.0) == pytest.approx(0.0)
    assert cubic_bezier(1.0) == pytest.approx(1.0)
    assert cubic_bezier(0.5) == pytest.approx(0.5)
    # Parameter 0.25 gives x = 0.353125 and y = 0.15625 on these control points.
    assert cubic_bezier(0.353125) == pytest.approx(0.15625, abs=1e-6)
    # Slow start and slow end are what this curve is for.
    assert cubic_bezier(0.1) < 0.02
    assert cubic_bezier(0.9) > 0.98


def test_b6_easing_is_point_symmetric_so_spans_average_their_ends() -> None:
    for i in range(1, 50):
        share = i / 100
        assert cubic_bezier(share) + cubic_bezier(1 - share) == pytest.approx(1.0, abs=1e-6)


def test_b6_source_length_of_the_ramp_is_the_closed_form_of_the_table() -> None:
    # 0.4 * 2.5 + 0.1 * 1.375 + 0.3 * 0.25 + 0.2 * 0.625 = 1.3375
    assert source_length(1.0) == pytest.approx(1.3375)
    assert source_length(0.94) == pytest.approx(0.94 * 1.3375)


@pytest.mark.parametrize("duration", [0.25, 0.94, 2.0])
def test_b6_source_length_is_the_integral_of_speed(duration: float) -> None:
    assert source_length(duration) == pytest.approx(midpoint_integral(duration), rel=1e-5)


def test_b6_source_length_of_a_constant_curve_is_speed_times_duration() -> None:
    assert curve_source_length(((0.0, 1.0), (1.0, 1.0)), 2.0) == pytest.approx(2.0)
    assert curve_source_length(((0.0, 0.5), (1.0, 0.5)), 2.0) == pytest.approx(1.0)


def test_b6_slow_hold_of_a_two_beat_slot_starts_on_the_middle_beat() -> None:
    beat = 0.5
    at = 12.0

    assert slow_hold_start(at, 2 * beat) == pytest.approx(at + beat)


@pytest.mark.parametrize("fps", [100.0, 120.0])
def test_b6_slow_frames_come_from_native_high_frame_rate_footage(fps: float) -> None:
    assert ramp_speed(fps) == Speed(curve=RAMP_CURVE, interpolate="native")


@pytest.mark.parametrize("fps", [24.0, 60.0, None])
def test_b6_slow_frames_fall_back_to_rife_on_normal_footage(fps: float | None) -> None:
    assert ramp_speed(fps) == Speed(curve=RAMP_CURVE, interpolate="rife")


@pytest.mark.parametrize(
    "name", [EASE_LINEAR, EASE_IN_OUT_CUBIC, EASE_OUT_EXPO, EASE_IN_EXPO, EASE_BEZIER]
)
def test_schema_every_plan_ease_runs_from_zero_to_one(name: str) -> None:
    assert eased(name, 0.0) == pytest.approx(0.0, abs=1e-3)
    assert eased(name, 1.0) == pytest.approx(1.0, abs=1e-3)
    assert 0.0 <= eased(name, 0.5) <= 1.0


def test_schema_an_unknown_ease_is_an_invalid_plan() -> None:
    with pytest.raises(RenderError) as caught:
        eased("bounce", 0.5)

    assert caught.value.code is ErrorCode.PLAN_INVALID
