#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = REPO_ROOT / "skills" / "recursive-mode" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))


def load_module(module_name: str, filename: str):
    module_path = SCRIPT_DIR / filename
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


training_sync = load_module("recursive_training_sync", "recursive-training-sync.py")
training_loader = load_module("recursive_training_loader", "recursive-training-loader.py")
training_grpo = load_module("recursive_training_grpo", "recursive-training-grpo.py")
recursive_init = load_module("recursive_init", "recursive-init.py")
recursive_closeout = load_module("recursive_closeout", "recursive-closeout.py")


MEMORY_ROUTER = """# MEMORY.md

<!-- RECURSIVE-MODE-MEMORY:START -->
## Memory Router

Use this file as the memory index.
<!-- RECURSIVE-MODE-MEMORY:END -->
"""


TRAINING_DOC = """Type: training
Status: CURRENT
Scope: commit-workflow
Owns-Paths:
Watch-Paths:
- git workflow
Source-Runs: run-a, run-b
Validated-At-Commit:
Last-Validated: 2026-05-12T00:00:00Z
Tags: training, reasoningbank

# Training Memory: commit-workflow

## Extracted Reasoning Items (2026-05-12T00:00:00Z)

### RB-0: Branch before commit

**Description:** Create a feature branch first

**Content:** Create a branch before remediation work and verify before commit.

```yaml
rb_id: "RB-0"
title: "Branch before commit"
description: "Create a feature branch first"
task_type: "commit-workflow"
subsystem: "git-workflow"
source_runs: ["run-a", "run-b"]
applies_to: ["git workflow", ".worktrees/"]
success_rate: 1.00
status: active
created_at: "2026-05-12T00:00:00Z"
```
"""

STALE_TRAINING_DOC = """Type: training
Status: STALE
Scope: stale-workflow
Owns-Paths:
Watch-Paths:
- stale workflow
Source-Runs: run-z
Validated-At-Commit:
Last-Validated: 2026-05-12T00:00:00Z
Tags: training, reasoningbank

# Training Memory: stale-workflow

## Extracted Reasoning Items (2026-05-12T00:00:00Z)

### RB-0: Ignore this stale doc

**Description:** This should not load by default

**Content:** Stale docs should be excluded from default retrieval.

```yaml
rb_id: "RB-0"
title: "Ignore this stale doc"
description: "This should not load by default"
task_type: "stale-workflow"
subsystem: "legacy"
source_runs: ["run-z"]
applies_to: ["legacy workflow"]
success_rate: 0.10
status: active
created_at: "2026-05-12T00:00:00Z"
```
"""


