"""Subject follow on 360 clips: the picked subject is measured and the camera follows it.

Spec: specs/08-osmo360.md (rule 5, 360-only effects, UI additions),
specs/05-editing-brain.md#b7-reframing-rules-reframepy [T-415]

The tracker here is a fake: it proves the planning, the wrap handling and the fallbacks. The real
SAM 2 run is the `gpu` test in tests/integration/test_subject_follow_gpu.py.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import numpy as np
import pytest

from app.adapters.equirect_view import (
    centered_on,
    view_maps,
    view_point_to_equirect,
)
from app.application.follow_subject import MAX_TRACK_SEC, FollowSubject
from app.domain.brain.planner import ClipInput
from app.domain.brain.reframe import camera_at
from app.domain.models import FollowPoint
from app.domain.plan import EditPlan, Segment
from app.domain.shots import SubjectSample
from app.ports.subject_follow import FollowTrack
from tests.unit.test_ramps_and_framing import SETTINGS, pano, plan_of

POINT = FollowPoint(0.5, 0.5, 0.0)


def x_of(yaw: float) -> float:
    """The equirect share of a yaw, the inverse of the planner's `(x - 0.5) * 360`."""
    return 0.5 + yaw / 360.0


def track(yaws: list[float], step: float = 0.25) -> tuple[SubjectSample, ...]:
    return tuple(SubjectSample(time=i * step, x=x_of(yaw), y=0.5) for i, yaw in enumerate(yaws))


def followed(samples: tuple[SubjectSample, ...]) -> EditPlan:
    clip: ClipInput = dataclasses.replace(pano(), follow_track=samples)
    return plan_of([clip], follow_point=POINT)


def spun(segment: Segment) -> bool:
    """A beat spin: an expo-eased first span that changes yaw only (a punch changes FOV)."""
    assert segment.camera360 is not None
    first, second = segment.camera360.keyframes[:2]
    return first.ease == "easeOutExpo" and first.fov == second.fov


def steady(segment: Segment) -> bool:
    return not spun(segment)


def test_08_rule5_the_camera_follows_the_measured_subject_not_the_detection() -> None:
    clip = dataclasses.replace(
        pano(track(list(np.full(120, -90.0)))),  # detections say the subject is behind-left
        follow_track=track(list(np.full(120, 54.0))),  # SAM 2 says it is at yaw 54
    )

    plan = plan_of([clip], follow_point=POINT)

    segment = next(s for s in plan.segments if s.camera360 and steady(s))
    assert segment.camera360 is not None
    assert segment.camera360.follow == "picked"
    assert camera_at(segment.camera360, 0.0).yaw == pytest.approx(54.0, abs=1.0)


def test_08_rule5_a_subject_crossing_the_seam_moves_the_camera_by_the_real_angle() -> None:
    """Bearing 170 to 190 over 30 s: 20 degrees in total, written as +-180 wrapped values."""
    yaws = [((170.0 + 20.0 * i / 120 + 180.0) % 360.0) - 180.0 for i in range(121)]
    assert max(yaws) > 179 and min(yaws) < -179

    plan = followed(track(yaws))

    checked = 0
    for segment in plan.segments:
        if segment.camera360 and steady(segment):
            keyed = [key.yaw for key in segment.camera360.keyframes]
            assert max(keyed) - min(keyed) < 20.0  # never a 358 degree whip inside a path
            checked += 1
    assert checked > 0


def test_08_rule5_a_jittering_track_over_the_seam_does_not_whip() -> None:
    yaws = [179.0, 179.5, 180.0, -179.5, -179.0] * 24
    plan = followed(track(yaws))

    for segment in plan.segments:
        if segment.camera360 and steady(segment):
            keyed = [key.yaw for key in segment.camera360.keyframes]
            assert max(keyed) - min(keyed) < 10.0


def test_08_beat_spin_is_one_turn_around_the_subject_at_the_seam() -> None:
    plan = followed(track([179.5] * 120))

    spins = [s for s in plan.segments if s.camera360 and spun(s)]

    assert spins
    for segment in spins:
        assert segment.camera360 is not None
        first, second = segment.camera360.keyframes[:2]
        assert second.yaw - first.yaw == pytest.approx(360.0, abs=5.0)
        assert first.yaw == pytest.approx(179.5, abs=5.0)


