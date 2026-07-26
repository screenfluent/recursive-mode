#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "skills" / "recursive-mode" / "scripts" / "recursive-review-bundle.py"
PS_SCRIPT_PATH = REPO_ROOT / "skills" / "recursive-mode" / "scripts" / "recursive-review-bundle.ps1"
RUNTIME = REPO_ROOT / "skills" / "recursive-mode" / "scripts"
sys.path.insert(0, str(RUNTIME))

import recursive_review_surface as review_surface
import recursive_review_ledger as review_ledger

LINT_SPEC = importlib.util.spec_from_file_location("review_bundle_lint", RUNTIME / "lint-recursive-run.py")
if LINT_SPEC is None or LINT_SPEC.loader is None:
    raise RuntimeError("Unable to load lint-recursive-run.py")
lint = importlib.util.module_from_spec(LINT_SPEC)
sys.modules[LINT_SPEC.name] = lint
LINT_SPEC.loader.exec_module(lint)


class RecursiveReviewBundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="recursive-review-bundle-test-"))
        self.repo_root = self.temp_dir / "repo"
        self.run_root = self.repo_root / ".recursive" / "run" / "run-123"
        self.run_root.mkdir(parents=True, exist_ok=True)
        self._write(self.repo_root / "src" / "app.py", "print('baseline')\n")
        self._write(self.repo_root / "src" / "context.py", "CONTEXT = True\n")
        self._write(self.repo_root / ".recursive" / "config" / "recursive-router.json", "{}\n")
        self._write(self.repo_root / ".recursive" / "config" / "recursive-router-discovered.json", "{}\n")
        self._git("init")
        self._git("config", "user.name", "Review Bundle Tests")
        self._git("config", "user.email", "review-bundle-tests@example.com")
        self._git("branch", "-M", "main")
        self._git("add", "-A")
        self._git("commit", "-m", "baseline")
        baseline = self._git("rev-parse", "HEAD").stdout.strip()
        self._write(
            self.run_root / "00-worktree.md",
            "\n".join(
                [
                    "## Diff Basis For Later Audits",
                    "",
                    "- Baseline type: `commit`",
                    f"- Baseline reference: `{baseline}`",
                    "- Comparison reference: `working-tree`",
                    f"- Normalized baseline: `{baseline}`",
                    "- Normalized comparison: `working-tree`",
                    f"- Normalized diff command: `git diff --name-only {baseline}`",
                ]
            ),
        )
        self._write(self.run_root / "03.5-code-review.md", "# Code Review\n")
        self._write(self.repo_root / "src" / "app.py", "print('changed')\n")

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=str(self.repo_root),
            text=True,
            capture_output=True,
            check=True,
        )

    def _write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content.rstrip() + "\n", encoding="utf-8", newline="\n")

    def test_review_bundle_includes_routing_metadata(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--repo-root",
                str(self.repo_root),
                "--run-id",
                "run-123",
                "--phase",
                "03.5 Code Review",
                "--role",
                "code-reviewer",
                "--artifact-path",
                ".recursive/run/run-123/03.5-code-review.md",
                "--review-id",
                "code-review",
                "--pass",
                "0001",
                "--code-ref",
                "src/app.py",
                "--audit-question",
                "Does the changed behavior match the plan?",
                "--routing-config-path",
                ".recursive/config/recursive-router.json",
                "--routing-discovery-path",
                ".recursive/config/recursive-router-discovered.json",
                "--routed-cli",
                "codex",
                "--routed-model",
                "gpt-5.4",
            ],
            cwd=str(REPO_ROOT),
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        bundle_path = self.run_root / "evidence" / "review-bundles" / "phase-3-5" / "code-review" / "0001.md"
        content = bundle_path.read_text(encoding="utf-8")
        self.assertIn("## Routing", content)
        self.assertIn("- Routed CLI: `codex`", content)
        self.assertIn("- Routed Model: `gpt-5.4`", content)
        self.assertIn("- Routing Config Path: `/.recursive/config/recursive-router.json`", content)
        self.assertIn("- Routing Discovery Path: `/.recursive/config/recursive-router-discovered.json`", content)

    def test_powershell_wrapper_forwards_routing_metadata(self) -> None:
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        if powershell is None:
            self.skipTest("PowerShell is required for wrapper parity tests")

        completed = subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-File",
                str(PS_SCRIPT_PATH),
                "-RepoRoot",
                str(self.repo_root),
                "-RunId",
                "run-123",
                "-Phase",
                "03.5 Code Review",
                "-Role",
                "code-reviewer",
                "-ArtifactPath",
                ".recursive/run/run-123/03.5-code-review.md",
                "-ReviewId",
                "code-review-powershell",
                "-ReviewPass",
                "0001",
                "-CodeRef",
                "src/app.py",
                "-AuditQuestion",
                "Does the changed behavior match the plan?",
                "-RoutingConfigPath",
                ".recursive/config/recursive-router.json",
                "-RoutingDiscoveryPath",
                ".recursive/config/recursive-router-discovered.json",
                "-RoutedCli",
                "codex",
                "-RoutedModel",
                "gpt-5.4",
            ],
            cwd=str(REPO_ROOT),
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        bundle_path = self.run_root / "evidence" / "review-bundles" / "phase-3-5" / "code-review-powershell" / "0001.md"
        content = bundle_path.read_text(encoding="utf-8")
        self.assertIn("- Routed CLI: `codex`", content)
        self.assertIn("- Routed Model: `gpt-5.4`", content)
        self.assertIn("- Routing Config Path: `/.recursive/config/recursive-router.json`", content)
        self.assertIn("- Routing Discovery Path: `/.recursive/config/recursive-router-discovered.json`", content)

    def test_powershell_wrapper_preserves_commas_in_array_items(self) -> None:
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        if powershell is None:
            self.skipTest("PowerShell is required for wrapper parity tests")
        comma_path = "src/amount,decimal.py"
        comma_question = "Check scope, evidence, and drift?"
        self._write(self.repo_root / comma_path, "VALUE = 1\n")

        completed = subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-File",
                str(PS_SCRIPT_PATH),
                "-RepoRoot",
                str(self.repo_root),
                "-RunId",
                "run-123",
                "-Phase",
                "03.5 Code Review",
                "-Role",
                "code-reviewer",
                "-ArtifactPath",
                ".recursive/run/run-123/03.5-code-review.md",
                "-ReviewId",
                "powershell-comma-items",
                "-ReviewPass",
                "0001",
                "-CodeRef",
                comma_path,
                "-AuditQuestion",
                comma_question,
            ],
            cwd=str(REPO_ROOT),
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        bundle = (
            self.run_root
            / "evidence/review-bundles/phase-3-5/powershell-comma-items/0001.md"
        )
        content = bundle.read_text(encoding="utf-8")
        self.assertEqual(
            review_surface.parse_markdown_list(
                lint.get_heading_body(content, "Targeted Code References")
            ),
            [comma_path],
        )
        self.assertEqual(
            review_surface.parse_markdown_list(
                lint.get_heading_body(content, "Audit Questions")
            ),
            [comma_question],
        )

    def test_deleted_changed_file_is_bound_as_missing_but_explicit_refs_stay_regular(self) -> None:
        (self.repo_root / "src" / "app.py").unlink()
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--repo-root",
                str(self.repo_root),
                "--run-id",
                "run-123",
                "--phase",
                "03.5 Code Review",
                "--role",
                "code-reviewer",
                "--artifact-path",
                ".recursive/run/run-123/03.5-code-review.md",
                "--review-id",
                "deletion-review",
                "--pass",
                "0001",
                "--code-ref",
                "src/context.py",
                "--audit-question",
                "Is the deletion intentional and complete?",
            ],
            cwd=str(REPO_ROOT),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        bundle_rel = ".recursive/run/run-123/evidence/review-bundles/phase-3-5/deletion-review/0001.md"
        bundle = self.repo_root / bundle_rel
        snapshot, issues = review_surface.parse(bundle.read_text(encoding="utf-8"))
        self.assertEqual(issues, [])
        changed = {record["path"]: record["state"] for record in snapshot["changed"]}
        references = {record["path"]: record["state"] for record in snapshot["references"]}
        self.assertEqual(changed["src/app.py"], "missing")
        self.assertEqual(references["src/context.py"], "file")

        phase_content = f"""## Review Metadata

- Review Bundle Path: `/{bundle_rel}`

## Bundle Citation

- `/{bundle_rel}`
"""
        lint_issues = lint.lint_review_bundle_reference(phase_content, self.run_root, self.repo_root)
        self.assertEqual(lint_issues, [])

        rejected = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--repo-root",
                str(self.repo_root),
                "--run-id",
                "run-123",
                "--phase",
                "03.5 Code Review",
                "--role",
                "code-reviewer",
                "--artifact-path",
                ".recursive/run/run-123/03.5-code-review.md",
                "--review-id",
                "invalid-deleted-ref",
                "--pass",
                "0001",
                "--code-ref",
                "src/app.py",
            ],
            cwd=str(REPO_ROOT),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(rejected.returncode, 0)
        self.assertFalse(
            (self.run_root / "evidence/review-bundles/phase-3-5/invalid-deleted-ref/0001.md").exists()
        )

    @unittest.skipIf(sys.platform == "win32", "POSIX permits literal backslashes in filenames")
    def test_git_surface_preserves_literal_backslash_and_literal_pathspec_metacharacters(self) -> None:
        literal_path = "src/literal\\name[1].py"
        self._write(self.repo_root / literal_path, "LITERAL = True\n")
        baseline = self._git("rev-parse", "HEAD").stdout.strip()
        snapshot = review_surface.capture(
            self.repo_root,
            run_id="run-123",
            baseline=baseline,
            comparison="working-tree",
            references=[literal_path],
        )
        changed = {record["path"]: record for record in snapshot["changed"]}
        references = {record["path"]: record for record in snapshot["references"]}
        self.assertIn(literal_path, changed)
        self.assertIn(literal_path, references)
        self.assertEqual(changed[literal_path]["sha256"], references[literal_path]["sha256"])

        self._git("--literal-pathspecs", "add", "--", literal_path)
        self._git("commit", "-m", "literal path")
        commit = self._git("rev-parse", "HEAD").stdout.strip()
        committed = review_surface.git_path_record(self.repo_root, commit, literal_path)
        self.assertEqual(committed["path"], literal_path)
        self.assertEqual(committed["state"], "file")

    @unittest.skipIf(sys.platform == "win32", "POSIX symlink regression")
    def test_changed_child_under_symlink_parent_is_missing_not_substituted(self) -> None:
        tracked = self.repo_root / "tracked-parent" / "child.py"
        self._write(tracked, "TRACKED = True\n")
        self._git("add", "--", "tracked-parent/child.py")
        self._git("commit", "-m", "tracked nested child")
        baseline = self._git("rev-parse", "HEAD").stdout.strip()

        shutil.rmtree(tracked.parent)
        substitute = self.repo_root / "substitute-parent"
        self._write(substitute / "child.py", "SUBSTITUTE = True\n")
        tracked.parent.symlink_to(substitute, target_is_directory=True)

        snapshot = review_surface.capture(
            self.repo_root,
            run_id="run-123",
            baseline=baseline,
            comparison="working-tree",
            references=[],
        )
        changed = {record["path"]: record for record in snapshot["changed"]}
        self.assertIn("tracked-parent/child.py", changed)
        self.assertEqual(
            changed["tracked-parent/child.py"],
            {
                "path": "tracked-parent/child.py",
                "state": "missing",
                "mode": "none",
                "sha256": "none",
            },
        )
        substitute_hash = review_surface.path_record(
            self.repo_root,
            "substitute-parent/child.py",
            from_git=True,
        )["sha256"]
        self.assertNotEqual(changed["tracked-parent/child.py"]["sha256"], substitute_hash)

    @unittest.skipIf(sys.platform == "win32", "POSIX permits control characters in filenames")
    def test_bundle_losslessly_encodes_adversarial_git_names_without_heading_injection(self) -> None:
        adversarial_paths = [
            "src/ leading.py",
            "src/trailing.py ",
            "src/line\n## Injected Changed Heading.py",
            "src/carriage\rreturn.py",
        ]
        for path in adversarial_paths:
            self._write(self.repo_root / path, "ADVERSARIAL = True\n")
        question = "Check commas, line breaks,\n## Injected Question Heading"
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--repo-root",
                str(self.repo_root),
                "--run-id",
                "run-123",
                "--phase",
                "03.5 Code Review",
                "--role",
                "code-reviewer",
                "--artifact-path",
                ".recursive/run/run-123/03.5-code-review.md",
                "--review-id",
                "adversarial-git-names",
                "--pass",
                "0001",
                "--audit-question",
                question,
            ],
            cwd=str(REPO_ROOT),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        bundle = (
            self.run_root
            / "evidence/review-bundles/phase-3-5/adversarial-git-names/0001.md"
        )
        content = bundle.read_text(encoding="utf-8")
        self.assertNotIn("\n## Injected Changed Heading", content)
        self.assertNotIn("\n## Injected Question Heading", content)
        snapshot, snapshot_issues = review_surface.parse(content)
        self.assertEqual(snapshot_issues, [])
        self.assertIsNotNone(snapshot)
        snapshot_paths = [record["path"] for record in snapshot["changed"]]
        for path in adversarial_paths:
            self.assertIn(path, snapshot_paths)
        listed_paths, list_issues = review_ledger.section_bullet_values(
            content,
            "Changed Files Reviewed",
        )
        self.assertEqual(list_issues, [])
        self.assertEqual(listed_paths, snapshot_paths)
        self.assertEqual(
            review_surface.parse_markdown_list(
                lint.get_heading_body(content, "Audit Questions")
            ),
            [question],
        )

    def test_render_validation_failure_leaves_no_bundle_artifact(self) -> None:
        bundle = (
            self.run_root
            / "evidence/review-bundles/phase-3-5/invalid-render/0001.md"
        )
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--repo-root",
                str(self.repo_root),
                "--run-id",
                "run-123",
                "--phase",
                "03.5 Code Review",
                "--role",
                "reviewer\n## Injected Header",
                "--artifact-path",
                ".recursive/run/run-123/03.5-code-review.md",
                "--review-id",
                "invalid-render",
                "--pass",
                "0001",
            ],
            cwd=str(REPO_ROOT),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("invalid rendered review bundle", completed.stdout)
        self.assertFalse(bundle.exists())

    def test_canonical_paths_reject_absolute_drive_empty_and_dot_components(self) -> None:
        invalid = ("", "//server/share.py", "C:/src/app.py", "src//app.py", "src/./app.py", "src/../app.py")
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    review_surface.normalize_path(value)
        with self.assertRaises(ValueError):
            review_surface.git_path("/src/app.py")

    @unittest.skipIf(sys.platform == "win32", "POSIX symlink regression")
    def test_bundle_rejects_external_symlink_and_invalid_utf8_without_traceback(self) -> None:
        outside = self.temp_dir / "outside.py"
        outside.write_text("OUTSIDE = True\n", encoding="utf-8")
        linked = self.repo_root / "src" / "external.py"
        linked.symlink_to(outside)
        symlinked = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--repo-root",
                str(self.repo_root),
                "--run-id",
                "run-123",
                "--phase",
                "03.5 Code Review",
                "--role",
                "code-reviewer",
                "--artifact-path",
                ".recursive/run/run-123/03.5-code-review.md",
                "--review-id",
                "external-symlink",
                "--pass",
                "0001",
                "--code-ref",
                "src/external.py",
            ],
            cwd=str(REPO_ROOT),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(symlinked.returncode, 0)
        self.assertIn("[FAIL]", symlinked.stdout)
        self.assertNotIn("Traceback", symlinked.stderr)

        linked.unlink()
        os.link(outside, linked)
        hardlinked = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--repo-root",
                str(self.repo_root),
                "--run-id",
                "run-123",
                "--phase",
                "03.5 Code Review",
                "--role",
                "code-reviewer",
                "--artifact-path",
                ".recursive/run/run-123/03.5-code-review.md",
                "--review-id",
                "external-hardlink",
                "--pass",
                "0001",
                "--code-ref",
                "src/external.py",
            ],
            cwd=str(REPO_ROOT),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(hardlinked.returncode, 0)
        self.assertIn("non-hardlink", hardlinked.stdout)
        self.assertNotIn("Traceback", hardlinked.stderr)

        (self.run_root / "03.5-code-review.md").write_bytes(b"\xff\xfe\xfa")
        invalid_utf8 = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--repo-root",
                str(self.repo_root),
                "--run-id",
                "run-123",
                "--phase",
                "03.5 Code Review",
                "--role",
                "code-reviewer",
                "--artifact-path",
                ".recursive/run/run-123/03.5-code-review.md",
                "--review-id",
                "invalid-utf8",
                "--pass",
                "0001",
            ],
            cwd=str(REPO_ROOT),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(invalid_utf8.returncode, 0)
        self.assertIn("[FAIL]", invalid_utf8.stdout)
        self.assertNotIn("Traceback", invalid_utf8.stderr)


if __name__ == "__main__":
    unittest.main()
