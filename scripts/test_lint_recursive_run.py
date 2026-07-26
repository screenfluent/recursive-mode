#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


RUNTIME = Path(__file__).resolve().parent.parent / "skills" / "recursive-mode" / "scripts"
ACTION_SCRIPT = RUNTIME / "recursive-subagent-action.py"
sys.path.insert(0, str(RUNTIME))
MODULE_PATH = RUNTIME / "lint-recursive-run.py"
SPEC = importlib.util.spec_from_file_location("lint_recursive_run", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load lint module from {MODULE_PATH}")
lint = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = lint
SPEC.loader.exec_module(lint)

CLOSEOUT_PATH = RUNTIME / "recursive-closeout.py"
CLOSEOUT_SPEC = importlib.util.spec_from_file_location("recursive_closeout", CLOSEOUT_PATH)
if CLOSEOUT_SPEC is None or CLOSEOUT_SPEC.loader is None:
    raise RuntimeError(f"Unable to load closeout module from {CLOSEOUT_PATH}")
closeout = importlib.util.module_from_spec(CLOSEOUT_SPEC)
sys.modules[CLOSEOUT_SPEC.name] = closeout
CLOSEOUT_SPEC.loader.exec_module(closeout)

STATUS_PATH = RUNTIME / "recursive-status.py"
STATUS_SPEC = importlib.util.spec_from_file_location("recursive_status_for_lint_tests", STATUS_PATH)
if STATUS_SPEC is None or STATUS_SPEC.loader is None:
    raise RuntimeError(f"Unable to load status module from {STATUS_PATH}")
status = importlib.util.module_from_spec(STATUS_SPEC)
sys.modules[STATUS_SPEC.name] = status
STATUS_SPEC.loader.exec_module(status)


class LintRecursiveRunTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="lint-recursive-run-test-"))
        self.repo_root = self.temp_dir / "repo"
        self.run_id = "benchmark-test-run"
        self.run_dir = self.repo_root / ".recursive" / "run" / self.run_id
        self.worktree_root = self.repo_root / ".worktrees" / self.run_id

        self._write(self.repo_root / "src" / "lib.rs", "pub fn baseline() -> i32 { 0 }\n")
        self._git(self.repo_root, "init")
        self._git(self.repo_root, "config", "user.name", "Lint Tests")
        self._git(self.repo_root, "config", "user.email", "lint-tests@example.com")
        self._git(self.repo_root, "branch", "-M", "main")
        self._git(self.repo_root, "add", "-A")
        self._git(self.repo_root, "commit", "-m", "baseline")
        self.baseline_commit = self._git(self.repo_root, "rev-parse", "HEAD").stdout.strip()
        self._git(self.repo_root, "worktree", "add", str(self.worktree_root), "-b", f"recursive/{self.run_id}")
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._write(
            self.run_dir / "00-worktree.md",
            "\n".join(
                [
                    "## Diff Basis For Later Audits",
                    "",
                    "- Baseline type: commit",
                    f"- Baseline reference: `{self.baseline_commit}`",
                    "- Comparison reference: working-tree",
                    f"- Normalized baseline: `{self.baseline_commit}`",
                    "- Normalized comparison: working-tree",
                    f"- Normalized diff command: `git diff --name-only {self.baseline_commit}`",
                    "",
                    "## Worktree Details",
                    "",
                    f"- Location: `.worktrees/{self.run_id}`",
                    f"- Product root: `.worktrees/{self.run_id}`",
                ]
            ),
        )

    def tearDown(self) -> None:
        subprocess.run(["git", "-C", str(self.repo_root), "worktree", "remove", "--force", str(self.worktree_root)], check=False)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _git(self, cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            text=True,
            capture_output=True,
            check=True,
        )

    def _write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")

    def _subagent_contribution(self, action_path: str) -> str:
        return f"""- Phase: Phase 3

## Audit Context
- Audit Execution Mode: subagent

## Review Metadata
- Review Ledger Path: `/.recursive/run/{self.run_id}/evidence/reviews/phase-3/review/ledger.md`
- Review Bundle Path: `/.recursive/run/{self.run_id}/evidence/review-bundles/phase-3/review/0001.md`

## Subagent Contribution Verification
- Reviewed Action Records:
  - `/{action_path}`
- Main-Agent Verification Performed: `/.recursive/run/{self.run_id}/03-implementation-summary.md`
- Acceptance Decision: accepted
- Refresh Handling: current pass checked
- Repair Performed After Verification: none
"""

    def _unsafe_action_issues(self, action_path: str) -> tuple[list[str], list[str]]:
        content = self._subagent_contribution(action_path)
        artifact = self.run_dir / "03-implementation-summary.md"
        return (
            lint.lint_subagent_contribution_verification(
                artifact,
                content,
                self.run_dir,
                self.repo_root,
                [],
            ),
            status.collect_subagent_contribution_blockers(
                artifact.name,
                content,
                self.run_dir,
                self.repo_root,
                [],
            ),
        )

    def _generate_action_record(self, output_name: str = "worker.md") -> Path:
        artifact = self.run_dir / "03-implementation-summary.md"
        self._write(artifact, "implementation summary\n")
        completed = subprocess.run(
            [
                sys.executable,
                str(ACTION_SCRIPT),
                "--repo-root",
                str(self.repo_root),
                "--run-id",
                self.run_id,
                "--subagent-id",
                "worker",
                "--phase",
                "Phase 3",
                "--purpose",
                "path confinement test",
                "--execution-mode",
                "implementer",
                "--artifact-path",
                f".recursive/run/{self.run_id}/03-implementation-summary.md",
                "--upstream-artifact",
                f".recursive/run/{self.run_id}/03-implementation-summary.md",
                "--code-ref",
                "src/lib.rs",
                "--action-taken",
                "inspected the requested path",
                "--reviewed-file",
                "src/lib.rs",
                "--artifact-read",
                f".recursive/run/{self.run_id}/03-implementation-summary.md",
                "--verification-path",
                "src/lib.rs",
                "--output-name",
                output_name,
            ],
            cwd=str(self.repo_root),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        return self.run_dir / "subagents" / output_name

    def test_filter_runtime_changed_files_ignores_playwright_runtime_dirs(self) -> None:
        filtered = lint.filter_runtime_changed_files(
            [
                ".playwright-mcp/page.yml",
                ".target/debug/app.js",
                ".cargo-target-dir/debug/output.txt",
                ".recursive/run/benchmark-test-run/03-implementation-summary.md",
                ".worktrees/benchmark-test-run/src/lib.rs",
            ],
            self.run_id,
        )

        self.assertEqual([".worktrees/benchmark-test-run/src/lib.rs"], filtered)

    def test_requirements_artifact_no_longer_requires_assumptions_section(self) -> None:
        sections = lint.get_artifact_required_sections("00-requirements.md")

        self.assertNotIn("Assumptions", sections)
        self.assertEqual(
            ["TODO", "Requirements", "Out of Scope", "Constraints", "Coverage Gate", "Approval Gate"],
            sections,
        )

    def test_closeout_scaffold_requires_real_capability_decision(self) -> None:
        audit_context = closeout.default_audit_context("04-test-summary.md", [".recursive/run/demo/03.5-code-review.md"])
        content = f"## Audit Context\n\n{audit_context}\n"

        issues = lint.lint_audit_sections(
            Path("04-test-summary.md"),
            content,
            actual_changed_files=None,
            diff_basis_error=None,
            run_id="demo",
            run_dir=Path(".recursive/run/demo"),
        )

        self.assertIn("Audit Context is missing a valid Audit Execution Mode: subagent|self-audit", issues)
        self.assertIn("Audit Context is missing a valid Subagent Availability: available|unavailable", issues)
        self.assertIn("Audit Context is missing Subagent Capability Probe", issues)
        self.assertIn("Audit Context is missing Delegation Decision Basis", issues)

    def test_diff_owned_deletion_is_valid_changed_file_but_not_standalone_evidence(self) -> None:
        deleted_path = f".worktrees/{self.run_id}/src/deleted.rs"
        evidence_path = f".recursive/run/{self.run_id}/03.5-code-review.md"
        self._write(self.repo_root / evidence_path, "deletion reviewed\n")
        fields = {
            "Changed Files": f"`/{deleted_path}`",
            "Implementation Evidence": f"`/{evidence_path}`",
        }
        lint_issues = lint.lint_requirement_disposition_fields(
            "R1",
            "implemented",
            fields,
            "03.5-code-review.md",
            self.run_dir,
            self.repo_root,
            [deleted_path],
        )
        status_issues = status.collect_requirement_disposition_blockers(
            "R1",
            "implemented",
            fields,
            "03.5-code-review.md",
            self.run_dir,
            self.repo_root,
            [deleted_path],
        )
        self.assertFalse(any("Changed Files path(s) do not exist" in issue for issue in lint_issues), lint_issues)
        self.assertFalse(any("Changed Files path(s) do not exist" in issue for issue in status_issues), status_issues)

        fields["Implementation Evidence"] = f"`/{deleted_path}`"
        lint_issues = lint.lint_requirement_disposition_fields(
            "R1",
            "implemented",
            fields,
            "03.5-code-review.md",
            self.run_dir,
            self.repo_root,
            [deleted_path],
        )
        status_issues = status.collect_requirement_disposition_blockers(
            "R1",
            "implemented",
            fields,
            "03.5-code-review.md",
            self.run_dir,
            self.repo_root,
            [deleted_path],
        )
        self.assertTrue(any("Implementation Evidence path(s) do not exist" in issue for issue in lint_issues), lint_issues)
        self.assertTrue(any("Implementation Evidence path(s) do not exist" in issue for issue in status_issues), status_issues)

    def test_lint_and_status_reject_leaf_symlink_action_records_with_shared_reason(self) -> None:
        external = self.temp_dir / "external-action.md"
        self._write(external, "# Subagent Action Record\n")
        subagents = self.run_dir / "subagents"
        subagents.mkdir()
        leaf = subagents / "linked.md"
        try:
            leaf.symlink_to(external)
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"file symlinks are unavailable: {exc}")

        action_path = f".recursive/run/{self.run_id}/subagents/linked.md"
        lint_issues, status_issues = self._unsafe_action_issues(action_path)
        lint_unsafe = sorted(issue for issue in lint_issues if "Unsafe subagent action record path" in issue)
        status_unsafe = sorted(issue for issue in status_issues if "Unsafe subagent action record path" in issue)
        self.assertTrue(lint_unsafe, lint_issues)
        self.assertEqual(lint_unsafe, status_unsafe)
        self.assertTrue(any("symlink or reparse point" in issue for issue in lint_unsafe))

    def test_lint_and_status_reject_symlinked_subagents_directory_with_shared_reason(self) -> None:
        external = self.temp_dir / "external-subagents"
        external.mkdir()
        self._write(external / "linked.md", "# Subagent Action Record\n")
        subagents = self.run_dir / "subagents"
        try:
            subagents.symlink_to(external, target_is_directory=True)
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"directory symlinks are unavailable: {exc}")

        action_path = f".recursive/run/{self.run_id}/subagents/linked.md"
        lint_issues, status_issues = self._unsafe_action_issues(action_path)
        lint_unsafe = sorted(issue for issue in lint_issues if "Unsafe subagent action record path" in issue)
        status_unsafe = sorted(issue for issue in status_issues if "Unsafe subagent action record path" in issue)
        self.assertTrue(lint_unsafe, lint_issues)
        self.assertEqual(lint_unsafe, status_unsafe)
        self.assertTrue(any("symlink or reparse point" in issue for issue in lint_unsafe))

    def test_lint_and_status_report_invalid_utf8_action_record_without_traceback(self) -> None:
        subagents = self.run_dir / "subagents"
        subagents.mkdir()
        (subagents / "invalid.md").write_bytes(b"\xff\xfe")
        action_path = f".recursive/run/{self.run_id}/subagents/invalid.md"

        lint_issues, status_issues = self._unsafe_action_issues(action_path)

        lint_invalid = sorted(issue for issue in lint_issues if "Invalid subagent action record" in issue)
        status_invalid = sorted(issue for issue in status_issues if "Invalid subagent action record" in issue)
        self.assertTrue(lint_invalid, lint_issues)
        self.assertEqual(lint_invalid, status_invalid)
        self.assertTrue(any("valid UTF-8" in issue for issue in lint_invalid))

    def test_lint_and_status_confine_current_artifact_reads_without_tracebacks(self) -> None:
        action_path = self._generate_action_record()
        original = action_path.read_text(encoding="utf-8")
        outside = self.temp_dir / "outside-artifact.md"
        self._write(outside, "outside\n")
        hardlink = self.repo_root / "hardlinked-artifact.md"
        hardlink.hardlink_to(outside)
        invalid = self.repo_root / "invalid-artifact.md"
        invalid.write_bytes(b"\xff\xfe")
        symlink = self.repo_root / "linked-artifact.md"
        try:
            symlink.symlink_to(outside)
        except (NotImplementedError, OSError):
            symlink = None

        cases = [
            ("/../outside-artifact.md", "dot-dot"),
            ("/hardlinked-artifact.md", "unique regular"),
            ("/invalid-artifact.md", "valid UTF-8"),
        ]
        if symlink is not None:
            cases.append(("/linked-artifact.md", "symlink"))
        action_rel = f".recursive/run/{self.run_id}/subagents/{action_path.name}"
        for value, expected in cases:
            with self.subTest(value=value):
                mutated = original.replace(
                    f"`/.recursive/run/{self.run_id}/03-implementation-summary.md`",
                    f"`{value}`",
                    1,
                )
                self._write(action_path, mutated)
                lint_issues, status_issues = self._unsafe_action_issues(action_rel)
                self.assertTrue(
                    any("Current Artifact" in issue and expected in issue for issue in lint_issues),
                    lint_issues,
                )
                self.assertTrue(
                    any("Current Artifact" in issue and expected in issue for issue in status_issues),
                    status_issues,
                )

    def test_lint_and_status_confine_review_bundle_reads_without_tracebacks(self) -> None:
        action_path = self._generate_action_record()
        original = action_path.read_text(encoding="utf-8")
        outside = self.temp_dir / "outside-bundle.md"
        self._write(outside, "outside\n")
        hardlink = self.repo_root / "hardlinked-bundle.md"
        hardlink.hardlink_to(outside)
        invalid = self.repo_root / "invalid-bundle.md"
        invalid.write_bytes(b"\xff")
        symlink = self.repo_root / "linked-bundle.md"
        try:
            symlink.symlink_to(outside)
        except (NotImplementedError, OSError):
            symlink = None

        cases = [
            ("/../outside-bundle.md", "dot-dot"),
            ("/hardlinked-bundle.md", "unique regular"),
            ("/invalid-bundle.md", "valid UTF-8"),
        ]
        if symlink is not None:
            cases.append(("/linked-bundle.md", "symlink"))
        action_rel = f".recursive/run/{self.run_id}/subagents/{action_path.name}"
        for value, expected in cases:
            with self.subTest(value=value):
                self._write(
                    action_path,
                    original.replace("- Review Bundle: `none`", f"- Review Bundle: `{value}`", 1),
                )
                lint_issues, status_issues = self._unsafe_action_issues(action_rel)
                self.assertTrue(
                    any("Review Bundle" in issue and expected in issue for issue in lint_issues),
                    lint_issues,
                )
                self.assertTrue(
                    any("Review Bundle" in issue and expected in issue for issue in status_issues),
                    status_issues,
                )

if __name__ == "__main__":
    unittest.main()
