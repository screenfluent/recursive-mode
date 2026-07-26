#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("run-recursive-benchmark.py")
SPEC = importlib.util.spec_from_file_location("run_recursive_benchmark", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load benchmark harness module from {MODULE_PATH}")
rrb = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = rrb
SPEC.loader.exec_module(rrb)


class RecursiveBenchmarkRepoSurfaceTests(unittest.TestCase):
    def test_repo_uses_single_authoritative_benchmark_fixture_tree(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        duplicate_root = repo_root / "references" / "benchmarks" / "benchmarks"
        duplicate_files = sorted(
            path.relative_to(repo_root).as_posix()
            for path in duplicate_root.rglob("*")
            if path.is_file()
        )

        self.assertEqual([], duplicate_files)


class RecursiveBenchmarkIntegrityTests(unittest.TestCase):
    def setUp(self) -> None:
        if shutil.which("git") is None:
            self.skipTest("git is required for benchmark integrity tests")
        self.temp_dir = Path(tempfile.mkdtemp(prefix="recursive-benchmark-test-"))
        self.workspace_root = self.temp_dir / "workspace"
        args = argparse.Namespace(
            scenario="scientific-calculator-rust",
            runner="codex",
            workspace_root=str(self.workspace_root),
            copilot_model="gpt-5.4",
            codex_model="gpt-5.4",
            kimi_model="kimi-k2.6",
            opencode_model="opencode/gpt-5-nano",
            max_minutes=5,
            command_timeout=120,
            preview_timeout=30,
            npm_command="npm",
            arm_mode="sequential",
            hint_penalty=5.0,
            prepare_only=False,
            skip_npm_install=True,
            provision_dependencies=False,
            list_scenarios=False,
        )
        self.harness = rrb.BenchmarkHarness(args)
        self.repo_root = self.temp_dir / "repo"
        self.run_id = "benchmark-test-run"
        self.worktree_root = self.repo_root / ".worktrees" / self.run_id
        self._create_repo_with_worktree()

    def tearDown(self) -> None:
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
        path.write_text(content.rstrip() + "\n", encoding="utf-8", newline="\n")

    def _create_repo_with_worktree(self) -> None:
        self._write(self.repo_root / "src" / "app.rs", "pub fn app_label() -> &'static str { \"starter\" }\n")
        self._write(
            self.repo_root / "src" / "calculator.rs",
            "pub fn starter_expression() -> &'static str { \"sin(45) + 2^3\" }\n",
        )
        self._write(self.repo_root / "Cargo.toml", "[package]\nname = \"benchmark\"\nversion = \"0.1.0\"\n")
        self._write(self.repo_root / "Cargo.lock", "version = 3\n")
        self._write(self.repo_root / ".gitignore", ".worktrees/\n.playwright-mcp/\n.cargo-target-dir/\n")
        self._write(self.repo_root / "styles.css", ".app-shell { display: grid; }\n")
        self._write(self.repo_root / "benchmark" / "agent-log.md", "# Benchmark agent log\n")
        self._git(self.repo_root, "init")
        self._git(self.repo_root, "config", "user.name", "Benchmark Tests")
        self._git(self.repo_root, "config", "user.email", "benchmark-tests@example.com")
        self._git(self.repo_root, "branch", "-M", "main")
        self._git(self.repo_root, "add", "-A")
        self._git(self.repo_root, "commit", "-m", "starter")
        self._git(self.repo_root, "worktree", "add", str(self.worktree_root), "-b", f"recursive/{self.run_id}")
        self._write_run_artifacts(["src/app.rs"])

    def _write_run_artifacts(self, claimed_files: list[str]) -> None:
        run_root = self.repo_root / ".recursive" / "run" / self.run_id
        baseline_ref = self._git(self.repo_root, "rev-parse", "HEAD").stdout.strip()
        claimed_block = "\n".join(f"- `{path}`" for path in claimed_files)
        changed_files_line = ", ".join(f"`{path}`" for path in claimed_files)
        self._write(
            run_root / "00-worktree.md",
            "\n".join(
                [
                    "## Diff Basis",
                    "",
                    "- Baseline type: `commit`",
                    f"- Baseline reference: `{baseline_ref}`",
                    "- Comparison reference: `working-tree`",
                    f"- Normalized baseline: `{baseline_ref}`",
                    "- Normalized comparison: `working-tree`",
                    f"- Normalized diff command: `git diff --name-only {baseline_ref}`",
                ]
            ),
        )
        self._write(
            run_root / "02-to-be-plan.md",
            "\n".join(
                [
                    "## Requirement Completion Status",
                    "",
                    f"- R1 | Status: planned | Changed Files: {changed_files_line}",
                    "",
                    "## Files Changed",
                    "",
                    claimed_block,
                ]
            ),
        )
        self._write(
            run_root / "03-implementation-summary.md",
            "\n".join(
                [
                    "## Files Changed",
                    "",
                    claimed_block,
                    "",
                    "## Requirement Completion Status",
                    "",
                    f"- R1 | Status: implemented | Changed Files: {changed_files_line}",
                ]
            ),
        )

    def _make_result(self) -> rrb.ArmResult:
        return rrb.ArmResult(
            runner_slug="codex",
            runner_name="Codex CLI",
            provider_family="codex",
            model="gpt-5.4",
            arm_name="recursive-on",
            run_id=self.run_id,
            expected_product_root=f".worktrees/{self.run_id}",
            recursive_isolation_status="isolated-worktree",
        )

    def _write_minimal_complete_recursive_run(self) -> Path:
        run_root = self.repo_root / ".recursive" / "run" / self.run_id
        self._write(run_root / "00-requirements.md", self.harness.render_seeded_run_requirements(self.run_id))
        self._write(
            run_root / "00-worktree.md",
            "\n".join(
                [
                    "## Directory Selection",
                    "",
                    f"- Selected worktree location: `.worktrees/{self.run_id}`",
                    f"- Product root: `.worktrees/{self.run_id}`",
                    "",
                    "## Diff Basis For Later Audits",
                    "",
                    "- Baseline type: `commit`",
                    f"- Baseline reference: `{self._git(self.repo_root, 'rev-parse', 'HEAD').stdout.strip()}`",
                    "- Comparison reference: `working-tree`",
                    f"- Normalized baseline: `{self._git(self.repo_root, 'rev-parse', 'HEAD').stdout.strip()}`",
                    "- Normalized comparison: `working-tree`",
                    f"- Normalized diff command: `git diff --name-only {self._git(self.repo_root, 'rev-parse', 'HEAD').stdout.strip()}`",
                ]
            ),
        )
        self._write(run_root / "01-as-is.md", "## Source Requirement Inventory\n")
        self._write(
            run_root / "02-to-be-plan.md",
            "\n".join(
                [
                    "## Requirement Mapping",
                    "",
                    "## Plan Drift Check",
                    "",
                    "## Requirement Completion Status",
                ]
            ),
        )
        for artifact_name in ("03-implementation-summary.md", "04-test-summary.md", "05-manual-qa.md", "06-decisions-update.md", "07-state-update.md", "08-memory-impact.md"):
            self._write(run_root / artifact_name, f"# {artifact_name}\n")
        return run_root

    def _canonical_routed_action(
        self,
        *,
        action_name: str = "worker-1.md",
        phase: str = "Phase 2",
        execution_mode: str = "planner",
        routed_role: str = "planner",
        routed_cli: str = "codex",
        routed_model: str = "gpt-5.4-mini",
        current_artifact: str | None = None,
        review_bundle: str = "none",
        prompt_bundle_path: str = "none",
        output_capture_paths: tuple[str, ...] = (),
        evidence_used: tuple[str, ...] = (),
        findings: str = "- none",
    ) -> str:
        current_artifact = current_artifact or f"/.recursive/run/{self.run_id}/02-to-be-plan.md"
        output_capture_lines = "\n".join(f"  - `{path}`" for path in output_capture_paths) or "  - none"
        evidence_lines = "\n".join(f"- `{path}`" for path in evidence_used) or "- none"
        return f"""# Subagent Action Record

## Metadata
- Subagent ID: `worker-1`
- Run ID: `{self.run_id}`
- Phase: `{phase}`
- Purpose: `delegated benchmark work`
- Execution Mode: `{execution_mode}`
- Timestamp: `2026-01-01T00:00:00Z`
- Action Record Path: `/.recursive/run/{self.run_id}/subagents/{action_name}`

## Inputs Provided
- Current Artifact: `{current_artifact}`
- Artifact Content Hash: `fixture`
- Upstream Artifacts:
  - `/.recursive/run/{self.run_id}/01-as-is.md`
- Addenda:
  - none
- Review Bundle: `{review_bundle}`
- Diff Basis: `baseline..working-tree`
- Code Refs:
  - `/src/app.rs`
- Memory Refs:
  - none
- Audit / Task Questions:
  - complete the routed task

## Routing
- Router Used: `recursive-router`
- Routed Role: `{routed_role}`
- Routed CLI: `{routed_cli}`
- Routed Model: `{routed_model}`
- Routing Config Path: `/.recursive/config/recursive-router.json`
- Routing Discovery Path: `/.recursive/config/recursive-router-discovered.json`
- Routing Resolution Basis: `role_routes.{routed_role}`
- Routing Fallback Reason: `none`
- CLI Probe Summary: `available`
- Prompt Bundle Path: `{prompt_bundle_path}`
- Invocation Exit Code: `0`
- Output Capture Paths:
{output_capture_lines}

## Claimed Actions Taken
- completed routed benchmark work

## Claimed File Impact
### Created
- none
### Modified
- none
### Reviewed
- `/src/app.rs`
### Relevant but Untouched
- none

## Claimed Artifact Impact
### Read
- `/.recursive/run/{self.run_id}/02-to-be-plan.md`
### Updated
- none
### Evidence Used
{evidence_lines}

## Claimed Findings
{findings}

## Verification Handoff
- Inspect first:
  - `/src/app.rs`
- Notes:
  - controller verification required
"""

    def _write_routed_provenance(
        self,
        run_root: Path,
        *,
        stem: str,
        routed_role: str = "planner",
        routed_cli: str = "codex",
        routed_model: str = "gpt-5.4-mini",
        output_text: str = "bounded routed response",
    ) -> tuple[str, tuple[str, str]]:
        prompt_path = run_root / "router-prompts" / f"{stem}.md"
        output_path = run_root / "evidence" / "router" / f"{stem}-output.md"
        receipt_path = run_root / "evidence" / "router" / f"{stem}-invocation.json"
        prompt_display = f"/.recursive/run/{self.run_id}/router-prompts/{stem}.md"
        output_display = f"/.recursive/run/{self.run_id}/evidence/router/{stem}-output.md"
        receipt_display = f"/.recursive/run/{self.run_id}/evidence/router/{stem}-invocation.json"
        self._write(prompt_path, f"Perform the bounded {routed_role} task.")
        self._write(output_path, output_text)
        self._write(
            receipt_path,
            json.dumps(
                {
                    "role": routed_role,
                    "decision": {
                        "role": routed_role,
                        "decision": "external-cli",
                        "cli": routed_cli,
                        "model": routed_model,
                        "config_path": ".recursive/config/recursive-router.json",
                        "discovery_path": ".recursive/config/recursive-router-discovered.json",
                    },
                    "cli": routed_cli,
                    "model": routed_model,
                    "output_text": output_text,
                    "exit_code": 0,
                    "success": True,
                    "prompt_source": "file",
                    "prompt_bundle_path": prompt_display.lstrip("/"),
                },
                indent=2,
            ),
        )
        return prompt_display, (output_display, receipt_display)

    def _write_canonical_routed_action_fixture(
        self,
        run_root: Path,
        *,
        stem: str = "planner",
    ) -> tuple[Path, str, dict[str, tuple[str, str]], str, tuple[str, str]]:
        subagents = run_root / "subagents"
        subagents.mkdir(exist_ok=True)
        action_name = f"{stem}.md"
        action_path = subagents / action_name
        prompt_path, capture_paths = self._write_routed_provenance(run_root, stem=stem)
        content = self._canonical_routed_action(
            action_name=action_name,
            prompt_bundle_path=prompt_path,
            output_capture_paths=capture_paths,
            evidence_used=capture_paths,
        )
        self._write(action_path, content)
        return (
            action_path,
            content,
            {"planner": ("codex", "gpt-5.4-mini")},
            prompt_path,
            capture_paths,
        )

    def test_seeded_run_requirements_are_locked_recursive_artifact(self) -> None:
        content = self.harness.render_seeded_run_requirements(self.run_id)

        self.assertIn(f"Run: `/.recursive/run/{self.run_id}/`", content)
        self.assertIn("Phase: `00 Requirements`", content)
        self.assertIn("Status: `LOCKED`", content)
        self.assertNotIn("Workflow version:", content)
        self.assertIn("## TODO", content)
        self.assertIn("## Requirements", content)
        self.assertIn("## Out of Scope", content)
        self.assertIn("## Constraints", content)
        self.assertNotIn("## Assumptions", content)
        self.assertIn("Coverage: PASS", content)
        self.assertIn("Approval: PASS", content)
        lock_hash = re.search(r"LockHash: `([0-9a-f]{64})`", content)
        self.assertIsNotNone(lock_hash)
        self.assertEqual(
            rrb.lock_hash_from_content(content.rstrip() + "\n"),
            lock_hash.group(1),
        )
        self.assertIn("### `R7` Quality gates", content)

    def test_dependency_provisioning_is_disabled_for_unit_fixtures_but_retained_as_integration_seam(self) -> None:
        logs_root = self.workspace_root / "provisioning-seam"
        logs_root.mkdir(parents=True)
        result = self._make_result()
        self.harness.prepare_rust_wasm_toolchain = mock.Mock()  # type: ignore[method-assign]

        self.harness.provision_scenario_dependencies(self.repo_root, logs_root, result)
        self.harness.prepare_rust_wasm_toolchain.assert_not_called()

        self.harness.provision_dependencies = True
        self.harness.provision_scenario_dependencies(self.repo_root, logs_root, result)
        self.harness.prepare_rust_wasm_toolchain.assert_called_once_with(logs_root, result)

    def test_prebuilt_trunk_download_failure_still_returns_false_for_cargo_fallback(self) -> None:
        logs_root = self.workspace_root / "prebuilt-trunk-fallback"
        logs_root.mkdir(parents=True)
        result = self._make_result()
        toolchain_root = self.temp_dir / "toolchain"
        self.harness.resolve_trunk_asset_name = mock.Mock(return_value="trunk-test.tar.gz")  # type: ignore[method-assign]
        self.harness.benchmark_toolchain_root = mock.Mock(return_value=toolchain_root)  # type: ignore[method-assign]

        with mock.patch.object(rrb.urllib.request, "urlopen", side_effect=OSError("offline fixture")):
            downloaded = self.harness.try_download_prebuilt_trunk(logs_root, result)

        self.assertFalse(downloaded)
        self.assertIn("trunk_download", result.log_paths)
        self.assertIn("offline fixture", (logs_root / "trunk-download.log").read_text(encoding="utf-8"))

    def test_seeded_recursive_templates_include_phase2_and_repo_root_relative_worktree_examples(self) -> None:
        templates = self.harness.render_recursive_template_files(
            self.run_id,
            f".worktrees/{self.run_id}",
            "a" * 40,
        )

        self.assertIn("00-worktree.md", templates)
        self.assertIn("02-to-be-plan.md", templates)
        self.assertIn("03-implementation-summary.md", templates)
        self.assertIn("benchmark/recursive-templates/", templates["00-worktree.md"])
        self.assertIn("Implementation Surface:", templates["02-to-be-plan.md"])
        self.assertIn("Verification Surface:", templates["02-to-be-plan.md"])
        self.assertIn("QA Surface:", templates["02-to-be-plan.md"])
        self.assertIn("## Test Surface", templates["02-to-be-plan.md"])
        test_surface_rows = [
            line
            for line in templates["02-to-be-plan.md"].splitlines()
            if line.startswith("- TS-")
        ]
        expected_criteria = [
            (spec.requirement_id, criterion)
            for spec in self.harness.benchmark_requirement_specs()
            for criterion in spec.acceptance_criteria
        ]
        self.assertEqual(len(expected_criteria), len(test_surface_rows))
        for requirement_id, criterion in expected_criteria:
            self.assertTrue(
                any(
                    f"Requirement: {requirement_id} | Behavior: {criterion} |" in row
                    for row in test_surface_rows
                ),
                f"missing criterion-level Test Surface for {requirement_id}: {criterion}",
            )
        self.assertTrue(
            any(
                "Behavior: Calculator state or recent history persists in browser-local storage across reloads."
                in row
                and "Seam: browser reload boundary and browser-local persisted state" in row
                for row in test_surface_rows
            )
        )
        self.assertTrue(
            any(
                "Behavior: `cargo test` succeeds." in row
                and "Seam: command boundary: `cargo test`" in row
                for row in test_surface_rows
            )
        )
        self.assertTrue(
            any(
                "Behavior: The implementation includes meaningful automated tests for expression evaluation, "
                "scientific-function correctness, angle-mode behavior, and at least one error case."
                in row
                and "Seam: command boundary: `cargo test`" in row
                for row in test_surface_rows
            )
        )
        self.assertFalse(any("public product behavior under" in row for row in test_surface_rows))
        self.assertIn("## Review Metadata", templates["03-implementation-summary.md"])
        self.assertIn(f".worktrees/{self.run_id}/src/main.rs", templates["02-to-be-plan.md"])
        self.assertNotIn("## Gaps Found", templates["03-implementation-summary.md"])
        self.assertNotIn("## Repair Work Performed", templates["03-implementation-summary.md"])
        self.assertNotIn("## Audit Verdict", templates["03-implementation-summary.md"])
        self.assertIn("TDD Compliance: FAIL", templates["03-implementation-summary.md"])
        self.assertIn(f".recursive/run/{self.run_id}/evidence/screenshots/replace-me.png", templates["02-to-be-plan.md"])
        self.assertIn("None because", templates["01-as-is.md"])
        self.assertIn("Prefer file-only screenshot capture", templates["04-test-summary.md"])
        self.assertIn(f"`{'a' * 40}`", templates["00-worktree.md"])

    def test_seed_recursive_templates_creates_run_evidence_directories(self) -> None:
        template_root = self.repo_root / "benchmark" / "recursive-templates"

        self.harness.seed_recursive_run_templates(
            template_root,
            self.run_id,
            f".worktrees/{self.run_id}",
            "b" * 40,
        )

        evidence_root = self.repo_root / ".recursive" / "run" / self.run_id / "evidence"
        self.assertTrue((evidence_root / "logs" / "baseline").is_dir())
        self.assertTrue((evidence_root / "logs" / "green").is_dir())
        self.assertTrue((evidence_root / "manual").is_dir())
        self.assertTrue((evidence_root / "screenshots").is_dir())
        self.assertTrue((evidence_root / "router").is_dir())
        self.assertTrue((self.repo_root / ".recursive" / "run" / self.run_id / "router-prompts").is_dir())

    def test_sync_recursive_run_evidence_copies_green_logs_and_screenshots(self) -> None:
        run_root = self.repo_root / ".recursive" / "run" / self.run_id
        logs_root = self.workspace_root / "codex" / "recursive-on" / "logs"
        logs_root.mkdir(parents=True, exist_ok=True)
        self._write(logs_root / "build.log", "build ok")
        self._write(logs_root / "test.log", "test ok")
        self._write(logs_root / "preview.log", "preview ok")
        self._write(self.worktree_root / "benchmark" / "screenshots" / "ui.png", "png-data")
        result = self._make_result()

        self.harness.sync_recursive_run_evidence(self.repo_root, self.worktree_root, logs_root, result)

        self.assertTrue((run_root / "evidence" / "logs" / "green" / "build.log").exists())
        self.assertTrue((run_root / "evidence" / "logs" / "green" / "test.log").exists())
        self.assertTrue((run_root / "evidence" / "logs" / "green" / "preview.log").exists())
        self.assertTrue((run_root / "evidence" / "screenshots" / "ui.png").exists())

    def test_repo_activity_payload_detects_real_repo_file_changes(self) -> None:
        result = self._make_result()
        result.repo_root = str(self.repo_root)
        tracked_file = self.repo_root / "README.md"

        self.harness.reset_repo_activity_baseline(result)
        time.sleep(0.01)
        tracked_file.write_text("# changed\n", encoding="utf-8")

        payload = self.harness.current_repo_activity_payload(result)

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(True, payload["repo_exists"])
        self.assertGreaterEqual(int(payload["changed_since_start_count"]), 1)
        self.assertIn("README.md", payload["recent_changed_paths"])
        self.assertIsNotNone(payload["last_change_at"])

    def test_write_arm_progress_records_repo_activity_snapshot(self) -> None:
        result = self._make_result()
        result.repo_root = str(self.repo_root)
        tracked_file = self.repo_root / "README.md"

        self.harness.reset_repo_activity_baseline(result)
        time.sleep(0.01)
        tracked_file.write_text("# changed again\n", encoding="utf-8")

        self.harness.write_arm_progress(result, "agent-running", detail="Checking repo activity.")

        progress_payload = json.loads(self.harness.arm_progress_path(result).read_text(encoding="utf-8"))
        self.assertIn("repo_activity", progress_payload)
        self.assertGreaterEqual(progress_payload["repo_activity"]["changed_since_start_count"], 1)
        self.assertIn("README.md", progress_payload["repo_activity"]["recent_changed_paths"])

    def test_recursive_on_prompt_only_references_existing_control_plane_files(self) -> None:
        prepared_repo = self.temp_dir / "prepared-repo"
        logs_root = self.workspace_root / "codex" / "recursive-on" / "logs"
        result = rrb.ArmResult(
            runner_slug="codex",
            runner_name="Codex CLI",
            provider_family="codex",
            model="gpt-5.4",
            arm_name="recursive-on",
        )
        runner = self.harness.runner_configs[0]

        self.harness.prepare_repo(prepared_repo, logs_root, runner, result, recursive_on=True)
        prompt_text, _ = self.harness.render_prompt(self.workspace_root / "prompts", result)

        read_block = re.search(r"(?ms)^Read:\s*$\n(.*?)(?=^\s*$|^Rules:\s*$)", prompt_text)
        self.assertIsNotNone(read_block)
        prompt_paths = [
            line.strip()[2:].strip().strip("`")
            for line in read_block.group(1).splitlines()
            if line.strip().startswith("- ")
        ]

        missing_paths = [path for path in prompt_paths if not (prepared_repo / Path(path)).exists()]
        self.assertEqual([], missing_paths, f"Prompt referenced missing files: {missing_paths}")
        discovery_path = prepared_repo / ".recursive" / "config" / "recursive-router-discovered.json"
        if discovery_path.exists():
            self.assertNotIn("If `/.recursive/config/recursive-router-discovered.json` is absent", prompt_text)
        else:
            self.assertIn(
                "If `/.recursive/config/recursive-router-discovered.json` is absent",
                prompt_text,
            )

    def test_prepare_repo_recursive_on_seeds_recursive_skill_docs(self) -> None:
        prepared_repo = self.temp_dir / "prepared-repo-skills"
        logs_root = self.workspace_root / "codex" / "recursive-on" / "logs"
        result = rrb.ArmResult(
            runner_slug="codex",
            runner_name="Codex CLI",
            provider_family="codex",
            model="gpt-5.4",
            arm_name="recursive-on",
        )
        runner = self.harness.runner_configs[0]

        self.harness.prepare_repo(prepared_repo, logs_root, runner, result, recursive_on=True)

        seeded_root = prepared_repo / "benchmark" / "recursive-skills"
        expected_docs = {
            skill_name: path
            for skill_name, path in self.harness.recursive_skill_doc_sources().items()
        }
        self.assertTrue(seeded_root.exists())
        for skill_name, source_path in expected_docs.items():
            with self.subTest(skill=skill_name):
                target_path = seeded_root / skill_name / "SKILL.md"
                self.assertTrue(target_path.exists())
                self.assertEqual(source_path.read_text(encoding="utf-8"), target_path.read_text(encoding="utf-8"))

    def test_prepare_repo_recursive_on_seeds_recursive_helper_scripts(self) -> None:
        prepared_repo = self.temp_dir / "prepared-repo-helper-scripts"
        logs_root = self.workspace_root / "codex" / "recursive-on" / "logs"
        result = rrb.ArmResult(
            runner_slug="codex",
            runner_name="Codex CLI",
            provider_family="codex",
            model="gpt-5.4",
            arm_name="recursive-on",
        )
        runner = self.harness.runner_configs[0]

        self.harness.prepare_repo(prepared_repo, logs_root, runner, result, recursive_on=True)

        expected_scripts = [
            "scripts/recursive-review-bundle.py",
            "scripts/recursive-review-bundle.ps1",
            "scripts/recursive-subagent-action.py",
            "scripts/recursive-subagent-action.ps1",
            "scripts/recursive-router-probe.py",
            "scripts/recursive-router-probe.ps1",
            "scripts/recursive-router-invoke.py",
            "scripts/recursive-router-invoke.ps1",
            "scripts/recursive_router_lib.py",
            "scripts/recursive_phase_rules.py",
            "scripts/recursive_review_action.py",
            "scripts/recursive_review_ledger.py",
            "scripts/recursive_review_surface.py",
        ]
        for relative_path in expected_scripts:
            with self.subTest(path=relative_path):
                target_path = prepared_repo / Path(relative_path)
                source_path = self.harness.runtime_dir / Path(relative_path).name
                self.assertTrue(target_path.exists(), f"Expected helper script to exist: {relative_path}")
                self.assertEqual(source_path.read_text(encoding="utf-8"), target_path.read_text(encoding="utf-8"))
        for helper_name in (
            "recursive-review-bundle.py",
            "recursive-subagent-action.py",
            "lint-recursive-run.py",
            "verify-locks.py",
        ):
            with self.subTest(importable=helper_name):
                help_result = subprocess.run(
                    [sys.executable, str(prepared_repo / "scripts" / helper_name), "--help"],
                    cwd=prepared_repo,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(0, help_result.returncode, help_result.stdout + help_result.stderr)

    def test_recursive_on_prompt_calls_out_lint_critical_headings_and_closeout_receipts(self) -> None:
        prompt_text, _ = self.harness.render_prompt(self.workspace_root / "prompts", self._make_result())
        prompt_text_lower = prompt_text.lower()

        self.assertIn("keep the required `## todo` heading", prompt_text_lower)
        self.assertIn("benchmark/recursive-templates/", prompt_text)
        self.assertIn("benchmark/recursive-skills/", prompt_text)
        self.assertIn("`## Changes Applied`", prompt_text)
        self.assertIn(
            "`05-manual-qa.md`, `06-decisions-update.md`, `07-state-update.md`, and `08-memory-impact.md`",
            prompt_text,
        )
        self.assertIn("distinct from the Phase 3 implementation evidence", prompt_text)
        self.assertIn("bootstrapped control-plane files under the worktree", prompt_text)
        self.assertIn("`Compensating validation:` field", prompt_text)
        self.assertIn(".recursive/config/recursive-router.json", prompt_text)
        self.assertIn(".recursive/config/recursive-router-discovered.json", prompt_text)
        self.assertIn("create or refresh it first with `python scripts/recursive-router-probe.py --repo-root . --json`", prompt_text)
        self.assertIn("follow that routed policy instead of inventing or hardcoding a cli/model", prompt_text_lower)
        self.assertIn("contains benchmark-local copies of the recursive skill docs", prompt_text)
        self.assertIn("If planner is routed, make a bounded planner call during Phase 2 before locking `02-to-be-plan.md`", prompt_text)
        self.assertIn("Do not defer all routed delegation until the end merely to save time", prompt_text)
        self.assertIn("Timeout or latency by itself is not a valid override reason for skipping a configured routed stage", prompt_text)
        self.assertIn("`python scripts/recursive-router-invoke.py`", prompt_text)
        self.assertIn("`python scripts/recursive-subagent-action.py`", prompt_text)

    def test_recursive_on_prompt_prefers_distinct_cli_when_route_matches_runner(self) -> None:
        logs_root = self.workspace_root / "kimi" / "recursive-on" / "logs"
        logs_root.mkdir(parents=True, exist_ok=True)
        result = self._make_result()
        result.runner_slug = "kimi"
        result.runner_name = "Kimi CLI"
        result.provider_family = "moonshot-kimi"
        result.model = "kimi-k2.6"
        repo_root = self.workspace_root / "kimi" / "recursive-on" / "repo"
        runner = rrb.RunnerConfig(
            slug="kimi",
            display_name="Kimi CLI",
            provider_family="moonshot-kimi",
            executable="C:\\Users\\fixture\\.local\\bin\\kimi.exe",
            model="kimi-k2.6",
            supports_json=False,
        )

        self.harness.prepare_repo(repo_root, logs_root, runner, result, recursive_on=True)
        self._write(
            repo_root / ".recursive" / "config" / "recursive-router.json",
            json.dumps(
                {
                    "role_routes": {
                        "planner": {
                            "enabled": True,
                            "mode": "external-cli",
                            "cli": "kimi",
                            "model": "kimi-code/kimi-for-coding",
                            "fallback": "self-audit",
                        },
                        "tester": {
                            "enabled": True,
                            "mode": "external-cli",
                            "cli": "codex",
                            "model": "gpt-5.3-codex",
                            "fallback": "self-audit",
                        },
                    },
                    "cli_overrides": {
                        "kimi": {"command": "C:\\Users\\fixture\\.local\\bin\\kimi.exe"},
                        "codex": {"command": "C:\\Users\\fixture\\.local\\bin\\codex.exe"},
                    },
                },
                indent=2,
            ),
        )

        prompt_text, _ = self.harness.render_prompt(self.workspace_root / "prompts", result)

        self.assertIn("planner` resolves to the same CLI as the orchestrator runner (`kimi`)", prompt_text)
        self.assertIn("Prefer the earliest later routed stage whose CLI differs from `kimi`", prompt_text)
        self.assertIn("tester->codex", prompt_text)
        self.assertIn("You must satisfy durable external routed evidence with one of these distinct routes no later than Phase 4 / `04-test-summary.md`", prompt_text)
        self.assertIn("If a same-runner routed call fails, do not lock or advance the current stage", prompt_text)
        self.assertNotIn("record that concrete failure once and continue with the earliest distinct-CLI routed stage", prompt_text)

    def test_recursive_on_prompt_includes_controller_stage_route_plan(self) -> None:
        logs_root = self.workspace_root / "kimi" / "recursive-on" / "logs"
        logs_root.mkdir(parents=True, exist_ok=True)
        result = self._make_result()
        result.runner_slug = "kimi"
        result.runner_name = "Kimi CLI"
        result.provider_family = "moonshot-kimi"
        result.model = "kimi-k2.6"
        repo_root = self.workspace_root / "kimi" / "recursive-on" / "repo"
        runner = rrb.RunnerConfig(
            slug="kimi",
            display_name="Kimi CLI",
            provider_family="moonshot-kimi",
            executable="C:\\Users\\fixture\\.local\\bin\\kimi.exe",
            model="kimi-k2.6",
            supports_json=False,
        )

        self.harness.prepare_repo(repo_root, logs_root, runner, result, recursive_on=True)
        self._write(
            repo_root / ".recursive" / "config" / "recursive-router.json",
            json.dumps(
                {
                    "role_routes": {
                        "analyst": {
                            "enabled": True,
                            "mode": "external-cli",
                            "cli": "codex",
                            "model": "gpt-5.4-mini",
                            "fallback": "self-audit",
                        },
                        "planner": {
                            "enabled": True,
                            "mode": "external-cli",
                            "cli": "kimi",
                            "model": "kimi-code/kimi-for-coding",
                            "fallback": "self-audit",
                        },
                        "code-reviewer": {
                            "enabled": True,
                            "mode": "external-cli",
                            "cli": "opencode",
                            "model": "github-copilot/claude-sonnet-4.6",
                            "fallback": "self-audit",
                        },
                        "tester": {
                            "enabled": True,
                            "mode": "external-cli",
                            "cli": "codex",
                            "model": "gpt-5.3-codex",
                            "fallback": "self-audit",
                        },
                        "memory-auditor": {
                            "enabled": True,
                            "mode": "external-cli",
                            "cli": "opencode",
                            "model": "github-copilot/gpt-5-mini",
                            "fallback": "self-audit",
                        },
                    },
                    "cli_overrides": {
                        "kimi": {"command": "C:\\Users\\fixture\\.local\\bin\\kimi.exe"},
                        "codex": {"command": "C:\\Users\\fixture\\.local\\bin\\codex.exe"},
                        "opencode": {"command": "C:\\Users\\fixture\\.local\\bin\\opencode.exe"},
                    },
                },
                indent=2,
            ),
        )

        prompt_text, _ = self.harness.render_prompt(self.workspace_root / "prompts", result)

        self.assertIn("benchmark/recursive-stage-routing.md", prompt_text)
        self.assertIn("benchmark/recursive-skills/recursive-subagent/SKILL.md", prompt_text)
        self.assertIn("Controller-coordinated routed stage plan for this run:", prompt_text)
        self.assertIn(
            f"Review Bundle Path: `/.recursive/run/{result.run_id}/evidence/review-bundles/<phase-key>/<review-id>/<NNNN>.md`",
            prompt_text,
        )
        self.assertIn(
            f"Review Ledger Path: `/.recursive/run/{result.run_id}/evidence/reviews/<phase-key>/<review-id>/ledger.md`",
            prompt_text,
        )
        self.assertIn(
            "Phase 1 / `01-as-is.md`: `analyst` -> `codex` (`gpt-5.4-mini`)",
            prompt_text,
        )
        self.assertIn(
            "Phase 2 / `02-to-be-plan.md`: `planner` -> `kimi` (`kimi-code/kimi-for-coding`) [same CLI as orchestrator runner]",
            prompt_text,
        )
        self.assertIn(
            "Phase 3.5 / `03.5-code-review.md`: `code-reviewer` -> `opencode` (`github-copilot/claude-sonnet-4.6`) [distinct CLI evidence candidate]",
            prompt_text,
        )
        self.assertIn(
            "Handoff: write the routed action record, reconcile it into `03.5-code-review.md`, lock it, and only then advance to Phase 4 / `04-test-summary.md`.",
            prompt_text,
        )
        self.assertIn(
            "Phase 4 / `04-test-summary.md`: `tester` -> `codex` (`gpt-5.3-codex`) [distinct CLI evidence candidate; complete by this stage if still missing]",
            prompt_text,
        )
        self.assertIn(
            "Phase 8 / `08-memory-impact.md`: `memory-auditor` -> `opencode` (`github-copilot/gpt-5-mini`)",
            prompt_text,
        )
        self.assertTrue((repo_root / "benchmark" / "recursive-stage-routing.md").exists())

    def test_has_configured_recursive_router_policy_requires_real_route_or_override(self) -> None:
        placeholder_policy = self.temp_dir / "placeholder-router.json"
        self._write(
            placeholder_policy,
            json.dumps(
                {
                    "role_routes": {
                        "analyst": {
                            "enabled": True,
                            "mode": "external-cli",
                            "cli": None,
                            "model": None,
                            "fallback": "self-audit",
                        }
                    },
                    "cli_overrides": {},
                },
                indent=2,
            ),
        )
        configured_policy = self.temp_dir / "configured-router.json"
        self._write(
            configured_policy,
            json.dumps(
                {
                    "role_routes": {
                        "analyst": {
                            "enabled": True,
                            "mode": "external-cli",
                            "cli": "codex",
                            "model": "gpt-5.4-mini",
                            "fallback": "self-audit",
                        }
                    },
                    "cli_overrides": {"codex": {"command": "C:\\codex.exe"}},
                },
                indent=2,
            ),
        )

        self.assertFalse(self.harness.has_configured_recursive_router_policy(placeholder_policy))
        self.assertTrue(self.harness.has_configured_recursive_router_policy(configured_policy))

    def test_has_configured_recursive_router_policy_fails_closed_for_unsafe_input(self) -> None:
        configured_payload = json.dumps(
            {
                "role_routes": {
                    "analyst": {
                        "enabled": True,
                        "mode": "external-cli",
                        "cli": "codex",
                        "model": "gpt-5.4-mini",
                    }
                },
                "cli_overrides": {"codex": {"command": "codex"}},
            }
        )
        for unsafe_kind in ("malformed-json", "malformed-schema", "invalid-utf8", "symlink", "hardlink"):
            with self.subTest(unsafe_kind=unsafe_kind):
                policy_path = self.temp_dir / f"unsafe-router-{unsafe_kind}.json"
                if unsafe_kind == "malformed-json":
                    self._write(policy_path, '{"role_routes":')
                elif unsafe_kind == "malformed-schema":
                    self._write(
                        policy_path,
                        json.dumps(
                            {
                                "role_routes": {
                                    "analyst": {
                                        "enabled": 1,
                                        "mode": "external-cli",
                                        "cli": "codex",
                                        "model": "gpt-5.4-mini",
                                    }
                                },
                                "cli_overrides": {},
                            }
                        ),
                    )
                elif unsafe_kind == "invalid-utf8":
                    policy_path.write_bytes(b"\xff\xfe")
                else:
                    external_path = self.temp_dir / f"external-router-{unsafe_kind}.json"
                    self._write(external_path, configured_payload)
                    try:
                        if unsafe_kind == "symlink":
                            policy_path.symlink_to(external_path)
                        else:
                            os.link(external_path, policy_path)
                    except (NotImplementedError, OSError) as exc:
                        self.skipTest(f"{unsafe_kind} is unavailable: {exc}")

                self.assertFalse(
                    self.harness.has_configured_recursive_router_policy(policy_path)
                )

    def test_router_config_sync_skips_unsafe_policy_even_with_safe_discovery(self) -> None:
        configured_payload = json.dumps(
            {
                "role_routes": {
                    "analyst": {
                        "enabled": True,
                        "mode": "external-cli",
                        "cli": "codex",
                        "model": "gpt-5.4-mini",
                    }
                },
                "cli_overrides": {"codex": {"command": "codex"}},
            }
        )
        safe_discovery = json.dumps(
            {
                "version": 1,
                "probe_tool": "recursive-router-probe",
                "probe_status": "ok",
                "clis": [],
            }
        )
        for unsafe_kind in (
            "malformed-json",
            "malformed-schema",
            "invalid-utf8",
            "symlink",
            "hardlink",
        ):
            with self.subTest(unsafe_kind=unsafe_kind):
                source_root = self.temp_dir / f"unsafe-sync-{unsafe_kind}" / "source"
                target_root = self.temp_dir / f"unsafe-sync-{unsafe_kind}" / "target"
                source_root.mkdir(parents=True)
                policy_path = source_root / "recursive-router.json"
                self._write(source_root / "recursive-router-discovered.json", safe_discovery)
                if unsafe_kind == "malformed-json":
                    self._write(policy_path, '{"role_routes":')
                elif unsafe_kind == "malformed-schema":
                    self._write(
                        policy_path,
                        json.dumps(
                            {
                                "role_routes": {
                                    "analyst": {
                                        "enabled": 1,
                                        "mode": "external-cli",
                                        "cli": "codex",
                                        "model": "gpt-5.4-mini",
                                    }
                                },
                                "cli_overrides": {},
                            }
                        ),
                    )
                elif unsafe_kind == "invalid-utf8":
                    policy_path.write_bytes(b"\xff\xfe")
                else:
                    external_path = self.temp_dir / f"sync-external-router-{unsafe_kind}.json"
                    self._write(external_path, configured_payload)
                    try:
                        if unsafe_kind == "symlink":
                            policy_path.symlink_to(external_path)
                        else:
                            os.link(external_path, policy_path)
                    except (NotImplementedError, OSError) as exc:
                        self.skipTest(f"{unsafe_kind} is unavailable: {exc}")

                self.assertTrue(
                    self.harness.should_bootstrap_recursive_router_config(source_root)
                )
                changed = self.harness.sync_recursive_router_config_tree(
                    source_root,
                    target_root,
                )

                self.assertTrue(changed)
                self.assertFalse((target_root / "recursive-router.json").exists())
                self.assertTrue(
                    (target_root / "recursive-router-discovered.json").is_file()
                )

    def test_sync_recursive_router_config_into_worktree_copies_configured_policy(self) -> None:
        result = self._make_result()
        source_config_root = self.repo_root / ".recursive" / "config"
        source_config_root.mkdir(parents=True, exist_ok=True)
        target_config_root = self.worktree_root / ".recursive" / "config"
        target_config_root.mkdir(parents=True, exist_ok=True)
        source_policy = {
            "version": 1,
            "role_routes": {
                "analyst": {
                    "enabled": True,
                    "mode": "external-cli",
                    "cli": "codex",
                    "model": "gpt-5.4-mini",
                    "fallback": "self-audit",
                },
                "memory-auditor": {
                    "enabled": True,
                    "mode": "external-cli",
                    "cli": "opencode",
                    "model": "github-copilot/gpt-5.4-mini",
                    "fallback": "self-audit",
                },
            },
            "cli_overrides": {
                "codex": {"command": "C:\\codex.exe"},
                "opencode": {"command": "D:\\opencode\\opencode-cli.exe"},
            },
        }
        discovered = {"version": 1, "probe_tool": "recursive-router-probe", "probe_status": "complete", "clis": []}
        self._write(source_config_root / "recursive-router.json", json.dumps(source_policy, indent=2))
        self._write(source_config_root / "recursive-router-discovered.json", json.dumps(discovered, indent=2))
        self._write(
            target_config_root / "recursive-router.json",
            json.dumps(
                {
                    "version": 1,
                    "role_routes": {
                        "analyst": {
                            "enabled": True,
                            "mode": "external-cli",
                            "cli": None,
                            "model": None,
                            "fallback": "self-audit",
                        }
                    },
                    "cli_overrides": {},
                },
                indent=2,
            ),
        )

        changed = self.harness.sync_recursive_router_config_into_worktree(self.repo_root, result)

        self.assertTrue(changed)
        synced_policy = json.loads((target_config_root / "recursive-router.json").read_text(encoding="utf-8"))
        self.assertEqual("codex", synced_policy["role_routes"]["analyst"]["cli"])
        self.assertEqual("gpt-5.4-mini", synced_policy["role_routes"]["analyst"]["model"])
        self.assertEqual(
            "github-copilot/gpt-5.4-mini",
            synced_policy["role_routes"]["memory-auditor"]["model"],
        )
        synced_discovery = json.loads((target_config_root / "recursive-router-discovered.json").read_text(encoding="utf-8"))
        self.assertEqual("complete", synced_discovery["probe_status"])

    def test_should_bootstrap_recursive_router_config_accepts_legacy_configured_policy(self) -> None:
        source_config_root = self.repo_root / ".recursive" / "config"
        source_config_root.mkdir(parents=True, exist_ok=True)
        self._write(
            source_config_root / "recursive-router-cli.json",
            json.dumps(
                {
                    "version": 1,
                    "role_routes": {
                        "analyst": {
                            "enabled": True,
                            "mode": "external-cli",
                            "cli": "codex",
                            "model": "gpt-5.4-mini",
                            "fallback": "self-audit",
                        }
                    },
                    "cli_overrides": {"codex": {"command": "C:\\codex.exe"}},
                },
                indent=2,
            ),
        )

        self.assertTrue(self.harness.should_bootstrap_recursive_router_config(source_config_root))

    def test_sync_recursive_router_config_tree_migrates_legacy_policy_to_canonical_name(self) -> None:
        source_config_root = self.repo_root / ".recursive" / "config"
        source_config_root.mkdir(parents=True, exist_ok=True)
        target_config_root = self.worktree_root / ".recursive" / "config"
        target_config_root.mkdir(parents=True, exist_ok=True)
        self._write(
            source_config_root / "recursive-router-cli.json",
            json.dumps(
                {
                    "version": 1,
                    "role_routes": {
                        "analyst": {
                            "enabled": True,
                            "mode": "external-cli",
                            "cli": "codex",
                            "model": "gpt-5.4-mini",
                            "fallback": "self-audit",
                        }
                    },
                    "cli_overrides": {"codex": {"command": "C:\\codex.exe"}},
                },
                indent=2,
            ),
        )

        changed = self.harness.sync_recursive_router_config_tree(source_config_root, target_config_root)

        self.assertTrue(changed)
        synced_policy = json.loads((target_config_root / "recursive-router.json").read_text(encoding="utf-8"))
        self.assertEqual("codex", synced_policy["role_routes"]["analyst"]["cli"])
        self.assertFalse((target_config_root / "recursive-router-cli.json").exists())

    def test_resolve_runner_executable_prefers_router_cli_override(self) -> None:
        source_repo_root = self.temp_dir / "device-router-source"
        source_config_root = source_repo_root / ".recursive" / "config"
        source_config_root.mkdir(parents=True, exist_ok=True)
        fake_codex = self.temp_dir / "bin" / "codex.exe"
        fake_codex.parent.mkdir(parents=True, exist_ok=True)
        fake_codex.write_text("stub", encoding="utf-8")
        self._write(
            source_config_root / "recursive-router.json",
            json.dumps(
                {
                    "version": 1,
                    "role_routes": {},
                    "cli_overrides": {"codex": {"command": str(fake_codex)}},
                },
                indent=2,
            ),
        )
        self.harness.repo_source_root = source_repo_root

        with mock.patch.object(rrb.shutil, "which", return_value=None):
            resolved = self.harness.resolve_runner_executable("codex")

        self.assertEqual(str(fake_codex), resolved)

    def test_resolve_runner_executable_falls_back_to_discovered_inventory(self) -> None:
        source_repo_root = self.temp_dir / "device-router-discovered"
        source_config_root = source_repo_root / ".recursive" / "config"
        source_config_root.mkdir(parents=True, exist_ok=True)
        fake_opencode = self.temp_dir / "bin" / "opencode-cli.exe"
        fake_opencode.parent.mkdir(parents=True, exist_ok=True)
        fake_opencode.write_text("stub", encoding="utf-8")
        self._write(
            source_config_root / "recursive-router-discovered.json",
            json.dumps(
                {
                    "version": 1,
                    "probe_tool": "recursive-router-probe",
                    "probe_status": "ok",
                    "clis": [
                        {
                            "id": "opencode",
                            "available": True,
                            "command": str(fake_opencode),
                            "resolved_path": str(fake_opencode),
                        }
                    ],
                },
                indent=2,
            ),
        )
        self.harness.repo_source_root = source_repo_root

        with mock.patch.object(rrb.shutil, "which", return_value=None):
            resolved = self.harness.resolve_runner_executable("opencode")

        self.assertEqual(str(fake_opencode), resolved)

    def test_sync_source_recursive_router_config_into_repo_copies_device_local_routing(self) -> None:
        source_repo_root = self.temp_dir / "device-router-source"
        source_config_root = source_repo_root / ".recursive" / "config"
        source_config_root.mkdir(parents=True, exist_ok=True)
        target_repo_root = self.temp_dir / "benchmark-target"
        target_config_root = target_repo_root / ".recursive" / "config"
        source_policy = {
            "version": 1,
            "role_routes": {
                "analyst": {
                    "enabled": True,
                    "mode": "external-cli",
                    "cli": "codex",
                    "model": "gpt-5.4-mini",
                    "fallback": "self-audit",
                }
            },
            "cli_overrides": {
                "codex": {"command": "C:\\codex.exe"},
            },
        }
        discovered = {"version": 1, "probe_tool": "recursive-router-probe", "probe_status": "complete", "clis": []}
        self._write(source_config_root / "recursive-router.json", json.dumps(source_policy, indent=2))
        self._write(source_config_root / "recursive-router-discovered.json", json.dumps(discovered, indent=2))
        self.harness.repo_source_root = source_repo_root

        changed = self.harness.sync_source_recursive_router_config_into_repo(target_repo_root)

        self.assertTrue(changed)
        synced_policy = json.loads((target_config_root / "recursive-router.json").read_text(encoding="utf-8"))
        self.assertEqual("codex", synced_policy["role_routes"]["analyst"]["cli"])
        self.assertEqual("complete", json.loads((target_config_root / "recursive-router-discovered.json").read_text(encoding="utf-8"))["probe_status"])

    def test_sync_source_recursive_router_config_into_repo_skips_placeholder_defaults(self) -> None:
        source_repo_root = self.temp_dir / "device-router-placeholder"
        source_config_root = source_repo_root / ".recursive" / "config"
        source_config_root.mkdir(parents=True, exist_ok=True)
        target_repo_root = self.temp_dir / "benchmark-target-placeholder"
        source_policy = {
            "version": 1,
            "role_routes": {
                "analyst": {
                    "enabled": True,
                    "mode": "external-cli",
                    "cli": None,
                    "model": None,
                    "fallback": "self-audit",
                }
            },
            "cli_overrides": {},
        }
        self._write(source_config_root / "recursive-router.json", json.dumps(source_policy, indent=2))
        self.harness.repo_source_root = source_repo_root

        changed = self.harness.sync_source_recursive_router_config_into_repo(target_repo_root)

        self.assertFalse(changed)
        self.assertFalse((target_repo_root / ".recursive" / "config" / "recursive-router.json").exists())

    def test_start_recursive_router_worktree_sync_waits_for_late_worktree(self) -> None:
        late_repo_root = self.temp_dir / "late-router-sync-repo"
        late_repo_root.mkdir(parents=True, exist_ok=True)
        source_config_root = late_repo_root / ".recursive" / "config"
        source_config_root.mkdir(parents=True, exist_ok=True)
        source_policy = {
            "version": 1,
            "role_routes": {
                "analyst": {
                    "enabled": True,
                    "mode": "external-cli",
                    "cli": "codex",
                    "model": "gpt-5.4-mini",
                    "fallback": "self-audit",
                }
            },
            "cli_overrides": {"codex": {"command": "C:\\codex.exe"}},
        }
        self._write(source_config_root / "recursive-router.json", json.dumps(source_policy, indent=2))
        late_result = rrb.ArmResult(
            runner_slug="codex",
            runner_name="Codex CLI",
            provider_family="codex",
            model="gpt-5.4",
            arm_name="recursive-on",
            run_id="benchmark-codex-late",
            expected_product_root=".worktrees/benchmark-codex-late",
        )

        thread, stop_event = self.harness.start_recursive_router_worktree_sync(late_repo_root, late_result)
        self.assertIsNotNone(thread)
        self.assertIsNotNone(stop_event)
        self.addCleanup(stop_event.set)
        self.addCleanup(lambda: thread.join(timeout=2.0))

        worktree_config_root = late_repo_root / ".worktrees" / "benchmark-codex-late" / ".recursive" / "config"
        self.assertFalse((worktree_config_root / "recursive-router.json").exists())

        worktree_config_root.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if (worktree_config_root / "recursive-router.json").exists():
                break
            time.sleep(0.05)
        else:
            self.fail("Router sync watcher did not copy recursive-router.json into the late-created worktree.")

        synced_policy = json.loads((worktree_config_root / "recursive-router.json").read_text(encoding="utf-8"))
        self.assertEqual("codex", synced_policy["role_routes"]["analyst"]["cli"])

    def test_build_kimi_temp_config_clones_existing_model_alias_section(self) -> None:
        config_path = self.temp_dir / "kimi-config.toml"
        self._write(
            config_path,
            "\n".join(
                [
                    'default_model = "kimi-code/kimi-for-coding"',
                    "",
                    '[models."kimi-code/kimi-for-coding"]',
                    'provider = "managed:kimi-code"',
                    'model = "kimi-for-coding"',
                    "max_context_size = 262144",
                    'capabilities = ["thinking", "video_in"]',
                    "",
                    '[models."benchmark-kimi"]',
                    'provider = "stale"',
                    'model = "stale-model"',
                    "temperature = 0.1",
                ]
            ),
        )
        self.harness.kimi_config_path = config_path

        temp_path = self.harness.build_kimi_temp_config("kimi-code/kimi-for-coding")
        self.addCleanup(lambda: temp_path.unlink(missing_ok=True))

        updated = temp_path.read_text(encoding="utf-8")

        self.assertIn('default_model = "benchmark-kimi"', updated)
        self.assertIn('[models."benchmark-kimi"]', updated)
        self.assertIn('provider = "managed:kimi-code"', updated)
        self.assertIn('model = "kimi-for-coding"', updated)
        self.assertIn('capabilities = ["thinking", "video_in"]', updated)
        self.assertIn("temperature = 0.6", updated)
        self.assertEqual(1, updated.count('[models."benchmark-kimi"]'))

    def test_build_kimi_temp_config_fallback_strips_alias_prefix_from_model_name(self) -> None:
        config_path = self.temp_dir / "kimi-config-fallback.toml"
        self._write(
            config_path,
            "\n".join(
                [
                    'default_model = "default-kimi"',
                    "",
                    '[models."default-kimi"]',
                    'provider = "moonshot"',
                    'model = "kimi-k2.6"',
                ]
            ),
        )
        self.harness.kimi_config_path = config_path

        temp_path = self.harness.build_kimi_temp_config("kimi-code/kimi-for-coding")
        self.addCleanup(lambda: temp_path.unlink(missing_ok=True))

        updated = temp_path.read_text(encoding="utf-8")

        self.assertIn('[models."benchmark-kimi"]', updated)
        self.assertIn('provider = "moonshot"', updated)
        self.assertIn('model = "kimi-for-coding"', updated)
        self.assertNotIn('model = "kimi-code/kimi-for-coding"', updated)
        self.assertIn("temperature = 0.6", updated)

    def test_maybe_repair_recursive_run_prompts_for_missing_artifacts_and_lossless_review(self) -> None:
        logs_root = self.workspace_root / "codex" / "recursive-on" / "logs"
        logs_root.mkdir(parents=True, exist_ok=True)
        self._write(
            logs_root / "recursive-lint.log",
            "\n".join(
                [
                    "Linting run: benchmark-test-run",
                    "[FAIL] 01-as-is.md: Recursive review: phase ledger must reach whole-ledger PASS before closure",
                    "[WARN] Missing artifact (ok if not reached yet): .recursive/run/benchmark-test-run/03-implementation-summary.md",
                    "[WARN] Missing artifact (ok if not reached yet): .recursive/run/benchmark-test-run/05-manual-qa.md",
                ]
            ),
        )
        result = self._make_result()
        result.recursive_workflow_status = "incomplete"
        result.recursive_artifact_status = {
            "00-requirements.md": True,
            "00-worktree.md": True,
            "01-as-is.md": True,
            "02-to-be-plan.md": True,
            "03-implementation-summary.md": False,
            "04-test-summary.md": False,
            "05-manual-qa.md": False,
            "06-decisions-update.md": False,
            "07-state-update.md": False,
            "08-memory-impact.md": False,
        }
        captured: dict[str, object] = {}

        def fake_run_model_prompt(
            repo_root: Path,
            logs_root_arg: Path,
            *,
            runner_slug: str,
            executable: str | None,
            model: str,
            prompt_text: str,
            log_stem: str,
            timeout_seconds: int,
        ) -> tuple[rrb.CommandResult, Path, Path]:
            captured["prompt"] = prompt_text
            captured["log_stem"] = log_stem
            stdout_log = logs_root_arg / f"{log_stem}-output.jsonl"
            stderr_log = logs_root_arg / f"{log_stem}-stderr.log"
            stdout_log.write_text("", encoding="utf-8")
            stderr_log.write_text("", encoding="utf-8")
            return (
                rrb.CommandResult(command=["repair"], returncode=0, stdout="", stderr="", duration_seconds=1.0),
                stdout_log,
                stderr_log,
            )

        def fake_evaluate_recursive_run(repo_root: Path, logs_root_arg: Path, result_arg: rrb.ArmResult) -> None:
            captured["reevaluated"] = True
            result_arg.recursive_workflow_status = "complete"

        self.harness.run_model_prompt = fake_run_model_prompt  # type: ignore[method-assign]
        self.harness.evaluate_recursive_run = fake_evaluate_recursive_run  # type: ignore[method-assign]

        repair_record = self.harness.maybe_repair_recursive_run(
            self.repo_root,
            logs_root,
            self.harness.runner_configs[0],
            result,
        )

        self.assertIsNotNone(repair_record)
        prompt_text = captured["prompt"]
        self.assertIn("03-implementation-summary.md", prompt_text)
        self.assertIn("05-manual-qa.md", prompt_text)
        self.assertIn("Review Ledger Path", prompt_text)
        self.assertIn("Review Bundle Path", prompt_text)
        self.assertIn("whole-ledger PASS", prompt_text)
        self.assertIn("`Compensating validation:` field", prompt_text)
        self.assertTrue(captured["reevaluated"])
        self.assertEqual("complete", result.recursive_workflow_status)
        self.assertIn("recursive_repair_stdout", result.log_paths)
        self.assertIn("recursive_repair_stderr", result.log_paths)
        self.assertEqual("recursive-repair", captured["log_stem"])

    def test_recursive_repair_prompt_requires_changed_files_to_match_current_diff(self) -> None:
        logs_root = self.workspace_root / "codex" / "recursive-on" / "logs"
        logs_root.mkdir(parents=True, exist_ok=True)
        self._write(
            logs_root / "recursive-lint.log",
            "\n".join(
                [
                    "Linting run: benchmark-test-run",
                    "[FAIL] 03-implementation-summary.md: Requirement R7 Changed Files are outside the current diff scope: .recursive/DECISIONS.md, .recursive/STATE.md, .worktrees/benchmark-test-run/.codex/AGENTS.md",
                ]
            ),
        )
        (logs_root / "recursive-lint-root").mkdir(parents=True, exist_ok=True)
        result = self._make_result()
        result.recursive_workflow_status = "lint-failed"
        result.recursive_artifact_status = {name: True for name in rrb.REQUIRED_RECURSIVE_RUN_FILES}

        prompt_text = self.harness.build_recursive_repair_prompt(self.repo_root, logs_root, result)

        self.assertIn("You are the orchestrator for this routed run", prompt_text)
        self.assertIn("the orchestrator stays responsible for the audit-repair loop", prompt_text)
        self.assertIn("Only list files in `Changed Files`", prompt_text)
        self.assertIn("actually present in the current `git diff --name-only` output", prompt_text)
        self.assertIn("Remove unchanged bootstrap or control-plane files", prompt_text)
        self.assertIn("recursive-lint-root", prompt_text)
        self.assertIn("benchmark/benchmark-context.json", prompt_text)
        self.assertIn("controller-provided lint findings and lint snapshot", prompt_text)
        self.assertIn("Repair the earliest failing audited stage first", prompt_text)
        self.assertIn("must not advance a stage on draft output alone", prompt_text)
        self.assertIn("Do not postpone routed delegation to Phase 8 if an earlier configured routed stage is still missing evidence", prompt_text)
        self.assertIn("Timeout or latency alone is not an acceptable override reason when a configured routed role is available", prompt_text)
        self.assertIn("Use `python scripts/recursive-router-invoke.py`", prompt_text)
        self.assertIn("write the matching durable action record with `python scripts/recursive-subagent-action.py`", prompt_text)
        self.assertIn("Do not lock or advance past a routed stage that timed out or failed", prompt_text)

    def test_recursive_repair_prompt_includes_controller_stage_route_plan(self) -> None:
        logs_root = self.workspace_root / "kimi" / "recursive-on" / "logs"
        logs_root.mkdir(parents=True, exist_ok=True)
        self._write(
            self.repo_root / ".recursive" / "config" / "recursive-router.json",
            json.dumps(
                {
                    "role_routes": {
                        "planner": {
                            "enabled": True,
                            "mode": "external-cli",
                            "cli": "kimi",
                            "model": "kimi-code/kimi-for-coding",
                            "fallback": "self-audit",
                        },
                        "code-reviewer": {
                            "enabled": True,
                            "mode": "external-cli",
                            "cli": "opencode",
                            "model": "github-copilot/claude-sonnet-4.6",
                            "fallback": "self-audit",
                        },
                        "tester": {
                            "enabled": True,
                            "mode": "external-cli",
                            "cli": "codex",
                            "model": "gpt-5.3-codex",
                            "fallback": "self-audit",
                        },
                    },
                    "cli_overrides": {
                        "kimi": {"command": "C:\\Users\\fixture\\.local\\bin\\kimi.exe"},
                        "codex": {"command": "C:\\Users\\fixture\\.local\\bin\\codex.exe"},
                        "opencode": {"command": "C:\\Users\\fixture\\.local\\bin\\opencode.exe"},
                    },
                },
                indent=2,
            ),
        )
        self._write(self.repo_root / "benchmark" / "benchmark-context.json", "{\"run_id\":\"benchmark-test-run\"}\n")
        result = self._make_result()
        result.runner_slug = "kimi"
        result.runner_name = "Kimi CLI"
        result.provider_family = "moonshot-kimi"
        result.model = "kimi-k2.6"
        result.recursive_workflow_status = "routed-evidence-missing"
        result.recursive_artifact_status = {name: True for name in rrb.REQUIRED_RECURSIVE_RUN_FILES}

        prompt_text = self.harness.build_recursive_repair_prompt(self.repo_root, logs_root, result)

        self.assertIn("benchmark/recursive-stage-routing.md", prompt_text)
        self.assertIn("benchmark/recursive-skills/recursive-subagent/SKILL.md", prompt_text)
        self.assertIn("Controller-coordinated routed stage plan for this repair:", prompt_text)
        self.assertIn("Review Bundle Path:", prompt_text)
        self.assertIn(
            "Phase 3.5 / `03.5-code-review.md`: `code-reviewer` -> `opencode` (`github-copilot/claude-sonnet-4.6`) [distinct CLI evidence candidate]",
            prompt_text,
        )
        self.assertIn(
            "Handoff: write the routed action record, reconcile it into `03.5-code-review.md`, lock it, and only then advance to Phase 4 / `04-test-summary.md`.",
            prompt_text,
        )
        self.assertIn(
            "Phase 4 / `04-test-summary.md`: `tester` -> `codex` (`gpt-5.3-codex`) [distinct CLI evidence candidate; complete by this stage if still missing]",
            prompt_text,
        )
        self.assertIn(
            "Phase 2 / `02-to-be-plan.md`: `planner` -> `kimi` (`kimi-code/kimi-for-coding`) [same CLI as orchestrator runner]",
            prompt_text,
        )


    def test_optional_missing_artifact_warnings_are_tolerated_for_recursive_lint(self) -> None:
        logs_root = self.workspace_root / "codex" / "recursive-on" / "logs"
        logs_root.mkdir(parents=True, exist_ok=True)
        self._write(
            logs_root / "recursive-lint.log",
            "\n".join(
                [
                    "Linting run: benchmark-test-run",
                    "[WARN] Missing artifact (ok if not reached yet): D:/repo/.recursive/run/benchmark-test-run/01.5-root-cause.md",
                    "[WARN] Missing artifact (ok if not reached yet): D:/repo/.recursive/run/benchmark-test-run/03.5-code-review.md",
                    "[FAIL] Lint failed",
                ]
            ),
        )

        tolerated = self.harness.lint_has_only_optional_missing_artifact_warnings(logs_root / "recursive-lint.log")

        self.assertTrue(tolerated)








    def test_evaluate_recursive_run_clears_stale_lint_and_missing_artifact_issues(self) -> None:
        run_root = self.repo_root / ".recursive" / "run" / self.run_id
        self._write(run_root / "00-requirements.md", self.harness.render_seeded_run_requirements(self.run_id))
        self._write(
            run_root / "00-worktree.md",
            "\n".join(
                [
                    "## Directory Selection",
                    "",
                    "- Selected worktree location: `.`",
                    "- Product root: `.`",
                    "",
                    "## Diff Basis For Later Audits",
                    "",
                    f"- Baseline reference: `{self._git(self.repo_root, 'rev-parse', 'HEAD').stdout.strip()}`",
                ]
            ),
        )
        self._write(run_root / "01-as-is.md", "## Source Requirement Inventory\n")
        self._write(
            run_root / "02-to-be-plan.md",
            "\n".join(
                [
                    "## Requirement Mapping",
                    "",
                    "## Plan Drift Check",
                    "",
                    "## Requirement Completion Status",
                ]
            ),
        )
        for artifact_name in ("03-implementation-summary.md", "04-test-summary.md", "05-manual-qa.md", "06-decisions-update.md", "07-state-update.md", "08-memory-impact.md"):
            self._write(run_root / artifact_name, f"# {artifact_name}\n")

        logs_root = self.workspace_root / "codex" / "recursive-on" / "logs"
        logs_root.mkdir(parents=True, exist_ok=True)
        result = self._make_result()
        result.expected_product_root = ""
        result.issues = [
            "Recursive run artifacts failed controller-side lint.",
            "Recursive workflow artifacts missing: 05-manual-qa.md, 06-decisions-update.md.",
            "Unrelated issue should remain.",
        ]

        def fake_run_command(*args, **kwargs) -> rrb.CommandResult:
            return rrb.CommandResult(
                command=["lint"],
                returncode=1,
                stdout="\n".join(
                    [
                        f"Linting run: {self.run_id}",
                        f"[WARN] Missing artifact (ok if not reached yet): D:/repo/.recursive/run/{self.run_id}/01.5-root-cause.md",
                        f"[WARN] Missing artifact (ok if not reached yet): D:/repo/.recursive/run/{self.run_id}/03.5-code-review.md",
                        "[FAIL] Lint failed",
                    ]
                ),
                stderr="",
                duration_seconds=0.5,
            )

        self.harness.run_command = fake_run_command  # type: ignore[method-assign]

        self.harness.evaluate_recursive_run(self.repo_root, logs_root, result)

        self.assertEqual("complete", result.recursive_workflow_status)
        self.assertNotIn("Recursive run artifacts failed controller-side lint.", result.issues)
        self.assertFalse(any(issue.startswith("Recursive workflow artifacts missing:") for issue in result.issues))
        self.assertIn("Unrelated issue should remain.", result.issues)

    def test_evaluate_recursive_run_requires_routed_action_records_when_router_is_configured(self) -> None:
        self._write_minimal_complete_recursive_run()
        self._write(
            self.repo_root / ".recursive" / "config" / "recursive-router.json",
            json.dumps(
                {
                    "role_routes": {
                        "code-reviewer": {
                            "enabled": True,
                            "mode": "external-cli",
                            "cli": "codex",
                            "model": "gpt-5.4-mini",
                            "fallback": "self-audit",
                        }
                    },
                    "cli_overrides": {"codex": {"command": "C:\\codex.exe"}},
                },
                indent=2,
            ),
        )
        logs_root = self.workspace_root / "codex" / "recursive-on" / "logs"
        logs_root.mkdir(parents=True, exist_ok=True)
        result = self._make_result()

        def fake_run_command(*args, **kwargs) -> rrb.CommandResult:
            return rrb.CommandResult(command=["lint"], returncode=0, stdout="lint ok\n", stderr="", duration_seconds=0.5)

        self.harness.run_command = fake_run_command  # type: ignore[method-assign]

        self.harness.evaluate_recursive_run(self.repo_root, logs_root, result)

        self.assertEqual("routed-evidence-missing", result.recursive_workflow_status)
        self.assertIn("Recursive routed delegation evidence missing: no routed subagent action records were found.", result.issues)

    def test_evaluate_recursive_run_requires_distinct_cli_evidence_when_policy_has_other_cli_routes(self) -> None:
        run_root = self._write_minimal_complete_recursive_run()
        self._write(
            self.repo_root / ".recursive" / "config" / "recursive-router.json",
            json.dumps(
                {
                    "role_routes": {
                        "planner": {
                            "enabled": True,
                            "mode": "external-cli",
                            "cli": "kimi",
                            "model": "kimi-code/kimi-for-coding",
                            "fallback": "self-audit",
                        },
                        "tester": {
                            "enabled": True,
                            "mode": "external-cli",
                            "cli": "codex",
                            "model": "gpt-5.3-codex",
                            "fallback": "self-audit",
                        },
                    },
                    "cli_overrides": {
                        "kimi": {"command": "C:\\Users\\fixture\\.local\\bin\\kimi.exe"},
                        "codex": {"command": "C:\\codex.exe"},
                    },
                },
                indent=2,
            ),
        )
        subagents_dir = run_root / "subagents"
        subagents_dir.mkdir(parents=True, exist_ok=True)
        self._write(
            subagents_dir / "planner-review.md",
            "\n".join(
                [
                    "# Subagent Action Record",
                    "",
                    "## Routing",
                    "- Router Used: `recursive-router`",
                    "- Routed CLI: `kimi`",
                    "- Routed Model: `kimi-code/kimi-for-coding`",
                ]
            ),
        )
        logs_root = self.workspace_root / "kimi" / "recursive-on" / "logs"
        logs_root.mkdir(parents=True, exist_ok=True)
        result = self._make_result()
        result.runner_slug = "kimi"
        result.runner_name = "Kimi CLI"
        result.provider_family = "moonshot-kimi"
        result.model = "kimi-k2.6"

        def fake_run_command(*args, **kwargs) -> rrb.CommandResult:
            return rrb.CommandResult(command=["lint"], returncode=0, stdout="lint ok\n", stderr="", duration_seconds=0.5)

        self.harness.run_command = fake_run_command  # type: ignore[method-assign]

        self.harness.evaluate_recursive_run(self.repo_root, logs_root, result)

        self.assertEqual("routed-evidence-missing", result.recursive_workflow_status)
        self.assertIn(
            "Recursive routed delegation evidence missing: no routed subagent action records using a CLI distinct from orchestrator runner were found.",
            result.issues,
        )

    def test_evaluate_recursive_run_rejects_malformed_pseudo_action_record_with_routing_lines(self) -> None:
        run_root = self._write_minimal_complete_recursive_run()
        self._write(
            self.repo_root / ".recursive" / "config" / "recursive-router.json",
            json.dumps(
                {
                    "role_routes": {
                        "planner": {
                            "enabled": True,
                            "mode": "external-cli",
                            "cli": "codex",
                            "model": "gpt-5.4-mini",
                            "fallback": "self-audit",
                        }
                    },
                    "cli_overrides": {"codex": {"command": "C:\\codex.exe"}},
                },
                indent=2,
            ),
        )
        subagents_dir = run_root / "subagents"
        subagents_dir.mkdir(parents=True, exist_ok=True)
        self._write(
            subagents_dir / "pseudo-action.md",
            "\n".join(
                [
                    "# Not a canonical action record",
                    "",
                    "## Routing",
                    "- Routed Role: `planner`",
                    "- Routed CLI: `codex`",
                    "- Routed Model: `gpt-5.4-mini`",
                ]
            ),
        )
        logs_root = self.workspace_root / "kimi" / "recursive-on" / "logs"
        logs_root.mkdir(parents=True, exist_ok=True)
        result = self._make_result()
        result.runner_slug = "kimi"
        result.runner_name = "Kimi CLI"
        result.provider_family = "moonshot-kimi"
        result.model = "kimi-k2.6"
        self.harness.run_command = mock.Mock(  # type: ignore[method-assign]
            return_value=rrb.CommandResult(
                command=["lint"],
                returncode=0,
                stdout="lint ok\n",
                stderr="",
                duration_seconds=0.5,
            )
        )

        self.harness.evaluate_recursive_run(self.repo_root, logs_root, result)

        self.assertEqual("routed-evidence-missing", result.recursive_workflow_status)
        self.assertIn("Recursive routed delegation evidence missing: no routed subagent action records were found.", result.issues)
        self.assertIn(
            "Recursive routed delegation evidence missing: no routed subagent action records using a CLI distinct from orchestrator runner were found.",
            result.issues,
        )

    def test_configured_routed_role_policy_uses_only_typed_enabled_external_routes(self) -> None:
        policy_path = self.repo_root / ".recursive" / "config" / "recursive-router.json"
        self._write(
            policy_path,
            json.dumps(
                {
                    "role_routes": {
                        "planner": {
                            "enabled": True,
                            "mode": "external-cli",
                            "cli": "codex",
                            "model": "gpt-5.4-mini",
                        },
                        "tester": {
                            "enabled": False,
                            "mode": "external-cli",
                            "cli": "opencode",
                            "model": "github-copilot/gpt-5-mini",
                        },
                        "analyst": {
                            "enabled": True,
                            "mode": "local-only",
                            "cli": "kimi",
                            "model": "kimi-code/kimi-for-coding",
                        },
                    }
                },
                indent=2,
            ),
        )

        bindings = self.harness.configured_recursive_routed_role_bindings(policy_path)

        self.assertEqual({"planner": ("codex", "gpt-5.4-mini")}, dict(bindings))
        self.assertEqual("", bindings.error)

    def test_configured_routed_role_policy_rejects_malformed_route_types(self) -> None:
        policy_path = self.repo_root / ".recursive" / "config" / "recursive-router.json"
        malformed_values = (
            ("enabled", 1),
            ("mode", ["external-cli"]),
            ("cli", 7),
            ("model", {"name": "gpt-5.4-mini"}),
            ("cli", ""),
            ("model", " "),
        )
        for field_name, malformed_value in malformed_values:
            with self.subTest(field_name=field_name):
                route = {
                    "enabled": True,
                    "mode": "external-cli",
                    "cli": "codex",
                    "model": "gpt-5.4-mini",
                }
                route[field_name] = malformed_value
                self._write(
                    policy_path,
                    json.dumps({"role_routes": {"planner": route}}, indent=2),
                )

                bindings = self.harness.configured_recursive_routed_role_bindings(policy_path)

                self.assertEqual({}, dict(bindings))
                self.assertIn(f".{field_name}", bindings.error)

    def test_malformed_routed_role_policy_produces_structured_benchmark_failure(self) -> None:
        run_root = self._write_minimal_complete_recursive_run()
        policy_path = self.repo_root / ".recursive" / "config" / "recursive-router.json"
        self._write(policy_path, '{"role_routes":')
        result = self._make_result()
        result.recursive_workflow_status = "complete"

        self.harness.evaluate_routed_recursive_evidence(self.repo_root, run_root, result)

        self.assertEqual("router-policy-invalid", result.recursive_workflow_status)
        self.assertTrue(
            any(issue.startswith("Recursive router policy invalid: ") for issue in result.issues)
        )

    def test_configured_routed_role_policy_rejects_missing_role_routes(self) -> None:
        policy_path = self.repo_root / ".recursive" / "config" / "recursive-router.json"
        self._write(policy_path, "{}")

        bindings = self.harness.configured_recursive_routed_role_bindings(policy_path)

        self.assertEqual({}, dict(bindings))
        self.assertIn("missing role_routes", bindings.error)

    def test_configured_routed_role_policy_rejects_invalid_utf8(self) -> None:
        policy_path = self.repo_root / ".recursive" / "config" / "recursive-router.json"
        policy_path.parent.mkdir(parents=True, exist_ok=True)
        policy_path.write_bytes(b"\xff\xfe\x00")

        bindings = self.harness.configured_recursive_routed_role_bindings(policy_path)

        self.assertEqual({}, dict(bindings))
        self.assertIn("UTF-8", bindings.error)

    def test_configured_routed_role_policy_rejects_symlink_or_hardlink(self) -> None:
        policy_path = self.repo_root / ".recursive" / "config" / "recursive-router.json"
        policy_path.parent.mkdir(parents=True, exist_ok=True)
        policy_payload = json.dumps(
            {
                "role_routes": {
                    "planner": {
                        "enabled": True,
                        "mode": "external-cli",
                        "cli": "codex",
                        "model": "gpt-5.4-mini",
                    }
                }
            }
        )
        for link_kind in ("symlink", "hardlink"):
            with self.subTest(link_kind=link_kind):
                policy_path.unlink(missing_ok=True)
                external_path = self.temp_dir / f"external-router-policy-{link_kind}.json"
                self._write(external_path, policy_payload)
                try:
                    if link_kind == "symlink":
                        policy_path.symlink_to(external_path)
                    else:
                        os.link(external_path, policy_path)
                except (NotImplementedError, OSError) as exc:
                    self.skipTest(f"{link_kind} is unavailable: {exc}")

                bindings = self.harness.configured_recursive_routed_role_bindings(policy_path)

                self.assertEqual({}, dict(bindings))
                self.assertIn("unique regular file", bindings.error)

    def test_configured_routed_role_policy_rejects_noncanonical_location(self) -> None:
        policy_path = self.temp_dir / "other" / "router-policy.json"
        self._write(policy_path, json.dumps({"role_routes": {}}))

        bindings = self.harness.configured_recursive_routed_role_bindings(policy_path)

        self.assertEqual({}, dict(bindings))
        self.assertIn("not at .recursive/config/recursive-router.json", bindings.error)

    def test_routed_binding_rejects_agent_only_records_without_prompt_output_or_receipt(self) -> None:
        run_root = self._write_minimal_complete_recursive_run()
        subagents = run_root / "subagents"
        subagents.mkdir()
        bindings = {"planner": ("codex", "gpt-5.4-mini")}
        for execution_mode in ("planner", "implementer"):
            with self.subTest(execution_mode=execution_mode):
                action_path = subagents / f"{execution_mode}.md"
                content = self._canonical_routed_action(execution_mode=execution_mode)
                self._write(action_path, content)
                binding = self.harness.routed_action_record_binding(
                    self.repo_root,
                    run_root,
                    action_path,
                    content,
                    bindings,
                )
                self.assertIsNone(binding)

    def test_routed_binding_accepts_canonical_prompt_output_and_receipt_chain(self) -> None:
        run_root = self._write_minimal_complete_recursive_run()
        subagents = run_root / "subagents"
        subagents.mkdir()
        bindings = {"planner": ("codex", "gpt-5.4-mini")}
        for execution_mode in ("planner", "implementer"):
            with self.subTest(execution_mode=execution_mode):
                action_name = f"{execution_mode}.md"
                action_path = subagents / action_name
                prompt_path, capture_paths = self._write_routed_provenance(
                    run_root,
                    stem=execution_mode,
                )
                content = self._canonical_routed_action(
                    action_name=action_name,
                    execution_mode=execution_mode,
                    prompt_bundle_path=prompt_path,
                    output_capture_paths=capture_paths,
                    evidence_used=capture_paths,
                )
                self._write(action_path, content)
                binding = self.harness.routed_action_record_binding(
                    self.repo_root,
                    run_root,
                    action_path,
                    content,
                    bindings,
                )
                self.assertEqual(("planner", "codex", "gpt-5.4-mini"), binding)

    def test_routed_binding_rejects_noncanonical_router_identity(self) -> None:
        run_root = self._write_minimal_complete_recursive_run()
        action_path, content, bindings, _prompt_display, _capture_displays = (
            self._write_canonical_routed_action_fixture(run_root)
        )
        content = content.replace(
            "- Router Used: `recursive-router`",
            "- Router Used: `agent-claimed-router`",
        )
        self._write(action_path, content)
        binding = self.harness.routed_action_record_binding(
            self.repo_root,
            run_root,
            action_path,
            content,
            bindings,
        )
        self.assertIsNone(binding)

    def test_routed_binding_rejects_config_or_discovery_metadata_mismatch(self) -> None:
        run_root = self._write_minimal_complete_recursive_run()
        mismatch_kinds = (
            "action-config",
            "action-discovery",
            "decision-config",
            "decision-discovery",
        )
        for mismatch_kind in mismatch_kinds:
            with self.subTest(mismatch_kind=mismatch_kind):
                action_path, content, bindings, _prompt_display, capture_displays = (
                    self._write_canonical_routed_action_fixture(
                        run_root,
                        stem=f"path-mismatch-{mismatch_kind}",
                    )
                )
                receipt_path = self.repo_root / capture_displays[1].lstrip("/")
                if mismatch_kind == "action-config":
                    content = content.replace(
                        "- Routing Config Path: `/.recursive/config/recursive-router.json`",
                        "- Routing Config Path: `/.recursive/config/other-router.json`",
                    )
                    self._write(action_path, content)
                elif mismatch_kind == "action-discovery":
                    content = content.replace(
                        "- Routing Discovery Path: `/.recursive/config/recursive-router-discovered.json`",
                        "- Routing Discovery Path: `/.recursive/config/other-discovery.json`",
                    )
                    self._write(action_path, content)
                else:
                    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                    decision_field = (
                        "config_path"
                        if mismatch_kind == "decision-config"
                        else "discovery_path"
                    )
                    receipt["decision"][decision_field] = ".recursive/config/other.json"
                    self._write(receipt_path, json.dumps(receipt, indent=2))

                binding = self.harness.routed_action_record_binding(
                    self.repo_root,
                    run_root,
                    action_path,
                    content,
                    bindings,
                )

                self.assertIsNone(binding)

    def test_routed_binding_rejects_non_string_receipt_route_metadata(self) -> None:
        run_root = self._write_minimal_complete_recursive_run()
        for field_name in ("role", "cli", "model", "config_path", "discovery_path"):
            with self.subTest(field_name=field_name):
                action_path, content, bindings, _prompt_display, capture_displays = (
                    self._write_canonical_routed_action_fixture(
                        run_root,
                        stem=f"non-string-{field_name}",
                    )
                )
                receipt_path = self.repo_root / capture_displays[1].lstrip("/")
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                if field_name in {"config_path", "discovery_path"}:
                    receipt["decision"][field_name] = 7
                else:
                    receipt[field_name] = 7
                    receipt["decision"][field_name] = 7
                self._write(receipt_path, json.dumps(receipt, indent=2))

                binding = self.harness.routed_action_record_binding(
                    self.repo_root,
                    run_root,
                    action_path,
                    content,
                    bindings,
                )

                self.assertIsNone(binding)

    def test_routed_binding_accepts_full_reviewer_record_bound_to_current_pass(self) -> None:
        run_root = self._write_minimal_complete_recursive_run()
        ledger_path = f"/.recursive/run/{self.run_id}/evidence/reviews/phase-3-5/review/ledger.md"
        bundle_path = f"/.recursive/run/{self.run_id}/evidence/review-bundles/phase-3-5/review/0001.md"
        self._write(self.repo_root / ledger_path.lstrip("/"), "# Review ledger fixture\n")
        self._write(self.repo_root / bundle_path.lstrip("/"), "# Review bundle fixture\n")
        self._write(
            run_root / "03.5-code-review.md",
            f"""## Review Metadata
- Review Ledger Path: `{ledger_path}`
- Review Bundle Path: `{bundle_path}`
""",
        )
        subagents = run_root / "subagents"
        subagents.mkdir()
        action_path = subagents / "reviewer.md"
        prompt_path, capture_paths = self._write_routed_provenance(
            run_root,
            stem="reviewer",
            routed_role="code-reviewer",
        )
        findings = f"""- Review Protocol: `/.agents/skills/recursive-review/references/finding-protocol.md`
- Review Bundle: `{bundle_path}`
- Review Ledger: `{ledger_path}`
- Review Pass: 0001
- Claims: none"""
        content = self._canonical_routed_action(
            action_name="reviewer.md",
            phase="Phase 3.5",
            execution_mode="reviewer",
            routed_role="code-reviewer",
            current_artifact=f"/.recursive/run/{self.run_id}/03.5-code-review.md",
            review_bundle=bundle_path,
            prompt_bundle_path=prompt_path,
            output_capture_paths=capture_paths,
            evidence_used=capture_paths,
            findings=findings,
        )
        self._write(action_path, content)
        document = rrb.recursive_action_contract.review_ledger.ReviewDocument(
            "",
            {"Pass": "0001", "Reviewed Artifact": bundle_path},
            {},
            {},
        )
        with mock.patch.object(
            rrb.recursive_action_contract.review_ledger,
            "validate_ledger",
            return_value=rrb.recursive_action_contract.review_ledger.ValidationResult(document=document),
        ):
            binding = self.harness.routed_action_record_binding(
                self.repo_root,
                run_root,
                action_path,
                content,
                {"code-reviewer": ("codex", "gpt-5.4-mini")},
            )
        self.assertEqual(("code-reviewer", "codex", "gpt-5.4-mini"), binding)

    def test_routed_binding_rejects_missing_prompt_output_or_receipt_file(self) -> None:
        run_root = self._write_minimal_complete_recursive_run()
        for missing_kind, capture_index in (("prompt", None), ("output", 0), ("receipt", 1)):
            with self.subTest(missing_kind=missing_kind):
                action_path, content, bindings, prompt_display, capture_displays = (
                    self._write_canonical_routed_action_fixture(
                        run_root,
                        stem=f"missing-{missing_kind}",
                    )
                )
                missing_display = (
                    prompt_display
                    if capture_index is None
                    else capture_displays[capture_index]
                )
                (self.repo_root / missing_display.lstrip("/")).unlink()
                binding = self.harness.routed_action_record_binding(
                    self.repo_root,
                    run_root,
                    action_path,
                    content,
                    bindings,
                )
                self.assertIsNone(binding)

    def test_routed_binding_rejects_symlinked_prompt_output_or_receipt_file(self) -> None:
        run_root = self._write_minimal_complete_recursive_run()
        for linked_kind, capture_index in (("prompt", None), ("output", 0), ("receipt", 1)):
            with self.subTest(linked_kind=linked_kind):
                action_path, content, bindings, prompt_display, capture_displays = (
                    self._write_canonical_routed_action_fixture(
                        run_root,
                        stem=f"linked-{linked_kind}",
                    )
                )
                linked_display = (
                    prompt_display
                    if capture_index is None
                    else capture_displays[capture_index]
                )
                linked_path = self.repo_root / linked_display.lstrip("/")
                external_path = self.temp_dir / f"external-{linked_kind}{linked_path.suffix}"
                shutil.copy2(linked_path, external_path)
                linked_path.unlink()
                try:
                    linked_path.symlink_to(external_path)
                except (NotImplementedError, OSError) as exc:
                    self.skipTest(f"file symlinks are unavailable: {exc}")
                binding = self.harness.routed_action_record_binding(
                    self.repo_root,
                    run_root,
                    action_path,
                    content,
                    bindings,
                )
                self.assertIsNone(binding)

    def test_routed_binding_rejects_hardlinked_prompt_output_or_receipt_file(self) -> None:
        run_root = self._write_minimal_complete_recursive_run()
        for linked_kind, capture_index in (("prompt", None), ("output", 0), ("receipt", 1)):
            with self.subTest(linked_kind=linked_kind):
                action_path, content, bindings, prompt_display, capture_displays = (
                    self._write_canonical_routed_action_fixture(
                        run_root,
                        stem=f"hardlinked-{linked_kind}",
                    )
                )
                linked_display = (
                    prompt_display
                    if capture_index is None
                    else capture_displays[capture_index]
                )
                linked_path = self.repo_root / linked_display.lstrip("/")
                external_path = self.temp_dir / f"hardlink-source-{linked_kind}{linked_path.suffix}"
                shutil.copy2(linked_path, external_path)
                linked_path.unlink()
                try:
                    os.link(external_path, linked_path)
                except OSError as exc:
                    self.skipTest(f"hardlinks are unavailable: {exc}")
                binding = self.harness.routed_action_record_binding(
                    self.repo_root,
                    run_root,
                    action_path,
                    content,
                    bindings,
                )
                self.assertIsNone(binding)

    def test_routed_binding_rejects_receipt_role_cli_model_or_exit_mismatch(self) -> None:
        run_root = self._write_minimal_complete_recursive_run()
        mutations = {
            "role": ("role", "tester"),
            "cli": ("cli", "opencode"),
            "model": ("model", "gpt-5-tampered"),
            "exit": ("exit_code", 1),
        }
        for mismatch_kind, (field_name, field_value) in mutations.items():
            with self.subTest(mismatch_kind=mismatch_kind):
                action_path, content, bindings, _prompt_display, capture_displays = (
                    self._write_canonical_routed_action_fixture(
                        run_root,
                        stem=f"mismatch-{mismatch_kind}",
                    )
                )
                receipt_path = self.repo_root / capture_displays[1].lstrip("/")
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                receipt[field_name] = field_value
                if field_name in {"role", "cli", "model"}:
                    receipt["decision"][field_name] = field_value
                self._write(receipt_path, json.dumps(receipt, indent=2))
                binding = self.harness.routed_action_record_binding(
                    self.repo_root,
                    run_root,
                    action_path,
                    content,
                    bindings,
                )
                self.assertIsNone(binding)

    def test_routed_binding_rejects_tampered_output_or_receipt_cross_binding(self) -> None:
        run_root = self._write_minimal_complete_recursive_run()
        for tamper_kind in ("action-path", "output", "receipt-output", "receipt-prompt"):
            with self.subTest(tamper_kind=tamper_kind):
                action_path, content, bindings, _prompt_display, capture_displays = (
                    self._write_canonical_routed_action_fixture(
                        run_root,
                        stem=f"tamper-{tamper_kind}",
                    )
                )
                output_path = self.repo_root / capture_displays[0].lstrip("/")
                receipt_path = self.repo_root / capture_displays[1].lstrip("/")
                if tamper_kind == "action-path":
                    content = content.replace(
                        f"/.recursive/run/{self.run_id}/subagents/tamper-action-path.md",
                        f"/.recursive/run/{self.run_id}/subagents/other.md",
                    )
                    self._write(action_path, content)
                elif tamper_kind == "output":
                    self._write(output_path, "tampered routed output")
                else:
                    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                    if tamper_kind == "receipt-output":
                        receipt["output_text"] = "tampered receipt output"
                    else:
                        receipt["prompt_bundle_path"] = (
                            f"/.recursive/run/{self.run_id}/router-prompts/other.md"
                        )
                    self._write(receipt_path, json.dumps(receipt, indent=2))
                binding = self.harness.routed_action_record_binding(
                    self.repo_root,
                    run_root,
                    action_path,
                    content,
                    bindings,
                )
                self.assertIsNone(binding)

    def test_evaluate_recursive_run_rejects_symlinked_subagents_directory(self) -> None:
        run_root = self._write_minimal_complete_recursive_run()
        self._write(
            self.repo_root / ".recursive" / "config" / "recursive-router.json",
            json.dumps(
                {
                    "role_routes": {
                        "planner": {
                            "enabled": True,
                            "mode": "external-cli",
                            "cli": "codex",
                            "model": "gpt-5.4-mini",
                            "fallback": "self-audit",
                        }
                    },
                    "cli_overrides": {"codex": {"command": "C:\\codex.exe"}},
                },
                indent=2,
            ),
        )
        external_subagents = self.temp_dir / "external-subagents"
        external_subagents.mkdir()
        self._write(external_subagents / "external-action.md", "# External action record")
        subagents_dir = run_root / "subagents"
        try:
            subagents_dir.symlink_to(external_subagents, target_is_directory=True)
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"directory symlinks are unavailable: {exc}")

        logs_root = self.workspace_root / "kimi" / "recursive-on" / "logs"
        logs_root.mkdir(parents=True, exist_ok=True)
        result = self._make_result()
        result.runner_slug = "kimi"
        result.runner_name = "Kimi CLI"
        result.provider_family = "moonshot-kimi"
        result.model = "kimi-k2.6"
        self.harness.run_command = mock.Mock(  # type: ignore[method-assign]
            return_value=rrb.CommandResult(
                command=["lint"],
                returncode=0,
                stdout="lint ok\n",
                stderr="",
                duration_seconds=0.5,
            )
        )
        self.harness.routed_action_record_binding = mock.Mock(  # type: ignore[method-assign]
            return_value=("planner", "codex", "gpt-5.4-mini")
        )

        self.harness.evaluate_recursive_run(self.repo_root, logs_root, result)

        self.harness.routed_action_record_binding.assert_not_called()
        self.assertEqual("routed-evidence-missing", result.recursive_workflow_status)
        self.assertIn("Recursive routed delegation evidence missing: no routed subagent action records were found.", result.issues)

    def test_evaluate_recursive_run_rejects_controller_synthesized_self_audit_when_routing_expected(self) -> None:
        run_root = self._write_minimal_complete_recursive_run()
        self._write(
            self.repo_root / ".recursive" / "config" / "recursive-router.json",
            json.dumps(
                {
                    "role_routes": {
                        "code-reviewer": {
                            "enabled": True,
                            "mode": "external-cli",
                            "cli": "codex",
                            "model": "gpt-5.4-mini",
                            "fallback": "self-audit",
                        }
                    },
                    "cli_overrides": {"codex": {"command": "C:\\codex.exe"}},
                },
                indent=2,
            ),
        )
        self._write(
            run_root / "04-test-summary.md",
            "\n".join(
                [
                    "## Audit Context",
                    "",
                    "- Audit Execution Mode: self-audit",
                    "- Subagent Availability: unavailable",
                    "- Subagent Capability Probe: Benchmark controller synthesized this audited test summary because no durable delegated subagent facility is available in the disposable benchmark workspace.",
                ]
            ),
        )
        subagents_dir = run_root / "subagents"
        subagents_dir.mkdir(parents=True, exist_ok=True)
        self._write(
            subagents_dir / "review-action.md",
            "\n".join(
                [
                    "# Subagent Action Record",
                    "",
                    "## Routing",
                    "- Router Used: `recursive-router`",
                    "- Routed CLI: `codex`",
                    "- Routed Model: `gpt-5.4-mini`",
                ]
            ),
        )
        logs_root = self.workspace_root / "codex" / "recursive-on" / "logs"
        logs_root.mkdir(parents=True, exist_ok=True)
        result = self._make_result()

        def fake_run_command(*args, **kwargs) -> rrb.CommandResult:
            return rrb.CommandResult(command=["lint"], returncode=0, stdout="lint ok\n", stderr="", duration_seconds=0.5)

        self.harness.run_command = fake_run_command  # type: ignore[method-assign]

        self.harness.evaluate_recursive_run(self.repo_root, logs_root, result)

        self.assertEqual("routed-evidence-missing", result.recursive_workflow_status)
        self.assertIn(
            "Recursive routed delegation evidence missing: controller-synthesized self-audit fallback remains in 04-test-summary.md.",
            result.issues,
        )

    def test_finalize_result_treats_kimi_image_capability_tail_as_benign(self) -> None:
        result = self._make_result()
        result.build_success = True
        result.test_success = True
        result.preview_success = True
        result.recursive_delivery_status = "ok"
        result.recursive_workflow_status = "complete"
        result.agent_status = "non-zero-exit"
        kimi_runner = rrb.RunnerConfig(
            slug="kimi",
            display_name="Kimi CLI",
            provider_family="moonshot-kimi",
            executable="kimi",
            model="kimi-k2.6",
            supports_json=False,
        )
        agent_record = rrb.CommandResult(
            command=["kimi"],
            returncode=1,
            stdout="LLM model 'kimi-k2.6' does not support required capability: image_in.",
            stderr="",
            duration_seconds=1.0,
        )

        self.harness.finalize_result(kimi_runner, agent_record, result)

        self.assertEqual("pass", result.status)
        self.assertNotIn("Agent execution exited non-zero after producing a passing artifact set.", result.issues)

    def test_finalize_result_marks_recursive_workflow_failure_as_non_pass(self) -> None:
        result = self._make_result()
        result.build_success = True
        result.test_success = True
        result.preview_success = True
        result.recursive_delivery_status = "ok"
        result.recursive_workflow_status = "lint-failed"
        result.agent_status = "clean-exit"
        runner = rrb.RunnerConfig(
            slug="codex",
            display_name="Codex CLI",
            provider_family="codex",
            executable="codex",
            model="gpt-5.4-mini",
            supports_json=True,
        )
        agent_record = rrb.CommandResult(command=["codex"], returncode=0, stdout="", stderr="", duration_seconds=1.0)

        self.harness.finalize_result(runner, agent_record, result)

        self.assertEqual("workflow-fail", result.status)

    def test_finalize_result_treats_controller_completed_timeout_as_runner_issue(self) -> None:
        result = self._make_result()
        result.build_success = True
        result.test_success = True
        result.preview_success = True
        result.recursive_delivery_status = "ok"
        result.recursive_workflow_status = "complete"
        result.agent_status = "timed-out"
        result.timed_out = True
        runner = rrb.RunnerConfig(
            slug="codex",
            display_name="Codex CLI",
            provider_family="codex",
            executable="codex",
            model="gpt-5.4-mini",
            supports_json=True,
        )
        agent_record = rrb.CommandResult(
            command=["codex"],
            returncode=1,
            stdout="",
            stderr="",
            duration_seconds=1.0,
            timed_out=True,
        )

        self.harness.finalize_result(runner, agent_record, result)

        self.assertEqual("pass-with-runner-issue", result.status)
        self.assertIn("Agent execution hit the benchmark timeout.", result.issues)

    def test_finalize_result_classifies_missing_worktree_runner_failure_as_workflow_runner_issue(self) -> None:
        result = self._make_result()
        result.build_success = True
        result.test_success = True
        result.preview_success = True
        result.recursive_delivery_status = "missing-expected-product-root"
        result.recursive_workflow_status = "incomplete"
        result.recursive_artifact_status = {
            "00-requirements.md": True,
            "00-worktree.md": True,
            "01-as-is.md": False,
        }
        result.agent_status = "non-zero-exit"
        runner = rrb.RunnerConfig(
            slug="codex",
            display_name="Codex CLI",
            provider_family="codex",
            executable="codex",
            model="gpt-5.4-mini",
            supports_json=True,
        )
        agent_record = rrb.CommandResult(
            command=["codex"],
            returncode=1,
            stdout="You've hit your usage limit. Upgrade to Pro or try again later.",
            stderr='Auth(TokenRefreshFailed("Failed to parse server response"))',
            duration_seconds=1.0,
        )

        self.harness.finalize_result(runner, agent_record, result)

        self.assertEqual("workflow-fail-with-runner-issue", result.status)
        self.assertIn("usage limit", "\n".join(result.issues).lower())

    def test_maybe_repair_recursive_run_retries_once_when_first_repair_still_incomplete(self) -> None:
        logs_root = self.workspace_root / "codex" / "recursive-on" / "logs"
        logs_root.mkdir(parents=True, exist_ok=True)
        result = self._make_result()
        result.recursive_workflow_status = "incomplete"
        result.recursive_artifact_status = {
            "00-requirements.md": True,
            "00-worktree.md": True,
            "01-as-is.md": True,
            "02-to-be-plan.md": True,
            "03-implementation-summary.md": False,
            "04-test-summary.md": False,
            "05-manual-qa.md": False,
            "06-decisions-update.md": False,
            "07-state-update.md": False,
            "08-memory-impact.md": False,
        }
        log_stems: list[str] = []
        evaluation_count = 0

        def fake_run_model_prompt(
            repo_root: Path,
            logs_root_arg: Path,
            *,
            runner_slug: str,
            executable: str | None,
            model: str,
            prompt_text: str,
            log_stem: str,
            timeout_seconds: int,
        ) -> tuple[rrb.CommandResult, Path, Path]:
            log_stems.append(log_stem)
            stdout_log = logs_root_arg / f"{log_stem}-output.jsonl"
            stderr_log = logs_root_arg / f"{log_stem}-stderr.log"
            stdout_log.write_text("", encoding="utf-8")
            stderr_log.write_text("", encoding="utf-8")
            return (
                rrb.CommandResult(command=[log_stem], returncode=0, stdout="", stderr="", duration_seconds=1.0),
                stdout_log,
                stderr_log,
            )

        def fake_evaluate_recursive_run(repo_root: Path, logs_root_arg: Path, result_arg: rrb.ArmResult) -> None:
            nonlocal evaluation_count
            evaluation_count += 1
            if evaluation_count == 1:
                result_arg.recursive_workflow_status = "incomplete"
                result_arg.recursive_artifact_status["08-memory-impact.md"] = False
            else:
                result_arg.recursive_workflow_status = "complete"
                for file_name in list(result_arg.recursive_artifact_status):
                    result_arg.recursive_artifact_status[file_name] = True

        self.harness.run_model_prompt = fake_run_model_prompt  # type: ignore[method-assign]
        self.harness.evaluate_recursive_run = fake_evaluate_recursive_run  # type: ignore[method-assign]

        repair_record = self.harness.maybe_repair_recursive_run(
            self.repo_root,
            logs_root,
            self.harness.runner_configs[0],
            result,
        )

        self.assertIsNotNone(repair_record)
        self.assertEqual(["recursive-repair", "recursive-repair-2"], log_stems)
        self.assertEqual(2, evaluation_count)
        self.assertEqual("complete", result.recursive_workflow_status)


    def test_maybe_repair_recursive_run_skips_preflight_runner_failure_without_worktree(self) -> None:
        logs_root = self.workspace_root / "codex" / "recursive-on" / "logs"
        logs_root.mkdir(parents=True, exist_ok=True)
        result = self._make_result()
        result.recursive_workflow_status = "incomplete"
        result.recursive_delivery_status = "missing-expected-product-root"
        result.runner_issue_detail = "Codex CLI hit a usage limit and auth refresh failure before recursive worktree setup completed."
        result.recursive_artifact_status = {
            "00-requirements.md": True,
            "00-worktree.md": True,
            "01-as-is.md": False,
        }
        run_root = self.repo_root / ".recursive" / "run" / self.run_id
        self._write(
            run_root / "00-worktree.md",
            "\n".join(
                [
                    "Status: `DRAFT`",
                    "",
                    "## Directory Selection",
                    "",
                    f"- Selected worktree location: `.worktrees/{self.run_id}`",
                ]
            ),
        )
        self.harness.run_model_prompt = mock.Mock(side_effect=AssertionError("model repair should not run"))  # type: ignore[method-assign]

        repair_record = self.harness.maybe_repair_recursive_run(
            self.repo_root,
            logs_root,
            self.harness.runner_configs[0],
            result,
        )

        self.assertIsNone(repair_record)
        self.assertIn("skipped closeout synthesis", "\n".join(result.issues).lower())


    def test_maybe_repair_recursive_run_attempts_routed_evidence_repair(self) -> None:
        logs_root = self.workspace_root / "codex" / "recursive-on" / "logs"
        logs_root.mkdir(parents=True, exist_ok=True)
        result = self._make_result()
        result.recursive_workflow_status = "routed-evidence-missing"
        result.recursive_artifact_status = {name: True for name in rrb.REQUIRED_RECURSIVE_RUN_FILES}
        captured: dict[str, object] = {}

        def fake_run_model_prompt(
            repo_root: Path,
            logs_root_arg: Path,
            *,
            runner_slug: str,
            executable: str | None,
            model: str,
            prompt_text: str,
            log_stem: str,
            timeout_seconds: int,
        ) -> tuple[rrb.CommandResult, Path, Path]:
            captured["prompt"] = prompt_text
            captured["log_stem"] = log_stem
            stdout_log = logs_root_arg / f"{log_stem}-output.jsonl"
            stderr_log = logs_root_arg / f"{log_stem}-stderr.log"
            stdout_log.write_text("", encoding="utf-8")
            stderr_log.write_text("", encoding="utf-8")
            return (
                rrb.CommandResult(command=["repair"], returncode=0, stdout="", stderr="", duration_seconds=1.0),
                stdout_log,
                stderr_log,
            )

        def fake_evaluate_recursive_run(repo_root: Path, logs_root_arg: Path, result_arg: rrb.ArmResult) -> None:
            result_arg.recursive_workflow_status = "complete"

        self.harness.run_model_prompt = fake_run_model_prompt  # type: ignore[method-assign]
        self.harness.evaluate_recursive_run = fake_evaluate_recursive_run  # type: ignore[method-assign]

        repair_record = self.harness.maybe_repair_recursive_run(
            self.repo_root,
            logs_root,
            self.harness.runner_configs[0],
            result,
        )

        self.assertIsNotNone(repair_record)
        self.assertEqual("recursive-repair", captured["log_stem"])
        self.assertIn("Repair the earliest failing audited stage first", captured["prompt"])

    def test_judge_brief_marks_worktree_agent_log_as_authoritative(self) -> None:
        result = self._make_result()
        result.recursive_workflow_status = "lint-failed"
        result.recursive_delivery_status = "ok"
        result.recursive_artifact_status = {"00-worktree.md": True}
        result.score_breakdown = {"responsive_ui": 5.0, "dual_display_editing": 10.0}
        result.score_breakdown_max = {"responsive_ui": 5.0, "dual_display_editing": 10.0}
        brief_path = self.harness.write_judge_brief(self.repo_root, self.worktree_root, result)

        brief = brief_path.read_text(encoding="utf-8")
        self.assertIn(f"- Authoritative benchmark progress log: .worktrees/{self.run_id}/benchmark/agent-log.md", brief)
        self.assertIn("repo-root `benchmark/agent-log.md` may contain controller metadata only", brief)
        self.assertIn('"entry_adjustments"', brief)
        self.assertIn("- responsive_ui: 5/5", brief)
        self.assertIn("- dual_display_editing: 10/10", brief)

    def test_load_judge_metric_applies_structured_entry_adjustments(self) -> None:
        result = self._make_result()
        result.score_breakdown = {
            "dual_display_editing": 10.0,
            "responsive_ui": 0.0,
            "scientific_functions": 15.0,
        }
        result.score_breakdown_max = {
            "dual_display_editing": 10.0,
            "responsive_ui": 5.0,
            "scientific_functions": 15.0,
        }
        result.score = 25.0
        result.score_max = 30.0
        metric_path = self.repo_root / "benchmark" / "judge-metric.json"
        metric_path.write_text(
            json.dumps(
                {
                    "score": 7,
                    "max": 10,
                    "judge_runner": "Codex CLI",
                    "judge_model": "GPT-5.4",
                    "summary": "Needs corrections.",
                    "notes": ["Visible controls are incomplete."],
                    "entry_adjustments": {
                        "dual_display_editing": {"score": 5, "reason": "Visible controls are incomplete."},
                        "responsive_ui": {"score": 99, "reason": "Responsive layout is clearly present in screenshots."},
                        "unknown_key": {"score": 1, "reason": "Should be ignored."},
                    },
                }
            ),
            encoding="utf-8",
        )

        self.harness.load_judge_metric(self.repo_root, result)

        self.assertEqual(result.judge_score, 7.0)
        self.assertEqual(result.judge_adjusted_score_breakdown["dual_display_editing"], 5.0)
        self.assertEqual(result.judge_adjusted_score_breakdown["responsive_ui"], 5.0)
        self.assertEqual(result.judge_adjusted_score_breakdown["scientific_functions"], 15.0)
        self.assertEqual(result.judge_adjusted_score, 25.0)
        self.assertEqual(
            result.judge_entry_adjustment_reasons["dual_display_editing"],
            "Visible controls are incomplete.",
        )
        self.assertIn("Judge entry adjustments referenced unknown score keys", result.issues[-1])

    def test_delivery_integrity_passes_when_expected_worktree_contains_product_edits(self) -> None:
        self._write(self.worktree_root / "src" / "app.rs", "pub fn app_label() -> &'static str { \"interactive\" }\n")
        self._write(
            self.worktree_root / "src" / "calculator.rs",
            "pub fn starter_expression() -> &'static str { \"1 + 2\" }\n",
        )
        self._write_run_artifacts(["src/app.rs", "src/calculator.rs"])

        result = self._make_result()
        self.harness.evaluate_recursive_delivery(self.repo_root, self.worktree_root, result)

        self.assertEqual(result.recursive_delivery_status, "ok")
        self.assertEqual(result.recursive_root_product_drift, [])
        self.assertEqual(result.recursive_missing_claimed_files, [])
        self.assertIn("src/app.rs", result.recursive_product_change_paths)
        self.assertIn("src/calculator.rs", result.recursive_product_change_paths)

    def test_delivery_integrity_fails_for_root_only_product_edits(self) -> None:
        self._write(self.repo_root / "src" / "app.rs", "pub fn app_label() -> &'static str { \"wrong-root\" }\n")

        result = self._make_result()
        self.harness.evaluate_recursive_delivery(self.repo_root, self.worktree_root, result)

        self.assertEqual(result.recursive_delivery_status, "wrong-root-edits")
        self.assertIn("src/app.rs", result.recursive_root_product_drift)
        self.assertEqual(result.recursive_product_change_paths, [])

    def test_delivery_integrity_fails_when_claimed_files_are_missing_from_worktree(self) -> None:
        self._write(self.worktree_root / "src" / "app.rs", "pub fn app_label() -> &'static str { \"partial\" }\n")
        self._write_run_artifacts(["src/app.rs", "src/calculator.rs"])

        result = self._make_result()
        self.harness.evaluate_recursive_delivery(self.repo_root, self.worktree_root, result)

        self.assertEqual(result.recursive_delivery_status, "claimed-files-missing-in-worktree")
        self.assertIn("src/calculator.rs", result.recursive_missing_claimed_files)
        self.assertIn("src/app.rs", result.recursive_product_change_paths)

    def test_delivery_integrity_ignores_phase2_plan_only_paths_and_normalizes_worktree_prefixed_claims(self) -> None:
        run_root = self.repo_root / ".recursive" / "run" / self.run_id
        self._write(self.worktree_root / "src" / "app.rs", "pub fn app_label() -> &'static str { \"interactive\" }\n")
        self._write(
            run_root / "02-to-be-plan.md",
            "\n".join(
                [
                    "## Requirement Completion Status",
                    "",
                    f"- R1 | Status: planned | Implementation Surface: `.worktrees/{self.run_id}/src/parser.rs` | Verification Surface: `.recursive/run/{self.run_id}/evidence/logs/green/r1.log` | QA Surface: `.worktrees/{self.run_id}/benchmark/screenshots/r1.png`",
                ]
            ),
        )
        self._write(
            run_root / "03-implementation-summary.md",
            "\n".join(
                [
                    "## Changes Applied",
                    "",
                    "Collapsed the parser into `parser.rs` prose-wise, but the real file is below.",
                    "",
                    "## Requirement Completion Status",
                    "",
                    f"- R1 | Status: implemented | Changed Files: `.worktrees/{self.run_id}/src/app.rs` | Implementation Evidence: `.worktrees/{self.run_id}/src/app.rs`",
                ]
            ),
        )
        self._write(
            run_root / "04-test-summary.md",
            "\n".join(
                [
                    "## Requirement Completion Status",
                    "",
                    f"- R1 | Status: verified | Changed Files: `.worktrees/{self.run_id}/src/app.rs` | Implementation Evidence: `.worktrees/{self.run_id}/src/app.rs` | Verification Evidence: `.recursive/run/{self.run_id}/evidence/logs/green/r1.log`",
                ]
            ),
        )

        result = self._make_result()
        self.harness.evaluate_recursive_delivery(self.repo_root, self.worktree_root, result)

        self.assertEqual(result.recursive_delivery_status, "ok")
        self.assertEqual(result.recursive_missing_claimed_files, [])
        self.assertEqual(result.recursive_claimed_files, ["src/app.rs"])

    def test_delivery_integrity_ignores_root_only_control_plane_changes(self) -> None:
        self._write(self.worktree_root / "src" / "app.rs", "pub fn app_label() -> &'static str { \"interactive\" }\n")
        self._write(self.repo_root / ".recursive" / "STATE.md", "updated state\n")
        self._write(self.repo_root / "benchmark" / "agent-log.md", "# Benchmark agent log\n\nupdated\n")
        self._write_run_artifacts(["src/app.rs"])

        result = self._make_result()
        self.harness.evaluate_recursive_delivery(self.repo_root, self.worktree_root, result)

        self.assertEqual(result.recursive_delivery_status, "ok")
        self.assertEqual(result.recursive_root_product_drift, [])
        self.assertEqual(result.recursive_missing_claimed_files, [])

    def test_delivery_integrity_ignores_root_runtime_output_dirs(self) -> None:
        self._write(self.worktree_root / "src" / "app.rs", "pub fn app_label() -> &'static str { \"interactive\" }\n")
        self._write(self.repo_root / ".cargo-target-dir" / "release" / "unit.json", "{\"artifact\": true}\n")
        self._write(self.repo_root / ".playwright-mcp" / "trace.json", "{\"trace\": true}\n")
        self._write_run_artifacts(["src/app.rs"])

        result = self._make_result()
        self.harness.evaluate_recursive_delivery(self.repo_root, self.worktree_root, result)

        self.assertEqual(result.recursive_delivery_status, "ok")
        self.assertEqual(result.recursive_root_product_drift, [])

    def _score_scientific_source(self, source_text: str) -> tuple[dict[str, float], rrb.ArmResult]:
        result = rrb.ArmResult(
            runner_slug="codex",
            runner_name="Codex CLI",
            provider_family="codex",
            model="gpt-5.4",
            arm_name="recursive-off",
        )
        breakdown: dict[str, float] = {}

        def add_score(
            label: str,
            awarded: float,
            maximum: float,
            *,
            zero_issue: str = "",
            partial_issue: str = "",
        ) -> None:
            bounded = max(0.0, min(maximum, awarded))
            breakdown[label] = bounded
            if bounded == 0 and zero_issue:
                result.issues.append(zero_issue)
            elif 0 < bounded < maximum and partial_issue:
                result.issues.append(partial_issue)

        self.harness.score_scientific_calculator_repo(source_text.lower(), result, add_score)
        return breakdown, result

    def test_scientific_calculator_heuristics_detect_recursive_descent_deg_rad_and_formatting(self) -> None:
        source_text = """
        enum AngleMode { Deg, Rad }
        fn parse_add_sub() {}
        fn parse_mul_div() {}
        fn parse_pow() {}
        fn format_val(value: f64) -> String { format!("{:.12}", value).trim_end_matches('0').trim_end_matches('.').to_string() }
        fn save_state() { let _ = storage.set_item("calc_angle_mode", "deg"); let _ = storage.set_item("calc_history", "1+2=3"); }
        fn load_state() { let _ = storage.get_item("calc_angle_mode"); let _ = storage.get_item("calc_history"); }
        let history = vec!["1+2=3"];
        let memory = 0.0;
        let expression = "sin(30)";
        let display = "result";
        let error = "division by zero";
        let keypad = "clear entry backspace sign";
        Callback::from(move |e: KeyboardEvent| match e.key().as_str() { "Enter" | "Backspace" | "Escape" => (), _ => () });
        @media (max-width: 520px) { .keypad { display: grid; grid-template-columns: repeat(4, 1fr); } .calc-container { max-width: 480px; } }
        parentheses sin cos tan sqrt log10 ln pi pow
        """

        breakdown, result = self._score_scientific_source(source_text)

        self.assertEqual(breakdown["dual_display_editing"], 10)
        self.assertEqual(breakdown["parser_precedence"], 15)
        self.assertEqual(breakdown["scientific_functions"], 15)
        self.assertEqual(breakdown["angle_mode"], 10)
        self.assertEqual(breakdown["memory_history"], 10)
        self.assertEqual(breakdown["persistence"], 10)
        self.assertEqual(breakdown["keyboard_support"], 5)
        self.assertEqual(breakdown["error_handling"], 5)
        self.assertEqual(breakdown["display_formatting"], 5)
        self.assertEqual(breakdown["responsive_ui"], 5)
        self.assertEqual(result.issues, [])

    def test_kimi_runner_env_enforces_utf8_output(self) -> None:
        env = self.harness.runner_invocation_env("kimi")
        self.assertEqual(env["PYTHONUTF8"], "1")
        self.assertEqual(env["PYTHONIOENCODING"], "utf-8")
        self.assertEqual(env["NO_COLOR"], "1")

    def test_build_runner_configs_all_includes_opencode_via_env_override(self) -> None:
        fake_cli = self.temp_dir / "opencode-cli.exe"
        fake_cli.write_text("stub\n", encoding="utf-8")
        args = argparse.Namespace(
            scenario="scientific-calculator-rust",
            runner="all",
            workspace_root=str(self.workspace_root / "opencode-all"),
            copilot_model="gpt-5.4",
            codex_model="gpt-5.4",
            kimi_model="kimi-k2.6",
            opencode_model="opencode/gpt-5-nano",
            max_minutes=5,
            command_timeout=120,
            preview_timeout=30,
            npm_command="npm",
            arm_mode="sequential",
            hint_penalty=5.0,
            prepare_only=False,
            skip_npm_install=True,
            list_scenarios=False,
        )
        real_which = shutil.which

        def fake_which(name: str) -> str | None:
            if name in {"opencode", "opencode-cli", "opencode-cli.exe"}:
                return None
            return real_which(name)

        with mock.patch.object(rrb.shutil, "which", side_effect=fake_which):
            with mock.patch.dict(rrb.os.environ, {"OPENCODE_CLI_PATH": str(fake_cli)}, clear=False):
                harness = rrb.BenchmarkHarness(args)

        runner_slugs = [runner.slug for runner in harness.runner_configs]
        self.assertNotIn("copilot", runner_slugs)
        self.assertIn("opencode", runner_slugs)
        opencode_runner = next(runner for runner in harness.runner_configs if runner.slug == "opencode")
        self.assertEqual(opencode_runner.display_name, "OpenCode CLI")
        self.assertEqual(opencode_runner.provider_family, "opencode")
        self.assertEqual(opencode_runner.executable, str(fake_cli))
        self.assertEqual(opencode_runner.model, "opencode/gpt-5-nano")

    def test_build_runner_configs_prefers_discovered_codex_model_over_gpt_5_1(self) -> None:
        args = argparse.Namespace(
            scenario="scientific-calculator-rust",
            runner="codex",
            workspace_root=str(self.workspace_root / "codex-discovery"),
            copilot_model="gpt-5.4",
            codex_model="gpt-5.1",
            kimi_model="kimi-k2.6",
            opencode_model="opencode/gpt-5-nano",
            max_minutes=5,
            command_timeout=120,
            preview_timeout=30,
            npm_command="npm",
            arm_mode="sequential",
            hint_penalty=5.0,
            prepare_only=False,
            skip_npm_install=True,
            list_scenarios=False,
        )

        with mock.patch.object(
            rrb.BenchmarkHarness,
            "discover_available_runner_models",
            return_value=["gpt-5.3-codex", "gpt-5.4", "gpt-5.4-mini"],
            create=True,
        ):
            harness = rrb.BenchmarkHarness(args)

        codex_runner = next(runner for runner in harness.runner_configs if runner.slug == "codex")
        self.assertEqual("gpt-5.4", codex_runner.model)

    def test_build_judge_candidates_excludes_copilot(self) -> None:
        benchmark_runner = rrb.RunnerConfig(
            slug="kimi",
            display_name="Kimi CLI",
            provider_family="moonshot-kimi",
            executable="kimi",
            model="kimi-k2.6",
            supports_json=True,
        )

        candidates = self.harness.build_judge_candidates(benchmark_runner)

        self.assertNotIn("copilot", [candidate.slug for candidate in candidates])

    def test_build_judge_candidates_prefers_router_resolved_codex(self) -> None:
        benchmark_runner = rrb.RunnerConfig(
            slug="kimi",
            display_name="Kimi CLI",
            provider_family="moonshot-kimi",
            executable="kimi",
            model="kimi-k2.6",
            supports_json=True,
        )

        with mock.patch.object(self.harness, "resolve_runner_executable", side_effect=lambda slug: "C:/tools/codex-router.exe" if slug == "codex" else None):
            with mock.patch.object(rrb.shutil, "which", return_value=None):
                candidates = self.harness.build_judge_candidates(benchmark_runner)

        judge_candidate = next(candidate for candidate in candidates if candidate.slug == "codex")
        self.assertEqual(judge_candidate.executable, "C:/tools/codex-router.exe")
        self.assertEqual(judge_candidate.model, rrb.DEFAULT_JUDGE_MODEL)

    def test_run_model_prompt_uses_opencode_json_mode(self) -> None:
        logs_root = self.workspace_root / "opencode" / "recursive-off" / "logs"
        logs_root.mkdir(parents=True, exist_ok=True)
        repo_root = self.repo_root
        captured: dict[str, object] = {}

        def fake_run_logged_command(
            command: list[str],
            *,
            cwd: Path | None = None,
            timeout_seconds: int = 0,
            stdout_path: Path | None = None,
            stderr_path: Path | None = None,
            env: dict[str, str] | None = None,
            check: bool = True,
            allowed_returncodes: tuple[int, ...] = (0,),
        ) -> rrb.CommandResult:
            captured["command"] = command
            captured["cwd"] = cwd
            captured["timeout_seconds"] = timeout_seconds
            captured["stdout_path"] = stdout_path
            captured["stderr_path"] = stderr_path
            captured["env"] = env
            captured["check"] = check
            captured["allowed_returncodes"] = allowed_returncodes
            assert stdout_path is not None
            assert stderr_path is not None
            stdout_path.write_text('{"type":"text"}\n', encoding="utf-8")
            stderr_path.write_text("", encoding="utf-8")
            return rrb.CommandResult(command=command, returncode=0, stdout='{"type":"text"}\n', stderr="", duration_seconds=0.5)

        self.harness.run_logged_command = fake_run_logged_command  # type: ignore[method-assign]

        record, stdout_log, stderr_log = self.harness.run_model_prompt(
            repo_root,
            logs_root,
            runner_slug="opencode",
            executable="D:\\opencode\\opencode-cli.exe",
            model="opencode/gpt-5-nano",
            prompt_text="Reply with exactly: pong",
            log_stem="opencode",
            timeout_seconds=45,
        )

        self.assertEqual(
            captured["command"],
            [
                "D:\\opencode\\opencode-cli.exe",
                "run",
                "--model",
                "opencode/gpt-5-nano",
                "--format",
                "json",
                "--dir",
                str(repo_root),
                "Reply with exactly: pong",
            ],
        )
        self.assertEqual(captured["cwd"], repo_root)
        self.assertEqual(captured["timeout_seconds"], 45)
        self.assertEqual(captured["env"], {})
        self.assertFalse(captured["check"])
        self.assertEqual(captured["stdout_path"], stdout_log)
        self.assertEqual(captured["stderr_path"], stderr_log)
        self.assertEqual(record.returncode, 0)
        self.assertTrue(stdout_log.exists())
        self.assertTrue(stderr_log.exists())

    def test_run_model_prompt_uses_explicit_kimi_benchmark_alias(self) -> None:
        logs_root = self.workspace_root / "kimi" / "recursive-on" / "logs"
        logs_root.mkdir(parents=True, exist_ok=True)
        repo_root = self.repo_root
        temp_config = self.temp_dir / "benchmark-kimi.toml"
        self._write(temp_config, 'default_model = "benchmark-kimi"')
        captured: dict[str, object] = {}

        def fake_build_kimi_temp_config(model_name: str) -> Path:
            captured["model_name"] = model_name
            return temp_config

        def fake_run_logged_command(
            command: list[str],
            *,
            cwd: Path | None = None,
            timeout_seconds: int = 0,
            stdout_path: Path | None = None,
            stderr_path: Path | None = None,
            env: dict[str, str] | None = None,
            check: bool = True,
            allowed_returncodes: tuple[int, ...] = (0,),
        ) -> rrb.CommandResult:
            captured["command"] = command
            captured["cwd"] = cwd
            captured["timeout_seconds"] = timeout_seconds
            captured["stdout_path"] = stdout_path
            captured["stderr_path"] = stderr_path
            captured["env"] = env
            captured["check"] = check
            captured["allowed_returncodes"] = allowed_returncodes
            assert stdout_path is not None
            assert stderr_path is not None
            stdout_path.write_text('{"role":"assistant"}\n', encoding="utf-8")
            stderr_path.write_text("", encoding="utf-8")
            return rrb.CommandResult(command=command, returncode=0, stdout='{"role":"assistant"}\n', stderr="", duration_seconds=0.5)

        self.harness.build_kimi_temp_config = fake_build_kimi_temp_config  # type: ignore[method-assign]
        self.harness.run_logged_command = fake_run_logged_command  # type: ignore[method-assign]

        record, stdout_log, stderr_log = self.harness.run_model_prompt(
            repo_root,
            logs_root,
            runner_slug="kimi",
            executable="C:\\Users\\fixture\\.local\\bin\\kimi.exe",
            model="kimi-code/kimi-for-coding",
            prompt_text="Reply with exactly: pong",
            log_stem="kimi",
            timeout_seconds=45,
        )

        self.assertEqual(captured["model_name"], "kimi-code/kimi-for-coding")
        self.assertEqual(
            captured["command"],
            [
                "C:\\Users\\fixture\\.local\\bin\\kimi.exe",
                "--config-file",
                str(temp_config),
                "--model",
                "benchmark-kimi",
                "--work-dir",
                str(repo_root),
                "--print",
                "--output-format",
                "stream-json",
                "--prompt",
                "Reply with exactly: pong",
            ],
        )
        self.assertEqual(captured["cwd"], repo_root)
        self.assertEqual(captured["timeout_seconds"], 45)
        self.assertEqual(captured["env"], self.harness.runner_invocation_env("kimi"))
        self.assertFalse(captured["check"])
        self.assertEqual(captured["stdout_path"], stdout_log)
        self.assertEqual(captured["stderr_path"], stderr_log)
        self.assertEqual(record.returncode, 0)
        self.assertTrue(stdout_log.exists())
        self.assertTrue(stderr_log.exists())

    def test_run_logged_command_returns_after_parent_exit_with_inherited_log_handles(self) -> None:
        script_path = self.temp_dir / "spawn_inherited_child.py"
        script_path.write_text(
            "\n".join(
                [
                    "import subprocess",
                    "import sys",
                    "import time",
                    "",
                    "if len(sys.argv) > 1 and sys.argv[1] == 'child':",
                    "    time.sleep(2.0)",
                    "    print('child complete', flush=True)",
                    "else:",
                    "    subprocess.Popen(",
                    "        [sys.executable, __file__, 'child'],",
                    "        stdout=None,",
                    "        stderr=None,",
                    "        stdin=subprocess.DEVNULL,",
                    "        close_fds=False,",
                    "    )",
                    "    print('parent complete', flush=True)",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        stdout_log = self.temp_dir / "spawn-stdout.log"
        stderr_log = self.temp_dir / "spawn-stderr.log"

        record = self.harness.run_logged_command(
            [sys.executable, str(script_path)],
            cwd=self.repo_root,
            timeout_seconds=5,
            stdout_path=stdout_log,
            stderr_path=stderr_log,
            check=False,
        )

        self.assertEqual(record.returncode, 0)
        self.assertFalse(record.timed_out)
        self.assertIn("parent complete", record.stdout)
        self.assertLess(record.duration_seconds, 2.0)
        time.sleep(2.2)

    def test_run_logged_command_stops_when_stop_condition_returns_reason(self) -> None:
        script_path = self.temp_dir / "sleep-forever.py"
        script_path.write_text("import time\nwhile True:\n    time.sleep(1)\n", encoding="utf-8")
        stdout_log = self.temp_dir / "stop-stdout.log"
        stderr_log = self.temp_dir / "stop-stderr.log"

        record = self.harness.run_logged_command(
            [sys.executable, str(script_path)],
            cwd=self.repo_root,
            timeout_seconds=30,
            stdout_path=stdout_log,
            stderr_path=stderr_log,
            check=False,
            stop_when=lambda: "controller stop",
        )

        self.assertFalse(record.timed_out)
        self.assertTrue(record.controller_stopped)
        self.assertEqual("controller stop", record.controller_stop_reason)
        self.assertLess(record.duration_seconds, 30.0)

    def test_delivery_completion_stop_reason_detects_idle_recursive_off_success(self) -> None:
        result = rrb.ArmResult(
            runner_slug="codex",
            runner_name="Codex CLI",
            provider_family="codex",
            model="gpt-5.4",
            arm_name="recursive-off",
            repo_root=self.harness.rel(self.repo_root),
            product_root=self.harness.rel(self.repo_root),
        )
        self.harness.reset_repo_activity_baseline(result)
        self._write(
            self.repo_root / "benchmark" / "agent-log.md",
            "\n".join(
                [
                    "# Benchmark Agent Log",
                    "",
                    "## 2026-04-18T22:41:13Z",
                    "",
                    "- Tried: validated the finished app and cleaned up temp artifacts.",
                    "- Issues met: no new issues.",
                    "- Build/test/preview status changed: build passed; test passed; preview still running on `http://127.0.0.1:4273/`.",
                    "- Screenshots: `benchmark/screenshots/team-capacity-board-desktop.png`.",
                    "- Token/usage metrics: unavailable from runtime.",
                ]
            ),
        )
        screenshot_path = self.repo_root / "benchmark" / "screenshots" / "team-capacity-board-desktop.png"
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        screenshot_path.write_bytes(b"png")
        self.harness.current_repo_activity_payload(result)
        state = self.harness._repo_activity_states[self.harness.arm_activity_key(result)]
        state.last_change_epoch = time.time() - 90

        reason = self.harness.delivery_completion_stop_reason(self.repo_root, self.repo_root, result)

        self.assertIsNotNone(reason)
        assert reason is not None
        self.assertIn("confirmed delivery evidence", reason)

    def test_score_planner_repo_detects_summary_from_visible_items(self) -> None:
        source_text = """
        const visibleItems = useMemo(() => filterItems(items, filters), [items, filters]);
        const groupedItems = useMemo(() => groupItemsByStatus(visibleItems), [visibleItems]);
        const summary = useMemo(() => summarizeItems(visibleItems), [visibleItems]);
        """
        result = self._make_result()
        awarded: dict[str, float] = {}

        def add_score(
            label: str,
            awarded_value: float,
            maximum: float,
            *,
            zero_issue: str = "",
            partial_issue: str = "",
        ) -> None:
            awarded[label] = awarded_value

        self.harness.score_planner_repo(source_text.lower(), result, add_score)

        self.assertEqual(5.0, awarded["displayed_summary"])

    def test_parse_args_accepts_opencode_runner_and_model(self) -> None:
        with mock.patch.object(
            sys,
            "argv",
            [
                "run-recursive-benchmark.py",
                "--runner",
                "opencode",
                "--opencode-model",
                "opencode/gpt-5-nano",
            ],
        ):
            args = rrb.parse_args()

        self.assertEqual(args.runner, "opencode")
        self.assertEqual(args.opencode_model, "opencode/gpt-5-nano")

    def test_parse_args_defaults_codex_model_to_gpt_5_4(self) -> None:
        with mock.patch.object(sys, "argv", ["run-recursive-benchmark.py"]):
            args = rrb.parse_args()

        self.assertEqual(args.codex_model, "gpt-5.4")
        self.assertTrue(args.provision_dependencies)

    def test_parse_args_supports_skipping_dependency_provisioning(self) -> None:
        with mock.patch.object(
            sys,
            "argv",
            ["run-recursive-benchmark.py", "--skip-dependency-provisioning"],
        ):
            args = rrb.parse_args()

        self.assertFalse(args.provision_dependencies)

    def test_powershell_wrapper_forwards_full_python_interface_with_real_pwsh(self) -> None:
        if os.name == "nt":
            self.skipTest("Unix executable shim is used for this portable PowerShell parity test.")
        pwsh = shutil.which("pwsh")
        if pwsh is None:
            self.skipTest("pwsh is unavailable")

        wrapper_root = self.temp_dir / "benchmark-powershell-wrapper"
        wrapper_root.mkdir(parents=True)
        source_wrapper = Path(rrb.__file__).with_suffix(".ps1")
        wrapper_path = wrapper_root / source_wrapper.name
        shutil.copy2(source_wrapper, wrapper_path)
        capture_path = wrapper_root / "forwarded-arguments.json"
        fake_driver = wrapper_root / "run-recursive-benchmark.py"
        self._write(
            fake_driver,
            "\n".join(
                [
                    "import json",
                    "import os",
                    "import sys",
                    "from pathlib import Path",
                    "Path(os.environ['RECURSIVE_BENCHMARK_ARGUMENT_CAPTURE']).write_text(",
                    "    json.dumps(sys.argv[1:]),",
                    "    encoding='utf-8',",
                    ")",
                ]
            ),
        )
        shim_root = wrapper_root / "bin"
        shim_root.mkdir()
        python_shim = shim_root / "python"
        self._write(
            python_shim,
            f"#!/bin/sh\nexec {shlex.quote(sys.executable)} \"$@\"\n",
        )
        python_shim.chmod(0o755)
        workspace_arg = str(wrapper_root / "workspace with spaces")
        environment = os.environ.copy()
        environment["PATH"] = str(shim_root) + os.pathsep + environment.get("PATH", "")
        environment["RECURSIVE_BENCHMARK_ARGUMENT_CAPTURE"] = str(capture_path)

        completed = subprocess.run(
            [
                pwsh,
                "-NoLogo",
                "-NoProfile",
                "-File",
                str(wrapper_path),
                "-Scenario",
                "scientific-calculator-rust",
                "-Runner",
                "opencode",
                "-WorkspaceRoot",
                workspace_arg,
                "-KimiModel",
                "kimi-test",
                "-OpenCodeModel",
                "opencode/test",
                "-MaxMinutes",
                "7",
                "-CommandTimeout",
                "123",
                "-PreviewTimeout",
                "19",
                "-NpmCommand",
                "npm-test",
                "-ArmMode",
                "parallel",
                "-HintPenalty",
                "6",
                "-ListScenarios",
                "-PrepareOnly",
                "-SkipNpmInstall",
                "-SkipDependencyProvisioning",
            ],
            cwd=wrapper_root,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        forwarded = json.loads(capture_path.read_text(encoding="utf-8"))
        self.assertEqual(
            [
                "--scenario",
                "scientific-calculator-rust",
                "--runner",
                "opencode",
                "--codex-model",
                "gpt-5.4",
                "--kimi-model",
                "kimi-test",
                "--opencode-model",
                "opencode/test",
                "--max-minutes",
                "7",
                "--command-timeout",
                "123",
                "--preview-timeout",
                "19",
                "--npm-command",
                "npm-test",
                "--arm-mode",
                "parallel",
                "--hint-penalty",
                "6",
                "--workspace-root",
                workspace_arg,
                "--list-scenarios",
                "--prepare-only",
                "--skip-npm-install",
                "--skip-dependency-provisioning",
            ],
            forwarded,
        )

    def test_parse_worktree_location_accepts_generic_location_field(self) -> None:
        text = "\n".join(
            [
                "## Worktree Details",
                "",
                f"- Location: `.worktrees/{self.run_id}`",
                f"- Product root: `.worktrees/{self.run_id}`",
            ]
        )

        candidate, isolation_status, raw_location = self.harness.parse_worktree_location(self.repo_root, text)

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.resolve(), self.worktree_root.resolve())
        self.assertEqual(isolation_status, "isolated-worktree")
        self.assertEqual(raw_location, f".worktrees/{self.run_id}")

    def test_read_repo_source_includes_files_under_worktree_root(self) -> None:
        self._write(
            self.worktree_root / "src" / "main.rs",
            "fn format_result() {} // keyboardevent localstorage memory history sin cos tan sqrt log10 ln\n",
        )
        self._write(self.worktree_root / "index.html", "<div class='expression-display main-display'></div>\n")
        self._write(self.worktree_root / "target" / "debug" / "ignored.rs", "should not be scanned\n")

        source_text = self.harness.read_repo_source(self.worktree_root)

        self.assertIn("format_result", source_text)
        self.assertIn("keyboardevent", source_text)
        self.assertIn("expression-display", source_text)
        self.assertNotIn("should not be scanned", source_text)

    def test_prepare_evaluation_root_snapshots_nested_rust_worktree(self) -> None:
        self._write(self.worktree_root / "src" / "main.rs", "fn main() {}\n")
        logs_root = self.workspace_root / "codex" / "recursive-on" / "logs"
        result = self._make_result()

        evaluation_root = self.harness.prepare_evaluation_root(self.repo_root, self.worktree_root, logs_root, result)

        self.assertNotEqual(evaluation_root.resolve(), self.worktree_root.resolve())
        self.assertTrue((evaluation_root / "Cargo.toml").exists())
        self.assertTrue((evaluation_root / "src" / "main.rs").exists())
        self.assertFalse((evaluation_root / ".git").exists())
        self.assertEqual(result.log_paths["evaluation_root"], "codex/recursive-on/logs/evaluation-root")

    def test_prepare_recursive_lint_root_materializes_worktree_changes_and_skips_runtime_dirs(self) -> None:
        self._write(self.worktree_root / "src" / "main.rs", "fn main() {}\n")
        self._write(self.worktree_root / "node_modules" / ".bin" / "tool.cmd", "runtime\n")
        self._write(self.worktree_root / "app.tsbuildinfo", "{}\n")
        self._write(self.repo_root / ".playwright-mcp" / "trace.json", "{\"trace\":true}\n")
        self._write(self.repo_root / ".cargo-target-dir" / "release" / "artifact.txt", "runtime\n")
        logs_root = self.workspace_root / "codex" / "recursive-on" / "logs"
        result = self._make_result()

        lint_root = self.harness.prepare_recursive_lint_root(self.repo_root, self.worktree_root, logs_root, result)

        self.assertTrue((lint_root / ".worktrees" / self.run_id / "src" / "main.rs").exists())
        self.assertFalse((lint_root / ".worktrees" / self.run_id / ".git").exists())
        self.assertFalse((lint_root / ".worktrees" / self.run_id / "node_modules").exists())
        self.assertFalse((lint_root / ".worktrees" / self.run_id / "app.tsbuildinfo").exists())
        self.assertFalse((lint_root / ".playwright-mcp").exists())
        self.assertFalse((lint_root / ".cargo-target-dir").exists())
        status = self._git(lint_root, "status", "--short", "--untracked-files=all").stdout
        diff = self._git(lint_root, "diff", "--name-only").stdout
        self.assertIn(f".worktrees/{self.run_id}/src/main.rs", diff)
        self.assertNotIn(".playwright-mcp/trace.json", status)
        self.assertNotIn(".cargo-target-dir/release/artifact.txt", status)
        self.assertNotIn(f".worktrees/{self.run_id}/node_modules/.bin/tool.cmd", diff)
        self.assertNotIn(f".worktrees/{self.run_id}/app.tsbuildinfo", diff)

    def test_prepare_recursive_lint_root_can_replace_existing_snapshot(self) -> None:
        self._write(self.worktree_root / "src" / "main.rs", "fn main() {}\n")
        logs_root = self.workspace_root / "codex" / "recursive-on" / "logs"
        result = self._make_result()

        first_lint_root = self.harness.prepare_recursive_lint_root(self.repo_root, self.worktree_root, logs_root, result)
        self.assertTrue((first_lint_root / ".worktrees" / self.run_id / "src" / "main.rs").exists())

        second_lint_root = self.harness.prepare_recursive_lint_root(self.repo_root, self.worktree_root, logs_root, result)

        self.assertEqual(first_lint_root, second_lint_root)
        self.assertTrue((second_lint_root / ".worktrees" / self.run_id / "src" / "main.rs").exists())

    def test_prepare_recursive_lint_root_only_surfaces_actual_worktree_drift(self) -> None:
        self._write(self.worktree_root / "src" / "main.rs", "fn main() {}\n")
        logs_root = self.workspace_root / "codex" / "recursive-on" / "logs"
        result = self._make_result()

        lint_root = self.harness.prepare_recursive_lint_root(self.repo_root, self.worktree_root, logs_root, result)

        diff = self._git(lint_root, "diff", "--name-only").stdout
        self.assertIn(f".worktrees/{self.run_id}/src/main.rs", diff)
        self.assertNotIn(f".worktrees/{self.run_id}/Cargo.lock", diff)
        self.assertNotIn(f".worktrees/{self.run_id}/styles.css", diff)
        self.assertNotIn(f".worktrees/{self.run_id}/benchmark/agent-log.md", diff)

    def test_prepare_recursive_lint_root_ignores_worktree_control_plane_duplicates(self) -> None:
        self._write(self.worktree_root / "src" / "main.rs", "fn main() {}\n")
        self._write(self.worktree_root / ".recursive" / "run" / self.run_id / "00-worktree.md", "worktree artifact\n")
        self._write(self.worktree_root / ".recursive" / "run" / self.run_id / "00-requirements.md", "requirements artifact\n")
        self._write(self.worktree_root / "benchmark" / "expected-product-root.txt", f".worktrees/{self.run_id}\n")
        self._write(self.worktree_root / "benchmark" / "benchmark-context.json", "{\"run_id\":\"benchmark-test-run\"}\n")
        self._write(self.worktree_root / "benchmark" / "run-id.txt", f"{self.run_id}\n")
        self._write(self.worktree_root / "benchmark" / "recursive-templates" / "00-worktree.md", "template\n")
        logs_root = self.workspace_root / "codex" / "recursive-on" / "logs"
        result = self._make_result()

        lint_root = self.harness.prepare_recursive_lint_root(self.repo_root, self.worktree_root, logs_root, result)

        diff = self._git(lint_root, "diff", "--name-only").stdout
        self.assertIn(f".worktrees/{self.run_id}/src/main.rs", diff)
        self.assertNotIn(
            f".worktrees/{self.run_id}/.recursive/run/{self.run_id}/00-worktree.md",
            diff,
        )
        self.assertNotIn(
            f".worktrees/{self.run_id}/.recursive/run/{self.run_id}/00-requirements.md",
            diff,
        )
        self.assertNotIn(f".worktrees/{self.run_id}/benchmark/expected-product-root.txt", diff)
        self.assertNotIn(f".worktrees/{self.run_id}/benchmark/benchmark-context.json", diff)
        self.assertNotIn(f".worktrees/{self.run_id}/benchmark/run-id.txt", diff)
        self.assertNotIn(f".worktrees/{self.run_id}/benchmark/recursive-templates/00-worktree.md", diff)

    def test_write_report_surfaces_judge_adjusted_entry_rows(self) -> None:
        off = rrb.ArmResult(
            runner_slug="codex",
            runner_name="Codex CLI",
            provider_family="codex",
            model="gpt-5.4",
            arm_name="recursive-off",
            status="pass",
            product_status="pass",
            agent_status="pass",
            score=30.0,
            score_max=35.0,
            heuristic_percentage=85.7,
            judge_score=8.0,
            judge_max=10.0,
            judge_percentage=80.0,
            benchmark_score=84.0,
            score_breakdown={"responsive_ui": 5.0},
            score_breakdown_max={"responsive_ui": 5.0},
        )
        on = rrb.ArmResult(
            runner_slug="codex",
            runner_name="Codex CLI",
            provider_family="codex",
            model="gpt-5.4",
            arm_name="recursive-on",
            status="pass-with-runner-issue",
            product_status="pass",
            agent_status="completed",
            score=35.0,
            score_max=35.0,
            heuristic_percentage=100.0,
            judge_score=7.0,
            judge_max=10.0,
            judge_percentage=70.0,
            benchmark_score=91.0,
            score_breakdown={"responsive_ui": 5.0},
            score_breakdown_max={"responsive_ui": 5.0},
            judge_adjusted_score_breakdown={"responsive_ui": 0.0},
            judge_adjusted_score=30.0,
            judge_entry_adjustment_reasons={"responsive_ui": "Screenshot review showed the layout broke on small screens."},
        )
        self.harness.results = [off, on]

        report_path = self.harness.write_report()
        report = report_path.read_text(encoding="utf-8")

        self.assertIn("normalized:entry-adjusted", report)
        self.assertIn("`0 (raw 5)`", report)
        self.assertIn("on adjusted 5 -> 0 (Screenshot review showed the layout broke on small screens.)", report)
        self.assertIn("#### Judge-adjusted score breakdown", report)

    def test_packaged_node_vite_starters_match_scenario_titles(self) -> None:
        benchmark_root = self.harness.repo_source_root / "references" / "benchmarks"
        node_vite_scenarios = {
            "local-first-planner": "Local First Planner",
            "team-capacity-board": "Team Capacity Board",
            "release-readiness-dashboard": "Release Readiness Dashboard",
        }

        for scenario_slug, scenario_title in node_vite_scenarios.items():
            starter_root = benchmark_root / scenario_slug / "starter"
            root_label = str(starter_root.relative_to(self.harness.repo_source_root))

            with self.subTest(root=root_label, file="README.md"):
                first_line = (starter_root / "README.md").read_text(encoding="utf-8").splitlines()[0]
                self.assertEqual(f"# {scenario_title} benchmark starter", first_line)

            with self.subTest(root=root_label, file="index.html"):
                index_html = (starter_root / "index.html").read_text(encoding="utf-8")
                self.assertIn(f"<title>{scenario_title} Benchmark</title>", index_html)

            with self.subTest(root=root_label, file="src/App.tsx"):
                app_source = (starter_root / "src" / "App.tsx").read_text(encoding="utf-8")
                self.assertIn(f"<h1>{scenario_title}</h1>", app_source)

            with self.subTest(root=root_label, file="src/App.test.tsx"):
                test_source = (starter_root / "src" / "App.test.tsx").read_text(encoding="utf-8")
                self.assertIn(f'name: "{scenario_title}"', test_source)

    def test_packaged_recursive_on_prompts_preserve_required_todo_heading(self) -> None:
        benchmark_root = self.harness.repo_source_root / "references" / "benchmarks"

        for prompt_path in sorted(benchmark_root.glob("*/prompt-recursive-on.md")):
            prompt_text = prompt_path.read_text(encoding="utf-8")

            with self.subTest(prompt=str(prompt_path.relative_to(self.harness.repo_source_root))):
                self.assertIn("Keep the required `## TODO` heading", prompt_text)
                self.assertNotIn("remove the template `## TODO` section entirely", prompt_text)
                self.assertIn("benchmark/recursive-skills/", prompt_text)
                self.assertIn("benchmark/recursive-templates/", prompt_text)
                self.assertIn(".recursive/config/recursive-router.json", prompt_text)
                self.assertIn(".recursive/config/recursive-router-discovered.json", prompt_text)
                self.assertIn("follow that routed policy instead of inventing or hardcoding a CLI/model", prompt_text)
                self.assertIn("Do not start Phase 2 until `01-as-is.md` is lint-valid and locked", prompt_text)
                self.assertIn("run strict recursive lint for run `{{RUN_ID}}`", prompt_text)
                self.assertIn("If planner is routed, make a bounded planner call during Phase 2 before locking `02-to-be-plan.md`", prompt_text)
                self.assertIn("Do not defer all routed delegation until the end merely to save time", prompt_text)
                self.assertIn("Timeout or latency by itself is not a valid override reason for skipping a configured routed stage", prompt_text)
                self.assertIn("`python scripts/recursive-router-invoke.py`", prompt_text)
                self.assertIn("`python scripts/recursive-subagent-action.py`", prompt_text)

    def test_packaged_recursive_on_prompts_include_stricter_worktree_and_closeout_rules(self) -> None:
        benchmark_root = self.harness.repo_source_root / "references" / "benchmarks"
        required_snippets = (
            "The expected implementation root for this run is `{{EXPECTED_PRODUCT_ROOT}}` relative to the repository root.",
            "Treat `{{EXPECTED_PRODUCT_ROOT}}` as the product root for all product edits, builds, tests, previews, and screenshots unless the control-plane docs force a different path.",
            "Do not implement the product in the control-plane repo root when `{{EXPECTED_PRODUCT_ROOT}}` is available.",
            "Before your final response, verify that the run folder contains concise, lock-valid artifacts through `08-memory-impact.md`",
            "Use pragmatic recursive defaults unless the control-plane docs require something stricter:",
        )

        for prompt_path in sorted(benchmark_root.glob("*/prompt-recursive-on.md")):
            prompt_text = prompt_path.read_text(encoding="utf-8")

            with self.subTest(prompt=str(prompt_path.relative_to(self.harness.repo_source_root))):
                for snippet in required_snippets:
                    self.assertIn(snippet, prompt_text)

    def test_packaged_benchmark_requirements_omit_assumptions_section(self) -> None:
        benchmark_root = self.harness.repo_source_root / "references" / "benchmarks"

        for requirements_path in sorted(benchmark_root.glob("*/00-requirements.md")):
            requirements_text = requirements_path.read_text(encoding="utf-8")

            with self.subTest(requirements=str(requirements_path.relative_to(self.harness.repo_source_root))):
                self.assertNotIn("## Assumptions", requirements_text)

    def test_benchmark_prompt_mirror_tree_is_absent(self) -> None:
        mirror_root = self.harness.repo_source_root / "references" / "benchmarks" / "benchmarks"
        self.assertEqual([], sorted(mirror_root.glob("*/prompt-recursive-on.md")))

    def test_benchmark_requirements_mirror_tree_is_absent(self) -> None:
        mirror_root = self.harness.repo_source_root / "references" / "benchmarks" / "benchmarks"
        self.assertEqual([], sorted(mirror_root.glob("*/00-requirements.md")))


if __name__ == "__main__":
    unittest.main()
