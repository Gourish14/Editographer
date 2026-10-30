"""Facts about a media file and what they mean for the edit.

Spec: specs/08-osmo360.md#handling-rules
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

PANO_ASPECT = 2.0
PANO_ASPECT_TOLERANCE = 0.01
PANO_8K_MIN_WIDTH = 7000
PANO_6K_MIN_WIDTH = 5000
SINGLE_5K_MIN_WIDTH = 4800
SINGLE_BOOST_4K_MIN_WIDTH = 3800
SINGLE_2K7_MIN_WIDTH = 2600
NATIVE_SLOW_MO_FPS = 100.0
TEN_BIT = 10

LOG_TRANSFERS = frozenset({"arib-std-b67", "log100", "log316"})
DJI_MARKER = "dji"
DLOG_MARKERS = ("d-log", "dlog")


class CameraMode(StrEnum):
    OSMO360_PANO_8K = "OSMO360_PANO_8K"
    OSMO360_PANO_6K = "OSMO360_PANO_6K"
    OSMO360_PANO_4K100 = "OSMO360_PANO_4K100"
    SINGLE_5K = "SINGLE_5K"
    SINGLE_BOOST_4K = "SINGLE_BOOST_4K"
    SINGLE_2K7 = "SINGLE_2K7"
    FLAT = "FLAT"


class LogProfile(StrEnum):
    DLOG_M = "DLOG_M"


@dataclass(frozen=True)
class MediaInfo:
    """What ffprobe reports. Sizes are as displayed, after rotation."""

    codec: str | None
    width: int | None
    height: int | None
    fps: float | None
    rotation: int
    duration_sec: float | None
    transfer: str | None
    bit_depth: int | None
    tags: tuple[str, ...] = field(default=())


def detect_camera_mode(info: MediaInfo, extension: str) -> CameraMode:
    """Spec rule 1: .OSV or a 2:1 frame is 360; DJI metadata marks single-lens footage."""
    width = info.width or 0
    if extension.lower() == "osv" or _is_pano(info):
        return _pano_mode(width)
    if _is_dji(info):
        return _single_lens_mode(width)
    return CameraMode.FLAT


def detect_log_profile(info: MediaInfo) -> LogProfile | None:
    """Spec rule 4: D-Log M from metadata, or a 10-bit HLG or log transfer."""
    if any(marker in tag.lower() for tag in info.tags for marker in DLOG_MARKERS):
        return LogProfile.DLOG_M
    if info.bit_depth == TEN_BIT and info.transfer in LOG_TRANSFERS:
        return LogProfile.DLOG_M
    return None


def is_native_slow_mo(info: MediaInfo) -> bool:
    """Spec rule 1: 100 and 120 fps clips are native slow-mo sources."""
    return (info.fps or 0.0) >= NATIVE_SLOW_MO_FPS


def _is_pano(info: MediaInfo) -> bool:
    if not info.width or not info.height:
        return False
    return abs(info.width / info.height - PANO_ASPECT) <= PANO_ASPECT_TOLERANCE


def _is_dji(info: MediaInfo) -> bool:
    return any(DJI_MARKER in tag.lower() for tag in info.tags)


def _pano_mode(width: int) -> CameraMode:
    if width >= PANO_8K_MIN_WIDTH:
        return CameraMode.OSMO360_PANO_8K
    if width >= PANO_6K_MIN_WIDTH:
        return CameraMode.OSMO360_PANO_6K
    return CameraMode.OSMO360_PANO_4K100


def _single_lens_mode(width: int) -> CameraMode:
    if width >= SINGLE_5K_MIN_WIDTH:
        return CameraMode.SINGLE_5K
    if width >= SINGLE_BOOST_4K_MIN_WIDTH:
        return CameraMode.SINGLE_BOOST_4K
    if width >= SINGLE_2K7_MIN_WIDTH:
        return CameraMode.SINGLE_2K7
    return CameraMode.FLAT
