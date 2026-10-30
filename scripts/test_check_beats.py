"""Tests for the beat checker. Spec: specs/10-roadmap.md#phase-1--core-engine [T-118]

Run with: python -m unittest discover -s scripts -p "test_*.py"
"""

from __future__ import annotations

import unittest

from check_beats import beat_grid, cut_times, distance_to_grid, worst_offset

BEATS = [0.0, 0.5, 1.0, 1.5, 2.0]


def plan(cuts: list[float], start: float = 0.0, fps: int = 30) -> dict:
    return {
        "output": {"fps": fps},
        "music": {"start": start},
        "segments": [{"at": cut} for cut in cuts],
    }


class CheckBeatsTests(unittest.TestCase):
    def test_grid_has_beats_and_midpoints(self) -> None:
        self.assertEqual(beat_grid([0.0, 0.5, 1.0]), [0.0, 0.25, 0.5, 0.75, 1.0])

    def test_distance_is_to_the_nearest_grid_point(self) -> None:
        grid = beat_grid(BEATS)
        self.assertAlmostEqual(distance_to_grid(0.26, grid), 0.01)
        self.assertAlmostEqual(distance_to_grid(0.0, grid), 0.0)
        self.assertAlmostEqual(distance_to_grid(5.0, grid), 3.0)

    def test_cuts_land_on_whole_frames_from_the_edit_start(self) -> None:
        self.assertEqual(cut_times(plan([0.0, 1.5])), [0.0, 1.5])
        self.assertAlmostEqual(cut_times(plan([0.25]))[0], 0.2666667, places=5)

    def test_a_plan_on_the_grid_stays_within_a_frame(self) -> None:
        self.assertLess(worst_offset(plan([0.0, 0.25, 0.5, 1.0, 1.25]), BEATS), 1 / 30)

    def test_a_cut_off_the_beat_is_measured(self) -> None:
        self.assertGreater(worst_offset(plan([0.0, 0.4]), BEATS), 1 / 30)


if __name__ == "__main__":
    unittest.main()
