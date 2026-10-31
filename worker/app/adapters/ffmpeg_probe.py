"""ffprobe adapter. Spec: specs/04-pipeline.md#stages (1)"""

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path
from typing import Any

from app.adapters.ffmpeg_runner import FfmpegError, run_tool
from app.domain.errors import AnalysisError, ErrorCode
from app.domain.media import MediaInfo

QUARTER_TURN = 90
FULL_TURN = 360
TEN_BIT_MARKER = "10"


class FfmpegProbe:
    def probe(self, path: Path) -> MediaInfo:
        try:
            output = run_tool(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-print_format",
                    "json",
                    "-show_streams",
                    "-show_format",
                    str(path),
                ]
            )
        except FfmpegError as error:
            raise AnalysisError(str(error), ErrorCode.ASSET_UNSUPPORTED) from error
        return parse_probe_output(json.loads(output))


def parse_probe_output(data: dict[str, Any]) -> MediaInfo:
    """Turns ffprobe JSON into MediaInfo. A file with only audio has no size or fps."""
    streams = data.get("streams", [])
    media_format = data.get("format", {})
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    main = video or audio or {}

    rotation = _rotation(video) if video else 0
    width, height = _display_size(video, rotation) if video else (None, None)
    return MediaInfo(
        codec=main.get("codec_name"),
        width=width,
        height=height,
        fps=_fps(video) if video else None,
        rotation=rotation,
        duration_sec=_float(media_format.get("duration")) or _float(main.get("duration")),
        transfer=video.get("color_transfer") if video else None,
        bit_depth=_bit_depth(video) if video else None,
        tags=_tags(media_format, streams),
        has_audio=audio is not None,
    )


def _rotation(video: dict[str, Any]) -> int:
    for side_data in video.get("side_data_list", []):
        if "rotation" in side_data:
            return int(side_data["rotation"]) % FULL_TURN
    rotate = video.get("tags", {}).get("rotate")
    return int(rotate) % FULL_TURN if rotate else 0


def _display_size(video: dict[str, Any], rotation: int) -> tuple[int | None, int | None]:
    width, height = video.get("width"), video.get("height")
    if rotation % (2 * QUARTER_TURN) == QUARTER_TURN:
        return height, width
    return width, height


def _fps(video: dict[str, Any]) -> float | None:
    for key in ("avg_frame_rate", "r_frame_rate"):
        value = video.get(key)
        if value and value != "0/0":
            return round(float(Fraction(value)), 3)
    return None


def _bit_depth(video: dict[str, Any]) -> int | None:
    depth = video.get("bits_per_raw_sample")
    if depth and str(depth).isdigit():
        return int(depth)
    pixel_format = video.get("pix_fmt", "")
    if not pixel_format:
        return None
    return 10 if TEN_BIT_MARKER in pixel_format else 8


def _float(value: object) -> float | None:
    try:
        return float(str(value)) if value is not None else None
    except ValueError:
        return None


def _tags(media_format: dict[str, Any], streams: list[dict[str, Any]]) -> tuple[str, ...]:
    values: list[str] = []
    for section in [media_format, *streams]:
        values.extend(f"{key}={value}" for key, value in section.get("tags", {}).items())
    return tuple(values)
