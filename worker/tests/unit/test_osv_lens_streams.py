"""Only real lens streams count in a raw .OSV. Spec: specs/08-osmo360.md (rule 3) [T-414]"""

from __future__ import annotations

from typing import Any

from app.adapters.ffmpeg_osv import lens_streams


def hevc(index: int, size: int = 3840) -> dict[str, Any]:
    return {
        "index": index,
        "codec_type": "video",
        "codec_name": "hevc",
        "width": size,
        "height": size,
    }


COVER = {"index": 7, "codec_type": "video", "codec_name": "mjpeg", "width": 344, "height": 612}
DATA = {"index": 3, "codec_type": "data", "codec_name": "unknown"}
AUDIO = {"index": 2, "codec_type": "audio", "codec_name": "aac"}


def test_rule_3_the_mjpeg_cover_is_not_a_lens() -> None:
    # Stream list shape of a real Osmo 360 .OSV: two lenses, audio, data tracks, cover last.
    streams = [hevc(0), hevc(1), AUDIO, DATA, DATA, COVER]

    assert [s["index"] for s in lens_streams(streams)] == [0, 1]


def test_rule_3_a_side_by_side_file_with_a_cover_has_one_lens_stream() -> None:
    streams = [hevc(0, 3840), AUDIO, DATA, COVER]

    assert len(lens_streams(streams)) == 1


def test_rule_3_an_attached_picture_is_not_a_lens() -> None:
    picture = {**hevc(4), "disposition": {"attached_pic": 1}}

    assert lens_streams([hevc(0), picture]) == [hevc(0)]
