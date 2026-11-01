"""Tests for the Phase 3 gate script. Spec: specs/10-roadmap.md#phase-3--360--osmo [T-416]

Run with: python -m unittest discover -s scripts -p "test_*.py"
"""

from __future__ import annotations

import unittest

import phase1_gate as gate
import phase3_gate as p3

SECTIONS = [
    {"kind": "VERSE", "start": 0.0, "end": 4.0},
    {"kind": "DROP", "start": 4.0, "end": 8.0},
    {"kind": "BREAK", "start": 8.0, "end": 12.0},
]


def segment(keys: list[dict], at: float = 3.0, duration: float = 2.0) -> dict:
    return {
        "id": "s1", "assetId": "a", "type": "video360", "srcIn": 1.0, "srcOut": 3.0,
        "at": at, "duration": duration, "camera360": {"keyframes": keys},
    }  # fmt: skip


class FollowPointTest(unittest.TestCase):
    def test_gate_follow_point_is_the_api_shape(self) -> None:
        self.assertEqual(p3.parse_follow([0.25, 0.5, 2.0]), {"x": 0.25, "y": 0.5, "timeSec": 2.0})

    def test_gate_follow_point_outside_the_frame_is_refused(self) -> None:
        with self.assertRaises(gate.GateError):
            p3.parse_follow([1.2, 0.5, 2.0])


class StitchTest(unittest.TestCase):
    OK = {"width": 7680, "height": 3840, "frames": 585, "pix_fmt": "yuv420p10le"}

    def test_gate_stitch_passes_with_size_frames_and_audio(self) -> None:
        self.assertTrue(p3.stitch_facts(self.OK, 585, 1)["passed"])

    def test_gate_stitch_fails_on_one_frame_short(self) -> None:
        facts = p3.stitch_facts(self.OK, 586, 1)
        self.assertFalse(facts["framesOk"])
        self.assertFalse(facts["passed"])

    def test_gate_stitch_fails_without_audio_or_at_4k(self) -> None:
        self.assertFalse(p3.stitch_facts(self.OK, 585, 0)["passed"])
        small = {**self.OK, "width": 3840, "height": 1920}
        self.assertFalse(p3.stitch_facts(small, 585, 1)["sizeOk"])


class EffectsTest(unittest.TestCase):
    BEAT = 0.7

    def test_gate_spin_is_a_360_turn_within_a_beat_and_starts_on_the_segment_key(self) -> None:
        keys = [{"t": 0.0, "yaw": 10, "fov": 100}, {"t": 0.7, "yaw": 370, "fov": 100}]
        found = p3.spins({"segments": [segment(keys)]}, self.BEAT)
        self.assertEqual([(s["start"], s["degrees"]) for s in found], [(3.0, 360.0)])

    def test_gate_slow_follow_is_not_a_spin(self) -> None:
        keys = [{"t": 0.0, "yaw": 10, "fov": 100}, {"t": 2.0, "yaw": 50, "fov": 100}]
        self.assertEqual(p3.spins({"segments": [segment(keys)]}, self.BEAT), [])

    def test_gate_a_turn_over_many_beats_is_not_a_spin(self) -> None:
        keys = [{"t": 0.0, "yaw": 0, "fov": 100}, {"t": 2.0, "yaw": 360, "fov": 100}]
        self.assertEqual(p3.spins({"segments": [segment(keys)]}, self.BEAT), [])

    def test_gate_tiny_planet_span_is_found_in_edit_time(self) -> None:
        keys = [
            {"t": 0.0, "yaw": 0, "fov": 100},
            {"t": 1.5, "yaw": 0, "fov": 100},
            {"t": 2.0, "yaw": 0, "fov": 160, "projection": "tinyplanet"},
        ]
        found = p3.tiny_planets({"segments": [segment(keys)]})
        self.assertEqual(found, [{"segment": "s1", "start": 4.5, "end": 5.0, "segmentEnd": 5.0}])


class SectionTest(unittest.TestCase):
    def test_gate_section_kind_and_change(self) -> None:
        self.assertEqual(p3.section_kind(4.0, SECTIONS), "drop")
        self.assertEqual(p3.section_kind(99.0, SECTIONS), "unknown")
        self.assertTrue(p3.is_section_change(8.5, SECTIONS, 1.0))
        self.assertFalse(p3.is_section_change(6.0, SECTIONS, 1.0))
        self.assertFalse(p3.is_section_change(0.2, SECTIONS, 1.0))

    def test_gate_beat_offset_is_to_the_nearest_beat(self) -> None:
        self.assertAlmostEqual(p3.nearest_beat_offset(1.1, [0.0, 0.5, 1.0]), 0.1)


class CameraMotionTest(unittest.TestCase):
    def test_gate_yaw_whip_ignores_the_wrap_and_the_skipped_spin(self) -> None:
        self.assertEqual(p3.yaw_whips([359.0, 1.0, 3.0], 12.0), [])
        self.assertEqual(p3.yaw_whips([0.0, 30.0, 31.0], 12.0), [(1, 30.0)])
        self.assertEqual(p3.yaw_whips([0.0, 30.0, 31.0], 12.0, [(1, 1)]), [])

    def test_gate_yaw_per_frame_follows_the_keyframes(self) -> None:
        keys = [{"t": 0.0, "yaw": 0, "fov": 100}, {"t": 1.0, "yaw": 10, "fov": 100}]
        yaws = p3.yaw_per_frame(segment(keys, duration=1.0), 10)
        self.assertEqual(len(yaws), 10)
        self.assertAlmostEqual(yaws[5], 5.0)

    def test_gate_share_of_visible_frames(self) -> None:
        self.assertEqual(p3.share([True, True, False, True]), 0.75)
        self.assertEqual(p3.share([]), 0.0)


class CoverageTest(unittest.TestCase):
    def test_gate_repeated_source_is_the_used_time_beyond_the_unique_time(self) -> None:
        plan = {
            "segments": [
                {"assetId": "a", "srcIn": 0.0, "srcOut": 2.0},
                {"assetId": "a", "srcIn": 1.0, "srcOut": 3.0},
                {"assetId": "b", "srcIn": 0.0, "srcOut": 1.0},
            ]
        }
        report = p3.source_coverage(plan, {"a": 10.0, "b": 4.0})
        self.assertEqual(report["a"]["uniqueSec"], 3.0)
        self.assertEqual(report["total"]["usedSec"], 5.0)
        self.assertEqual(report["total"]["uniqueSec"], 4.0)
        self.assertEqual(report["total"]["repeatedShare"], 0.2)

    def test_gate_expected_size_for_both_ratios_at_4k(self) -> None:
        self.assertEqual(p3.expected_size("16:9"), (3840, 2160))
        self.assertEqual(p3.expected_size("9:16"), (2160, 3840))


if __name__ == "__main__":
    unittest.main()
