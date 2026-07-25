#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import subprocess
import sys
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


if __name__ == "__main__":
    unittest.main()
