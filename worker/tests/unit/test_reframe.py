"""B7 reframing rules. Spec: specs/05-editing-brain.md#b7-reframing-rules-reframepy [T-302]"""

from __future__ import annotations

import math
import random

import pytest

from app.domain.brain.ramps import EASE_LINEAR, EASE_OUT_EXPO
from app.domain.brain.reframe import (
    DEAD_ZONE_SHARE,
    FOLLOW_PITCH,
    KEN_BURNS_END_SCALE,
    MAX_PAN_SHARE_PER_SEC,
    MIN_PITCH,
    CropWindow,
    FrameSize,
    SubjectBearing,
    SubjectPoint,
    base_fov,
    camera_at,
    crop_path,
    crop_size,
    follow_camera,
    ken_burns_motion,
    ken_burns_window,
    limit_pitch,
    one_euro_filter,
    ratio_value,
    unwrap_yaw,
    view_pixel_width,
    with_beat_spin,
    with_rabbit_hole,
    with_tiny_planet,
)
from app.domain.plan import Camera360, CameraKeyframe

UHD = FrameSize(3840, 2160)
TALL = 9 / 16
FPS = 30


def center_x(window: CropWindow) -> float:
    return window.x + window.width / 2


def center_y(window: CropWindow) -> float:
    return window.y + window.height / 2


def walk(speed_share: float, seconds: float, start: float = 1920.0) -> list[SubjectPoint]:
    """A subject crossing the frame at a share of the width per second."""
    return [
        SubjectPoint(i / FPS, start + speed_share * UHD.width * i / FPS, 1080.0)
        for i in range(int(seconds * FPS) + 1)
    ]


def path(*keys: tuple[float, float]) -> Camera360:
    return Camera360(
        keyframes=tuple(CameraKeyframe(t=t, yaw=yaw, pitch=-5.0, fov=100.0) for t, yaw in keys)
    )


# Flat clips


@pytest.mark.parametrize(
    ("ratio", "size"),
    [
        (9 / 16, (1215.0, 2160.0)),
        (16 / 9, (3840.0, 2160.0)),
        (1.0, (2160.0, 2160.0)),
        (21 / 9, (3840.0, 3840 * 9 / 21)),
    ],
)
def test_b7_crop_window_is_as_large_as_possible_at_the_output_ratio(
    ratio: float, size: tuple[float, float]
) -> None:
    assert crop_size(UHD, ratio) == pytest.approx(size)


def test_b7_no_subject_gives_a_centered_static_crop() -> None:
    windows = crop_path([], UHD, TALL)

    assert len(windows) == 1
    assert center_x(windows[0]) == pytest.approx(1920.0)
    assert center_y(windows[0]) == pytest.approx(1080.0)


def test_b7_one_euro_filter_calms_a_jittering_still_subject() -> None:
    rng = random.Random(1)
    times = [i / FPS for i in range(90)]
    noisy = [0.5 + rng.uniform(-0.01, 0.01) for _ in times]

    smooth = one_euro_filter(times, noisy)

    def spread(values: list[float]) -> float:
        return max(values[30:]) - min(values[30:])

    assert spread(smooth) < spread(noisy) / 2


def test_b7_one_euro_filter_lags_less_on_fast_motion_than_a_fixed_low_pass() -> None:
    times = [i / FPS for i in range(60)]
    fast = [2.0 * time for time in times]

    adaptive = one_euro_filter(times, fast)
    fixed = one_euro_filter(times, fast, beta=0.0)

    assert abs(fast[-1] - adaptive[-1]) < abs(fast[-1] - fixed[-1]) / 2


def test_b7_one_euro_filter_ignores_a_repeated_timestamp() -> None:
    assert one_euro_filter([0.0, 0.0, 0.1], [1.0, 9.0, 1.0])[1] == 1.0


def test_b7_window_starts_on_the_subject_because_pan_is_unlimited_across_cuts() -> None:
    track = [SubjectPoint(i / FPS, 1000.0, 1080.0) for i in range(5)]

    windows = crop_path(track, UHD, TALL)

    assert center_x(windows[0]) == pytest.approx(1000.0)


def test_b7_dead_zone_holds_the_window_while_the_subject_drifts_inside_it() -> None:
    width, _ = crop_size(UHD, TALL)
    inside = 0.9 * DEAD_ZONE_SHARE * width
    track = [
        SubjectPoint(i / FPS, 1920.0 + inside * math.sin(i / 3), 1080.0) for i in range(FPS * 2)
    ]

    windows = crop_path(track, UHD, TALL)

    assert {round(window.x, 6) for window in windows} == {round(windows[0].x, 6)}


