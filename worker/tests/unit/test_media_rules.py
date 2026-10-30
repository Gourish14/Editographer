"""Tests for camera and log detection. Spec: specs/08-osmo360.md#handling-rules [T-109]"""

from __future__ import annotations

import pytest

from app.domain.media import (
    CameraMode,
    LogProfile,
    MediaInfo,
    detect_camera_mode,
    detect_log_profile,
    is_native_slow_mo,
)


def info(
    width: int | None = 1920,
    height: int | None = 1080,
    fps: float | None = 30.0,
    tags: tuple[str, ...] = (),
    transfer: str | None = None,
    bit_depth: int | None = 8,
) -> MediaInfo:
    return MediaInfo("hevc", width, height, fps, 0, 10.0, transfer, bit_depth, tags)


DJI = ("encoder=DJI Osmo 360",)


@pytest.mark.parametrize(
    ("clip", "extension", "expected"),
    [
        (info(7680, 3840), "mp4", CameraMode.OSMO360_PANO_8K),
        (info(6000, 3000), "mp4", CameraMode.OSMO360_PANO_6K),
        (info(3840, 1920, 100.0), "mp4", CameraMode.OSMO360_PANO_4K100),
        (info(5120, 2880, tags=DJI), "mp4", CameraMode.SINGLE_5K),
        (info(3840, 2160, 120.0, tags=DJI), "mp4", CameraMode.SINGLE_BOOST_4K),
        (info(2688, 1512, tags=DJI), "mp4", CameraMode.SINGLE_2K7),
        (info(1920, 1080), "mp4", CameraMode.FLAT),
        (info(3840, 2160), "mov", CameraMode.FLAT),
    ],
)
def test_rule_1_every_mode_is_detected(
    clip: MediaInfo, extension: str, expected: CameraMode
) -> None:
    assert detect_camera_mode(clip, extension) is expected


def test_rule_1_osv_is_360_whatever_its_frame_size() -> None:
    assert detect_camera_mode(info(None, None), "OSV") is CameraMode.OSMO360_PANO_4K100
    assert detect_camera_mode(info(7680, 1920), "osv") is CameraMode.OSMO360_PANO_8K


def test_a_small_dji_clip_is_flat() -> None:
    assert detect_camera_mode(info(1280, 720, tags=DJI), "mp4") is CameraMode.FLAT


def test_music_has_no_frame_and_is_flat() -> None:
    assert detect_camera_mode(info(None, None, None), "mp3") is CameraMode.FLAT


def test_dji_tag_is_found_in_any_case() -> None:
    assert detect_camera_mode(info(5120, 2880, tags=("make=dJi",)), "mp4") is CameraMode.SINGLE_5K


@pytest.mark.parametrize("transfer", ["arib-std-b67", "log100", "log316"])
def test_rule_4_ten_bit_log_transfer_is_d_log_m(transfer: str) -> None:
    assert detect_log_profile(info(transfer=transfer, bit_depth=10)) is LogProfile.DLOG_M


def test_rule_4_eight_bit_log_transfer_is_not() -> None:
    assert detect_log_profile(info(transfer="arib-std-b67", bit_depth=8)) is None


def test_rule_4_metadata_marks_d_log_m_directly() -> None:
    clip = info(tags=("color_mode=D-Log M",))

    assert detect_log_profile(clip) is LogProfile.DLOG_M


def test_rule_4_normal_footage_has_no_log_profile() -> None:
    assert detect_log_profile(info(transfer="bt709", bit_depth=10)) is None


@pytest.mark.parametrize(
    ("fps", "expected"),
    [(100.0, True), (120.0, True), (60.0, False), (None, False)],
)
def test_rule_1_high_frame_rates_are_native_slow_mo(fps: float | None, expected: bool) -> None:
    assert is_native_slow_mo(info(fps=fps)) is expected