class RecursiveTrainingTests(unittest.TestCase):
    def create_repo(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory(prefix="recursive-training-")
        self.addCleanup(temp_dir.cleanup)
        repo_root = Path(temp_dir.name) / "repo"
        (repo_root / ".recursive" / "memory" / "training").mkdir(parents=True, exist_ok=True)
        (repo_root / ".recursive" / "memory" / "domains").mkdir(parents=True, exist_ok=True)
        (repo_root / ".github").mkdir(parents=True, exist_ok=True)
        (repo_root / ".recursive" / "memory" / "MEMORY.md").write_text(
            MEMORY_ROUTER,
            encoding="utf-8",
            newline="\n",
        )
        (repo_root / ".recursive" / "memory" / "training" / "commit-workflow.md").write_text(
            TRAINING_DOC,
            encoding="utf-8",
            newline="\n",
        )
        (repo_root / "AGENTS.md").write_text(
            "# Existing AGENTS\n\nKeep this content.\n",
            encoding="utf-8",
            newline="\n",
        )
        (repo_root / ".cursorrules").write_text(
            "# Existing Cursor rules\n",
            encoding="utf-8",
            newline="\n",
        )
        (repo_root / "CLAUDE.md").write_text(
            "# Existing Claude notes\n",
            encoding="utf-8",
            newline="\n",
        )
        (repo_root / ".github" / "copilot-instructions.md").write_text(
            "# Existing Copilot notes\n",
            encoding="utf-8",
            newline="\n",
        )
        return repo_root

    def test_sync_prints_startup_guidance_without_touching_memory_or_pointer_files(self) -> None:
        repo_root = self.create_repo()
        original_agents = (repo_root / "AGENTS.md").read_text(encoding="utf-8")
        original_cursorrules = (repo_root / ".cursorrules").read_text(encoding="utf-8")
        original_claude = (repo_root / "CLAUDE.md").read_text(encoding="utf-8")
        original_copilot = (repo_root / ".github" / "copilot-instructions.md").read_text(encoding="utf-8")
        original_memory_md = (repo_root / ".recursive" / "memory" / "MEMORY.md").read_text(encoding="utf-8")

        sync = training_sync.ExperienceSync(str(repo_root))
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            sync.sync_all()

        updated_agents = (repo_root / "AGENTS.md").read_text(encoding="utf-8")
        memory_md = (repo_root / ".recursive" / "memory" / "MEMORY.md").read_text(encoding="utf-8")

        self.assertEqual(original_agents, updated_agents)
        self.assertEqual(original_cursorrules, (repo_root / ".cursorrules").read_text(encoding="utf-8"))
        self.assertEqual(original_claude, (repo_root / "CLAUDE.md").read_text(encoding="utf-8"))
        self.assertEqual(
            original_copilot,
            (repo_root / ".github" / "copilot-instructions.md").read_text(encoding="utf-8"),
        )
        self.assertEqual(original_memory_md, memory_md)
        self.assertIn("read `/.recursive/memory/memory.md` first", stdout.getvalue().lower())
        self.assertIn("training/commit-workflow.md", stdout.getvalue())
        self.assertFalse((repo_root / ".recursive" / "memory" / "TRAINING-REGISTRY.md").exists())
        self.assertFalse((repo_root / "README-EXPERIENCES.md").exists())

    def test_loader_discovers_training_docs_from_filesystem(self) -> None:
        repo_root = self.create_repo()

        registry = training_loader.MemoryRegistry(str(repo_root))
        docs = registry.discover()

        self.assertTrue(any(doc.rel_path == "training/commit-workflow.md" for doc in docs))
        self.assertTrue(any(doc.doc_type == "training" for doc in docs))

    def test_loader_excludes_stale_docs_from_default_discovery(self) -> None:
        repo_root = self.create_repo()
        (repo_root / ".recursive" / "memory" / "training" / "stale-workflow.md").write_text(
            STALE_TRAINING_DOC,
            encoding="utf-8",
            newline="\n",
        )

        registry = training_loader.MemoryRegistry(str(repo_root))
        docs = registry.discover()

        self.assertFalse(any(doc.rel_path == "training/stale-workflow.md" for doc in docs))

    def test_loader_dry_run_returns_preview(self) -> None:
        repo_root = self.create_repo()
        sync = training_sync.ExperienceSync(str(repo_root))
        sync.sync_all()

        loader = training_loader.MemoryLoader(str(repo_root))
        output = loader.load(query="commit workflow", dry_run=True)

        self.assertIn("DRY RUN: Memory Loader Preview", output)
        self.assertIn("training/commit-workflow.md", output)

    def test_recursive_init_runs_training_loader_when_installed(self) -> None:
        repo_root = self.create_repo()
        scripts_dir = repo_root / ".recursive" / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        capture_path = repo_root / "loader-args.txt"
        (scripts_dir / "recursive-training-loader.py").write_text(
            "\n".join(
                [
                    "import pathlib",
                    "import sys",
                    f"pathlib.Path(r\"{capture_path}\").write_text(' '.join(sys.argv[1:]), encoding='utf-8')",
                    "print('loader ran')",
                ]
            ),
            encoding="utf-8",
            newline="\n",
        )

        result = recursive_init.run_training_loader(repo_root, "phase-1_commit-fix", "bugfix", "#123")

        self.assertEqual(result, 0)
        captured = capture_path.read_text(encoding="utf-8")
        self.assertIn("--repo-root", captured)
        self.assertIn("--query", captured)
        self.assertIn("bugfix recursive run phase 1 commit fix #123", captured)

    def test_recursive_init_continues_when_training_loader_fails(self) -> None:
        repo_root = self.create_repo()
        scripts_dir = repo_root / ".recursive" / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        (scripts_dir / "recursive-training-loader.py").write_text(
            "import sys\nprint('loader failed intentionally')\nsys.exit(2)\n",
            encoding="utf-8",
            newline="\n",
        )

        result = recursive_init.run_training_loader(repo_root, "phase-1_commit-fix", "bugfix", "#123")

        self.assertEqual(result, 0)

    def test_recursive_closeout_runs_phase8_trigger_when_installed(self) -> None:
        repo_root = self.create_repo()
        scripts_dir = repo_root / ".recursive" / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        capture_path = repo_root / "trigger-args.txt"
        (scripts_dir / "recursive-training-phase8-trigger.py").write_text(
            "\n".join(
                [
                    "import pathlib",
                    "import sys",
                    f"pathlib.Path(r\"{capture_path}\").write_text(' '.join(sys.argv[1:]), encoding='utf-8')",
                    "print('trigger ran')",
                ]
            ),
            encoding="utf-8",
            newline="\n",
        )

        result = recursive_closeout.run_phase8_training_trigger(repo_root, "run-123")

        self.assertEqual(result, 0)
        captured = capture_path.read_text(encoding="utf-8")
        self.assertIn("--repo-root", captured)
        self.assertIn("--run-id run-123", captured)
        self.assertIn("--auto", captured)

    def test_training_extract_script_skips_cleanly_by_default(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "recursive-training-extract.py"),
                "--repo-root",
                str(SCRIPT_DIR.parent),
                "--prompt-file",
                str(SCRIPT_DIR / "recursive-training-extract.py"),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("Training extractor is not available", completed.stderr)

    def test_training_extract_script_honors_response_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="recursive-training-extract-") as temp_dir:
            prompt = Path(temp_dir) / "prompt.txt"
            response = Path(temp_dir) / "items.json"
            prompt.write_text("extract", encoding="utf-8")
            response.write_text('[{"title":"T","description":"D","content":"C"}]', encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "recursive-training-extract.py"),
                    "--repo-root",
                    str(SCRIPT_DIR.parent),
                    "--prompt-file",
                    str(prompt),
                    "--response-file",
                    str(response),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(completed.returncode, 0)
        self.assertIn('"title":"T"', completed.stdout)

    def test_training_grpo_uses_generic_extractor_contract(self) -> None:
        source = (SCRIPT_DIR / "recursive-training-grpo.py").read_text(encoding="utf-8")

        self.assertNotIn("OPENAI_API_KEY", source)
        self.assertNotIn("OPENAI_BASE_URL", source)
        self.assertNotIn("AsyncOpenAI", source)
        self.assertNotIn("extraction runtime", source)

    def test_training_memory_writer_includes_subsystem_schema_field(self) -> None:
        repo_root = self.create_repo()
        rb_memory = training_grpo.ReasoningBankMemory(repo_root)

        rb_memory.write_training_memory(
            "commit-workflow",
            "git-workflow",
            [{
                "title": "Branch before commit",
                "description": "Create a feature branch first",
                "content": "Create a branch before remediation work and verify before commit.",
                "applies_to": ["git workflow", ".worktrees/"],
            }],
            ["run-a", "run-b"],
            ["run-a", "run-b"],
        )

        content = (repo_root / ".recursive" / "memory" / "training" / "commit-workflow.md").read_text(encoding="utf-8")
        self.assertIn('subsystem: "git-workflow"', content)

    def test_powershell_wrappers_do_not_pass_removed_llm_provider(self) -> None:
        for name in (
            "recursive-training-grpo.ps1",
            "recursive-training-phase8-trigger.ps1",
            "recursive-training-extract.ps1",
        ):
            text = (SCRIPT_DIR / name).read_text(encoding="utf-8")
            self.assertNotIn("llm-provider", text.lower().replace("_", "-"))
            self.assertNotIn("LlmProvider", text)

    def test_shared_rb_id_and_dedup_across_domain_and_training_writes(self) -> None:
        repo_root = self.create_repo()
        rb = training_grpo.ReasoningBankMemory(repo_root)
        item = {
            "title": "Shared identity",
            "description": "One id",
            "content": "Same learning once.",
            "task_type": "commit-workflow",
            "applies_to": ["scripts/"],
        }
        written = rb.write_domain_memory("scripts", [item], ["run-a"], ["run-a"], ["scripts/a.mjs"])
        self.assertEqual(len(written), 1)
        rb.write_training_memory("shared-identity-workflow", "scripts", written, ["run-a"], ["run-a"])
        # Second identical domain write should dedup
        again = rb.write_domain_memory("scripts", [item], ["run-b"], ["run-b"], ["scripts/b.mjs"])
        self.assertEqual(again, [])

        domain = (repo_root / ".recursive" / "memory" / "domains" / "scripts.md").read_text(encoding="utf-8")
        training = (repo_root / ".recursive" / "memory" / "training" / "shared-identity-workflow.md").read_text(encoding="utf-8")
        import re
        self.assertEqual(re.findall(r'rb_id: "(RB-\d+)"', domain), re.findall(r'rb_id: "(RB-\d+)"', training))
        self.assertEqual(domain.count("### RB-"), 1)

    def test_phase4_pass_rows_ignore_red_and_phase8_gate(self) -> None:
        repo_root = self.create_repo()
        runs = repo_root / ".recursive" / "run"
        complete = runs / "80-complete"
        incomplete = runs / "82-incomplete"
        for run_dir, with_phase8 in ((complete, True), (incomplete, False)):
            run_dir.mkdir(parents=True)
            (run_dir / "00-requirements.md").write_text(
                "Status: LOCKED\n\nThis run implements product work.\n\n"
                "- `scripts/track-b/a.mjs`\nCoverage: PASS\nApproval: PASS\n"
                "## Audit Verdict\n\n**PASS**\n",
                encoding="utf-8",
                newline="\n",
            )
            (run_dir / "03-implementation-summary.md").write_text(
                "Status: LOCKED\n\n- `scripts/track-b/a.mjs`\nCoverage: PASS\nApproval: PASS\n"
                "## Audit Verdict\n\n**PASS**\n",
                encoding="utf-8",
                newline="\n",
            )
            (run_dir / "04-test-summary.md").write_text(
                "Status: LOCKED\nCoverage: PASS\nApproval: PASS\n## Audit Verdict\n\n**PASS**\n\n"
                "## Results Summary\n\n| Suite | Result |\n|---|---|\n"
                "| Bindings | 5/5 PASS |\n| Historical RED | 4/5 FAIL as expected |\n\n"
                "Overall Phase 4 automated verdict: PASS\n",
                encoding="utf-8",
                newline="\n",
            )
            (run_dir / "05-manual-qa.md").write_text(
                "Status: LOCKED\n\n## QA Verdict\n\n**PASS**\nApproval: PASS\n",
                encoding="utf-8",
                newline="\n",
            )
            if with_phase8:
                (run_dir / "08-memory-impact.md").write_text(
                    "Status: LOCKED\nLockedAt: 2026-07-25T00:00:00Z\nCoverage: PASS\nApproval: PASS\n"
                    "## Audit Verdict\n\n**PASS**\n",
                    encoding="utf-8",
                    newline="\n",
                )

        rollouts = training_grpo.parse_all_runs(runs)
        ids = {r.run_id for r in rollouts}
        self.assertIn("80-complete", ids)
        self.assertNotIn("82-incomplete", ids)
        winner = next(r for r in rollouts if r.run_id == "80-complete")
        self.assertTrue(winner.is_complete_winner)
        self.assertEqual(winner.subsystem, "scripts")

    def test_incremental_keeps_subsystem_peers_only(self) -> None:
        repo_root = self.create_repo()
        runs = repo_root / ".recursive" / "run"

        def add_run(run_id: str, path: str) -> None:
            run_dir = runs / run_id
            run_dir.mkdir(parents=True)
            for name in (
                "00-requirements.md",
                "03-implementation-summary.md",
                "04-test-summary.md",
                "05-manual-qa.md",
                "08-memory-impact.md",
            ):
                body = (
                    f"Status: LOCKED\nLockedAt: 2026-07-25T00:00:00Z\n"
                    f"Coverage: PASS\nApproval: PASS\n## Audit Verdict\n\n**PASS**\n\n"
                    f"- `{path}`\n\n## Results Summary\n\n| Suite | Result |\n|---|---|\n"
                    f"| Unit | 1/1 PASS |\n\nOverall Phase 4 automated verdict: PASS\n\n"
                    f"## QA Verdict\n\n**PASS**\n"
                )
                (run_dir / name).write_text(body, encoding="utf-8", newline="\n")

        add_run("79-a", "scripts/a.mjs")
        add_run("80-b", "scripts/b.mjs")
        add_run("81-other", "extensions/foo.ts")
        rollouts = training_grpo.parse_all_runs(runs)
        filtered = training_grpo.filter_rollouts_for_training(rollouts, "80-b")
        ids = {r.run_id for r in filtered}
        self.assertEqual(ids, {"79-a", "80-b"})

    def test_grpo_exits_nonzero_when_extractor_unavailable(self) -> None:
        repo_root = self.create_repo()
        runs = repo_root / ".recursive" / "run"
        for run_id in ("79-a", "80-b"):
            run_dir = runs / run_id
            run_dir.mkdir(parents=True)
            for name in (
                "00-requirements.md",
                "03-implementation-summary.md",
                "04-test-summary.md",
                "05-manual-qa.md",
                "08-memory-impact.md",
            ):
                (run_dir / name).write_text(
                    "Status: LOCKED\nLockedAt: 2026-07-25T00:00:00Z\n"
                    "Coverage: PASS\nApproval: PASS\n## Audit Verdict\n\n**PASS**\n\n"
                    "- `scripts/a.mjs`\n\n## Results Summary\n\n| Suite | Result |\n|---|---|\n"
                    "| Unit | 1/1 PASS |\n\nOverall Phase 4 automated verdict: PASS\n\n"
                    "## QA Verdict\n\n**PASS**\n",
                    encoding="utf-8",
                    newline="\n",
                )

        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "recursive-training-grpo.py"),
                "--repo-root",
                str(repo_root),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)

    def test_closeout_warns_when_phase8_trigger_exits_non_success(self) -> None:
        repo_root = self.create_repo()
        scripts_dir = repo_root / ".recursive" / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        (scripts_dir / "recursive-training-phase8-trigger.py").write_text(
            "import sys\nprint('no items')\nsys.exit(3)\n",
            encoding="utf-8",
            newline="\n",
        )
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = recursive_closeout.run_phase8_training_trigger(repo_root, "run-123")
        self.assertEqual(result, 3)
        self.assertIn("[WARN]", stdout.getvalue())
        self.assertNotIn("[OK] Ran recursive-training Phase 8 trigger.", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