def test_b7_window_moves_once_the_subject_leaves_the_dead_zone_and_keeps_it_at_the_edge() -> None:
    width, _ = crop_size(UHD, TALL)
    zone = DEAD_ZONE_SHARE * width
    track = [SubjectPoint(0.0, 1920.0, 1080.0)]
    track += [SubjectPoint(i / FPS, 1920.0 + zone * 1.5, 1080.0) for i in range(1, FPS * 6)]

    windows = crop_path(track, UHD, TALL, subject_count=2)

    assert center_x(windows[-1]) == pytest.approx(1920.0 + zone * 0.5, abs=2.0)


def test_b7_pan_never_exceeds_15_percent_of_frame_width_per_second() -> None:
    windows = crop_path(walk(1.0, 0.9, start=300.0), UHD, TALL)

    speeds = [
        abs(center_x(after) - center_x(before)) / (after.time - before.time)
        for before, after in zip(windows, windows[1:], strict=False)
    ]
    assert max(speeds) <= MAX_PAN_SHARE_PER_SEC * UHD.width + 1e-6
    assert max(speeds) == pytest.approx(MAX_PAN_SHARE_PER_SEC * UHD.width)


def test_b7_vertical_pan_has_the_same_limit() -> None:
    wide = crop_size(UHD, 21 / 9)
    assert wide[1] < UHD.height
    track = [SubjectPoint(i / FPS, 1920.0, 400.0 + 2000.0 * i / FPS) for i in range(FPS)]

    windows = crop_path(track, UHD, 21 / 9)

    speeds = [
        abs(center_y(after) - center_y(before)) * FPS
        for before, after in zip(windows, windows[1:], strict=False)
    ]
    assert max(speeds) <= MAX_PAN_SHARE_PER_SEC * UHD.width + 1e-6


def test_b7_window_stays_inside_the_frame_at_the_edges() -> None:
    track = [SubjectPoint(i / FPS, 3830.0, 5.0) for i in range(30)]

    for window in crop_path(track, UHD, 1.0):
        assert window.x >= 0
        assert window.y >= 0
        assert window.x + window.width <= UHD.width + 1e-6
        assert window.y + window.height <= UHD.height + 1e-6


def test_b7_single_subject_moving_right_sits_on_the_left_third_with_room_ahead() -> None:
    track = walk(0.05, 1.0)
    first = crop_path(track, UHD, TALL)[0]

    assert (track[0].x - first.x) / first.width == pytest.approx(1 / 3)


def test_b7_single_subject_moving_left_sits_on_the_right_third_with_room_ahead() -> None:
    track = walk(-0.05, 1.0)
    first = crop_path(track, UHD, TALL)[0]

    assert (track[0].x - first.x) / first.width == pytest.approx(2 / 3)


def test_b7_a_still_subject_stays_centered() -> None:
    track = [SubjectPoint(i / FPS, 1500.0, 1080.0) for i in range(30)]

    assert center_x(crop_path(track, UHD, TALL)[0]) == pytest.approx(1500.0)


def test_b7_thirds_is_only_for_a_single_subject() -> None:
    track = walk(0.05, 1.0)

    assert center_x(crop_path(track, UHD, TALL, subject_count=2)[0]) == pytest.approx(track[0].x)


def test_b11_a_slow_subject_stays_in_the_window_for_at_least_90_percent() -> None:
    track = walk(0.1, 2.0, start=1500.0)

    windows = crop_path(track, UHD, TALL)

    inside = sum(
        window.x <= point.x <= window.x + window.width
        for window, point in zip(windows, track, strict=True)
    )
    assert inside / len(track) >= 0.9


# 360 clips


@pytest.mark.parametrize(
    ("ratio", "fov"),
    [("16:9", 100), ("1:1", 100), ("4:3", 100), ("21:9", 100), ("9:16", 90), ("4:5", 90)],
)
def test_b7_fov_is_100_or_90_for_tall_ratios(ratio: str, fov: float) -> None:
    assert base_fov(ratio) == fov


def test_08_rule_8_view_width_of_8k_at_fov_100_is_about_2130_px() -> None:
    assert view_pixel_width(7680, 100.0) == pytest.approx(2133.3, abs=0.1)


def test_b7_follow_keeps_pitch_at_minus_5_and_the_ratio_fov() -> None:
    camera = follow_camera(
        [SubjectBearing(0.0, 20.0), SubjectBearing(1.0, 20.0)], (0.0, 1.0), "9:16", "person_1"
    )

    assert camera.follow == "person_1"
    assert [key.pitch for key in camera.keyframes] == [FOLLOW_PITCH, FOLLOW_PITCH]
    assert FOLLOW_PITCH == -5.0
    assert [key.fov for key in camera.keyframes] == [90.0, 90.0]
    assert [key.yaw for key in camera.keyframes] == pytest.approx([20.0, 20.0])


