"""Stitches a raw Osmo 360 .OSV into an equirect video. Spec: specs/08-osmo360.md (rule 3)

Each lens is projected on its own with FFmpeg's `v360` filter (`input=fisheye`, `output=equirect`)
using the values of its camera profile in `osmo_calibration.json`: one shared lens FOV and a small
yaw, pitch and roll for the second lens. The two pictures are then cross-faded over the overlap of
the lenses with a static mask (`maskedmerge`), all in 10-bit. A raw .OSV has its lenses either as
two video streams or as one frame with the lenses side by side; both are handled.

The profiles were measured on two real files (Osmo 360 and Osmo 360 II). See the file's `proof`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog

from app.adapters.ffmpeg_runner import FfmpegError, run_tool
from app.domain.errors import AnalysisError, ErrorCode

log = structlog.get_logger()

CALIBRATION_FILE = Path(__file__).with_name("osmo_calibration.json")
BASE_ARGUMENTS = ("ffmpeg", "-hide_banner", "-loglevel", "error", "-y")
STITCH_QUALITY = 14
STITCH_PRESET = "p5"
TWO_LENSES = 2
COVER_CODECS = frozenset({"mjpeg", "png", "bmp", "gif", "webp"})
SEAM_LONGITUDE = 90.0  # the lenses meet a quarter and three quarters across the picture


def load_calibration(path: Path = CALIBRATION_FILE) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def pick_profile(calibration: dict[str, Any], encoder: str | None) -> dict[str, Any]:
    """The profile of the camera named in the file's `encoder` tag, else the default one."""
    profiles: dict[str, dict[str, Any]] = calibration["profiles"]
    wanted = (encoder or "").strip().lower()
    for profile in profiles.values():
        if profile["encoder"].lower() == wanted:
            return profile
    log.warning("osv.profile_unknown", encoder=encoder)
    return profiles[calibration["default_profile"]]


def blend_mask(width: int, height: int, feather_degrees: float) -> str:
    """Filter text of the one-frame blend mask: 0 where lens A is used, 1 where lens B is.

    Lens A covers longitudes -90..90 and lens B the rest; inside `feather` degrees either side of
    the 90 degree seam the weight rises along a smoothstep. The expression uses each plane's own
    width, so the chroma planes get the same weights.
    """
    t = (
        f"clip((abs((X+0.5)/W*360-180)-({SEAM_LONGITUDE:g}-{feather_degrees:g}))"
        f"/(2*{feather_degrees:g}),0,1)"
    )
    weight = f"1023*pow({t},2)*(3-2*{t})"
    return (
        f"color=c=black:s={width}x{height}:r=25:d=1,format=yuv420p10le,"
        f"geq=lum='{weight}':cb='{weight}':cr='{weight}',loop=loop=-1:size=1"
    )


def stitch_graph(
    calibration: dict[str, Any], profile: dict[str, Any], streams: int, lens_height: int
) -> str:
    """Filter text: two lens pictures to equirect, cross-fade over the overlap, centre stream 1.

    The picture is `2 x lens height` wide and `lens height` high: every lens pixel at the
    center survives, and equirect is 2:1.
    """
    height = round(lens_height * float(calibration["equirect_height_per_lens_height"]))
    height -= height % 2
    width = height * 2
    fov = f"{profile['fov_degrees']:g}"
    interp = calibration["interpolation"]
    lens = (
        f"format=yuv420p10le,v360=input=fisheye:output=equirect:ih_fov={fov}:iv_fov={fov}"
        f":interp={interp}:w={width}:h={height}"
    )
    second = wrap_degrees(180.0 + float(profile["lens2_yaw"]))
    rotation = (
        f":yaw={second:g}:pitch={float(profile['lens2_pitch']):g}"
        f":roll={float(profile['lens2_roll']):g}"
    )
    if streams >= TWO_LENSES:
        sources = "[0:v:0]null[l0];[0:v:1]null[l1];"
    else:
        sources = "[0:v:0]split[w0][w1];[w0]crop=iw/2:ih:0:0[l0];[w1]crop=iw/2:ih:iw/2:0[l1];"
    mask = blend_mask(width, height, float(calibration["feather_degrees"]))
    return (
        f"{sources}[l0]{lens}[a];[l1]{lens}{rotation}[b];{mask}[m];"
        f"[a][b][m]maskedmerge,split[x][y];"
        f"[x]crop=iw/2:ih:0:0[left];[y]crop=iw/2:ih:iw/2:0[right];[right][left]hstack[out]"
    )


def wrap_degrees(value: float) -> float:
    return (value + 180.0) % 360.0 - 180.0


def lens_streams(streams: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The video streams that are lenses. An .OSV also lists its cover picture (an MJPEG
    still, ffprobe index 7 or 9) as a video stream; it is not a lens."""
    return [
        s
        for s in streams
        if s.get("codec_type") == "video"
        and s.get("codec_name") not in COVER_CODECS
        and not (s.get("disposition") or {}).get("attached_pic")
    ]


class FfmpegOsvStitcher:
    def stitch(self, source: Path, target: Path) -> None:
        calibration = load_calibration()
        streams, lens_height, encoder = self._inspect(source)
        profile = pick_profile(calibration, encoder)
        target.parent.mkdir(parents=True, exist_ok=True)
        log.info(
            "osv.stitch",
            streams=streams,
            encoder=encoder,
            profile=profile["encoder"],
            proven=calibration["proven_on_real_files"],
        )
        try:
            run_tool(
                [
                    *BASE_ARGUMENTS,
                    "-i",
                    str(source),
                    "-filter_complex",
                    stitch_graph(calibration, profile, streams, lens_height),
                    "-map",
                    "[out]",
                    "-map",
                    "0:a:0?",
                    "-c:v",
                    "hevc_nvenc",
                    "-preset",
                    STITCH_PRESET,
                    "-rc",
                    "vbr",
                    "-cq",
                    str(STITCH_QUALITY),
                    "-b:v",
                    "0",
                    "-profile:v",
                    "main10",
                    "-pix_fmt",
                    "p010le",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "256k",
                    str(target),
                ]
            )
        except FfmpegError as error:
            target.unlink(missing_ok=True)
            raise AnalysisError(str(error), ErrorCode.ASSET_UNSUPPORTED) from error

    @staticmethod
    def _inspect(source: Path) -> tuple[int, int, str | None]:
        """How many lens streams the file has, the height of the first, and the camera name."""
        try:
            data = json.loads(
                run_tool(
                    [
                        "ffprobe",
                        "-v",
                        "error",
                        "-print_format",
                        "json",
                        "-show_streams",
                        "-show_format",
                        str(source),
                    ]
                )
            )
        except FfmpegError as error:
            raise AnalysisError(str(error), ErrorCode.ASSET_UNSUPPORTED) from error
        lenses = lens_streams(data.get("streams", []))
        if not lenses:
            raise AnalysisError(f"No video in {source.name}", ErrorCode.ASSET_UNSUPPORTED)
        encoder = (data.get("format", {}).get("tags") or {}).get("encoder")
        return len(lenses), int(lenses[0]["height"]), encoder
