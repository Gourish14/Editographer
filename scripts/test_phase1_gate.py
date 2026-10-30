"""Tests for the Phase 1 gate script. Spec: specs/10-roadmap.md#phase-1--core-engine [T-118]

Run with: python -m unittest discover -s scripts -p "test_*.py"
"""

from __future__ import annotations

import base64
import unittest
from pathlib import Path
from unittest import mock

import phase1_gate as gate
import phase1_media as media


def plan() -> dict:
    return {
        "output": {"fps": 30},
        "music": {"start": 10.0},
        "segments": [
            {"at": 10.0, "duration": 0.5, "effects": []},
            {"at": 10.5, "duration": 1.0, "effects": [{"type": "shake"}]},
            {"at": 11.5, "duration": 0.04, "effects": []},
        ],
    }


def scores(values: list[float]) -> list[gate.FrameScore]:
    return [gate.FrameScore(index / 30, value) for index, value in enumerate(values)]


def finished(ratio: str, seconds: float, label: str = "edit") -> gate.RenderResult:
    check = gate.BeatCheck(10, 5.0, 33.3, 1800, 1800, True)
    return gate.RenderResult(
        label, ratio, "DONE", seconds, beat_check=check, worst_measured_frames=0
    )


class ParsingTests(unittest.TestCase):
    def test_tus_metadata_is_base64_pairs(self) -> None:
        header = gate.tus_metadata("abc", "clip one.mp4")

        project, filename = header.split(",")
        self.assertEqual(project.split(" ")[0], "projectId")
        self.assertEqual(base64.b64decode(filename.split(" ")[1]), b"clip one.mp4")

    def test_beat_check_output_is_read(self) -> None:
        output = (
            "cuts: 140, worst offset from the grid: 12.5 ms\n"
            "one frame is 33.3 ms; frames expected 1800, got 1799\nFAIL\n"
        )

        check = gate.parse_beat_check(output, 1)

        self.assertEqual((check.cuts, check.worst_ms), (140, 12.5))
        self.assertEqual((check.frames_expected, check.frames_actual), (1800, 1799))
        self.assertFalse(check.passed)

    def test_unexpected_beat_check_output_stops_the_gate(self) -> None:
        with self.assertRaises(gate.GateError):
            gate.parse_beat_check("Traceback", 1)

    def test_scene_scores_pair_each_frame_with_its_score(self) -> None:
        output = (
            "frame:0    pts:0       pts_time:0\nlavfi.scene_score=0.000000\n"
            "frame:1    pts:512     pts_time:0.0333\nlavfi.scene_score=0.250000\n"
        )

        parsed = gate.parse_scene_scores(output)

        self.assertEqual(parsed, [gate.FrameScore(0.0, 0.0), gate.FrameScore(0.0333, 0.25)])


class CutTests(unittest.TestCase):
    def test_the_first_segment_is_not_a_cut(self) -> None:
        self.assertEqual(gate.planned_cut_frames(plan()), [15, 45])

    def test_a_cut_on_its_frame_has_no_offset(self) -> None:
        values = [0.0] * 20
        values[10] = 0.5

        self.assertEqual(gate.cut_offsets(scores(values), [10]), [0])

    def test_a_late_cut_shows_its_offset(self) -> None:
        values = [0.0] * 20
        values[12] = 0.5

        self.assertEqual(gate.cut_offsets(scores(values), [10]), [2])

    def test_a_flash_ending_after_the_cut_does_not_move_it(self) -> None:
        values = [0.0] * 20
        values[10] = 0.4
        values[13] = 0.7

        self.assertEqual(gate.cut_offsets(scores(values), [10]), [0])

    def test_a_cut_too_faint_to_see_is_left_out(self) -> None:
        self.assertEqual(gate.cut_offsets(scores([0.001] * 20), [10]), [])

    def test_frame_times_are_compared_with_their_index(self) -> None:
        drifted = [gate.FrameScore(0.0, 0), gate.FrameScore(0.1, 0)]

        self.assertAlmostEqual(gate.worst_pts_drift(drifted, 30), 0.1 - 1 / 30)