def test_08_rule_6_follow_keyframes_sit_on_the_beats() -> None:
    track = [SubjectBearing(i / FPS, float(i)) for i in range(FPS)]
    beats = (0.0, 0.47, 0.94)

    camera = follow_camera(track, beats, "16:9")

    assert tuple(key.t for key in camera.keyframes) == beats


def test_b7_yaw_follows_the_subject_through_a_turn() -> None:
    track = [SubjectBearing(i / FPS, 30.0 * i / FPS) for i in range(FPS * 4)]

    camera = follow_camera(track, (0.0, 1.0, 2.0, 3.0), "16:9")

    yaws = [key.yaw for key in camera.keyframes]
    assert yaws == sorted(yaws)
    assert yaws[-1] == pytest.approx(90.0, abs=10.0)


def test_b7_a_subject_crossing_behind_the_camera_does_not_whip_the_long_way_round() -> None:
    assert unwrap_yaw([170.0, 179.0, -179.0, -170.0]) == pytest.approx([170.0, 179.0, 181.0, 190.0])
    track = [SubjectBearing(i / 10, ((170 + i * 2 + 180) % 360) - 180) for i in range(11)]

    camera = follow_camera(track, (0.0, 1.0), "16:9")

    assert camera.keyframes[1].yaw - camera.keyframes[0].yaw == pytest.approx(20.0, abs=8.0)


def test_b7_yaw_is_smoothed_in_turns_so_jitter_in_degrees_is_calmed_too() -> None:
    rng = random.Random(1)
    still = [SubjectBearing(i / FPS, 40.0 + rng.uniform(-4.0, 4.0)) for i in range(90)]
    beats = tuple(i / FPS for i in range(30, 90))

    camera = follow_camera(still, beats, "16:9")

    yaws = [key.yaw for key in camera.keyframes]
    raw = [bearing.yaw for bearing in still[30:]]
    assert max(yaws) - min(yaws) < (max(raw) - min(raw)) / 2


def test_b7_no_subject_holds_the_camera_forward() -> None:
    camera = follow_camera([], (0.0, 1.0), "16:9")

    assert [key.yaw for key in camera.keyframes] == [0.0, 0.0]


def test_b7_drop_spin_turns_exactly_360_degrees_over_one_beat() -> None:
    camera = with_beat_spin(path((0.0, 30.0), (2.0, 30.0)), 0.0, 0.5)

    assert camera_at(camera, 0.0).yaw == pytest.approx(30.0)
    assert camera_at(camera, 0.5).yaw == pytest.approx(390.0)


def test_b7_drop_spin_does_not_unwind_after_the_beat() -> None:
    camera = with_beat_spin(path((0.0, 0.0), (1.0, 10.0), (2.0, 20.0)), 0.0, 0.5)

    assert camera_at(camera, 1.0).yaw == pytest.approx(370.0)
    assert camera_at(camera, 2.0).yaw == pytest.approx(380.0)


def test_b7_drop_spin_keeps_the_keyframes_before_it() -> None:
    camera = with_beat_spin(path((0.0, 0.0), (0.2, 40.0), (2.0, 40.0)), 1.0, 0.5)

    assert camera.keyframes[1].t == 0.2
    assert camera_at(camera, 1.0).yaw == pytest.approx(40.0)
    assert camera_at(camera, 1.5).yaw == pytest.approx(400.0)


def test_b7_drop_spin_fits_a_slot_shorter_than_a_beat() -> None:
    camera = with_beat_spin(path((0.0, 0.0), (0.25, 0.0)), 0.0, 0.5)

    assert camera.keyframes[-1].t == 0.25
    assert camera.keyframes[-1].yaw == pytest.approx(360.0)


def test_b7_tiny_planet_is_pitch_minus_90_fov_160_stereographic() -> None:
    camera = with_tiny_planet(path((0.0, 0.0), (0.94, 0.0)), 0.47, 0.94)

    last = camera.keyframes[-1]
    assert (last.t, last.pitch, last.fov, last.projection) == (0.94, -90.0, 160.0, "tinyplanet")
    assert camera_at(camera, 0.94).projection == "tinyplanet"


def test_08_tiny_planet_curls_in_over_its_span_from_the_pose_it_found() -> None:
    camera = with_tiny_planet(path((0.0, 12.0), (0.94, 12.0)), 0.47, 0.94)

    assert camera_at(camera, 0.4).projection == "rectilinear"
    middle = camera_at(camera, 0.705)
    assert middle.projection == "tinyplanet"
    assert middle.pitch == pytest.approx((-5.0 - 90.0) / 2)
    assert middle.yaw == pytest.approx(12.0)


def test_08_rabbit_hole_is_the_tiny_planet_looking_straight_up() -> None:
    camera = with_rabbit_hole(path((0.0, 0.0), (1.0, 0.0)), 0.5, 1.0)

    last = camera.keyframes[-1]
    assert (last.pitch, last.fov, last.projection) == (90.0, 160.0, "rabbithole")


