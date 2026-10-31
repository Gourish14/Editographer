"""Tests for the Phase 4 gate script. Spec: specs/10-roadmap.md#phase-4--ultra-quality [T-412]

Run with: python -m unittest discover -s scripts -p "test_*.py"
"""

from __future__ import annotations

import json
import unittest

import phase4_gate as p4


def sample(at: float, temp: float | None = 70.0, throttle: str = "0x1") -> p4.Sample:
    return p4.Sample(at, temp, 40.0, 1500.0, 6000.0, 4000.0, 90.0, 10.0, throttle)


def run(times: list[float], temp: float = 70.0) -> list[p4.Sample]:
    return [sample(at, temp) for at in times]


class SmiParsing(unittest.TestCase):
    def test_a_normal_line_is_read(self) -> None:
        found = p4.parse_smi_line("71, 38.5, 1590, 6001, 4096, 99, 12, 0x0000000000000000", 5.0)
        assert found is not None
        assert found.temp_c == 71 and found.mem_used_mb == 4096 and found.enc_util == 12

    def test_na_fields_become_none_and_a_short_line_is_dropped(self) -> None:
        found = p4.parse_smi_line("71, [N/A], 1590, 6001, 4096, 99, 12, 0x0", 5.0)
        assert found is not None and found.power_w is None
        assert p4.parse_smi_line("71, 38", 5.0) is None


class ThermalLimit(unittest.TestCase):
    def test_gate_c1_every_sample_under_85_passes(self) -> None:
        summary = p4.summarize_thermal(run([0, 5, 10, 15], 84.0))
        assert summary.over_limit == 0 and summary.max_temp_c == 84.0 and summary.passed

    def test_gate_c1_one_sample_at_85_fails(self) -> None:
        samples = run([0, 5, 10]) + [sample(15, 85.0)]
        summary = p4.summarize_thermal(samples)
        assert summary.over_limit == 1 and not summary.passed

    def test_gate_c1_a_gap_longer_than_30_s_fails(self) -> None:
        summary = p4.summarize_thermal(run([0, 5, 10, 41, 46]))
        assert summary.longest_gap_sec == 31 and not summary.passed

    def test_gate_c1_a_gap_of_exactly_30_s_passes(self) -> None:
        assert p4.summarize_thermal(run([0, 30, 60])).passed

    def test_gate_c1_no_samples_is_not_a_pass(self) -> None:
        assert not p4.summarize_thermal([]).passed
        assert not p4.summarize_thermal(run([0])).passed

    def test_time_at_or_above_the_pause_temperature_is_counted(self) -> None:
        samples = [sample(0, 70), sample(5, 83), sample(10, 83), sample(15, 76)]
        assert p4.summarize_thermal(samples).seconds_at_or_above_pause == 10

    def test_throttle_reasons_are_counted(self) -> None:
        samples = [sample(0, throttle="0x1"), sample(5, throttle="0x4"), sample(10, throttle="0x4")]
        assert p4.summarize_thermal(samples).throttle_seen == {"0x1": 1, "0x4": 2}

    def test_the_samples_must_cover_the_render(self) -> None:
        samples = run([0, 5, 10, 15])
        assert p4.covers(samples, 3.0, 12.0)
        assert not p4.covers(samples, -1.0, 12.0)
        assert not p4.covers(samples, 3.0, 20.0)
        assert not p4.covers([], 0.0, 0.0)


class ThermalVerdict(unittest.TestCase):
    def verdict(self, status: str = "DONE", frames: tuple[int, int] = (1800, 1800)) -> dict:
        return p4.thermal_verdict(status, frames, p4.summarize_thermal(run([0, 5, 10])))

    def test_gate_c1_needs_done_and_an_exact_frame_count(self) -> None:
        assert self.verdict()["passed"]
        assert not self.verdict(status="FAILED")["passed"]
        assert not self.verdict(frames=(1799, 1800))["passed"]

    def test_uncovered_samples_fail_the_line(self) -> None:
        summary = p4.summarize_thermal(run([0, 5, 10]))
        assert not p4.thermal_verdict("DONE", (1, 1), summary, covered=False)["passed"]


