"""Tests for the Phase 2 gate script. Spec: specs/10-roadmap.md#phase-2--ai-director [T-411]

Run with: python -m unittest discover -s scripts -p "test_*.py"
"""

from __future__ import annotations

import unittest

import phase1_gate as gate
import phase2_gate as p2

SECTIONS = [
    {"kind": "VERSE", "start": 0.0, "end": 4.0},
    {"kind": "DROP", "start": 4.0, "end": 8.0},
]
RAMP = {
    "curve": [[0.0, 2.5], [0.4, 2.5], [0.5, 0.25], [0.8, 0.25], [1.0, 1.0]],
    "interpolate": "rife",
}
FLAT = {"curve": [[0.0, 1.0], [1.0, 1.0]], "interpolate": "none"}


def segment(name: str, asset: str, at: float, speed: dict, effects: list | None = None) -> dict:
    return {
        "id": name, "assetId": asset, "srcIn": 1.0, "srcOut": 2.0, "at": at, "duration": 1.0,
        "speed": speed, "effects": effects or [],
    }  # fmt: skip


def plan(segments: list, style: str = "velocity", log: list | None = None) -> dict:
    return {
        "style": style, "segments": segments, "log": log or [],
        "output": {"fps": 10}, "music": {"start": 0.0},
    }  # fmt: skip


SHOTS = {
    "a": [{"start": 0.0, "end": 3.0, "tags": ["sports car", "road"]}],
    "b": [{"start": 0.0, "end": 3.0, "tags": ["carpet"]}],
}


def result(label: str, facts: p2.PlanFacts | None, **fields) -> p2.RunResult:
    return p2.RunResult(label, None, "DONE", 1.0, facts=facts, **fields)


def facts(**fields) -> p2.PlanFacts:
    base = dict(
        style="velocity", segments=10, car_segments=2, ramps=0, ramps_in_drop=0,
        drop_segments=4, shakes=3, flashes=1, zooms=1, fallback_note=False,
    )  # fmt: skip
    return p2.PlanFacts(**{**base, **fields})


class TagsTest(unittest.TestCase):
    def test_gate_car_matches_whole_words_only(self) -> None:
        self.assertTrue(p2.tag_matches(["sports car"], "car"))
        self.assertTrue(p2.tag_matches(["cars"], "car"))
        self.assertFalse(p2.tag_matches(["carpet"], "car"))

    def test_gate_segment_takes_the_shot_it_overlaps_most(self) -> None:
        shots = [
            {"start": 0.0, "end": 1.2, "tags": ["x"]},
            {"start": 1.2, "end": 5.0, "tags": ["y"]},
        ]
        self.assertEqual(p2.shot_tags({"srcIn": 1.0, "srcOut": 2.0}, shots), ["y"])
        self.assertEqual(p2.shot_tags({"srcIn": 9.0, "srcOut": 10.0}, shots), [])


class FactsTest(unittest.TestCase):
    def test_gate_facts_count_car_ramps_in_drop_and_shakes(self) -> None:
        shake = [{"type": "shake"}]
        document = plan(
            [
                segment("s1", "a", 0.0, FLAT, shake),
                segment("s2", "b", 2.0, FLAT),
                segment("s3", "a", 4.0, RAMP, shake),
                segment("s4", "a", 6.0, RAMP),
            ],
            log=[p2.FALLBACK_NOTE],
        )
        found = p2.plan_facts(document, SHOTS, SECTIONS)
        self.assertEqual((found.segments, found.car_segments), (4, 3))
        self.assertEqual((found.ramps, found.ramps_in_drop, found.drop_segments), (2, 2, 2))
        self.assertEqual(found.shakes, 2)
        self.assertTrue(found.fallback_note)

    def test_gate_ramp_outside_the_drop_is_not_in_the_drop(self) -> None:
        found = p2.plan_facts(plan([segment("s1", "a", 0.0, RAMP)]), SHOTS, SECTIONS)
        self.assertEqual((found.ramps, found.ramps_in_drop), (1, 0))

    def test_gate_director_source_reads_the_worker_log(self) -> None:
        self.assertEqual(p2.director_source('{"event": "director.decided"}'), "llm")
        self.assertEqual(p2.director_source("director.fallback director.decided"), "fallback")
        self.assertEqual(p2.director_source(""), "none")