def test_08_rule5_a_lost_subject_holds_the_last_measured_bearing() -> None:
    plan = followed(track([60.0] * 20))  # measured to 5 s, then lost: 25 s without samples

    later = [s for s in plan.segments if s.src_in >= 6.0 and s.camera360 and steady(s)]

    assert later
    for segment in later:
        assert segment.camera360 is not None
        for key in segment.camera360.keyframes:
            assert key.yaw == pytest.approx(60.0, abs=1.0)


def test_08_rule5_no_measurement_keeps_the_detection_track_and_the_picked_start() -> None:
    plan = followed(())

    segment = plan.segments[0]
    assert segment.camera360 is not None
    assert segment.camera360.follow == "picked"
    assert camera_at(segment.camera360, 0.0).yaw == pytest.approx(0.0, abs=1.0)


class FakeFollower:
    def __init__(self, result: FollowTrack | Exception) -> None:
        self.result = result
        self.asked: list[tuple[float, float, FollowPoint]] = []

    def follow(
        self, video: Path, point: FollowPoint, start: float, end: float, folder: Path
    ) -> FollowTrack:
        self.asked.append((start, end, point))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def a_plan() -> EditPlan:
    return plan_of([pano()], follow_point=POINT)


def measure_with(follower: FakeFollower, point: FollowPoint = POINT) -> tuple[object, ...]:
    samples, notes = FollowSubject(follower).measure(
        a_plan(), "v0", Path("c.mp4"), point, Path("f")
    )
    return samples, notes


def test_08_rule5_the_tracker_is_asked_for_the_window_the_segments_use() -> None:
    follower = FakeFollower(FollowTrack(track([10.0, 12.0])))
    plan = a_plan()
    segments = [s for s in plan.segments if s.type == "video360"]

    FollowSubject(follower).measure(plan, "v0", Path("c.mp4"), POINT, Path("f"))

    start, end, point = follower.asked[0]
    assert start == pytest.approx(min(s.src_in for s in segments))
    assert end == pytest.approx(max(s.src_out for s in segments))
    assert point == POINT


def test_08_rule5_a_lost_subject_is_in_the_plan_notes() -> None:
    samples, notes = measure_with(FakeFollower(FollowTrack(track([10.0, 12.0]), lost=(7.5,))))

    assert len(samples) == 2  # type: ignore[arg-type]
    assert any("lost at 7.5s" in note and "holds" in note for note in notes)  # type: ignore[attr-defined]


def test_08_rule5_a_tracker_failure_falls_back_to_detections_with_a_note() -> None:
    samples, notes = measure_with(FakeFollower(RuntimeError("CUDA out of memory")))

    assert samples == ()
    assert len(notes) == 1  # type: ignore[arg-type]
    assert "tracking failed" in notes[0]  # type: ignore[index]


def test_08_rule5_a_subject_never_found_falls_back_with_a_note() -> None:
    samples, notes = measure_with(FakeFollower(FollowTrack()))

    assert samples == ()
    assert "no subject found" in notes[0]  # type: ignore[index]


def test_08_rule5_a_clip_with_no_360_segment_is_not_tracked() -> None:
    follower = FakeFollower(FollowTrack(track([1.0])))

    samples, notes = FollowSubject(follower).measure(
        a_plan(), "other", Path("c.mp4"), POINT, Path("f")
    )

    assert (samples, notes) == ((), ())
    assert follower.asked == []


def test_08_rule5_a_very_long_window_is_capped_and_says_so() -> None:
    follower = FakeFollower(FollowTrack(track([1.0])))
    plan = a_plan()
    far = dataclasses.replace(POINT, time_sec=MAX_TRACK_SEC * 3)

    _, notes = FollowSubject(follower).measure(plan, "v0", Path("c.mp4"), far, Path("f"))

    start, end, _ = follower.asked[0]
    assert end - start == pytest.approx(MAX_TRACK_SEC)
    assert any("only" in note and "tracked" in note for note in notes)


