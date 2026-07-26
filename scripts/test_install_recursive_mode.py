#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
ROOT_SKILL_DIR = REPO_ROOT / "skills" / "recursive-mode"
RUNTIME_DIR = ROOT_SKILL_DIR / "scripts"
MODULE_PATH = RUNTIME_DIR / "install-recursive-mode.py"
SPEC = importlib.util.spec_from_file_location("install_recursive_mode", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load install module from {MODULE_PATH}")
install = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = install
SPEC.loader.exec_module(install)

ROUTER_LIB_PATH = RUNTIME_DIR / "recursive_router_lib.py"
ROUTER_SPEC = importlib.util.spec_from_file_location("recursive_router_lib", ROUTER_LIB_PATH)
if ROUTER_SPEC is None or ROUTER_SPEC.loader is None:
    raise RuntimeError(f"Unable to load router module from {ROUTER_LIB_PATH}")
router_lib = importlib.util.module_from_spec(ROUTER_SPEC)
sys.modules[ROUTER_SPEC.name] = router_lib
ROUTER_SPEC.loader.exec_module(router_lib)

HYGIENE_MODULE_PATH = RUNTIME_DIR / "check-reusable-repo-hygiene.py"
HYGIENE_SPEC = importlib.util.spec_from_file_location("check_reusable_repo_hygiene", HYGIENE_MODULE_PATH)
if HYGIENE_SPEC is None or HYGIENE_SPEC.loader is None:
    raise RuntimeError(f"Unable to load hygiene module from {HYGIENE_MODULE_PATH}")
hygiene = importlib.util.module_from_spec(HYGIENE_SPEC)
sys.modules[HYGIENE_SPEC.name] = hygiene
HYGIENE_SPEC.loader.exec_module(hygiene)


def windows_temp_source_fixture() -> str:
    return "\\".join(("C:", "Users", "example", "AppData", "Local", "Temp", "skills-src"))


class InstallRecursiveModeTests(unittest.TestCase):
    def _assert_skills_cli_local_install_set(self, *required_skills: str) -> None:
        if os.environ.get("RUN_SKILLS_CLI_INTEGRATION") != "1":
            self.skipTest("Set RUN_SKILLS_CLI_INTEGRATION=1 to enable local Skills CLI integration coverage")

        npx = shutil.which("npx")
        if npx is None:
            self.skipTest("npx is required for Skills CLI integration coverage")

        with tempfile.TemporaryDirectory(prefix="skills-cli-distribution-") as temp_dir:
            workspace = Path(temp_dir)
            completed = subprocess.run(
                [
                    npx,
                    "skills",
                    "add",
                    str(REPO_ROOT),
                    "--skill",
                    *required_skills,
                    "--full-depth",
                    "--agent",
                    "codex",
                    "-y",
                ],
                cwd=workspace,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
                timeout=180,
            )

            self.assertEqual(
                completed.returncode,
                0,
                f"skills add failed\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}",
            )
            installed_skills = workspace / ".agents" / "skills"
            self.assertEqual(set(required_skills), {path.name for path in installed_skills.iterdir()})
            for skill_name in required_skills:
                with self.subTest(skill=skill_name):
                    self.assertTrue((installed_skills / skill_name / "SKILL.md").exists())

    def test_documented_recursive_mode_install_commands_use_published_fork(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        install_section = readme.split("## Install", 1)[1].split("## Quick Start", 1)[0]
        recursive_mode_sources = re.findall(
            r"^npx skills add (\S*recursive-mode\S*)",
            install_section,
            flags=re.MULTILINE,
        )

        self.assertTrue(recursive_mode_sources)
        self.assertEqual({"screenfluent/recursive-mode"}, set(recursive_mode_sources))
        self.assertNotIn("try-works/recursive-mode", readme)

    def test_documented_recursive_spec_install_sets_cover_supported_branches(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        install_section = readme.split("## Install", 1)[1].split("## Quick Start", 1)[0]
        selected_skill_sets = {
            tuple(tokens[tokens.index("--skill") + 1 : tokens.index("--full-depth")])
            for line in install_section.splitlines()
            if line.startswith("npx skills add screenfluent/recursive-mode --skill")
            for tokens in (shlex.split(line),)
        }

        self.assertTrue(
            {
                ("recursive-spec",),
                ("recursive-mode", "recursive-spec"),
                ("recursive-mode", "recursive-spec", "recursive-delivery-slicing"),
                (
                    "recursive-mode",
                    "recursive-spec",
                    "recursive-delivery-slicing",
                    "recursive-router",
                    "recursive-subagent",
                ),
            }.issubset(selected_skill_sets)
        )

    def test_package_surface_matches_expected_skills(self) -> None:
        repo_root = REPO_ROOT
        installable_skills = {path.parent.name for path in (repo_root / "skills").glob("*/SKILL.md")}

        self.assertEqual(
            {
                "recursive-architecture-survey",
                "recursive-debugging",
                "recursive-codebase-design",
                "recursive-delivery-slicing",
                "recursive-domain-modeling",
                "recursive-grilling",
                "recursive-handoff",
                "recursive-merge-conflicts",
                "recursive-mode",
                "recursive-prototype",
                "recursive-research",
                "recursive-residue-sweep",
                "recursive-review",
                "recursive-review-bundle",
                "recursive-router",
                "recursive-spec",
                "recursive-subagent",
                "recursive-tdd",
                "recursive-training",
                "recursive-wayfinder",
                "recursive-worktree",
            },
            installable_skills,
        )
        self.assertFalse((repo_root / "SKILL.md").exists())
        self.assertTrue((ROOT_SKILL_DIR / "scripts" / "install-recursive-mode.py").exists())

    def test_bootstrap_workflow_copy_matches_canonical(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        start = "<!-- RECURSIVE-MODE-CANONICAL:START -->"
        end = "<!-- RECURSIVE-MODE-CANONICAL:END -->"
        canonical_raw = (repo_root / ".recursive" / "RECURSIVE.md").read_text(encoding="utf-8")
        bootstrap_raw = (ROOT_SKILL_DIR / "references" / "bootstrap" / "RECURSIVE.md").read_text(encoding="utf-8")

        canonical = install.normalize_plain_or_wrapped_content(canonical_raw, start, end)
        bootstrap = install.normalize_plain_or_wrapped_content(bootstrap_raw, start, end)

        self.assertEqual(canonical, bootstrap)

    def test_resolve_canonical_workflow_path_prefers_repo_recursive_doc(self) -> None:
        with tempfile.TemporaryDirectory(prefix="install-recursive-mode-workflow-") as temp_dir:
            skill_root = Path(temp_dir)
            bootstrap_path = skill_root / "references" / "bootstrap" / "RECURSIVE.md"
            repo_recursive_path = skill_root / ".recursive" / "RECURSIVE.md"
            bootstrap_path.parent.mkdir(parents=True, exist_ok=True)
            repo_recursive_path.parent.mkdir(parents=True, exist_ok=True)
            bootstrap_path.write_text("bootstrap", encoding="utf-8")
            repo_recursive_path.write_text("repo-recursive", encoding="utf-8")

            resolved = install.resolve_canonical_workflow_path(skill_root)

            self.assertEqual(repo_recursive_path, resolved)

    def test_powershell_installer_prefers_repo_recursive_doc(self) -> None:
        ps1_script = MODULE_PATH.with_suffix(".ps1").read_text(encoding="utf-8")
        repo_index = ps1_script.index('(Join-Path (Join-Path $SkillRoot ".recursive") "RECURSIVE.md")')
        bootstrap_index = ps1_script.index(
            '(Join-Path (Join-Path $SkillRoot "references") "bootstrap\\RECURSIVE.md")'
        )

        self.assertLess(repo_index, bootstrap_index)

    def test_normalize_plain_or_wrapped_content_prefers_plain_prefix(self) -> None:
        start = "<!-- START -->"
        end = "<!-- END -->"
        plain = "alpha\nbeta"
        malformed = f"{plain}\n\n{start}\nwrapped body\n{end}\n"

        self.assertEqual(plain, install.normalize_plain_or_wrapped_content(malformed, start, end))

    def test_generated_bridges_avoid_source_repository_only_paths(self) -> None:
        generated_bodies = {
            "recursive agents router": install.recursive_agents_router_body(),
            "plans bridge": install.plans_bridge_body(),
        }
        source_repository_only_paths = (
            "`/.recursive/README.md`",
            "`/skills/recursive-spec/SKILL.md`",
            "`/scripts/install-recursive-mode.py`",
            "`/references/artifact-template.md`",
            "`/skills/recursive-router/SKILL.md`",
            "`/skills/recursive-training/SKILL.md`",
            "/skills/recursive-benchmark/SKILL.md",
            "/references/benchmarks/local-first-planner/README.md",
            "/scripts/run-recursive-benchmark.py",
        )

        for body_name, body in generated_bodies.items():
            for source_path in source_repository_only_paths:
                with self.subTest(body=body_name, source_path=source_path):
                    self.assertNotIn(source_path, body)

    def test_tracked_model_facing_bridges_match_installer_generated_blocks(self) -> None:
        bridges = (
            (
                REPO_ROOT / ".agent" / "PLANS.md",
                "<!-- RECURSIVE-MODE-PLANS-BRIDGE:START -->",
                "<!-- RECURSIVE-MODE-PLANS-BRIDGE:END -->",
                install.plans_bridge_body(),
            ),
            (
                REPO_ROOT / ".recursive" / "AGENTS.md",
                "<!-- RECURSIVE-MODE-AGENTS:START -->",
                "<!-- RECURSIVE-MODE-AGENTS:END -->",
                install.recursive_agents_router_body(),
            ),
        )

        for path, start_marker, end_marker, generated_body in bridges:
            with self.subTest(path=str(path.relative_to(REPO_ROOT))):
                content = path.read_bytes()
                start_bytes = start_marker.encode("utf-8")
                end_bytes = end_marker.encode("utf-8")
                self.assertEqual(1, content.count(start_bytes))
                self.assertEqual(1, content.count(end_bytes))
                actual_block = content[
                    content.index(start_bytes) : content.index(end_bytes) + len(end_bytes)
                ]
                expected_block = (
                    start_bytes
                    + b"\n"
                    + generated_body.rstrip("\r\n").encode("utf-8")
                    + b"\n"
                    + end_bytes
                )
                self.assertEqual(expected_block, actual_block)

    def test_generated_delegated_review_route_includes_finding_protocol_owner(self) -> None:
        body = install.recursive_agents_router_body()
        delegated_review_route = body.split(
            "- Working on delegated review, subagent behavior, or routed CLI delegation:",
            1,
        )[1].split("- Working on memory behavior:", 1)[0]

        self.assertIn("`recursive-review`", delegated_review_route)
        self.assertIn("`recursive-review-bundle`", delegated_review_route)

    def test_gitattributes_excludes_benchmark_add_on_from_default_exports(self) -> None:
        gitattributes = Path(__file__).resolve().parent.parent / ".gitattributes"
        content = gitattributes.read_text(encoding="utf-8")

        self.assertIn("references/benchmark-addon export-ignore", content)
        self.assertIn("references/benchmarks export-ignore", content)
        self.assertIn("scripts/run-recursive-benchmark.py export-ignore", content)

    def test_benchmark_add_on_is_not_a_default_skill_entrypoint(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        self.assertFalse((repo_root / "skills" / "recursive-benchmark" / "SKILL.md").exists())
        self.assertFalse((repo_root / "skills" / "recursive-benchmark" / "recursive-benchmark" / "SKILL.md").exists())
        self.assertTrue(
            (repo_root / "references" / "benchmark-addon" / "recursive-benchmark" / "BENCHMARK-ADDON.md").exists()
        )
        self.assertTrue(
            (
                repo_root
                / "references"
                / "benchmark-addon"
                / "recursive-benchmark"
                / "recursive-benchmark"
                / "BENCHMARK-ADDON.md"
            ).exists()
        )

    def test_mirrored_benchmark_add_on_source_doc_matches_primary_copy(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        primary = (
            repo_root / "references" / "benchmark-addon" / "recursive-benchmark" / "BENCHMARK-ADDON.md"
        ).read_text(encoding="utf-8")
        mirror = (
            repo_root
            / "references"
            / "benchmark-addon"
            / "recursive-benchmark"
            / "recursive-benchmark"
            / "BENCHMARK-ADDON.md"
        ).read_text(encoding="utf-8")

        self.assertEqual(primary, mirror)

    def test_training_and_router_skill_manifests_exist(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        self.assertTrue((repo_root / "skills" / "recursive-training" / "agents" / "openai.yaml").exists())
        self.assertTrue((repo_root / "skills" / "recursive-router" / "agents" / "openai.yaml").exists())

    def test_installer_gitignores_device_local_router_discovery_inventory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="install-recursive-mode-") as temp_dir:
            repo_root = Path(temp_dir) / "repo"
            completed = subprocess.run(
                [sys.executable, str(MODULE_PATH), "--repo-root", str(repo_root)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(
                completed.returncode,
                0,
                f"installer failed\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}",
            )
            self.assertTrue((repo_root / ".recursive" / "config" / "recursive-router.json").exists())
            self.assertFalse((repo_root / ".recursive" / "config" / "recursive-router-discovered.json").exists())
            gitignore = (repo_root / ".gitignore").read_text(encoding="utf-8")
            self.assertIn("/.recursive/config/recursive-router-discovered.json", gitignore)

    def test_installer_bootstraps_runtime_and_training_memory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="install-recursive-mode-training-") as temp_dir:
            repo_root = Path(temp_dir) / "repo"
            completed = subprocess.run(
                [sys.executable, str(MODULE_PATH), "--repo-root", str(repo_root)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(
                completed.returncode,
                0,
                f"installer failed\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}",
            )
            self.assertTrue((repo_root / ".recursive" / "memory" / "training" / ".gitkeep").exists())
            self.assertTrue((repo_root / ".recursive" / "scripts" / "recursive-training-loader.py").exists())
            self.assertTrue((repo_root / ".recursive" / "scripts" / "recursive-training-sync.py").exists())
            self.assertTrue((repo_root / ".recursive" / "scripts" / "recursive-training-extract.py").exists())
            for script_name in (
                "recursive-init.py",
                "recursive-status.py",
                "lint-recursive-run.py",
                "recursive-lock.py",
                "verify-locks.py",
                "recursive-closeout.py",
                "recursive-review-bundle.py",
                "recursive-review-ledger.py",
                "recursive-review-ledger.ps1",
                "recursive-subagent-action.py",
                "recursive_phase_rules.py",
                "recursive_review_action.py",
                "recursive_review_ledger.py",
                "recursive_review_surface.py",
                "recursive_router_lib.py",
            ):
                with self.subTest(script_name=script_name):
                    self.assertTrue((repo_root / ".recursive" / "scripts" / script_name).exists())
            self.assertIn(
                "RECURSIVE-MODE-MEMORY-POINTERS:START",
                (repo_root / ".cursorrules").read_text(encoding="utf-8"),
            )
            self.assertIn(
                "recursive-mode memory pointers",
                (repo_root / "CLAUDE.md").read_text(encoding="utf-8"),
            )
            self.assertIn(
                "recursive-mode memory pointers",
                (repo_root / ".github" / "copilot-instructions.md").read_text(encoding="utf-8"),
            )

    def test_installer_upserts_assistant_memory_pointers_without_removing_existing_content(self) -> None:
        with tempfile.TemporaryDirectory(prefix="install-recursive-mode-pointers-") as temp_dir:
            repo_root = Path(temp_dir) / "repo"
            github_root = repo_root / ".github"
            github_root.mkdir(parents=True, exist_ok=True)
            (repo_root / ".cursorrules").write_text("# Custom cursor notes\n", encoding="utf-8", newline="\n")
            (repo_root / "CLAUDE.md").write_text("# Team Claude notes\n", encoding="utf-8", newline="\n")
            (github_root / "copilot-instructions.md").write_text(
                "# Team Copilot notes\n",
                encoding="utf-8",
                newline="\n",
            )

            completed = subprocess.run(
                [sys.executable, str(MODULE_PATH), "--repo-root", str(repo_root)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(
                completed.returncode,
                0,
                f"installer failed\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}",
            )
            self.assertIn("Custom cursor notes", (repo_root / ".cursorrules").read_text(encoding="utf-8"))
            self.assertIn("Team Claude notes", (repo_root / "CLAUDE.md").read_text(encoding="utf-8"))
            self.assertIn(
                "Team Copilot notes",
                (github_root / "copilot-instructions.md").read_text(encoding="utf-8"),
            )
            self.assertIn(
                "RECURSIVE-MODE-MEMORY-POINTERS:START",
                (repo_root / ".cursorrules").read_text(encoding="utf-8"),
            )
            self.assertIn(
                "RECURSIVE-MODE-MEMORY-POINTERS:START",
                (repo_root / "CLAUDE.md").read_text(encoding="utf-8"),
            )
            self.assertIn(
                "RECURSIVE-MODE-MEMORY-POINTERS:START",
                (github_root / "copilot-instructions.md").read_text(encoding="utf-8"),
            )

    def test_installer_upserts_root_agents_without_removing_existing_content(self) -> None:
        with tempfile.TemporaryDirectory(prefix="install-recursive-mode-agents-") as temp_dir:
            repo_root = Path(temp_dir) / "repo"
            repo_root.mkdir(parents=True, exist_ok=True)
            agents_path = repo_root / "AGENTS.md"
            agents_path.write_text("# Team Notes\n\nKeep this custom content.\n", encoding="utf-8", newline="\n")

            completed = subprocess.run(
                [sys.executable, str(MODULE_PATH), "--repo-root", str(repo_root)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(
                completed.returncode,
                0,
                f"installer failed\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}",
            )
            updated = agents_path.read_text(encoding="utf-8")
            self.assertIn("Keep this custom content.", updated)
            self.assertIn("<!-- RECURSIVE-MODE-AGENTS:START -->", updated)

    def test_installer_upserts_recursive_md_without_replacing_existing_content(self) -> None:
        with tempfile.TemporaryDirectory(prefix="install-recursive-mode-recursive-upsert-") as temp_dir:
            repo_root = Path(temp_dir) / "repo"
            recursive_root = repo_root / ".recursive"
            recursive_root.mkdir(parents=True, exist_ok=True)
            recursive_path = recursive_root / "RECURSIVE.md"
            custom_header = "# My Repo\n\nCustom notes above the workflow.\n"
            recursive_path.write_text(custom_header, encoding="utf-8", newline="\n")

            completed = subprocess.run(
                [sys.executable, str(MODULE_PATH), "--repo-root", str(repo_root)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(
                completed.returncode,
                0,
                f"installer failed\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}",
            )
            updated = recursive_path.read_text(encoding="utf-8")
            self.assertIn("Custom notes above the workflow.", updated)
            self.assertIn("<!-- RECURSIVE-MODE-CANONICAL:START -->", updated)
            self.assertIn("<!-- RECURSIVE-MODE-CANONICAL:END -->", updated)

    def test_installer_migrates_plain_recursive_md_to_marked_version(self) -> None:
        with tempfile.TemporaryDirectory(prefix="install-recursive-mode-recursive-migrate-") as temp_dir:
            repo_root = Path(temp_dir) / "repo"

            # First install: creates a marked RECURSIVE.md
            completed = subprocess.run(
                [sys.executable, str(MODULE_PATH), "--repo-root", str(repo_root)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(
                completed.returncode,
                0,
                f"first install failed\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}",
            )
            recursive_path = repo_root / ".recursive" / "RECURSIVE.md"
            first_content = recursive_path.read_text(encoding="utf-8")
            self.assertIn("<!-- RECURSIVE-MODE-CANONICAL:START -->", first_content)

            # Re-install: must be idempotent — no content duplication
            completed2 = subprocess.run(
                [sys.executable, str(MODULE_PATH), "--repo-root", str(repo_root)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(
                completed2.returncode,
                0,
                f"re-install failed\nSTDOUT:\n{completed2.stdout}\nSTDERR:\n{completed2.stderr}",
            )
            second_content = recursive_path.read_text(encoding="utf-8")
            self.assertEqual(first_content, second_content, "Re-install must not alter RECURSIVE.md content")
            # Canonical block must appear exactly once
            self.assertEqual(1, second_content.count("<!-- RECURSIVE-MODE-CANONICAL:START -->"))

    def test_installer_migrates_legacy_plain_recursive_md_without_duplication(self) -> None:
        """Simulates upgrading a repo that was bootstrapped with the old sync_plain_file installer."""
        with tempfile.TemporaryDirectory(prefix="install-recursive-mode-recursive-legacy-") as temp_dir:
            repo_root = Path(temp_dir) / "repo"
            recursive_root = repo_root / ".recursive"
            recursive_root.mkdir(parents=True, exist_ok=True)
            recursive_path = recursive_root / "RECURSIVE.md"

            # Simulate the old installer: write the canonical body as plain content (no markers)
            skill_root = Path(MODULE_PATH).resolve().parent.parent
            canonical_source = install.resolve_canonical_workflow_path(skill_root)
            canonical_body = install.normalize_plain_or_wrapped_content(
                canonical_source.read_text(encoding="utf-8"),
                "<!-- RECURSIVE-MODE-CANONICAL:START -->",
                "<!-- RECURSIVE-MODE-CANONICAL:END -->",
            )
            recursive_path.write_text(canonical_body + "\n", encoding="utf-8", newline="\n")
            self.assertNotIn("<!-- RECURSIVE-MODE-CANONICAL:START -->", recursive_path.read_text(encoding="utf-8"))

            # Run updated installer — should migrate to marked version, not duplicate content
            completed = subprocess.run(
                [sys.executable, str(MODULE_PATH), "--repo-root", str(repo_root)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(
                completed.returncode,
                0,
                f"installer failed\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}",
            )
            updated = recursive_path.read_text(encoding="utf-8")
            self.assertIn("<!-- RECURSIVE-MODE-CANONICAL:START -->", updated)
            self.assertEqual(1, updated.count("<!-- RECURSIVE-MODE-CANONICAL:START -->"),
                             "Canonical block must not be duplicated on legacy migration")

    def test_powershell_installer_migrates_legacy_router_policy(self) -> None:
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        if powershell is None:
            self.skipTest("PowerShell is required for installer parity tests")

        with tempfile.TemporaryDirectory(prefix="install-recursive-mode-ps1-") as temp_dir:
            repo_root = Path(temp_dir) / "repo"
            config_root = repo_root / ".recursive" / "config"
            config_root.mkdir(parents=True, exist_ok=True)
            legacy_policy_path = config_root / "recursive-router-cli.json"
            legacy_discovery_path = config_root / "recursive-router-cli-discovered.json"
            policy = router_lib.default_router_policy()
            role_routes = policy["role_routes"]
            assert isinstance(role_routes, dict)
            code_reviewer = role_routes["code-reviewer"]
            assert isinstance(code_reviewer, dict)
            code_reviewer["cli"] = "codex"
            code_reviewer["model"] = "gpt-5.4-mini"
            cli_overrides = policy["cli_overrides"]
            assert isinstance(cli_overrides, dict)
            cli_overrides["codex"] = {"command": "codex-router.exe"}
            legacy_policy_path.write_text(router_lib.pretty_json(policy), encoding="utf-8", newline="\n")
            legacy_discovery_path.write_text(
                router_lib.pretty_json(
                    router_lib.empty_discovery_inventory(
                        probe_tool="recursive-router-probe",
                        probe_status="complete",
                        clis=[{"id": "codex", "resolved_path": "C:/tools/codex-router.exe", "models": ["gpt-5.4-mini"]}],
                    )
                ),
                encoding="utf-8",
                newline="\n",
            )

            completed = subprocess.run(
                [powershell, "-NoProfile", "-File", str(MODULE_PATH.with_suffix(".ps1")), "-RepoRoot", str(repo_root)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(
                completed.returncode,
                0,
                f"PowerShell installer failed\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}",
            )
            canonical_policy = json.loads((config_root / "recursive-router.json").read_text(encoding="utf-8"))
            self.assertEqual(canonical_policy["role_routes"]["code-reviewer"]["cli"], "codex")
            self.assertEqual(canonical_policy["role_routes"]["code-reviewer"]["model"], "gpt-5.4-mini")
            self.assertEqual(canonical_policy["cli_overrides"]["codex"]["command"], "codex-router.exe")
            self.assertFalse(legacy_policy_path.exists())
            self.assertFalse(legacy_discovery_path.exists())
            self.assertTrue((config_root / "recursive-router-discovered.json").exists())

    def test_powershell_installer_bootstraps_canonical_router_policy_defaults(self) -> None:
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        if powershell is None:
            self.skipTest("PowerShell is required for installer parity tests")

        with tempfile.TemporaryDirectory(prefix="install-recursive-mode-ps1-defaults-") as temp_dir:
            repo_root = Path(temp_dir) / "repo"
            completed = subprocess.run(
                [powershell, "-NoProfile", "-File", str(MODULE_PATH.with_suffix(".ps1")), "-RepoRoot", str(repo_root)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(
                completed.returncode,
                0,
                f"PowerShell installer failed\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}",
            )
            canonical_policy = json.loads((repo_root / ".recursive" / "config" / "recursive-router.json").read_text(encoding="utf-8"))
            self.assertEqual(router_lib.default_router_policy(), canonical_policy)

    def test_powershell_installer_source_includes_runtime_scaffold(self) -> None:
        ps1_script = MODULE_PATH.with_suffix(".ps1").read_text(encoding="utf-8")

        self.assertIn('Join-Path $memoryRoot "training"', ps1_script)
        self.assertIn('$_.Name.StartsWith("recursive-")', ps1_script)
        self.assertIn('"recursive_phase_rules.py"', ps1_script)
        self.assertIn('"recursive_review_action.py"', ps1_script)
        self.assertIn('"recursive_review_ledger.py"', ps1_script)
        self.assertIn('"recursive_review_surface.py"', ps1_script)
        self.assertIn('Join-Path $recursiveRoot "scripts"', ps1_script)

    def test_packaged_powershell_scripts_parse(self) -> None:
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        if powershell is None:
            self.skipTest("PowerShell is required for packaged script syntax coverage")

        parse_command = (
            "$tokens = $null; $parseErrors = $null; "
            "[void][System.Management.Automation.Language.Parser]::ParseFile("
            "$env:RECURSIVE_PS_PARSE_TARGET, [ref]$tokens, [ref]$parseErrors); "
            "if ($parseErrors.Count -gt 0) { "
            "$parseErrors | ForEach-Object { Write-Error $_.Message }; exit 1 }"
        )
        for script_path in sorted(RUNTIME_DIR.glob("*.ps1")):
            with self.subTest(script=script_path.name):
                environment = os.environ.copy()
                environment["RECURSIVE_PS_PARSE_TARGET"] = str(script_path)
                completed = subprocess.run(
                    [powershell, "-NoProfile", "-Command", parse_command],
                    text=True,
                    capture_output=True,
                    check=False,
                    env=environment,
                )
                self.assertEqual(
                    completed.returncode,
                    0,
                    f"PowerShell parse failed for {script_path.name}\n"
                    f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}",
                )

    def test_python_and_powershell_installers_generate_equivalent_scaffolds(self) -> None:
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        if powershell is None:
            self.skipTest("PowerShell is required for cross-installer parity coverage")

        def normalized_snapshot(root: Path) -> dict[Path, str]:
            return {
                path.relative_to(root): path.read_text(encoding="utf-8").replace("\r\n", "\n").rstrip("\n")
                for path in root.rglob("*")
                if path.is_file()
            }

        with tempfile.TemporaryDirectory(prefix="install-recursive-mode-parity-") as temp_dir:
            temp_root = Path(temp_dir)
            python_root = temp_root / "python"
            powershell_root = temp_root / "powershell"
            python_completed = subprocess.run(
                [sys.executable, str(MODULE_PATH), "--repo-root", str(python_root)],
                text=True,
                capture_output=True,
                check=False,
            )
            powershell_completed = subprocess.run(
                [powershell, "-NoProfile", "-File", str(MODULE_PATH.with_suffix(".ps1")), "-RepoRoot", str(powershell_root)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(python_completed.returncode, 0, python_completed.stderr)
            self.assertEqual(powershell_completed.returncode, 0, powershell_completed.stderr)
            python_snapshot = normalized_snapshot(python_root)
            powershell_snapshot = normalized_snapshot(powershell_root)
            self.assertEqual(python_snapshot.keys(), powershell_snapshot.keys())
            for relative_path, python_content in python_snapshot.items():
                with self.subTest(path=str(relative_path)):
                    self.assertEqual(python_content, powershell_snapshot[relative_path])

    def test_shell_installer_source_includes_runtime_fallbacks(self) -> None:
        shell_script = MODULE_PATH.with_suffix(".sh").read_text(encoding="utf-8")

        self.assertIn("run_python_installer python3", shell_script)
        self.assertIn("run_python_installer python", shell_script)
        self.assertIn('py -3 "$SCRIPT_DIR/install-recursive-mode.py"', shell_script)
        self.assertIn('run_powershell_installer pwsh', shell_script)
        self.assertIn('run_powershell_installer powershell', shell_script)
        self.assertIn('"-RepoRoot"', shell_script)
        self.assertIn('"-SkipRecursiveUpdate"', shell_script)
        self.assertFalse(shell_script.endswith("\n\n"))

    def test_shell_installer_powershell_fallback_preserves_skip_recursive_update(self) -> None:
        bash_candidates = []
        if os.name == "nt":
            bash_candidates.extend(
                [
                    Path(r"C:\Program Files\Git\bin\bash.exe"),
                    Path(r"C:\Program Files\Git\usr\bin\bash.exe"),
                ]
            )
        bash_path = next((candidate for candidate in bash_candidates if candidate.exists()), None)
        if bash_path is None:
            bash_from_path = shutil.which("bash")
            if bash_from_path:
                bash_path = Path(bash_from_path)
        if bash_path is None:
            self.skipTest("bash is required for shell installer fallback coverage")

        with tempfile.TemporaryDirectory(prefix="install-recursive-mode-shell-fallback-") as temp_dir:
            repo_root = Path(temp_dir) / "repo"
            repo_root.mkdir(parents=True, exist_ok=True)
            driver_path = Path(temp_dir) / "run-shell-installer.sh"
            shim_dir = Path(temp_dir) / "bin"
            shim_dir.mkdir(parents=True, exist_ok=True)
            powershell_args_path = Path(temp_dir) / "powershell-args.txt"

            def to_git_bash_path(path: Path) -> str:
                raw = path.resolve().as_posix()
                if os.name == "nt" and len(raw) >= 2 and raw[1] == ":":
                    return f"/{raw[0].lower()}/{raw[3:]}"
                return raw

            failing_python_shim = "#!/usr/bin/env bash\nexit 1\n"
            for executable_name in ("python3", "python", "py"):
                executable_path = shim_dir / executable_name
                executable_path.write_text(failing_python_shim, encoding="utf-8", newline="\n")
                executable_path.chmod(0o755)

            powershell_shim = shim_dir / "pwsh"
            powershell_shim.write_text(
                """#!/usr/bin/env bash
set -eu
printf '%s\n' "$@" > "$RECURSIVE_TEST_POWERSHELL_ARGS"
test "$#" -eq 6
test "$1" = "-NoProfile"
test "$2" = "-File"
test "$3" = "$RECURSIVE_TEST_EXPECTED_PS1"
test "$4" = "-SkipRecursiveUpdate"
test "$5" = "-RepoRoot"
test "$6" = "$RECURSIVE_TEST_EXPECTED_REPO"
mkdir -p "$RECURSIVE_TEST_EXPECTED_REPO/.recursive/scripts"
: > "$RECURSIVE_TEST_EXPECTED_REPO/.recursive/scripts/recursive-init.py"
printf '%s\n' 'Skipped RECURSIVE.md update by configuration.'
""",
                encoding="utf-8",
                newline="\n",
            )
            powershell_shim.chmod(0o755)

            script_target = to_git_bash_path(MODULE_PATH.with_suffix(".sh"))
            repo_target = to_git_bash_path(repo_root)
            powershell_target = to_git_bash_path(MODULE_PATH.with_suffix(".ps1"))
            shim_target = to_git_bash_path(shim_dir)
            args_target = to_git_bash_path(powershell_args_path)

            if os.name == "nt":
                path_value = f"{shim_target}:/usr/bin:/bin"
            else:
                path_value = os.pathsep.join((str(shim_dir), "/usr/bin", "/bin"))

            driver_lines = [
                "#!/usr/bin/env bash",
                "set -e",
                f"export PATH='{path_value}'",
                f"export RECURSIVE_TEST_POWERSHELL_ARGS='{args_target}'",
                f"export RECURSIVE_TEST_EXPECTED_PS1='{powershell_target}'",
                f"export RECURSIVE_TEST_EXPECTED_REPO='{repo_target}'",
                f"bash '{script_target}' --skip-recursive-update --repo-root '{repo_target}'",
            ]

            driver_path.write_text("\n".join(driver_lines) + "\n", encoding="utf-8", newline="\n")
            completed = subprocess.run(
                [str(bash_path), str(driver_path)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(
                completed.returncode,
                0,
                f"shell installer fallback failed\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}",
            )
            self.assertIn("Skipped RECURSIVE.md update by configuration.", completed.stdout)
            self.assertTrue((repo_root / ".recursive" / "scripts" / "recursive-init.py").exists())
            self.assertEqual(
                [
                    "-NoProfile",
                    "-File",
                    powershell_target,
                    "-SkipRecursiveUpdate",
                    "-RepoRoot",
                    repo_target,
                ],
                powershell_args_path.read_text(encoding="utf-8").splitlines(),
            )

    def test_hygiene_checker_allows_local_skills_lock_temp_sources(self) -> None:
        with tempfile.TemporaryDirectory(prefix="install-recursive-mode-hygiene-") as temp_dir:
            repo_root = Path(temp_dir) / "repo"
            completed = subprocess.run(
                [sys.executable, str(MODULE_PATH), "--repo-root", str(repo_root)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(
                completed.returncode,
                0,
                f"installer failed\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}",
            )

            (repo_root / ".agents" / "skills" / "recursive-mode").mkdir(parents=True, exist_ok=True)
            skills_lock = {
                "version": 1,
                "skills": {
                    "recursive-mode": {
                        "source": windows_temp_source_fixture(),
                        "sourceType": "local",
                        "computedHash": "abc123",
                    }
                },
            }
            (repo_root / "skills-lock.json").write_text(
                json.dumps(skills_lock, indent=2),
                encoding="utf-8",
                newline="\n",
            )

            hygiene_completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH.with_name("check-reusable-repo-hygiene.py")),
                    "--repo-root",
                    str(repo_root),
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(
                hygiene_completed.returncode,
                0,
                f"hygiene check failed\nSTDOUT:\n{hygiene_completed.stdout}\nSTDERR:\n{hygiene_completed.stderr}",
            )

    def test_repository_sources_contain_no_temp_path_residue(self) -> None:
        offenders = []
        for path in hygiene.iter_text_files(REPO_ROOT):
            content = path.read_text(encoding="utf-8")
            relative_path = path.relative_to(REPO_ROOT).as_posix()
            for pattern in hygiene.TEMP_PATH_RESIDUE_RES:
                if pattern.search(content):
                    offenders.append(relative_path)
                    break

        self.assertEqual([], offenders)

    def test_hygiene_checker_rejects_local_skills_lock_temp_sources_outside_installed_workspace(self) -> None:
        with tempfile.TemporaryDirectory(prefix="install-recursive-mode-hygiene-source-") as temp_dir:
            repo_root = Path(temp_dir) / "repo"
            completed = subprocess.run(
                [sys.executable, str(MODULE_PATH), "--repo-root", str(repo_root)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(
                completed.returncode,
                0,
                f"installer failed\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}",
            )

            skills_lock = {
                "version": 1,
                "skills": {
                    "recursive-mode": {
                        "source": windows_temp_source_fixture(),
                        "sourceType": "local",
                        "computedHash": "abc123",
                    }
                },
            }
            (repo_root / "skills-lock.json").write_text(
                json.dumps(skills_lock, indent=2),
                encoding="utf-8",
                newline="\n",
            )

            hygiene_completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH.with_name("check-reusable-repo-hygiene.py")),
                    "--repo-root",
                    str(repo_root),
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertNotEqual(
                hygiene_completed.returncode,
                0,
                "hygiene check unexpectedly passed for temp-path residue in source workspace",
            )
            self.assertIn("skills-lock.json contains temp-path residue", hygiene_completed.stdout)

    def test_skills_cli_local_install_and_bootstrap_include_runtime(self) -> None:
        if os.environ.get("RUN_SKILLS_CLI_INTEGRATION") != "1":
            self.skipTest("Set RUN_SKILLS_CLI_INTEGRATION=1 to enable local Skills CLI integration coverage")

        npx = shutil.which("npx")
        if npx is None:
            self.skipTest("npx is required for Skills CLI integration coverage")

        repo_root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory(prefix="install-recursive-mode-skills-cli-") as temp_dir:
            workspace = Path(temp_dir)
            try:
                install_completed = subprocess.run(
                    [
                        npx,
                        "skills",
                        "add",
                        str(repo_root),
                        "--skill",
                        "*",
                        "--full-depth",
                        "--agent",
                        "codex",
                        "-y",
                    ],
                    cwd=workspace,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    capture_output=True,
                    check=False,
                    timeout=180,
                )
            except subprocess.TimeoutExpired as exc:
                self.skipTest(f"Skills CLI integration timed out: {exc}")
            combined_output = f"{install_completed.stdout}\n{install_completed.stderr}"
            if "ENOSPC" in combined_output or "no space left on device" in combined_output.lower():
                self.skipTest("Insufficient disk space for Skills CLI integration coverage")

            self.assertEqual(
                install_completed.returncode,
                0,
                f"skills add failed\nSTDOUT:\n{install_completed.stdout}\nSTDERR:\n{install_completed.stderr}",
            )

            installed_root_skill = workspace / ".agents" / "skills" / "recursive-mode"
            self.assertTrue(
                installed_root_skill.exists(),
                f"installed root skill missing\nSTDOUT:\n{install_completed.stdout}\nSTDERR:\n{install_completed.stderr}",
            )
            self.assertTrue((installed_root_skill / "scripts" / "install-recursive-mode.py").exists())
            self.assertTrue((installed_root_skill / "references" / "bootstrap" / "RECURSIVE.md").exists())
            self.assertTrue((installed_root_skill / "references" / "artifact-template.md").exists())
            self.assertTrue((workspace / ".agents" / "skills" / "recursive-training" / "SKILL.md").exists())
            installed_subagent = workspace / ".agents" / "skills" / "recursive-subagent"
            self.assertTrue((installed_subagent / "agents" / "code-reviewer.md").exists())
            self.assertTrue((installed_subagent / "agents" / "implementer.md").exists())

            bootstrap_completed = subprocess.run(
                [
                    sys.executable,
                    str(installed_root_skill / "scripts" / "install-recursive-mode.py"),
                    "--repo-root",
                    str(workspace),
                ],
                cwd=workspace,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(
                bootstrap_completed.returncode,
                0,
                f"installed bootstrap failed\nSTDOUT:\n{bootstrap_completed.stdout}\nSTDERR:\n{bootstrap_completed.stderr}",
            )

            self.assertTrue((workspace / ".recursive" / "memory" / "training" / ".gitkeep").exists())
            self.assertTrue((workspace / ".recursive" / "scripts" / "recursive-training-loader.py").exists())
            self.assertTrue((workspace / ".recursive" / "scripts" / "recursive-training-sync.py").exists())
            self.assertTrue((workspace / ".recursive" / "scripts" / "recursive-training-extract.py").exists())
            self.assertTrue((workspace / ".recursive" / "scripts" / "recursive-init.py").exists())
            self.assertTrue((workspace / ".recursive" / "scripts" / "recursive-status.py").exists())
            self.assertTrue((workspace / ".recursive" / "scripts" / "lint-recursive-run.py").exists())
            self.assertTrue((workspace / ".recursive" / "scripts" / "recursive-lock.py").exists())
            self.assertTrue((workspace / ".recursive" / "scripts" / "verify-locks.py").exists())
            self.assertTrue((workspace / ".cursorrules").exists())
            self.assertTrue((workspace / "CLAUDE.md").exists())
            self.assertTrue((workspace / ".github" / "copilot-instructions.md").exists())

            hygiene_completed = subprocess.run(
                [
                    sys.executable,
                    str(installed_root_skill / "scripts" / "check-reusable-repo-hygiene.py"),
                    "--repo-root",
                    str(workspace),
                ],
                cwd=workspace,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(
                hygiene_completed.returncode,
                0,
                f"installed hygiene check failed\nSTDOUT:\n{hygiene_completed.stdout}\nSTDERR:\n{hygiene_completed.stderr}",
            )

            installed_recursive = (workspace / ".recursive" / "RECURSIVE.md").read_text(encoding="utf-8")
            self.assertIn("/.recursive/memory/training/", installed_recursive)
            self.assertIn("recursive-training-loader.py", installed_recursive)

            first_snapshot = {
                path.relative_to(workspace): path.read_bytes()
                for path in workspace.rglob("*")
                if path.is_file() and ".git" not in path.parts
            }
            bootstrap_again = subprocess.run(
                [
                    sys.executable,
                    str(installed_root_skill / "scripts" / "install-recursive-mode.py"),
                    "--repo-root",
                    str(workspace),
                ],
                cwd=workspace,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(bootstrap_again.returncode, 0, bootstrap_again.stderr)
            second_snapshot = {
                path.relative_to(workspace): path.read_bytes()
                for path in workspace.rglob("*")
                if path.is_file() and ".git" not in path.parts
            }
            self.assertEqual(first_snapshot, second_snapshot)

    def test_skills_cli_local_recursive_spec_install_is_standalone(self) -> None:
        self._assert_skills_cli_local_install_set("recursive-spec")

    def test_skills_cli_local_routed_delivery_install_has_dependency_closure(self) -> None:
        required_skills = (
            "recursive-mode",
            "recursive-spec",
            "recursive-delivery-slicing",
            "recursive-router",
            "recursive-subagent",
        )
        self._assert_skills_cli_local_install_set(*required_skills)

    def test_repo_root_router_policy_is_not_personalized(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        policy_path = repo_root / ".recursive" / "config" / "recursive-router.json"
        self.assertTrue(policy_path.exists())
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        self.assertEqual(router_lib.default_router_policy(), policy)

    def test_repo_root_router_discovery_inventory_is_not_bootstrapped(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        discovery_path = repo_root / ".recursive" / "config" / "recursive-router-discovered.json"
        self.assertFalse(discovery_path.exists())

    def test_root_lockfile_requires_root_package_manifest(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        if (repo_root / "package-lock.json").exists():
            self.assertTrue((repo_root / "package.json").exists())


if __name__ == "__main__":
    unittest.main()
