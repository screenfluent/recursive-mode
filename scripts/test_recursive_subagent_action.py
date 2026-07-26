#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "skills" / "recursive-mode" / "scripts" / "recursive-subagent-action.py"
POWERSHELL_PATH = SCRIPT_PATH.with_suffix(".ps1")
VALIDATOR_PATH = SCRIPT_PATH.parent / "recursive_review_action.py"
sys.path.insert(0, str(SCRIPT_PATH.parent))

import recursive_review_action as review_action


class RecursiveSubagentActionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="recursive-subagent-action-test-"))
        self.repo_root = self.temp_dir / "repo"
        (self.repo_root / ".recursive" / "run" / "run-123").mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def run_action(self, *extra: str, run_id: str = "run-123") -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--repo-root",
                str(self.repo_root),
                "--run-id",
                run_id,
                "--subagent-id",
                "code-reviewer",
                "--phase",
                "Phase 5 Manual QA",
                "--purpose",
                "Delegated code review",
                "--execution-mode",
                "review",
                *extra,
            ],
            cwd=str(REPO_ROOT),
            text=True,
            capture_output=True,
            check=False,
        )

    def test_action_record_includes_router_metadata_fields(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--repo-root",
                str(self.repo_root),
                "--run-id",
                "run-123",
                "--subagent-id",
                "code-reviewer",
                "--phase",
                "Phase 5 Manual QA",
                "--purpose",
                "Delegated code review",
                "--execution-mode",
                "review",
                "--router-used",
                "recursive-router",
                "--routed-role",
                "code-reviewer",
                "--routed-cli",
                "codex",
                "--routed-model",
                "gpt-5",
                "--routing-config-path",
                ".recursive/config/recursive-router.json",
                "--routing-discovery-path",
                ".recursive/config/recursive-router-discovered.json",
                "--routing-resolution-basis",
                "role_routes.code-reviewer",
                "--cli-probe-summary",
                "codex available",
                "--prompt-bundle-path",
                ".recursive/run/run-123/router-prompts/code-reviewer-bundle.md",
                "--invocation-exit-code",
                "0",
                "--output-capture-path",
                ".recursive/run/run-123/evidence/router/code-reviewer-output.md",
            ],
            cwd=str(REPO_ROOT),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

        action_records = list((self.repo_root / ".recursive" / "run" / "run-123" / "subagents").glob("*.md"))
        self.assertEqual(len(action_records), 1)
        content = action_records[0].read_text(encoding="utf-8")
        validation = review_action.validate_action_record(
            self.repo_root,
            content,
            expected_run="run-123",
            expected_phase="Phase 5 Manual QA",
        )
        self.assertTrue(validation.valid, validation.issues)
        self.assertIn("- Router Used: `recursive-router`", content)
        self.assertIn("- Routed Role: `code-reviewer`", content)
        self.assertIn("- Routed CLI: `codex`", content)
        self.assertIn("- Routed Model: `gpt-5`", content)
        self.assertIn("- Routing Config Path: `/.recursive/config/recursive-router.json`", content)
        self.assertIn("- Prompt Bundle Path: `/.recursive/run/run-123/router-prompts/code-reviewer-bundle.md`", content)
        self.assertIn("- Invocation Exit Code: `0`", content)
        self.assertIn("- `/.recursive/run/run-123/evidence/router/code-reviewer-output.md`", content)

    def test_rejects_output_name_path_traversal(self) -> None:
        completed = self.run_action("--output-name", "../../../escaped.md")

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("single filename", completed.stdout)
        self.assertFalse((self.repo_root / ".recursive" / "escaped.md").exists())

    def test_rejects_run_id_path_traversal(self) -> None:
        escaped_run = self.repo_root / ".recursive" / "escape-run"
        escaped_run.mkdir(parents=True)

        completed = self.run_action(run_id="../../escape-run")

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("canonical kebab-case", completed.stdout)
        self.assertFalse((escaped_run / "subagents").exists())

    def test_refuses_to_persist_text_that_breaks_the_canonical_grammar(self) -> None:
        completed = self.run_action(
            "--action-taken",
            "completed safely\n## Injected Section",
            "--output-name",
            "injected.md",
        )

        self.assertNotEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("canonical grammar", completed.stdout)
        self.assertFalse(
            (
                self.repo_root
                / ".recursive"
                / "run"
                / "run-123"
                / "subagents"
                / "injected.md"
            ).exists()
        )

    def test_refuses_to_overwrite_any_existing_output_leaf(self) -> None:
        subagents = self.repo_root / ".recursive" / "run" / "run-123" / "subagents"
        subagents.mkdir()
        outside = self.temp_dir / "outside.md"
        cases: list[tuple[str, Path]] = []

        regular = subagents / "regular.md"
        regular.write_text("regular sentinel", encoding="utf-8")
        cases.append(("regular.md", regular))

        hardlink = subagents / "hardlink.md"
        outside.write_text("outside sentinel", encoding="utf-8")
        os.link(outside, hardlink)
        cases.append(("hardlink.md", hardlink))

        symlink = subagents / "symlink.md"
        try:
            symlink.symlink_to(outside)
        except (NotImplementedError, OSError):
            symlink = None
        if symlink is not None:
            cases.append(("symlink.md", symlink))

        for output_name, output_path in cases:
            with self.subTest(output_name=output_name):
                before = output_path.read_text(encoding="utf-8")
                completed = self.run_action("--output-name", output_name)
                self.assertNotEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                self.assertEqual(output_path.read_text(encoding="utf-8"), before)
        self.assertEqual(outside.read_text(encoding="utf-8"), "outside sentinel")

        path_validation = review_action.validate_action_record_path(
            self.repo_root,
            self.repo_root / ".recursive" / "run" / "run-123",
            hardlink,
        )
        self.assertFalse(path_validation.valid)
        self.assertTrue(any("hard" in issue.lower() for issue in path_validation.issues))

    def test_parent_symlink_is_rejected_before_subagents_directory_creation(self) -> None:
        outside_recursive = self.temp_dir / "outside-recursive"
        (outside_recursive / "run" / "run-123").mkdir(parents=True)
        shutil.rmtree(self.repo_root / ".recursive")
        try:
            (self.repo_root / ".recursive").symlink_to(outside_recursive, target_is_directory=True)
        except (NotImplementedError, OSError) as error:
            self.skipTest(f"directory symlinks unavailable: {error}")

        completed = self.run_action("--output-name", "escaped.md")

        self.assertNotEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("without indirection", completed.stdout)
        self.assertFalse((outside_recursive / "run" / "run-123" / "subagents").exists())

    def test_artifact_read_rejects_traversal_symlink_and_invalid_utf8(self) -> None:
        outside = self.temp_dir / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        symlink = self.repo_root / "linked-artifact.txt"
        try:
            symlink.symlink_to(outside)
        except (NotImplementedError, OSError):
            symlink = None
        invalid_utf8 = self.repo_root / "invalid-artifact.txt"
        invalid_utf8.write_bytes(b"\xff\xfe")
        hardlink = self.repo_root / "hardlinked-artifact.txt"
        os.link(outside, hardlink)

        cases = [
            ("../outside.txt", "dot-dot"),
            ("C:/outside.txt", "drive"),
            (" spaced.txt", "whitespace"),
            ("invalid-artifact.txt", "valid UTF-8"),
            ("hardlinked-artifact.txt", "unique regular"),
        ]
        if symlink is not None:
            cases.append(("linked-artifact.txt", "symlink"))
        for artifact_path, expected_issue in cases:
            with self.subTest(artifact_path=artifact_path):
                completed = self.run_action(
                    "--artifact-path",
                    artifact_path,
                    "--output-name",
                    f"{artifact_path.replace('/', '-')}.md",
                )
                self.assertNotEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                self.assertIn(expected_issue, completed.stdout)

    def test_all_path_arguments_reject_noncanonical_values_before_persistence(self) -> None:
        cases = (
            ("--code-ref", "src/./app.rs"),
            ("--reviewed-file", "src//app.rs"),
            ("--verification-path", "src/../app.rs"),
            ("--routing-config-path", r"C:\repo\router.json"),
            ("--output-capture-path", "//server/share/out.txt"),
            ("--memory-ref", "memory.md "),
            ("--upstream-artifact", "upstream\nartifact.md"),
        )
        for index, (option, value) in enumerate(cases):
            with self.subTest(option=option, value=value):
                completed = self.run_action(
                    option,
                    value,
                    "--output-name",
                    f"invalid-{index}.md",
                )
                self.assertNotEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                self.assertIn(option, completed.stdout)
                self.assertFalse(
                    (
                        self.repo_root
                        / ".recursive"
                        / "run"
                        / "run-123"
                        / "subagents"
                        / f"invalid-{index}.md"
                    ).exists()
                )

    def test_invalid_utf8_action_record_is_reported_without_traceback(self) -> None:
        subagents = self.repo_root / ".recursive" / "run" / "run-123" / "subagents"
        subagents.mkdir()
        action_path = subagents / "invalid.md"
        action_path.write_bytes(b"\xff\xfe")

        completed = subprocess.run(
            [
                sys.executable,
                str(VALIDATOR_PATH),
                "--repo-root",
                str(self.repo_root),
                "--action-record",
                "/.recursive/run/run-123/subagents/invalid.md",
            ],
            cwd=str(REPO_ROOT),
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("valid UTF-8", completed.stdout)
        self.assertNotIn("Traceback", completed.stdout + completed.stderr)

    def test_powershell_wrapper_preserves_commas_in_text_fields(self) -> None:
        wrapper = POWERSHELL_PATH.read_text(encoding="utf-8")
        for variable, option in (
            ("AuditQuestion", "--audit-question"),
            ("ActionTaken", "--action-taken"),
            ("Finding", "--finding"),
            ("VerificationItem", "--verification-item"),
        ):
            with self.subTest(variable=variable):
                loop = next(
                    (
                        line
                        for line in wrapper.splitlines()
                        if line.startswith(f"foreach ($value in @(${variable}))")
                    ),
                    None,
                )
                self.assertIsNotNone(loop)
                assert loop is not None
                self.assertIn(option, loop)
                self.assertNotIn("-split", loop)

    def test_powershell_wrapper_treats_every_path_array_item_as_one_atom(self) -> None:
        wrapper = POWERSHELL_PATH.read_text(encoding="utf-8")
        for variable, option in (
            ("UpstreamArtifact", "--upstream-artifact"),
            ("Addendum", "--addendum"),
            ("CodeRef", "--code-ref"),
            ("MemoryRef", "--memory-ref"),
            ("CreatedFile", "--created-file"),
            ("ModifiedFile", "--modified-file"),
            ("ReviewedFile", "--reviewed-file"),
            ("UntouchedFile", "--untouched-file"),
            ("ArtifactRead", "--artifact-read"),
            ("ArtifactUpdated", "--artifact-updated"),
            ("EvidenceUsed", "--evidence-used"),
            ("FindingChange", "--finding-change"),
            ("VerificationPath", "--verification-path"),
            ("OutputCapturePath", "--output-capture-path"),
        ):
            with self.subTest(variable=variable):
                loop = next(
                    (
                        line
                        for line in wrapper.splitlines()
                        if line.startswith(f"foreach ($value in @(${variable}))")
                    ),
                    None,
                )
                self.assertIsNotNone(loop)
                assert loop is not None
                self.assertIn(option, loop)
                self.assertNotIn("-split", loop)

    def test_powershell_runtime_preserves_comma_inside_one_path_item(self) -> None:
        pwsh = shutil.which("pwsh")
        if pwsh is None:
            self.skipTest("pwsh is unavailable")
        comma_path = "src/one,two.rs"
        (self.repo_root / "src").mkdir()
        (self.repo_root / comma_path).write_text("pub fn comma() {}\n", encoding="utf-8")
        completed = subprocess.run(
            [
                pwsh,
                "-NoLogo",
                "-NoProfile",
                "-File",
                str(POWERSHELL_PATH),
                "-RepoRoot",
                str(self.repo_root),
                "-RunId",
                "run-123",
                "-SubagentId",
                "planner",
                "-Phase",
                "Phase 2",
                "-Purpose",
                "Comma path parity",
                "-ExecutionMode",
                "planner",
                "-CodeRef",
                comma_path,
                "-ReviewedFile",
                comma_path,
                "-VerificationPath",
                comma_path,
                "-ActionTaken",
                "reviewed comma path",
                "-OutputName",
                "powershell-comma.md",
            ],
            cwd=str(REPO_ROOT),
            env={**os.environ, "PYTHON": sys.executable},
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        content = (
            self.repo_root
            / ".recursive"
            / "run"
            / "run-123"
            / "subagents"
            / "powershell-comma.md"
        ).read_text(encoding="utf-8")
        self.assertGreaterEqual(content.count("`/src/one,two.rs`"), 3)
        self.assertNotIn("`/src/one`", content)
        self.assertNotIn("`/two.rs`", content)


if __name__ == "__main__":
    unittest.main()