def test_08_a_planet_unrolls_back_to_flat_in_the_same_projection() -> None:
    camera = with_tiny_planet(path((0.0, 0.0), (1.0, 0.0), (2.0, 0.0)), 0.0, 1.0)

    assert camera_at(camera, 1.5).projection == "tinyplanet"
    assert camera_at(camera, 2.0).pitch == pytest.approx(-5.0)


def test_b7_pitch_stays_above_minus_60_outside_a_tiny_planet() -> None:
    camera = Camera360(
        keyframes=(
            CameraKeyframe(t=0.0, yaw=0.0, pitch=-75.0, fov=100.0),
            CameraKeyframe(t=1.0, yaw=0.0, pitch=-30.0, fov=100.0),
        )
    )

    limited = limit_pitch(camera)

    assert [key.pitch for key in limited.keyframes] == [MIN_PITCH, -30.0]
    assert MIN_PITCH == -60.0


def test_b7_pitch_limit_leaves_the_tiny_planet_alone() -> None:
    camera = with_tiny_planet(path((0.0, 0.0), (1.0, 0.0)), 0.5, 1.0)

    assert limit_pitch(camera).keyframes[-1].pitch == -90.0


def test_b7_every_rule_together_keeps_pitch_legal_at_every_rectilinear_frame() -> None:
    track = [SubjectBearing(i / FPS, 5.0 * i) for i in range(FPS)]
    camera = follow_camera(track, (0.0, 0.5, 1.0), "9:16")
    camera = limit_pitch(with_tiny_planet(with_beat_spin(camera, 0.0, 0.5), 0.5, 1.0))

    poses = [camera_at(camera, i / FPS) for i in range(FPS + 1)]

    assert all(pose.pitch >= MIN_PITCH for pose in poses if pose.projection == "rectilinear")


def test_camera_at_interpolates_between_keyframes_along_the_ease() -> None:
    camera = Camera360(
        keyframes=(
            CameraKeyframe(t=0.0, yaw=0.0, pitch=0.0, fov=100.0, ease=EASE_OUT_EXPO),
            CameraKeyframe(t=1.0, yaw=100.0, pitch=0.0, fov=100.0, ease=EASE_LINEAR),
            CameraKeyframe(t=2.0, yaw=200.0, pitch=0.0, fov=100.0),
        )
    )

    assert camera_at(camera, 0.5).yaw == pytest.approx(96.875)
    assert camera_at(camera, 1.5).yaw == pytest.approx(150.0)


def test_camera_at_holds_the_end_poses_outside_the_path() -> None:
    camera = path((1.0, 10.0), (2.0, 20.0))

    assert camera_at(camera, 0.0).yaw == 10.0
    assert camera_at(camera, 5.0).yaw == 20.0


def test_camera_at_a_single_keyframe_is_a_held_pose() -> None:
    assert camera_at(path((0.0, 42.0)), 3.0).yaw == 42.0


def test_ratio_value_reads_the_output_ratio() -> None:
    assert ratio_value("9:16") == pytest.approx(TALL)


# Photos


def test_b7_ken_burns_runs_from_1_0_to_1_12() -> None:
    motion = ken_burns_motion((0.3, 0.7))

    assert motion.type == "kenburns"
    assert ken_burns_window(motion, 0.0).scale == 1.0
    assert ken_burns_window(motion, 1.0).scale == pytest.approx(KEN_BURNS_END_SCALE)
    assert KEN_BURNS_END_SCALE == 1.12


def test_b7_ken_burns_pushes_toward_the_subject() -> None:
    motion = ken_burns_motion((0.8, 0.2))

    start = ken_burns_window(motion, 0.0)
    end = ken_burns_window(motion, 1.0)

    assert (start.center_x, start.center_y) == pytest.approx((0.5, 0.5))
    assert end.center_x > 0.5
    assert end.center_y < 0.5
    screen_x = (motion.focus_x - end.center_x) * end.scale + 0.5
    assert screen_x == pytest.approx(motion.focus_x)


def test_b7_ken_burns_without_a_subject_pushes_to_the_center() -> None:
    window = ken_burns_window(ken_burns_motion(None), 1.0)

    assert (window.center_x, window.center_y) == pytest.approx((0.5, 0.5))


@pytest.mark.parametrize("focus", [0.0, 0.5, 1.0])
def test_b7_ken_burns_never_shows_past_the_photo_edge(focus: float) -> None:
    window = ken_burns_window(ken_burns_motion((focus, focus)), 1.0)
    half = 0.5 / window.scale

    assert window.center_x - half >= -1e-9
    assert window.center_x + half <= 1 + 1e-9
