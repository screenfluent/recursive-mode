#!/usr/bin/env python3
"""Executable coverage for canonical run IDs across installed runtime commands."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "skills" / "recursive-mode" / "scripts"
EXPECTED_ERROR = "[FAIL] Run ID must be a canonical kebab-case directory name."

COMMANDS = {
    "recursive-lock.py": ["--artifact", "00-requirements.md"],
    "recursive-closeout.py": ["--phase", "04"],
    "recursive-status.py": [],
    "lint-recursive-run.py": [],
    "verify-locks.py": [],
    "recursive-review-ledger.py": ["--phase-artifact", "03.5-code-review.md"],
    "recursive-review-bundle.py": [
        "--phase",
        "03.5 Code Review",
        "--role",
        "code-reviewer",
        "--artifact-path",
        ".recursive/run/real-run/03.5-code-review.md",
        "--pass",
        "0001",
    ],
    "recursive-subagent-action.py": [
        "--subagent-id",
        "fixture-agent",
        "--phase",
        "03.5 Code Review",
        "--purpose",
        "review",
        "--execution-mode",
        "review",
    ],
}

INVALID_RUN_IDS = (
    "../../../outside/escape",
    "Run-Id",
    "run_id",
    "run-id\n",
    " real-run ",
    "   ",
    "",
)


class RecursiveRunIdCommandTests(unittest.TestCase):
    def test_all_run_commands_reject_noncanonical_ids_before_path_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repo_root = Path(temporary_directory)
            (repo_root / ".recursive" / "run").mkdir(parents=True)

            for script_name, extra_arguments in COMMANDS.items():
                for run_id in INVALID_RUN_IDS:
                    with self.subTest(script=script_name, run_id=repr(run_id)):
                        result = subprocess.run(
                            [
                                sys.executable,
                                str(RUNTIME / script_name),
                                "--repo-root",
                                str(repo_root),
                                "--run-id",
                                run_id,
                                *extra_arguments,
                            ],
                            check=False,
                            capture_output=True,
                            text=True,
                        )
                        diagnostics = result.stdout + result.stderr
                        self.assertEqual(result.returncode, 1, diagnostics)
                        self.assertIn(EXPECTED_ERROR, diagnostics)
                        self.assertNotIn("Traceback", diagnostics)


if __name__ == "__main__":
    unittest.main()
