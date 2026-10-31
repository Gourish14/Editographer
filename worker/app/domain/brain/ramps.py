"""Speed ramp curve. Spec: specs/05-editing-brain.md#b6-speed-ramp-curve-rampspy

Also holds the plan's easing names, since the B6 easing is one of them. Curves are
(share of the slot, speed) points; speed moves between two points along the B6 easing.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence

from app.domain.brain.pacing import Slot
from app.domain.errors import ErrorCode, RenderError
from app.domain.music import SectionKind
from app.domain.plan import Speed

FAST_SPEED = 2.5
SLOW_SPEED = 0.25
NORMAL_SPEED = 1.0
EASE_DOWN_START = 0.4
SLOW_HOLD_START = 0.5
SLOW_HOLD_END = 0.8
RAMP_CURVE: tuple[tuple[float, float], ...] = (
    (0.0, FAST_SPEED),
    (EASE_DOWN_START, FAST_SPEED),
    (SLOW_HOLD_START, SLOW_SPEED),
    (SLOW_HOLD_END, SLOW_SPEED),
    (1.0, NORMAL_SPEED),
)

BEZIER_X1 = 0.7
BEZIER_Y1 = 0.0
BEZIER_X2 = 0.3
BEZIER_Y2 = 1.0
BEZIER_SOLVE_STEPS = 40
EXPO_SHARPNESS = 10.0

EASE_LINEAR = "linear"
EASE_IN_OUT_CUBIC = "easeInOutCubic"
EASE_OUT_EXPO = "easeOutExpo"
EASE_IN_EXPO = "easeInExpo"
EASE_BEZIER = "bezier(0.7,0,0.3,1)"

NATIVE_SLOWMO_MIN_FPS = 100.0
INTERPOLATE_NATIVE = "native"
INTERPOLATE_RIFE = "rife"


def cubic_bezier(share: float) -> float:
    """cubic-bezier(0.7, 0, 0.3, 1). x grows with the parameter, so bisection always converges."""
    low, high = 0.0, 1.0
    for _ in range(BEZIER_SOLVE_STEPS):
        middle = (low + high) / 2
        if _bezier_axis(middle, BEZIER_X1, BEZIER_X2) < share:
            low = middle
        else:
            high = middle
    return _bezier_axis((low + high) / 2, BEZIER_Y1, BEZIER_Y2)


def _bezier_axis(parameter: float, first: float, second: float) -> float:
    rest = 1 - parameter
    return 3 * rest * rest * parameter * first + 3 * rest * parameter**2 * second + parameter**3


def _ease_in_out_cubic(share: float) -> float:
    if share < 0.5:
        return 4 * share**3
    return 1 - (2 - 2 * share) ** 3 / 2


def _ease_out_expo(share: float) -> float:
    return 1.0 if share >= 1 else 1 - math.pow(2, -EXPO_SHARPNESS * share)


def _ease_in_expo(share: float) -> float:
    return 0.0 if share <= 0 else math.pow(2, EXPO_SHARPNESS * (share - 1))


EASINGS: dict[str, Callable[[float], float]] = {
    EASE_LINEAR: lambda share: share,
    EASE_IN_OUT_CUBIC: _ease_in_out_cubic,
    EASE_OUT_EXPO: _ease_out_expo,
    EASE_IN_EXPO: _ease_in_expo,
    EASE_BEZIER: cubic_bezier,
}


def eased(name: str, share: float) -> float:
    """The plan's `ease` enumeration, specs/06-edit-plan-schema.md#enumerations."""
    easing = EASINGS.get(name)
    if easing is None:
        raise RenderError(f"Unknown ease {name}", ErrorCode.PLAN_INVALID)
    return easing(share)


def speed_at(curve: Sequence[tuple[float, float]], share: float) -> float:
    """Speed at a share of the slot."""
    for (start, before), (end, after) in zip(curve, curve[1:], strict=False):
        if share <= end:
            progress = max(0.0, (share - start) / (end - start))
            return before + (after - before) * cubic_bezier(progress)
    return curve[-1][1]


def curve_source_length(curve: Sequence[tuple[float, float]], duration: float) -> float:
    """Source seconds a curve consumes: the integral of speed over the slot.

    The easing is point-symmetric around its middle, so each eased span averages its two ends.
    """
    spans = zip(curve, curve[1:], strict=False)
    return duration * sum((end - start) * (a + b) / 2 for (start, a), (end, b) in spans)


