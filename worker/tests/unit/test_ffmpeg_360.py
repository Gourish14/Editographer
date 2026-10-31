"""360 filter text. Spec: specs/08-osmo360.md (rules 6 to 8) [T-302]"""

from __future__ import annotations

import math
import re

import pytest

from app.adapters.ffmpeg_360 import camera_filter, view_size
from app.domain.brain.reframe import with_tiny_planet
from app.domain.plan import Camera360, CameraKeyframe

OUTPUT = (1920, 1080)
SOURCE_8K = 7680
FPS = 30


def still(yaw: float = 20.0, pitch: float = -5.0, fov: float = 100.0) -> Camera360:
    return Camera360(keyframes=(CameraKeyframe(t=0.0, yaw=yaw, pitch=pitch, fov=fov),))


def pan(start: float, end: float, seconds: float = 1.0) -> Camera360:
    return Camera360(
        keyframes=(
            CameraKeyframe(t=0.0, yaw=start, pitch=-5.0, fov=100.0),
            CameraKeyframe(t=seconds, yaw=end, pitch=-5.0, fov=100.0),
        )
    )


def option(text: str, name: str) -> float:
    match = re.search(rf":{name}=(-?[\d.]+)", text)
    assert match is not None
    return float(match.group(1))


def test_08_rule_7_a_held_pose_is_one_rectilinear_view_with_no_commands() -> None:
    text = camera_filter(still(), 1.0, SOURCE_8K, OUTPUT, FPS)

    assert "sendcmd" not in text
    assert ":flat:" in text
    assert text.count("v360@") == 1
    assert option(text, "yaw") == 20.0
    assert option(text, "pitch") == -5.0


def test_08_rectilinear_vertical_fov_follows_the_output_shape() -> None:
    text = camera_filter(still(), 1.0, SOURCE_8K, OUTPUT, FPS)

    assert option(text, "h_fov") == pytest.approx(100.0)
    expected = 2 * math.degrees(math.atan(math.tan(math.radians(50)) * 9 / 16))
    assert option(text, "v_fov") == pytest.approx(expected, abs=0.1)


def test_08_rule_7_rotation_is_absolute_because_v360_commands_accumulate_otherwise() -> None:
    assert ":reset_rot=1" in camera_filter(pan(0.0, 30.0), 1.0, SOURCE_8K, OUTPUT, FPS)


def test_08_rule_7_each_frame_after_the_first_gets_one_command_when_only_yaw_moves() -> None:
    text = camera_filter(pan(0.0, 30.0), 1.0, SOURCE_8K, OUTPUT, FPS)

    assert text.count(" yaw ") == FPS - 1
    assert " pitch " not in text
    assert " h_fov " not in text


def test_08_rule_7_commands_fire_before_their_frame_so_rounding_never_makes_them_late() -> None:
    text = camera_filter(pan(0.0, 30.0), 1.0, SOURCE_8K, OUTPUT, FPS)

    first = re.search(r"c='([\d.]+) ", text)
    assert first is not None
    assert 0 < float(first.group(1)) < 1 / FPS


def test_08_rule_7_yaw_is_wrapped_into_the_range_v360_accepts() -> None:
    text = camera_filter(pan(0.0, 720.0), 1.0, SOURCE_8K, OUTPUT, FPS)

    values = [float(value) for value in re.findall(r" yaw (-?[\d.]+)", text)]
    assert min(values) >= -180.0
    assert max(values) <= 180.0
    assert min(values) < -100.0


def test_08_rule_7_fov_commands_keep_both_fovs_in_step() -> None:
    camera = Camera360(
        keyframes=(
            CameraKeyframe(t=0.0, yaw=0.0, pitch=-5.0, fov=140.0),
            CameraKeyframe(t=1.0, yaw=0.0, pitch=-5.0, fov=70.0),
        )
    )

    text = camera_filter(camera, 1.0, SOURCE_8K, OUTPUT, FPS)

    assert text.count(" h_fov ") == text.count(" v_fov ") == FPS - 1


def test_08_rule_7_a_tiny_planet_view_is_stereographic() -> None:
    camera = with_tiny_planet(pan(0.0, 0.0), 0.0, 1.0)

    assert ":sg:" in camera_filter(camera, 1.0, SOURCE_8K, OUTPUT, FPS)


def test_08_rule_7_plan_fov_160_becomes_about_282_on_a_square_stereographic_view() -> None:
    camera = Camera360(
        projection="tinyplanet",
        keyframes=(CameraKeyframe(t=0.0, yaw=0.0, pitch=-90.0, fov=160.0),),
    )

    text = camera_filter(camera, 1.0, SOURCE_8K, (1080, 1080), FPS)

    assert option(text, "h_fov") == pytest.approx(282.3, abs=0.1)
    assert option(text, "v_fov") == pytest.approx(282.3, abs=0.1)


def test_08_rule_7_a_projection_change_splits_into_one_graph_with_a_view_per_run() -> None:
    camera = with_tiny_planet(pan(0.0, 0.0), 0.5, 1.0)

    text = camera_filter(camera, 1.0, SOURCE_8K, OUTPUT, FPS)

    assert text.startswith("split=2[in0][in1];")
    assert "trim=start_frame=0:end_frame=15" in text
    assert "trim=start_frame=15:end_frame=30" in text
    assert "concat=n=2:v=1:a=0" in text
    assert "v360@p0=e:flat" in text
    assert "v360@p1=e:sg" in text


def test_08_rule_7_commands_name_their_own_view_so_they_cannot_reach_another() -> None:
    camera = with_tiny_planet(pan(0.0, 30.0), 0.5, 1.0)

    text = camera_filter(camera, 1.0, SOURCE_8K, OUTPUT, FPS)

    second = text.split(";[in1]")[1]
    assert "v360@p1 pitch" in second
    assert "v360@p0" not in second


def test_08_rule_8_view_holds_the_real_pixels_of_an_8k_source() -> None:
    assert view_size(still(), 1.0, SOURCE_8K, (7680, 4320), FPS) == (2134, 1200)


def test_08_rule_8_tall_output_keeps_its_shape() -> None:
    assert view_size(still(fov=90.0), 1.0, SOURCE_8K, (4320, 7680), FPS) == (1920, 3414)


def test_08_rule_8_view_never_exceeds_the_output_size() -> None:
    assert view_size(still(), 1.0, SOURCE_8K, (1280, 720), FPS) == (1280, 720)


def test_08_rule_8_the_tightest_fov_sets_the_view_size() -> None:
    camera = Camera360(
        keyframes=(
            CameraKeyframe(t=0.0, yaw=0.0, pitch=-5.0, fov=140.0),
            CameraKeyframe(t=1.0, yaw=0.0, pitch=-5.0, fov=70.0),
        )
    )

    # The last frame sits at 29/30 s, so the path reaches FOV 72.33: 7680 * 72.33 / 360.
    assert view_size(camera, 1.0, SOURCE_8K, (7680, 4320), FPS)[0] == 1544


def test_08_rule_8_fast_mode_scales_the_view_to_the_output_with_lanczos() -> None:
    text = camera_filter(still(), 1.0, SOURCE_8K, (7680, 4320), FPS)

    assert text.endswith("scale=7680:4320:flags=lanczos")


def test_08_rule_8_scaling_comes_after_the_join_on_a_split_graph() -> None:
    camera = with_tiny_planet(pan(0.0, 0.0), 0.5, 1.0)

    text = camera_filter(camera, 1.0, SOURCE_8K, (7680, 4320), FPS)

    assert text.endswith("concat=n=2:v=1:a=0,scale=7680:4320:flags=lanczos")