class StressPlanTests(unittest.TestCase):
    def test_every_segment_gets_shake_zoom_and_flash(self) -> None:
        saturated = gate.saturated_plan(plan())

        for segment in saturated["segments"]:
            kinds = {effect["type"] for effect in segment["effects"]}
            self.assertEqual(kinds, {"flash", "zoomPunch", "shake"})

    def test_shake_and_zoom_last_the_whole_segment(self) -> None:
        segment = gate.saturated_plan(plan())["segments"][1]

        lengths = {e["type"]: e["duration"] for e in segment["effects"]}
        self.assertEqual(lengths["shake"], 1.0)
        self.assertEqual(lengths["zoomPunch"], 1.0)

    def test_a_flash_never_runs_past_a_short_segment(self) -> None:
        segment = gate.saturated_plan(plan())["segments"][2]

        flash = next(e for e in segment["effects"] if e["type"] == "flash")
        self.assertEqual(flash["duration"], 0.04)

    def test_the_source_plan_is_left_alone(self) -> None:
        source = plan()

        gate.saturated_plan(source)

        self.assertEqual(source, plan())


class CoverageTests(unittest.TestCase):
    def test_effects_are_counted_per_section(self) -> None:
        sections = [
            {"kind": "BUILD", "start": 0.0, "end": 10.5},
            {"kind": "DROP", "start": 10.5, "end": 20.0},
        ]

        coverage = gate.effect_coverage(plan(), sections)

        self.assertEqual(coverage["build"], {"segments": 1})
        self.assertEqual(coverage["drop"], {"segments": 2, "shake": 1})

    def test_beat_accuracy_ignores_beats_past_the_song(self) -> None:
        accuracy = gate.beat_accuracy([0.02, 0.52, 9.0], [0.0, 0.5])

        self.assertEqual(accuracy["foundBeats"], 2)
        self.assertEqual(accuracy["meanErrorMs"], 20.0)
        self.assertEqual(accuracy["worstErrorMs"], 20.0)


class StoredAssetTests(unittest.TestCase):
    def test_paths_follow_the_backend_upload_layout(self) -> None:
        asset = {"id": "a1", "type": "VIDEO", "filename": "clip.mp4"}

        stored = gate.stored_assets([asset], "p1")

        self.assertEqual(stored[0]["path"], "uploads/p1/a1.mp4")


class VerdictTests(unittest.TestCase):
    def test_the_slowest_ratio_is_named(self) -> None:
        verdict = gate.judge([finished("16:9", 300), finished("1:1", 600)], 15, False)

        self.assertEqual(verdict["slowestRatio"], "1:1")
        self.assertTrue(verdict["passed"])

    def test_a_slow_edit_fails_on_a_free_machine(self) -> None:
        verdict = gate.judge([finished("1:1", 1000)], 15, False)

        self.assertFalse(verdict["timePassed"])
        self.assertFalse(verdict["passed"])

    def test_a_slow_edit_is_only_reported_on_a_shared_machine(self) -> None:
        verdict = gate.judge([finished("1:1", 1000)], 15, True)

        self.assertFalse(verdict["timePassed"])
        self.assertFalse(verdict["timeJudged"])
        self.assertTrue(verdict["passed"])

    def test_a_shared_machine_never_excuses_a_cut_off_the_grid(self) -> None:
        late = finished("1:1", 100)
        late.worst_measured_frames = 2

        self.assertFalse(gate.judge([late], 15, True)["passed"])

    def test_a_slow_stress_render_is_not_the_edit_time(self) -> None:
        results = [finished("1:1", 300), finished("1:1", 5000, "stress")]

        self.assertEqual(gate.judge(results, 15, False)["slowestSeconds"], 300)

    def test_a_failed_render_fails_the_gate(self) -> None:
        failed = gate.RenderResult("edit", "1:1", "FAILED", 10.0, error="RENDER_FAILED")

        self.assertFalse(gate.judge([finished("16:9", 10), failed], 15, True)["passed"])

    def test_no_renders_is_no_pass(self) -> None:
        self.assertFalse(gate.judge([], 15, True)["passed"])


