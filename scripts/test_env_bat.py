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
ROOT = ENV_BAT.parent.parent


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

    def env_after_env_bat(self) -> dict[str, str]:
        result = subprocess.run(
            ["cmd", "/c", "call", str(ENV_BAT), "&&", "set"],
            capture_output=True,
            text=True,
            check=True,
        )
        return dict(row.split("=", 1) for row in result.stdout.splitlines() if "=" in row)

    def test_rule3_ollama_runs_on_its_own_port_and_stores_models_in_the_project(self) -> None:
        env = self.env_after_env_bat()
        port = env["OLLAMA_PORT"]

        self.assertNotEqual("11434", port)
        self.assertEqual(f"127.0.0.1:{port}", env["OLLAMA_HOST"])
        self.assertEqual(f"http://127.0.0.1:{port}", env["OLLAMA_URL"])
        self.assertEqual(str(ROOT / "models" / "ollama"), env["OLLAMA_MODELS"])

    def test_rule3_no_script_or_config_points_at_the_shared_ollama_port(self) -> None:
        for path in [*ROOT.glob("*.bat"), ROOT / "config" / "local.env.example"]:
            text = path.read_text()
            self.assertNotIn("11434", text, path.name)
            self.assertNotIn("OLLAMA_URL=", text.replace("set \"OLLAMA_URL=", ""), path.name)

    def test_rule3_scripts_never_stop_ollama_by_program_name(self) -> None:
        for path in [*ROOT.glob("*.bat"), *(ROOT / "scripts").glob("*.bat")]:
            for line in path.read_text().lower().splitlines():
                if "taskkill" in line:
                    self.assertNotIn("/im", line, path.name)
                    self.assertNotIn("windowtitle", line, path.name)

    def test_rule3_an_old_ollama_url_in_local_env_is_dropped(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "scripts").mkdir()
            (root / "config").mkdir()
            for name in ("env.bat", "drop_stale_ollama_url.bat"):
                (root / "scripts" / name).write_bytes((ROOT / "scripts" / name).read_bytes())
            local = root / "config" / "local.env"
            local.write_bytes(b"WORKER_PORT=8090\r\nOLLAMA_URL=http://127.0.0.1:11434\r\nWORKER_TOKEN=abc\r\n")

            subprocess.run(["cmd", "/c", str(root / "scripts" / "drop_stale_ollama_url.bat")], check=True)

            self.assertEqual(b"WORKER_PORT=8090\r\nWORKER_TOKEN=abc\r\n", local.read_bytes())


if __name__ == "__main__":
    unittest.main()
