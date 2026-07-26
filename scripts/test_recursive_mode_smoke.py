#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).with_name("test-recursive-mode-smoke.py")
SPEC = importlib.util.spec_from_file_location("recursive_mode_smoke", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load smoke harness: {SCRIPT_PATH}")
SMOKE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = SMOKE
SPEC.loader.exec_module(SMOKE)


class SmokeHarnessTests(unittest.TestCase):
    def test_powershell_wrappers_receive_the_selected_python_executable(self) -> None:
        harness = SMOKE.SmokeHarness.__new__(SMOKE.SmokeHarness)
        harness.repo_root = Path("/fixture/repo")
        harness.temp_dir = Path("/fixture/smoke-temp")
        harness.command_timeout = 5
        harness.python_exe = Path("/opt/recursive/python3")
        harness.powershell_exe = Path("/usr/bin/pwsh")

        completed = subprocess.CompletedProcess(
            args=[str(harness.powershell_exe)],
            returncode=0,
            stdout="",
            stderr="",
        )
        with mock.patch.object(SMOKE.subprocess, "run", return_value=completed) as run:
            harness.run_command(
                [str(harness.powershell_exe), "-File", "recursive-status.ps1"],
                cwd=harness.repo_root,
            )

        environment = run.call_args.kwargs["env"]
        self.assertEqual(environment.get("PYTHON"), str(harness.python_exe))
        self.assertEqual(
            environment.get("XDG_CACHE_HOME"),
            str(harness.temp_dir / "powershell-cache"),
        )
        self.assertFalse(
            Path(environment["XDG_CACHE_HOME"]).is_relative_to(harness.repo_root),
        )

    def test_post_bootstrap_commands_use_installed_runtime(self) -> None:
        harness = SMOKE.SmokeHarness.__new__(SMOKE.SmokeHarness)
        harness.python_exe = Path("/opt/recursive/python3")
        harness.repo_root = Path("/fixture/repo")
        harness.runtime_dir = harness.repo_root / ".recursive" / "scripts"

        command = harness.python_command("recursive-status.py", "--repo-root", str(harness.repo_root))

        self.assertEqual(
            command,
            [
                str(harness.python_exe),
                str(harness.repo_root / ".recursive" / "scripts" / "recursive-status.py"),
                "--repo-root",
                str(harness.repo_root),
            ],
        )

    def test_missing_or_corrupt_installed_dependency_fails_without_source_fallback(self) -> None:
        source_runtime = SCRIPT_PATH.parent.parent / "skills" / "recursive-mode" / "scripts"
        with tempfile.TemporaryDirectory(prefix="recursive-smoke-installed-runtime-") as temp_dir:
            repo_root = Path(temp_dir) / "repo"
            installed_runtime = repo_root / ".recursive" / "scripts"
            installed_runtime.mkdir(parents=True)
            shutil.copy2(source_runtime / "recursive-status.py", installed_runtime / "recursive-status.py")

            harness = SMOKE.SmokeHarness.__new__(SMOKE.SmokeHarness)
            harness.repo_root = repo_root
            harness.command_timeout = 10
            harness.python_exe = Path(sys.executable).resolve()
            harness.powershell_exe = None
            harness.runtime_dir = installed_runtime

            with self.subTest(sabotage="missing dependency"):
                with self.assertRaisesRegex(SMOKE.SmokeError, "recursive_phase_rules"):
                    harness.run_command(harness.python_command("recursive-status.py", "--help"))

            (installed_runtime / "recursive_phase_rules.py").write_text(
                "def broken(:\n",
                encoding="utf-8",
                newline="\n",
            )
            with self.subTest(sabotage="corrupt dependency"):
                with self.assertRaisesRegex(SMOKE.SmokeError, "SyntaxError"):
                    harness.run_command(harness.python_command("recursive-status.py", "--help"))


if __name__ == "__main__":
    unittest.main()
