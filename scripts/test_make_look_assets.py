"""Tests for the LUT and SFX maker. Spec: specs/09-local-setup.md#setupbat-run-once [T-303]

Run with: python -m unittest discover -s scripts -p "test_*.py"
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import make_look_assets
from make_look_assets import DJI_LUT, GENERIC_LOG_LUT, STYLE_LOOKS, cube_text, write_luts


class CubeFiles(unittest.TestCase):
    def test_a_cube_has_one_line_per_grid_point_with_red_changing_fastest(self) -> None:
        text = cube_text("plain", lambda red, green, blue: (red, green, blue), size=2)

        rows = [line for line in text.splitlines() if line[0].isdigit()]
        self.assertEqual(8, len(rows))
        self.assertEqual("1.000000 0.000000 0.000000", rows[1])
        self.assertEqual("0.000000 0.000000 1.000000", rows[4])

    def test_values_stay_between_zero_and_one(self) -> None:
        text = cube_text("hot", lambda red, green, blue: (2.0, -1.0, blue), size=2)

        self.assertIn("1.000000 0.000000 0.000000", text)

    def test_every_style_and_the_fallback_are_written_and_none_claims_to_be_dji(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            write_luts(Path(folder))
            names = {path.name for path in Path(folder).iterdir()}
            header = (Path(folder) / GENERIC_LOG_LUT).read_text(encoding="ascii")[:200]

        self.assertEqual({f"{name}.cube" for name in STYLE_LOOKS} | {GENERIC_LOG_LUT}, names)
        self.assertIn("Not a DJI LUT", header)

    def test_teal_orange_warms_highlights_and_cools_shadows(self) -> None:
        bright = make_look_assets.teal_orange(0.8, 0.8, 0.8)
        dark = make_look_assets.teal_orange(0.2, 0.2, 0.2)

        self.assertGreater(bright[0], bright[2])
        self.assertLess(dark[0], dark[2])


class DjiLut(unittest.TestCase):
    def test_the_dji_file_comes_from_djis_server_with_a_full_checksum(self) -> None:
        self.assertTrue(DJI_LUT.url.startswith("https://terra-1-g.djicdn.com/"))
        self.assertEqual(64, len(DJI_LUT.sha256))


if __name__ == "__main__":
    unittest.main()