def source_length(duration: float) -> float:
    """Source seconds a ramped slot needs. B4's length fit and B11's coverage check use this."""
    return curve_source_length(RAMP_CURVE, duration)


def slow_hold_start(at: float, duration: float) -> float:
    """Timeline time the slow hold begins. B6 wants this on a beat, which a two-beat slot gives."""
    return at + SLOW_HOLD_START * duration


INTEGRATION_STEPS = 64
RAMP_MIN_SEC = 0.5
RETIME_TABLE_POINTS = 48


def _integral(curve: Sequence[tuple[float, float]], share: float) -> float:
    """Slot shares of source passed between the slot start and `share` (trapezoids, 64 per span)."""
    total = 0.0
    for (start, _), (end, _) in zip(curve, curve[1:], strict=False):
        if share <= start:
            break
        stop = min(share, end)
        step = (stop - start) / INTEGRATION_STEPS
        previous = speed_at(curve, start)
        for index in range(1, INTEGRATION_STEPS + 1):
            current = speed_at(curve, start + step * index)
            total += step * (previous + current) / 2
            previous = current
    return total


def source_time_at(curve: Sequence[tuple[float, float]], duration: float, time: float) -> float:
    """Source seconds past the window start at `time` seconds into the slot."""
    return duration * _integral(curve, min(1.0, max(0.0, time / duration)))


def timeline_time_at(
    curve: Sequence[tuple[float, float]], duration: float, source_offset: float
) -> float:
    """The inverse of source_time_at. Past the curve's end the speed is the last point's."""
    total = curve_source_length(curve, duration)
    if source_offset >= total:
        return duration + (source_offset - total) / curve[-1][1]
    low, high = 0.0, duration
    for _ in range(BEZIER_SOLVE_STEPS):
        middle = (low + high) / 2
        if source_time_at(curve, duration, middle) < source_offset:
            low = middle
        else:
            high = middle
    return (low + high) / 2


def retime_expression(curve: Sequence[tuple[float, float]], duration: float) -> str:
    """A setpts expression that moves each source frame to its place on the slot's timeline.

    Applying it and then `fps` picks the frame the curve wants for every output frame, so native
    high frame rate footage plays its own frames. Piecewise linear, from points along the curve.
    """
    shares = [index / RETIME_TABLE_POINTS for index in range(RETIME_TABLE_POINTS + 1)]
    points = [(duration * _integral(curve, share), duration * share) for share in shares]
    expression = f"{duration:.6f}+(SRC-{points[-1][0]:.6f})/{curve[-1][1]:.6f}"
    for (source_a, time_a), (source_b, time_b) in reversed(
        list(zip(points, points[1:], strict=False))
    ):
        slope = (time_b - time_a) / (source_b - source_a)
        piece = f"{time_a:.6f}+(SRC-{source_a:.6f})*{slope:.6f}"
        expression = f"if(lt(SRC,{source_b:.6f}),{piece},{expression})"
    return f"({expression.replace('SRC', 'PTS*TB')})/TB"


def ramp_slot_starts(
    slots: Sequence[Slot],
    slowmo: Sequence[SectionKind],
    first_drops: bool,
    grid: Sequence[float],
    frame_sec: float,
) -> frozenset[float]:
    """Slots that get the B6 ramp: slow-mo sections and, when asked, the first slot of a drop.

    The slow hold starts half way through the slot, so that point must be on the beat grid.
    """
    chosen: set[float] = set()
    previous: SectionKind | None = None
    for slot in slots:
        wanted = slot.section in slowmo or (
            first_drops and slot.section is SectionKind.DROP and previous is not SectionKind.DROP
        )
        previous = slot.section
        hold = slow_hold_start(slot.start, slot.duration)
        on_grid = any(abs(hold - time) <= frame_sec for time in grid)
        if wanted and slot.duration >= RAMP_MIN_SEC and on_grid:
            chosen.add(slot.start)
    return frozenset(chosen)


def ramp_speed(native_fps: float | None) -> Speed:
    """The plan's `speed` for a ramped slot: native slow-mo on 100/120 fps footage, else RIFE."""
    is_native = native_fps is not None and native_fps >= NATIVE_SLOWMO_MIN_FPS
    return Speed(
        curve=RAMP_CURVE, interpolate=INTERPOLATE_NATIVE if is_native else INTERPOLATE_RIFE
    )
