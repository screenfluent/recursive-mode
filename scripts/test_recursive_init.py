#!/usr/bin/env python3

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "skills" / "recursive-mode" / "scripts"
RECURSIVE_INIT = RUNTIME / "recursive-init.py"


class RecursiveInitForceGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        if shutil.which("git") is None:
            self.skipTest("git is required for recursive-init tests")
        self.temp_dir = Path(tempfile.mkdtemp(prefix="recursive-init-test-"))
        self.repo_root = self.temp_dir / "repo"
        self.repo_root.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo_root)], check=True)
        subprocess.run(["git", "-C", str(self.repo_root), "config", "user.name", "Recursive Init Test"], check=True)
        subprocess.run(
            ["git", "-C", str(self.repo_root), "config", "user.email", "recursive-init@example.invalid"],
            check=True,
        )
        (self.repo_root / "README.md").write_text("# Fixture\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.repo_root), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(self.repo_root), "commit", "-q", "-m", "fixture"], check=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def run_init(self, run_id: str = "guard-fixture", *, force: bool = True) -> subprocess.CompletedProcess[str]:
        command = [
            sys.executable,
            str(RECURSIVE_INIT),
            "--repo-root",
            str(self.repo_root),
            "--run-id",
            run_id,
        ]
        if force:
            command.append("--force")
        return subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
        )

    def write_phase_zero(self, status: str, marker: str) -> tuple[Path, Path]:
        run_dir = self.repo_root / ".recursive" / "run" / "guard-fixture"
        run_dir.mkdir(parents=True, exist_ok=True)
        requirements = run_dir / "00-requirements.md"
        worktree = run_dir / "00-worktree.md"
        requirements.write_text(f"Status: `{status}`\n{marker}\n", encoding="utf-8")
        worktree.write_text(f"Status: `{status}`\n{marker}\n", encoding="utf-8")
        return requirements, worktree

    def test_force_refuses_locked_artifacts_without_changing_bytes(self) -> None:
        requirements, worktree = self.write_phase_zero("LOCKED", "locked-history-must-survive")
        before = {path: path.read_bytes() for path in (requirements, worktree)}

        result = self.run_init()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("--force may replace only DRAFT scaffolds", result.stdout)
        self.assertIn("recursive-lock --reopen", result.stdout)
        self.assertEqual(before, {path: path.read_bytes() for path in (requirements, worktree)})

    def test_force_refuses_non_draft_artifacts_without_changing_bytes(self) -> None:
        requirements, worktree = self.write_phase_zero("UNKNOWN", "unknown-status-must-survive")
        before = {path: path.read_bytes() for path in (requirements, worktree)}

        result = self.run_init()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("has Status: UNKNOWN", result.stdout)
        self.assertEqual(before, {path: path.read_bytes() for path in (requirements, worktree)})

    def test_force_refuses_duplicate_status_fields_without_changing_bytes(self) -> None:
        requirements, worktree = self.write_phase_zero("DRAFT", "duplicate-status-must-survive")
        requirements.write_text(
            "Status: `DRAFT`\nStatus: `LOCKED`\nduplicate-status-must-survive\n",
            encoding="utf-8",
        )
        before = {path: path.read_bytes() for path in (requirements, worktree)}

        result = self.run_init()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("must contain exactly one Status field", result.stdout)
        self.assertEqual(before, {path: path.read_bytes() for path in (requirements, worktree)})

    def test_force_refuses_symlinked_artifact_without_changing_any_target(self) -> None:
        requirements, worktree = self.write_phase_zero("DRAFT", "regular-draft-must-survive")
        external = self.temp_dir / "external.md"
        external.write_text("Status: `DRAFT`\nexternal-target-must-survive\n", encoding="utf-8")
        requirements.unlink()
        try:
            requirements.symlink_to(external)
        except OSError as exc:
            self.skipTest(f"symlink creation is unavailable: {exc}")
        before_external = external.read_bytes()
        before_worktree = worktree.read_bytes()

        result = self.run_init()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("must be a regular file and cannot be a symlink or reparse point", result.stdout)
        self.assertTrue(requirements.is_symlink())
        self.assertEqual(before_external, external.read_bytes())
        self.assertEqual(before_worktree, worktree.read_bytes())

    def test_force_refuses_hardlinked_artifact_without_changing_shared_inode(self) -> None:
        run_dir = self.repo_root / ".recursive" / "run" / "guard-fixture"
        run_dir.mkdir(parents=True)
        external = self.temp_dir / "external-hardlink.md"
        external.write_text("Status: `DRAFT`\nexternal-hardlink-must-survive\n", encoding="utf-8")
        requirements = run_dir / "00-requirements.md"
        try:
            requirements.hardlink_to(external)
        except OSError as exc:
            self.skipTest(f"hardlink creation is unavailable: {exc}")
        worktree = run_dir / "00-worktree.md"
        worktree.write_text("Status: `DRAFT`\nworktree-must-survive\n", encoding="utf-8")
        before = {path: path.read_bytes() for path in (external, requirements, worktree)}

        result = self.run_init()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("must not have multiple hard links", result.stdout)
        self.assertEqual(before, {path: path.read_bytes() for path in (external, requirements, worktree)})

    def test_force_refuses_symlinked_run_directory_without_changing_external_files(self) -> None:
        run_root = self.repo_root / ".recursive" / "run"
        run_root.mkdir(parents=True)
        external_run = self.temp_dir / "external-run"
        external_run.mkdir()
        requirements = external_run / "00-requirements.md"
        worktree = external_run / "00-worktree.md"
        requirements.write_text("Status: `DRAFT`\nexternal-requirements-must-survive\n", encoding="utf-8")
        worktree.write_text("Status: `DRAFT`\nexternal-worktree-must-survive\n", encoding="utf-8")
        run_dir = run_root / "guard-fixture"
        try:
            run_dir.symlink_to(external_run, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"directory symlink creation is unavailable: {exc}")
        before = {path: path.read_bytes() for path in (requirements, worktree)}

        result = self.run_init()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("run directory must be a real directory and cannot be a symlink or reparse point", result.stdout)
        self.assertTrue(run_dir.is_symlink())
        self.assertEqual(before, {path: path.read_bytes() for path in (requirements, worktree)})

    @unittest.skipUnless(sys.platform == "win32", "Windows junction semantics require Windows")
    def test_force_refuses_windows_junction_to_another_run_without_changing_bytes(self) -> None:
        run_root = self.repo_root / ".recursive" / "run"
        run_root.mkdir(parents=True)
        other_run = run_root / "other-run"
        other_run.mkdir()
        requirements = other_run / "00-requirements.md"
        worktree = other_run / "00-worktree.md"
        requirements.write_text("Status: `DRAFT`\nother-run-requirements-must-survive\n", encoding="utf-8")
        worktree.write_text("Status: `DRAFT`\nother-run-worktree-must-survive\n", encoding="utf-8")
        run_dir = run_root / "guard-fixture"
        junction = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(run_dir), str(other_run)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, junction.returncode, junction.stdout + junction.stderr)
        self.addCleanup(
            subprocess.run,
            ["cmd.exe", "/d", "/c", "rmdir", str(run_dir)],
            capture_output=True,
            check=False,
        )
        self.assertTrue(run_dir.is_junction())
        before = {path: path.read_bytes() for path in (requirements, worktree)}

        result = self.run_init()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("run directory must be a real directory and cannot be a symlink or reparse point", result.stdout)
        self.assertEqual(before, {path: path.read_bytes() for path in (requirements, worktree)})

    def test_non_force_refuses_dangling_phase_zero_symlinks_without_writing_outside_repo(self) -> None:
        for filename in ("00-requirements.md", "00-worktree.md"):
            with self.subTest(filename=filename):
                run_id = f"dangling-{Path(filename).stem.removeprefix('00-')}"
                run_dir = self.repo_root / ".recursive" / "run" / run_id
                run_dir.mkdir(parents=True)
                external = self.temp_dir / f"external-{filename}"
                linked = run_dir / filename
                try:
                    linked.symlink_to(external)
                except OSError as exc:
                    self.skipTest(f"symlink creation is unavailable: {exc}")
                sibling_name = "00-worktree.md" if filename == "00-requirements.md" else "00-requirements.md"
                sibling = run_dir / sibling_name
                sibling.write_text("Status: `DRAFT`\nsibling-must-survive\n", encoding="utf-8")
                before_sibling = sibling.read_bytes()

                result = self.run_init(run_id, force=False)

                self.assertNotEqual(0, result.returncode)
                self.assertIn("must be a regular file and cannot be a symlink or reparse point", result.stdout)
                self.assertFalse(external.exists())
                self.assertEqual(before_sibling, sibling.read_bytes())

    def test_refuses_symlinked_evidence_directory_before_creating_children(self) -> None:
        for force in (False, True):
            with self.subTest(force=force):
                run_id = f"evidence-link-{'force' if force else 'normal'}"
                run_dir = self.repo_root / ".recursive" / "run" / run_id
                run_dir.mkdir(parents=True)
                external_evidence = self.temp_dir / f"external-evidence-{'force' if force else 'normal'}"
                external_evidence.mkdir()
                evidence_dir = run_dir / "evidence"
                try:
                    evidence_dir.symlink_to(external_evidence, target_is_directory=True)
                except OSError as exc:
                    self.skipTest(f"directory symlink creation is unavailable: {exc}")

                result = self.run_init(run_id, force=force)

                self.assertNotEqual(0, result.returncode)
                self.assertIn("evidence directory must be a real directory and cannot be a symlink or reparse point", result.stdout)
                self.assertEqual([], list(external_evidence.iterdir()))

    def test_force_rejects_run_id_path_traversal_before_writing(self) -> None:
        external_run = self.repo_root / "escape"
        external_run.mkdir()
        requirements = external_run / "00-requirements.md"
        worktree = external_run / "00-worktree.md"
        requirements.write_text("Status: `DRAFT`\nexternal-requirements-must-survive\n", encoding="utf-8")
        worktree.write_text("Status: `DRAFT`\nexternal-worktree-must-survive\n", encoding="utf-8")
        before = {path: path.read_bytes() for path in (requirements, worktree)}

        result = self.run_init("../../../escape")

        self.assertNotEqual(0, result.returncode)
        self.assertIn("Run ID must be a canonical kebab-case directory name", result.stdout)
        self.assertEqual(before, {path: path.read_bytes() for path in (requirements, worktree)})

    def test_force_replaces_existing_draft_scaffolds(self) -> None:
        requirements, worktree = self.write_phase_zero("DRAFT", "replace-this-draft")

        result = self.run_init()

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertNotIn("replace-this-draft", requirements.read_text(encoding="utf-8"))
        self.assertNotIn("replace-this-draft", worktree.read_text(encoding="utf-8"))
        self.assertIn("Status: `DRAFT`", requirements.read_text(encoding="utf-8"))
        self.assertIn("Status: `DRAFT`", worktree.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
