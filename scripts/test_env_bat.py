"""Tests for env.bat tool discovery. Spec: specs/09-local-setup.md#setupbat-run-once [BUG-001]

Run with: python -m unittest discover -s scripts -p "test_*.py"
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ENV_BAT = Path(__file__).resolve().parent / "env.bat"


@unittest.skipUnless(os.name == "nt", "env.bat only runs on Windows")
class EnvBatTests(unittest.TestCase):
    def path_entries_with(self, local_app_data: Path) -> list[str]:
        result = subprocess.run(
            ["cmd", "/c", "call", str(ENV_BAT), "&&", "set", "PATH"],
            env={**os.environ, "LOCALAPPDATA": str(local_app_data)},
            capture_output=True,
            text=True,
            check=True,
        )
        line = next(row for row in result.stdout.splitlines() if row.upper().startswith("PATH="))
        return line.partition("=")[2].split(";")

    def test_bug_001_finds_ffmpeg_in_the_winget_package_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = "Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
            bin_dir = root / package / "ffmpeg-9.0.2-full_build" / "bin"
            bin_dir.mkdir(parents=True)

            self.assertIn(str(bin_dir), self.path_entries_with(root))

    def test_bug_001_finds_ollama_in_its_user_install_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ollama_dir = root / "Programs" / "Ollama"
            ollama_dir.mkdir(parents=True)

            self.assertIn(str(ollama_dir), self.path_entries_with(root))

    def test_works_when_nothing_is_installed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            entries = self.path_entries_with(Path(temp))

        self.assertTrue(any(entry.endswith(r"tools\uv") for entry in entries))


if __name__ == "__main__":
    unittest.main()