class ServicesTests(unittest.TestCase):
    def test_only_started_pids_are_killed_with_their_trees(self) -> None:
        services = gate.Services(Path("."))
        running = mock.Mock(pid=4321)
        running.poll.return_value = None
        services._started.append(("worker", running))

        with mock.patch.object(gate.subprocess, "run") as run:
            services.stop_all()

        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], ["taskkill", "/PID", "4321", "/T", "/F"])

    def test_a_process_that_already_ended_is_not_killed(self) -> None:
        services = gate.Services(Path("."))
        ended = mock.Mock(pid=4321)
        ended.poll.return_value = 0
        services._started.append(("worker", ended))

        with mock.patch.object(gate.subprocess, "run") as run:
            services.stop_all()

        run.assert_not_called()

    def test_stopping_twice_kills_once(self) -> None:
        services = gate.Services(Path("."))
        running = mock.Mock(pid=1)
        running.poll.return_value = None
        services._started.append(("worker", running))

        with mock.patch.object(gate.subprocess, "run") as run:
            services.stop_all()
            services.stop_all()

        run.assert_called_once()

    def test_a_dead_service_stops_the_gate(self) -> None:
        services = gate.Services(Path("."))
        ended = mock.Mock(pid=1, returncode=1)
        ended.poll.return_value = 1
        services._started.append(("backend", ended))

        with self.assertRaises(gate.GateError):
            services.require_running()


class EnvironmentTests(unittest.TestCase):
    def test_services_get_private_folders_ports_and_token(self) -> None:
        env = gate.service_environment({"PATH": "x"}, Path("media/phase1_gate/runs/1"), 18080, 18090)

        self.assertEqual(env["PATH"], "x")
        self.assertEqual(env["MEDIA_DIR"], "media/phase1_gate/runs/1/media")
        self.assertEqual(env["DATA_DIR"], "media/phase1_gate/runs/1/data")
        self.assertEqual(env["BACKEND_PORT"], "18080")
        self.assertEqual(env["WORKER_PORT"], "18090")
        self.assertGreaterEqual(len(env["WORKER_TOKEN"]), 32)


class MediaTests(unittest.TestCase):
    def test_there_are_ten_clips_of_at_least_15_seconds(self) -> None:
        specs = media.clip_specs()

        self.assertEqual(len(specs), 10)
        self.assertTrue(all(spec.seconds >= 15 for spec in specs))

    def test_at_least_two_clips_have_a_hard_cut(self) -> None:
        cuts = [spec for spec in media.clip_specs() if spec.hard_cut_at is not None]

        self.assertGreaterEqual(len(cuts), 2)

    def test_clips_are_1080p_or_4k(self) -> None:
        for spec in media.clip_specs():
            self.assertIn(max(spec.width, spec.height), (1920, 3840), spec.name)

    def test_some_clips_have_moving_shapes(self) -> None:
        shapes = [spec for spec in media.clip_specs() if "overlay=" in spec.graph]

        self.assertGreaterEqual(len(shapes), 2)

    def test_the_song_is_over_70_seconds_and_has_every_part(self) -> None:
        truth = media.song_truth()

        self.assertGreater(truth["sections"][-1]["end"], 70)
        kinds = {section["kind"] for section in truth["sections"]}
        self.assertLessEqual({"intro", "build", "drop", "break"}, kinds)

    def test_the_beat_does_not_land_on_whole_frames(self) -> None:
        frames = media.beat_seconds() * 30

        self.assertGreater(abs(frames - round(frames)), 0.1)


if __name__ == "__main__":
    unittest.main()