class FileCheckTest(unittest.TestCase):
    def test_gate_slow_hold_moves_less_than_the_fast_start(self) -> None:
        document = plan([segment("s1", "a", 0.0, RAMP)])
        values = [0.5] * 4 + [0.1] * 6
        scores = [gate.FrameScore(i / 10, value) for i, value in enumerate(values)]
        (check,) = p2.ramp_checks(document, scores)
        self.assertTrue(check.slower)
        flipped = [gate.FrameScore(i / 10, 0.1 if i < 4 else 0.5) for i in range(10)]
        self.assertFalse(p2.ramp_checks(document, flipped)[0].slower)

    def test_gate_unramped_segments_are_not_checked(self) -> None:
        self.assertEqual(p2.ramp_checks(plan([segment("s1", "a", 0.0, FLAT)]), []), [])


class VerdictTest(unittest.TestCase):
    def test_gate_car_needs_a_rise_from_the_llm(self) -> None:
        base = result("baseline", facts(car_segments=2))
        rose = result("c", facts(car_segments=7), director="llm")
        self.assertTrue(p2.judge_car(base, rose)["passed"])
        self.assertFalse(
            p2.judge_car(base, result("c", facts(car_segments=7), director="fallback"))["passed"]
        )
        self.assertFalse(
            p2.judge_car(base, result("c", facts(car_segments=2), director="llm"))["passed"]
        )

    def test_gate_slowmo_needs_ramps_in_the_drop_and_in_the_file(self) -> None:
        base = result("baseline", facts())
        good = result(
            "s", facts(ramps=2, ramps_in_drop=2), director="llm",
            ramp_checks=[p2.RampCheck("s1", 0.4, 0.1)],
        )  # fmt: skip
        self.assertTrue(p2.judge_slowmo(base, good)["passed"])
        none = result("s", facts(), director="llm")
        self.assertFalse(p2.judge_slowmo(base, none)["passed"])
        flat = result(
            "s", facts(ramps=2, ramps_in_drop=2), director="llm",
            ramp_checks=[p2.RampCheck("s1", 0.1, 0.4)],
        )  # fmt: skip
        self.assertFalse(p2.judge_slowmo(base, flat)["passed"])

    def test_gate_cinematic_needs_the_style_and_no_shakes(self) -> None:
        base = result("baseline", facts())
        good = result("c", facts(style="cinematic", shakes=0), director="llm")
        self.assertTrue(p2.judge_cinematic(base, good)["passed"])
        shaky = result("c", facts(style="cinematic", shakes=1), director="llm")
        self.assertFalse(p2.judge_cinematic(base, shaky)["passed"])

    def test_gate_cinematic_with_nothing_changed_is_not_a_pass(self) -> None:
        base = result("baseline", facts(style="cinematic", shakes=0))
        same = result("c", facts(style="cinematic", shakes=0), director="llm")
        self.assertFalse(p2.judge_cinematic(base, same)["passed"])
        fewer = result("baseline", facts(style="cinematic", shakes=4))
        self.assertTrue(p2.judge_cinematic(fewer, same)["passed"])

    def test_gate_down_needs_done_and_the_fallback_note(self) -> None:
        good = result(
            "d", facts(fallback_note=True, style="cinematic", shakes=0), director="fallback"
        )
        self.assertTrue(p2.judge_down(good)["passed"])
        self.assertFalse(p2.judge_down(result("d", facts(), director="fallback"))["passed"])
        failed = p2.RunResult("d", None, "FAILED", 1.0)
        self.assertFalse(p2.judge_down(failed)["passed"])

    def test_gate_table_has_a_row_per_run(self) -> None:
        table = p2.report_table(
            [result("baseline", facts()), p2.RunResult("x", None, "FAILED", 1.0)]
        )
        self.assertEqual(len(table.splitlines()), 4)


if __name__ == "__main__":
    unittest.main()