class Projection(unittest.TestCase):
    def test_the_first_ten_percent_projects_the_whole_render(self) -> None:
        assert p4.projected_total_sec(1000.0, 10) == 10000.0
        assert p4.projected_total_sec(1000.0, 0) is None

    def test_only_more_than_8_hours_is_too_long(self) -> None:
        assert not p4.exceeds_limit(8 * 3600.0)
        assert p4.exceeds_limit(8 * 3600.0 + 1)
        assert not p4.exceeds_limit(None)

    def test_per_frame_cost(self) -> None:
        assert p4.per_frame_ms(3600.0, 1800) == 2000.0
        assert p4.per_frame_ms(10.0, 0) == 0.0


class CoolPauses(unittest.TestCase):
    def lines(self, *events: tuple[str, str]) -> str:
        return (
            "\n".join(json.dumps({"event": event, "ts": ts, "tempC": 84}) for event, ts in events)
            + "\nnot json\n"
        )

    def test_holds_are_summed_from_paused_to_resumed(self) -> None:
        text = self.lines(
            ("cool_mode.paused", "2026-11-01T00:00:00Z"),
            ("cool_mode.resumed", "2026-11-01T00:01:30Z"),
            ("other", "2026-11-01T00:02:00Z"),
            ("cool_mode.paused", "2026-11-01T00:03:00Z"),
            ("cool_mode.resumed", "2026-11-01T00:03:30Z"),
        )
        found = p4.parse_cool_pauses(text)
        assert found == {
            "holds": 2, "holdSeconds": 120.0, "longestHoldSeconds": 90.0, "unfinishedHold": False,
        }  # fmt: skip

    def test_a_render_that_never_paused_has_no_holds(self) -> None:
        assert p4.parse_cool_pauses("")["holds"] == 0

    def test_an_unfinished_hold_is_flagged(self) -> None:
        assert p4.parse_cool_pauses(self.lines(("cool_mode.paused", "2026-11-01T00:00:00Z")))[
            "unfinishedHold"
        ]


class Smoothness(unittest.TestCase):
    STDERR = (
        "frame=  100 fps= 90 q=-0.0 size=N/A time=00:00:03.33 speed=3.0x\r"
        "frame= 1800 fps= 95 q=-0.0 Lsize=N/A time=00:01:00.00 speed=3.17x\n"
    )

    def test_the_last_stats_line_is_read(self) -> None:
        assert p4.parse_decode_speed(self.STDERR) == {"frames": 1800, "fps": 95.0, "speed": 3.17}

    def test_no_stats_line_gives_none(self) -> None:
        assert p4.parse_decode_speed("boom")["speed"] is None

    def test_decode_must_be_real_time_with_every_frame(self) -> None:
        good = {"exitCode": 0, "frames": 1800, "speed": 1.2}
        assert p4.judge_decode(good, 1800)
        assert not p4.judge_decode({**good, "speed": 0.9}, 1800)
        assert not p4.judge_decode({**good, "frames": 1799}, 1800)
        assert not p4.judge_decode({**good, "exitCode": 1}, 1800)

    def test_playback_must_end_with_no_error_and_few_drops(self) -> None:
        good = {"ended": True, "error": None, "totalFrames": 1800, "droppedFrames": 18}
        assert p4.judge_playback(good, 1800)
        assert not p4.judge_playback({**good, "droppedFrames": 19}, 1800)
        assert not p4.judge_playback({**good, "ended": False}, 1800)
        assert not p4.judge_playback({**good, "error": "4: unsupported"}, 1800)
        assert not p4.judge_playback({**good, "totalFrames": 1700}, 1800)

    def test_the_line_needs_a_decoder_and_every_page_to_play(self) -> None:
        decode = {"d3d11va": {"exitCode": 0, "frames": 10, "speed": 2.0}}
        page = {"ended": True, "error": None, "totalFrames": 10, "droppedFrames": 0}
        assert p4.smooth_verdict(decode, {"a": page, "b": page}, 10)["passed"]
        assert not p4.smooth_verdict(decode, {"a": page, "b": {**page, "ended": False}}, 10)[
            "passed"
        ]
        assert not p4.smooth_verdict(decode, {}, 10)["passed"]


if __name__ == "__main__":
    unittest.main()