def test_08_rule5_settings_without_a_follow_point_are_not_a_follow() -> None:
    assert SETTINGS.follow_point is None


# The view SAM 2 sees: geometry on the CPU, no model involved.


def test_08_rule5_a_subject_cut_by_the_frame_edge_is_whole_in_the_centered_view() -> None:
    width, height = 512, 256
    frame = np.zeros((height, width), dtype=np.uint8)
    frame[100:150, :12] = 255  # a subject cut in two by the seam: left edge...
    frame[100:150, width - 12 :] = 255  # ...and right edge
    yaw, pitch = centered_on(0.0, 0.5 + 25 / height)  # centered on the seam

    map_x, map_y = view_maps(width, height, 128, 100.0, yaw, pitch)
    view = np.zeros((128, 128), dtype=np.uint8)
    inside = (map_x >= 0) & (map_x <= width - 1)
    cols = np.rint(map_x).astype(int) % width
    rows = np.clip(np.rint(map_y).astype(int), 0, height - 1)
    view[inside] = frame[rows, cols][inside]

    ys, xs = np.nonzero(view)
    assert xs.size > 0
    assert abs(xs.mean() - 64) < 6  # one blob in the middle, not two at the edges
    assert xs.min() < 60 < xs.max()


def test_08_rule5_a_view_pixel_maps_back_to_the_equirect_position_across_the_wrap() -> None:
    yaw, pitch = centered_on(0.99, 0.4)  # near the seam, a bit above the horizon

    x, y = view_point_to_equirect(64, 64, 128, 100.0, yaw, pitch)

    assert x == pytest.approx(0.99, abs=1e-6)
    assert y == pytest.approx(0.4, abs=1e-6)
    right, _ = view_point_to_equirect(100, 64, 128, 100.0, yaw, pitch)
    assert right < 0.1 or right > 0.99  # past the edge it wraps to the other side
    assert (right - 0.99 + 0.5) % 1.0 - 0.5 > 0  # and it is to the right of the subject


# The wiring in RenderEdit: plan once, measure, plan again.


def wired(follower: FakeFollower, tmp_path: Path) -> tuple[EditPlan, EditPlan]:
    from typing import Any

    from app.application.job_runner import CancellationToken
    from app.application.render_job import RenderEdit
    from app.domain.constraints import Direction
    from app.domain.models import AssetInput, AssetType, RenderJob
    from tests.unit.test_planner import music_map

    nothing: Any = None
    edit = RenderEdit(
        tmp_path,
        nothing,
        nothing,
        nothing,
        nothing,
        nothing,
        nothing,
        follow=FollowSubject(follower),
    )
    clip = pano()
    asset = AssetInput(
        "v0", AssetType.VIDEO, "uploads/c.mp4", None, None, None, 30.0, 7680, 3840, 30.0
    )
    job = RenderJob("j", "r", "p", dataclasses.replace(SETTINGS, follow_point=POINT), (asset,))
    first = plan_of([clip], follow_point=POINT)
    second = edit._followed(
        job, first, ("m1", music_map()), [asset], [clip], Direction(), [], CancellationToken()
    )
    return first, second


def test_08_rule5_the_second_planning_pass_frames_on_the_measurement(tmp_path: Path) -> None:
    follower = FakeFollower(FollowTrack(track([54.0] * 120), lost=(20.0,)))

    first, second = wired(follower, tmp_path)

    assert [s.src_in for s in second.segments] == [s.src_in for s in first.segments]
    assert [s.at for s in second.segments] == [s.at for s in first.segments]
    steady_segment = next(s for s in second.segments if s.camera360 and steady(s))
    assert steady_segment.camera360 is not None
    assert camera_at(steady_segment.camera360, 0.0).yaw == pytest.approx(54.0, abs=1.0)
    assert any("lost at 20.0s" in note for note in second.log)


def test_08_rule5_a_failed_tracker_keeps_the_first_plan_and_logs_why(tmp_path: Path) -> None:
    first, second = wired(FakeFollower(RuntimeError("boom")), tmp_path)

    assert second.segments == first.segments
    assert second.log[-1].startswith("Subject follow: tracking failed")
