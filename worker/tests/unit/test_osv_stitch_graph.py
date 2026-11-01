"""The raw .OSV stitch graph and its camera profiles. Spec: specs/08-osmo360.md (rule 3) [T-414]"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.adapters import ffmpeg_osv
from app.adapters.ffmpeg_osv import (
    DECODE_THREADS,
    FfmpegOsvStitcher,
    blend_mask,
    frame_count,
    load_calibration,
    pick_profile,
    stitch_graph,
)
from app.adapters.ffmpeg_runner import FfmpegError
from app.domain.errors import AnalysisError

PROBE = json.dumps(
    {
        "streams": [
            {"codec_type": "video", "codec_name": "hevc", "height": 3840, "nb_frames": "25"},
            {"codec_type": "video", "codec_name": "hevc", "height": 3840, "nb_frames": "25"},
        ],
        "format": {"duration": "1.0", "tags": {"encoder": "Osmo 360"}},
    }
)


class FakeFfmpeg:
    """Stands in for run_tool: answers ffprobe, and writes the output file ffmpeg was given."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.command: list[str] = []

    def __call__(self, command: list[str]) -> str:
        if command[0] == "ffprobe":
            return PROBE
        self.command = command
        Path(command[-1]).write_text("half a file")
        if self.fail:
            raise FfmpegError("killed")
        return ""


def test_rule_3_the_profile_follows_the_encoder_tag_of_the_file() -> None:
    calibration = load_calibration()

    first = pick_profile(calibration, "Osmo 360")
    second = pick_profile(calibration, "Osmo 360 II")

    assert first["encoder"] == "Osmo 360"
    assert second["encoder"] == "Osmo 360 II"
    assert first != second


def test_rule_3_an_unknown_camera_gets_the_default_profile() -> None:
    calibration = load_calibration()

    unknown = pick_profile(calibration, "Some Other Camera")
    missing = pick_profile(calibration, None)

    default = calibration["profiles"][calibration["default_profile"]]
    assert unknown == default
    assert missing == default


def test_rule_3_two_lens_streams_are_projected_one_by_one_and_blended() -> None:
    calibration = load_calibration()
    profile = pick_profile(calibration, "Osmo 360")

    graph = stitch_graph(calibration, profile, 2, 3840)

    assert graph.startswith("[0:v:0]null[l0];[0:v:1]null[l1];")
    assert graph.count("v360=input=fisheye:output=equirect") == 2
    assert f"ih_fov={profile['fov_degrees']:g}" in graph
    assert "w=7680:h=3840" in graph
    assert "maskedmerge" in graph
    assert graph.endswith("[out]")
    assert "dfisheye" not in graph
    assert "[0:v:2]" not in graph  # the cover picture is never a lens


def test_rule_3_a_side_by_side_frame_is_cropped_into_its_two_lenses() -> None:
    calibration = load_calibration()
    profile = pick_profile(calibration, "Osmo 360")

    graph = stitch_graph(calibration, profile, 1, 3840)

    assert graph.startswith("[0:v:0]split[w0][w1];[w0]crop=iw/2:ih:0:0[l0];")
    assert "[w1]crop=iw/2:ih:iw/2:0[l1]" in graph


def test_rule_3_only_the_second_lens_is_turned_by_its_profile() -> None:
    calibration = load_calibration()
    profile = pick_profile(calibration, "Osmo 360")

    graph = stitch_graph(calibration, profile, 2, 3840)
    first, second = graph.split("[a];")

    assert "yaw=" not in first.split("[l0]")[-1]
    assert f"roll={profile['lens2_roll']:g}" in second


def test_rule_3_the_blend_mask_rises_across_the_seam_in_every_plane() -> None:
    mask = blend_mask(7680, 3840, 4.0)

    assert "s=7680x3840" in mask
    assert "format=yuv420p10le" in mask
    assert "lum='" in mask and "cb='" in mask and "cr='" in mask
    assert "(90-4)" in mask
    assert "loop=loop=-1:size=1" in mask


def test_rule_3_the_stitch_writes_exactly_the_lens_frames_because_the_mask_never_ends() -> None:
    assert frame_count({"nb_frames": "585"}, "23.4") == 585


def test_rule_3_a_file_without_a_frame_count_uses_rate_and_length() -> None:
    assert frame_count({"avg_frame_rate": "25/1"}, "23.4") == 585


def test_bug_013_the_lenses_use_linear_tables_because_cubic_outgrows_the_laptop() -> None:
    calibration = load_calibration()

    graph = stitch_graph(calibration, pick_profile(calibration, "Osmo 360"), 2, 3840)

    assert graph.count("interp=linear") == 2


def test_bug_013_the_lens_decoders_are_held_to_a_few_threads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeFfmpeg()
    monkeypatch.setattr(ffmpeg_osv, "run_tool", fake)

    FfmpegOsvStitcher().stitch(tmp_path / "a.osv", tmp_path / "a.mp4")

    threads = fake.command.index("-threads")
    assert fake.command[threads + 1] == str(DECODE_THREADS)
    assert threads < fake.command.index("-i")  # after -i it would mean the encoder


def test_bug_014_a_finished_stitch_reaches_its_final_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeFfmpeg()
    monkeypatch.setattr(ffmpeg_osv, "run_tool", fake)
    target = tmp_path / "a.mp4"

    FfmpegOsvStitcher().stitch(tmp_path / "a.osv", target)

    assert fake.command[-1] != str(target)
    assert target.read_text() == "half a file"
    assert [path.name for path in tmp_path.iterdir()] == ["a.mp4"]


def test_bug_014_a_failed_stitch_leaves_nothing_a_retry_could_mistake_for_finished(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ffmpeg_osv, "run_tool", FakeFfmpeg(fail=True))

    with pytest.raises(AnalysisError):
        FfmpegOsvStitcher().stitch(tmp_path / "a.osv", tmp_path / "a.mp4")

    assert list(tmp_path.iterdir()) == []


def test_rule_3_the_calibration_says_what_was_proven() -> None:
    calibration = load_calibration()

    assert calibration["proven_on_real_files"] is True
    assert "Osmo 360 II" in calibration["proof"]
