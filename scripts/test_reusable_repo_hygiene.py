#!/usr/bin/env python3
"""Behavioral tests for reusable-repository hygiene checks."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/recursive-mode/scripts/check-reusable-repo-hygiene.py"
POWERSHELL = ROOT / "skills/recursive-mode/scripts/check-reusable-repo-hygiene.ps1"
PACKAGED_WORKFLOW = ROOT / "skills/recursive-mode/references/bootstrap/RECURSIVE.md"


class ReusableRepoHygieneTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary.name)
        self.write(
            self.repo / ".recursive/RECURSIVE.md",
            PACKAGED_WORKFLOW.read_text(encoding="utf-8"),
        )
        self.write(self.repo / ".recursive/run/.gitkeep", "")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")

    def run_check(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--repo-root", str(self.repo), *args],
            text=True,
            capture_output=True,
            check=False,
        )

    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=self.repo,
            text=True,
            capture_output=True,
            check=True,
        )

    def test_clean_packaged_repository_passes(self) -> None:
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Reusable-repo hygiene check passed", result.stdout)
        self.assertIn("run contamination: 0", result.stdout)
        self.assertIn("generated residue: 0", result.stdout)
        self.assertIn("snapshot cleanliness: 0", result.stdout)

    def test_run_cache_and_temp_path_residue_fail_by_category(self) -> None:
        run_reference = PurePosixPath(".recursive", "run", "2099-01-01-example")
        temp_report = PurePosixPath("/", "tmp", "session", "report.md")
        self.write(self.repo / run_reference / "ledger.md", "open\n")
        self.write(self.repo / "src/__pycache__/module.pyc", "cache\n")
        self.write(self.repo / "notes.md", f"artifact: {temp_report}\n")

        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("committed run residue", result.stdout)
        self.assertIn("Generated local residue", result.stdout)
        self.assertIn("temp-path residue", result.stdout)
        self.assertRegex(result.stdout, r"run contamination: [1-9]\d*")
        self.assertRegex(result.stdout, r"generated residue: [1-9]\d*")

    def test_concrete_run_reference_fails_without_matching_run_artifact(self) -> None:
        run_reference = PurePosixPath(".recursive", "run", "2099-01-01-example")
        self.write(
            self.repo / "notes.md",
            f"See {run_reference} for evidence.\n",
        )

        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("contains a concrete recursive run reference", result.stdout)

    def test_packaged_snapshot_drift_fails(self) -> None:
        self.write(self.repo / ".recursive/RECURSIVE.md", "# Stale workflow\n")

        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match .recursive/RECURSIVE.md", result.stdout)
        self.assertRegex(result.stdout, r"snapshot cleanliness: [1-9]\d*")

    def test_require_clean_git_rejects_a_dirty_tree(self) -> None:
        self.git("init", "-q")
        self.git("config", "user.email", "fixture@example.com")
        self.git("config", "user.name", "Fixture")
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        self.write(self.repo / "dirty.md", "dirty\n")

        result = self.run_check("--require-clean-git")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Git worktree is not clean", result.stdout)

    def test_powershell_wrapper_forwards_both_options(self) -> None:
        wrapper = POWERSHELL.read_text(encoding="utf-8")
        self.assertIn('"check-reusable-repo-hygiene.py"', wrapper)
        self.assertIn('"--repo-root"', wrapper)
        self.assertIn('"--require-clean-git"', wrapper)
        self.assertIn("exit $LASTEXITCODE", wrapper)


if __name__ == "__main__":
    unittest.main(verbosity=2)
