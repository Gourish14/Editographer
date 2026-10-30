"""360 filters on a real generated 2:1 equirect image. Spec: specs/08-osmo360.md [T-302]

Runs on the CPU. A static v360 is the oracle for what commands must produce, and known colored
landmarks on the sphere pin the sign conventions.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np
import pytest
from numpy.typing import NDArray

from app.adapters.ffmpeg_360 import camera_filter
from app.domain.brain.reframe import (
    camera_at,
    with_beat_spin,
    with_rabbit_hole,
    with_tiny_planet,
)
from app.domain.plan import Camera360, CameraKeyframe

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs FFmpeg on PATH")

Image = NDArray[np.uint8]
Color = NDArray[np.float64]

WIDTH, HEIGHT = 1920, 960
VIEW = (320, 180)
FPS = 30
SKY = (230, 120, 30)
GROUND = (30, 130, 40)
FRONT = (0, 0, 255)
RIGHT = (0, 160, 255)
BACK = (255, 0, 255)
LEFT = (255, 255, 0)
UP_MARK = (255, 255, 255)
DOWN_MARK = (0, 0, 0)
ZENITH = (0, 230, 255)
NADIR = (0, 0, 120)


def run(*arguments: str) -> None:
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *arguments],
        check=True,
        capture_output=True,
    )


def place(card: Image, yaw: float, pitch: float, color: tuple[int, int, int]) -> None:
    x = int((yaw + 180) / 360 * WIDTH) % WIDTH
    y = int((90 - pitch) / 180 * HEIGHT)
    for wrapped in (x - WIDTH, x, x + WIDTH):
        cv2.circle(card, (wrapped, y), 70, color, -1)


@pytest.fixture(scope="module")
def equirect(tmp_path_factory: pytest.TempPathFactory) -> Path:
    card: Image = np.zeros((HEIGHT, WIDTH, 3), np.uint8)
    card[: HEIGHT // 2] = SKY
    card[HEIGHT // 2 :] = GROUND
    place(card, 0, 0, FRONT)
    place(card, 90, 0, RIGHT)
    place(card, 180, 0, BACK)
    place(card, -90, 0, LEFT)
    place(card, 0, 40, UP_MARK)
    place(card, 0, -40, DOWN_MARK)
    card[:50] = ZENITH
    card[-50:] = NADIR
    path = tmp_path_factory.mktemp("equirect") / "card.png"
    cv2.imwrite(str(path), card)
    return path


def render(
    source: Path, target: Path, video_filter: str, frames: int, size: tuple[int, int] = VIEW
) -> list[Image]:
    """Plays the still as a conformed stream, the way the compositor hands frames over."""
    run(
        "-loop",
        "1",
        "-framerate",
        str(FPS),
        "-i",
        str(source),
        "-vf",
        video_filter,
        "-frames:v",
        str(frames),
        str(target / "frame_%03d.png"),
    )
    images = []
    for path in sorted(target.glob("frame_*.png")):
        image = cv2.imread(str(path))
        assert image is not None
        assert image.shape[:2] == (size[1], size[0])
        images.append(np.asarray(image, np.uint8))
    return images


def static_view(
    source: Path, target: Path, yaw: float, pitch: float, fov: float, size: tuple[int, int] = VIEW
) -> Image:
    held = Camera360(keyframes=(CameraKeyframe(t=0.0, yaw=yaw, pitch=pitch, fov=fov),))
    folder = target / f"static_{yaw}_{pitch}_{fov}"
    folder.mkdir()
    return render(source, folder, camera_filter(held, 1 / FPS, WIDTH, size, FPS), 1, size)[0]


def center_color(image: Image) -> Color:
    height, width = image.shape[:2]
    pixels = image[height // 2 - 2 : height // 2 + 2, width // 2 - 2 : width // 2 + 2]
    average: Color = pixels.reshape(-1, 3).astype(np.float64).mean(axis=0)
    return average


def pixel(image: Image, row: int, column: int) -> Color:
    return np.asarray(image[row, column], np.float64)


def assert_color(actual: Color, expected: tuple[int, int, int]) -> None:
    assert np.abs(actual - np.array(expected)).max() < 12, f"{actual} is not {expected}"


def looks(image: Image, color: tuple[int, int, int]) -> float:
    """Share of the image that shows a color."""
    distance = np.abs(image.astype(np.int32) - np.array(color)).max(axis=2)
    return float((distance < 16).mean())


@pytest.mark.parametrize(
    ("yaw", "pitch", "color"),
    [
        (0, 0, FRONT),
        (90, 0, RIGHT),
        (180, 0, BACK),
        (-90, 0, LEFT),
        (0, 40, UP_MARK),
        (0, -40, DOWN_MARK),
    ],
)
def test_08_rule_7_plan_yaw_turns_right_and_plan_pitch_looks_up(
    equirect: Path, tmp_path: Path, yaw: float, pitch: float, color: tuple[int, int, int]
) -> None:
    assert_color(center_color(static_view(equirect, tmp_path, yaw, pitch, 100.0)), color)


def test_08_rule_7_every_commanded_frame_equals_a_static_view_of_its_pose(
    equirect: Path, tmp_path: Path
) -> None:
    camera = Camera360(
        keyframes=(
            CameraKeyframe(t=0.0, yaw=150.0, pitch=-5.0, fov=100.0),
            CameraKeyframe(t=0.2, yaw=215.0, pitch=-30.0, roll=8.0, fov=75.0),
        )
    )
    frames = 7

    images = render(equirect, tmp_path, camera_filter(camera, 0.2334, WIDTH, VIEW, FPS), frames)

    assert len(images) == frames
    for index, image in enumerate(images):
        pose = camera_at(camera, index / FPS)
        oracle = _oracle(equirect, tmp_path, index, pose.yaw, pose.pitch, pose.roll, pose.fov)
        assert np.abs(image.astype(np.int32) - oracle).mean() < 0.5, f"frame {index}"


def _oracle(
    source: Path, target: Path, index: int, yaw: float, pitch: float, roll: float, fov: float
) -> Image:
    camera = Camera360(keyframes=(CameraKeyframe(t=0.0, yaw=yaw, pitch=pitch, roll=roll, fov=fov),))
    folder = target / f"oracle_{index}"
    folder.mkdir()
    return render(source, folder, camera_filter(camera, 1 / FPS, WIDTH, VIEW, FPS), 1)[0]


def test_b7_a_beat_spin_sweeps_the_whole_sphere_and_lands_where_it_began(
    equirect: Path, tmp_path: Path
) -> None:
    camera = with_beat_spin(
        Camera360(
            keyframes=(
                CameraKeyframe(t=0.0, yaw=0.0, pitch=-5.0, fov=100.0),
                CameraKeyframe(t=1.0, yaw=0.0, pitch=-5.0, fov=100.0),
            )
        ),
        0.0,
        1.0,
    )
    camera = camera.model_copy(
        update={
            "keyframes": tuple(
                key.model_copy(update={"ease": "linear"}) for key in camera.keyframes
            )
        }
    )

    images = render(
        equirect, tmp_path, camera_filter(camera, 1.0 + 1 / FPS, WIDTH, VIEW, FPS), FPS + 1
    )

    assert_color(center_color(images[0]), FRONT)
    assert_color(center_color(images[FPS // 4]), RIGHT)
    assert_color(center_color(images[FPS // 2]), BACK)
    assert_color(center_color(images[3 * FPS // 4]), LEFT)
    assert_color(center_color(images[FPS]), FRONT)


def test_08_tiny_planet_shows_a_small_globe_with_the_ground_inside_and_sky_around(
    equirect: Path, tmp_path: Path
) -> None:
    camera = Camera360(
        projection="tinyplanet",
        keyframes=(CameraKeyframe(t=0.0, yaw=0.0, pitch=-90.0, fov=160.0),),
    )
    size = (400, 400)

    image = render(equirect, tmp_path, camera_filter(camera, 1 / FPS, WIDTH, size, FPS), 1, size)[0]

    assert_color(center_color(image), NADIR)
    assert_color(pixel(image, 6, 6), SKY)
    assert_color(pixel(image, 200, 150), GROUND)
    assert looks(image, SKY) > 0.5
    assert 0.03 < looks(image, GROUND) < 0.3


def test_08_rabbit_hole_turns_the_sky_into_the_center_of_a_tunnel(
    equirect: Path, tmp_path: Path
) -> None:
    camera = Camera360(
        projection="rabbithole",
        keyframes=(CameraKeyframe(t=0.0, yaw=0.0, pitch=90.0, fov=160.0),),
    )
    size = (400, 400)

    image = render(equirect, tmp_path, camera_filter(camera, 1 / FPS, WIDTH, size, FPS), 1, size)[0]

    assert_color(center_color(image), ZENITH)
    assert_color(pixel(image, 6, 6), GROUND)
    assert looks(image, GROUND) > 0.5


def test_08_a_planet_transition_renders_through_one_graph_and_does_not_jump_at_the_switch(
    equirect: Path, tmp_path: Path
) -> None:
    flat = Camera360(
        keyframes=(
            CameraKeyframe(t=0.0, yaw=0.0, pitch=-5.0, fov=100.0),
            CameraKeyframe(t=0.5, yaw=0.0, pitch=-5.0, fov=100.0),
        )
    )
    camera = with_tiny_planet(flat, 0.25, 0.5)
    frames = 16

    images = render(equirect, tmp_path, camera_filter(camera, 0.5 + 1 / FPS, WIDTH, VIEW, FPS), 16)

    assert len(images) == frames
    assert_color(center_color(images[0]), FRONT)
    assert_color(center_color(images[7]), FRONT)
    assert camera_at(camera, 8 / FPS).projection == "tinyplanet"
    assert_color(center_color(images[8]), FRONT)
    assert_color(center_color(images[-1]), NADIR)


def test_08_rabbit_hole_transition_ends_looking_up(equirect: Path, tmp_path: Path) -> None:
    flat = Camera360(
        keyframes=(
            CameraKeyframe(t=0.0, yaw=0.0, pitch=-5.0, fov=100.0),
            CameraKeyframe(t=0.5, yaw=0.0, pitch=-5.0, fov=100.0),
        )
    )
    camera = with_rabbit_hole(flat, 0.0, 0.5)

    images = render(equirect, tmp_path, camera_filter(camera, 0.5 + 1 / FPS, WIDTH, VIEW, FPS), 16)

    assert_color(center_color(images[-1]), ZENITH)


def test_08_rule_8_a_small_view_scales_up_to_the_output(equirect: Path, tmp_path: Path) -> None:
    held = Camera360(keyframes=(CameraKeyframe(t=0.0, yaw=0.0, pitch=0.0, fov=100.0),))
    size = (1600, 900)

    image = render(equirect, tmp_path, camera_filter(held, 1 / FPS, WIDTH, size, FPS), 1, size)[0]

    assert_color(center_color(image), FRONT)


def test_08_real_10_bit_video_keeps_every_frame_across_a_projection_change(tmp_path: Path) -> None:
    clip = tmp_path / "pano.mp4"
    run(
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=640x320:rate=30:duration=1.2",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(clip),
    )
    flat = Camera360(
        keyframes=(
            CameraKeyframe(t=0.0, yaw=0.0, pitch=-5.0, fov=100.0),
            CameraKeyframe(t=1.0, yaw=90.0, pitch=-5.0, fov=100.0),
        )
    )
    camera = with_tiny_planet(flat, 0.5, 1.0)
    frames = tmp_path / "frames"
    frames.mkdir()

    run(
        "-ss",
        "0.1",
        "-i",
        str(clip),
        "-vf",
        f"fps={FPS},format=yuv420p10le,{camera_filter(camera, 1.0, 640, VIEW, FPS)},format=rgb24",
        "-frames:v",
        str(FPS),
        str(frames / "frame_%03d.png"),
    )

    assert len(list(frames.glob("frame_*.png"))) == FPS
