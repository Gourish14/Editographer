"""Stitches a raw Osmo 360 .OSV into an equirect video. Spec: specs/08-osmo360.md (rule 3)

FFmpeg's `v360` filter turns two fisheye images into one equirect picture
(`input=dfisheye:output=equirect`), using the lens values in `osmo_calibration.json`. An .OSV
holds the lenses either as two video streams or as one frame with the lenses side by side; both
are handled. The calibration is NOT proven on a real camera file: no .OSV was available, so it is
checked only by a round trip through `v360` on a generated clip.
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


def load_calibration(path: Path = CALIBRATION_FILE) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def stitch_graph(calibration: dict[str, Any], streams: int, lens_height: int) -> str:
    """Filter text: join the lens streams if there are two, then v360 to equirect.

    The picture is `2 x lens height` wide and `lens height` high: every lens pixel at the
    center survives, and equirect is 2:1.
    """
    lens = f"{calibration['fov_degrees']:g}"
    height = round(lens_height * float(calibration["equirect_height_per_lens_height"]))
    height -= height % 2
    join = (
        "[0:v:0][0:v:1]hstack=inputs=2,format=yuv420p10le,"
        if streams >= TWO_LENSES
        else ("[0:v:0]format=yuv420p10le,")
    )
    projection = (
        f"v360=input=dfisheye:output=equirect:ih_fov={lens}:iv_fov={lens}"
        f":interp={calibration['interpolation']}:w={height * 2}:h={height}"
    )
    return f"{join}{projection}[out]"


class FfmpegOsvStitcher:
    def stitch(self, source: Path, target: Path) -> None:
        calibration = load_calibration()
        streams, lens_height = self._lenses(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        log.info("osv.stitch", streams=streams, proven=calibration["proven_on_real_files"])
        try:
            run_tool(
                [
                    *BASE_ARGUMENTS,
                    "-i",
                    str(source),
                    "-filter_complex",
                    stitch_graph(calibration, streams, lens_height),
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
    def _lenses(source: Path) -> tuple[int, int]:
        """How many video streams the file has, and the height of the first."""
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
                        str(source),
                    ]
                )
            )
        except FfmpegError as error:
            raise AnalysisError(str(error), ErrorCode.ASSET_UNSUPPORTED) from error
        videos = [s for s in data.get("streams", []) if s.get("codec_type") == "video"]
        if not videos:
            raise AnalysisError(f"No video in {source.name}", ErrorCode.ASSET_UNSUPPORTED)
        return len(videos), int(videos[0]["height"])
