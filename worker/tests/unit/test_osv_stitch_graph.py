"""The raw .OSV stitch graph and its camera profiles. Spec: specs/08-osmo360.md (rule 3) [T-414]"""

from __future__ import annotations

from app.adapters.ffmpeg_osv import blend_mask, load_calibration, pick_profile, stitch_graph


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


def test_rule_3_the_calibration_says_what_was_proven() -> None:
    calibration = load_calibration()

    assert calibration["proven_on_real_files"] is True
    assert "Osmo 360 II" in calibration["proof"]
