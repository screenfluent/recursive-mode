#!/usr/bin/env python3
"""
Maintainer regression harness for recursive-mode.

The harness creates a disposable repository, bootstraps recursive-mode into it,
drives a small strict-TDD run through Phase 8, and validates the resulting run
with bounded subprocess timeouts so smoke tests fail fast instead of hanging.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


ARTIFACT_SEQUENCE = [
    "00-requirements.md",
    "00-worktree.md",
    "01-as-is.md",
    "02-to-be-plan.md",
    "03-implementation-summary.md",
    "03.5-code-review.md",
    "04-test-summary.md",
    "05-manual-qa.md",
    "06-decisions-update.md",
    "07-state-update.md",
    "08-memory-impact.md",
]

AUDITED_PHASE_KEYS = {
    "01-as-is.md": "phase-1",
    "02-to-be-plan.md": "phase-2",
    "03-implementation-summary.md": "phase-3",
    "03.5-code-review.md": "phase-3-5",
    "04-test-summary.md": "phase-4",
    "06-decisions-update.md": "phase-6",
    "07-state-update.md": "phase-7",
    "08-memory-impact.md": "phase-8",
}


class SmokeError(RuntimeError):
    """Raised when the smoke harness encounters a hard failure."""


@dataclass
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8", newline="\n")


def append_text(path: Path, content: str) -> None:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    separator = "" if not existing or existing.endswith("\n") else "\n"
    write_text(path, existing + separator + content.rstrip() + "\n")


def dedent_block(content: str) -> str:
    return textwrap.dedent(content).strip() + "\n"


def quote_md(value: str) -> str:
    return f"`{value}`"


def list_block(values: list[str], *, prefix: str = "- ") -> str:
    return "\n".join(f"{prefix}{value}" for value in values)


def replace_field(content: str, field_name: str, raw_value: str) -> str:
    pattern = re.compile(rf"(?m)^[ \t]*(?:[-*][ \t]+)?{re.escape(field_name)}:\s*.*$")
    replacement = f"{field_name}: {raw_value}"
    if pattern.search(content):
        return pattern.sub(replacement, content, count=1)
    return content + ("\n" if not content.endswith("\n") else "") + replacement + "\n"


def remove_field(content: str, field_name: str) -> str:
    pattern = re.compile(rf"(?m)^[ \t]*(?:[-*][ \t]+)?{re.escape(field_name)}:\s*.*(?:\n|$)")
    return pattern.sub("", content)


def strip_lock_metadata(content: str) -> str:
    unlocked = replace_field(content, "Status", quote_md("DRAFT"))
    unlocked = remove_field(unlocked, "LockedAt")
    unlocked = remove_field(unlocked, "LockHash")
    return unlocked


def remove_path_references(content: str, path: str) -> str:
    variants = {path, path.lstrip("/")}
    updated = content
    for variant in variants:
        updated = updated.replace(quote_md(variant), "")
        updated = updated.replace(variant, "")
    return re.sub(r"\n{3,}", "\n\n", updated)


def replace_section(content: str, heading: str, body: str) -> str:
    pattern = re.compile(rf"(?ms)^##\s+{re.escape(heading)}\s*$\n?(.*?)(?=^##\s+|\Z)")
    replacement = f"## {heading}\n\n{body.strip()}\n\n"
    if pattern.search(content):
        return pattern.sub(lambda _match: replacement, content, count=1)
    return content + ("\n" if not content.endswith("\n") else "") + replacement


class SmokeHarness:
    def __init__(
        self,
        *,
        requested_toolchain: str,
        scenario: str,
        temp_root: str,
        keep_temp: bool,
        command_timeout: int,
    ) -> None:
        self.requested_toolchain = requested_toolchain
        self.selected_toolchain = self.normalize_toolchain(requested_toolchain)
        self.scenario = scenario
        self.keep_temp = keep_temp
        self.command_timeout = command_timeout
        self.script_dir = Path(__file__).resolve().parent
        self.repo_source_root = self.script_dir.parent
        self.source_runtime_dir = self.repo_source_root / "skills" / "recursive-mode" / "scripts"
        self.python_exe = Path(sys.executable).resolve()
        self.preflight_notes: list[str] = []
        self.powershell_exe = self._resolve_powershell()
        self.temp_root = Path(temp_root).resolve() if temp_root else None
        self.temp_dir = self._make_temp_dir()
        self.repo_root = self.temp_dir / "repo"
        self.runtime_dir = self.repo_root / ".recursive" / "scripts"
        self.run_id = datetime.now(timezone.utc).strftime("%Y-%m-%d-tiny-tasks-smoke-%H%M%S")
        self.feature_branch = f"recursive/{self.run_id}"
        self.base_branch = "main"
        self.base_commit = ""
        self.bundle_path = ""
        self.review_bundle_paths: dict[str, str] = {}
        self.parity_bundle_path = ""
        self.red_log = ""
        self.green_log = ""
        self.qa_log = ""
        self.preview_log = ""
        self.preview_url = ""
        self.memory_domain_path = ""
        self.plan_addendum_path = ""
        self.test_upstream_gap_addendum_path = ""
        self.subagent_action_record_path = ""
        self.summary: list[str] = []
        self.current_stage = "initialization"

    def note_preflight(self, message: str) -> None:
        if message not in self.preflight_notes:
            self.preflight_notes.append(message)

    @staticmethod
    def normalize_toolchain(value: str) -> str:
        return "mixed" if value == "both" else value

    def _resolve_powershell(self) -> Path | None:
        if os.environ.get("RECURSIVE_SMOKE_DISABLE_POWERSHELL") == "1":
            self.note_preflight("PowerShell discovery disabled by RECURSIVE_SMOKE_DISABLE_POWERSHELL=1.")
            return None
        exe = shutil.which("pwsh") or shutil.which("powershell")
        if not exe:
            return None
        return Path(exe).resolve()

    def _make_temp_dir(self) -> Path:
        if self.temp_root:
            self.temp_root.mkdir(parents=True, exist_ok=True)
            return Path(tempfile.mkdtemp(prefix="recursive-mode-smoke-", dir=str(self.temp_root)))
        return Path(tempfile.mkdtemp(prefix="recursive-mode-smoke-"))

    def log(self, message: str) -> None:
        print(f"[INFO] {message}")

    def run_stage(self, label: str, callback) -> None:
        self.current_stage = label
        self.log(f"Stage start: {label}")
        callback()
        self.summary.append(f"Stage success: {label}")
        self.log(f"Stage success: {label}")

    def repo_rel(self, path: Path | str) -> str:
        candidate = Path(path) if not isinstance(path, Path) else path
        try:
            relative = candidate.resolve().relative_to(self.repo_root.resolve())
        except ValueError:
            relative = Path(str(candidate).replace("\\", "/").lstrip("/"))
        return "/" + relative.as_posix()

    def run_command(
        self,
        command: list[str],
        *,
        cwd: Path | None = None,
        allowed_returncodes: tuple[int, ...] = (0,),
    ) -> CommandResult:
        start = time.perf_counter()
        try:
            env = os.environ.copy()
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            if self.powershell_exe is not None and Path(command[0]).resolve() == self.powershell_exe.resolve():
                env["PYTHON"] = str(self.python_exe)
                env["XDG_CACHE_HOME"] = str(self.temp_dir / "powershell-cache")
            completed = subprocess.run(
                command,
                cwd=str(cwd or self.repo_root),
                text=True,
                capture_output=True,
                timeout=self.command_timeout,
                check=False,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise SmokeError(
                f"Command timed out after {self.command_timeout}s: {' '.join(command)}"
            ) from exc

        duration = time.perf_counter() - start
        result = CommandResult(
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            duration_seconds=duration,
        )
        if completed.returncode not in allowed_returncodes:
            raise SmokeError(self.format_failure("Command failed", result))
        return result

    def format_failure(self, heading: str, result: CommandResult) -> str:
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        details = [
            f"{heading}: {' '.join(result.command)}",
            f"Return code: {result.returncode}",
            f"Duration: {result.duration_seconds:.2f}s",
        ]
        if stdout:
            details.append("STDOUT:")
            details.append(stdout)
        if stderr:
            details.append("STDERR:")
            details.append(stderr)
        return "\n".join(details)

    def git(self, *args: str, allowed_returncodes: tuple[int, ...] = (0,)) -> CommandResult:
        return self.run_command(["git", *args], cwd=self.repo_root, allowed_returncodes=allowed_returncodes)

    def python_command(self, script_name: str, *args: str) -> list[str]:
        return [str(self.python_exe), str(self.runtime_dir / script_name), *args]

    def powershell_command(self, script_name: str, *args: str) -> list[str]:
        if self.powershell_exe is None:
            raise SmokeError("PowerShell command requested but no PowerShell executable is available.")
        return [
            str(self.powershell_exe),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self.runtime_dir / script_name),
            *args,
        ]

    def powershell_splat_command(self, script_name: str, parameters: dict[str, object]) -> list[str]:
        """Invoke a wrapper with real PowerShell arrays instead of ambiguous CSV."""
        if self.powershell_exe is None:
            raise SmokeError("PowerShell command requested but no PowerShell executable is available.")
        payload = base64.b64encode(
            json.dumps(
                {
                    "script": str(self.runtime_dir / script_name),
                    "parameters": parameters,
                },
                ensure_ascii=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).decode("ascii")
        program = "\n".join(
            [
                f"$payloadBytes = [Convert]::FromBase64String('{payload}')",
                "$payloadJson = [Text.Encoding]::UTF8.GetString($payloadBytes)",
                "$payloadObject = $payloadJson | ConvertFrom-Json",
                "$splat = @{}",
                "foreach ($property in $payloadObject.parameters.PSObject.Properties) {",
                "    if ($property.Value -is [System.Array]) {",
                "        $splat[$property.Name] = [string[]]@($property.Value)",
                "    } else {",
                "        $splat[$property.Name] = $property.Value",
                "    }",
                "}",
                "& $payloadObject.script @splat",
                "exit $LASTEXITCODE",
            ]
        )
        encoded_program = base64.b64encode(program.encode("utf-16-le")).decode("ascii")
        return [
            str(self.powershell_exe),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-EncodedCommand",
            encoded_program,
        ]

    def script_command(self, toolchain: str, script_stem: str, *args: str) -> list[str]:
        if toolchain == "python":
            return self.python_command(f"{script_stem}.py", *args)
        if toolchain == "powershell":
            return self.powershell_command(f"{script_stem}.ps1", *args)
        raise SmokeError(f"Unsupported toolchain: {toolchain}")

    def bootstrap_command(self, toolchain: str, *args: str) -> list[str]:
        if toolchain == "python":
            return [str(self.python_exe), str(self.source_runtime_dir / "install-recursive-mode.py"), *args]
        if toolchain == "powershell":
            if self.powershell_exe is None:
                raise SmokeError("PowerShell command requested but no PowerShell executable is available.")
            return [
                str(self.powershell_exe),
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(self.source_runtime_dir / "install-recursive-mode.ps1"),
                *args,
            ]
        raise SmokeError(f"Unsupported bootstrap toolchain: {toolchain}")

    def primary_toolchain(self) -> str:
        return "python" if self.selected_toolchain in {"python", "mixed"} else "powershell"

    def validation_toolchains(self) -> list[str]:
        if self.selected_toolchain == "python":
            return ["python"]
        if self.selected_toolchain == "powershell":
            if self.powershell_exe is None:
                raise SmokeError("Selected toolchain 'powershell' requires a PowerShell executable, but none was detected.")
            return ["powershell"]
        if self.selected_toolchain == "mixed":
            toolchains = ["python"]
            if self.powershell_exe is not None:
                toolchains.append("powershell")
            else:
                self.note_preflight("Skipped PowerShell parity path because no PowerShell executable was detected.")
            return toolchains
        raise SmokeError(f"Unsupported toolchain selection: {self.selected_toolchain}")

    def record_preflight(self) -> None:
        detected_python = str(self.python_exe)
        detected_powershell = str(self.powershell_exe) if self.powershell_exe else "not found"
        executed_toolchains = ", ".join(self.validation_toolchains())
        self.summary.append(f"Requested toolchain: {self.requested_toolchain}")
        self.summary.append(f"Selected toolchain mode: {self.selected_toolchain}")
        self.summary.append(f"Detected executables: python={detected_python}; powershell={detected_powershell}")
        self.summary.append(f"Executed toolchain paths: {executed_toolchains}")
        if self.preflight_notes:
            for note in self.preflight_notes:
                self.summary.append(f"Preflight note: {note}")
                self.log(note)
        else:
            self.summary.append("Preflight note: no fallback or skip decisions were needed.")
        self.log(f"Selected toolchain mode: {self.selected_toolchain}")
        self.log(f"Detected executables -> python: {detected_python}; powershell: {detected_powershell}")
        self.summary.append("Preflight success: toolchain selection and executable discovery completed.")

    def create_base_repo(self) -> None:
        self.repo_root.mkdir(parents=True, exist_ok=True)
        self.git("init")
        self.git("config", "user.name", "Recursive Smoke Harness")
        self.git("config", "user.email", "smoke@example.com")
        self.write_base_fixture()

        primary = self.primary_toolchain()
        self.log(f"Bootstrapping recursive-mode with {primary}.")
        if primary == "python":
            self.run_command(
                self.bootstrap_command("python", "--repo-root", str(self.repo_root)),
                cwd=self.repo_root,
            )
        else:
            self.run_command(
                self.bootstrap_command("powershell", "-RepoRoot", str(self.repo_root)),
                cwd=self.repo_root,
            )

        recursive_agents = (self.repo_root / ".recursive" / "AGENTS.md").read_text(encoding="utf-8")
        if "/skills/recursive-benchmark/SKILL.md" in recursive_agents or "/references/benchmarks/" in recursive_agents:
            raise SmokeError("Default recursive-mode bootstrap still hard-wires benchmark skill/file paths into .recursive/AGENTS.md.")
        if "separate optional `recursive-benchmark` add-on" not in recursive_agents:
            raise SmokeError("Default recursive-mode bootstrap did not explain that recursive-benchmark is a separate opt-in add-on in .recursive/AGENTS.md.")
        for forbidden in (
            "`/.recursive/README.md`",
            "`/skills/recursive-spec/SKILL.md`",
            "`/scripts/install-recursive-mode.py`",
            "`/references/artifact-template.md`",
        ):
            if forbidden in recursive_agents:
                raise SmokeError(f"Default recursive-mode bootstrap still points .recursive/AGENTS.md at missing source-repo path {forbidden}.")

        plans_bridge = (self.repo_root / ".agent" / "PLANS.md").read_text(encoding="utf-8")
        if "separate optional `recursive-benchmark` add-on" not in plans_bridge:
            raise SmokeError("Default recursive-mode bootstrap did not explain that recursive-benchmark is a separate opt-in add-on in .agent/PLANS.md.")
        if "should use the packaged benchmark fixture" in plans_bridge:
            raise SmokeError("Default recursive-mode bootstrap still assumes benchmark fixtures are present in .agent/PLANS.md.")

        codex_agents = (self.repo_root / ".codex" / "AGENTS.md").read_text(encoding="utf-8")
        for forbidden in (
            "`scripts/install-recursive-mode.py`",
            "`scripts/recursive-status.py`",
            "`scripts/lint-recursive-run.py`",
            "`scripts/verify-locks.py`",
        ):
            if forbidden in codex_agents:
                raise SmokeError(f"Default recursive-mode bootstrap still points .codex/AGENTS.md at missing source-repo helper path {forbidden}.")

        router_policy_path = self.repo_root / ".recursive" / "config" / "recursive-router.json"
        router_discovery_path = self.repo_root / ".recursive" / "config" / "recursive-router-discovered.json"
        gitignore_path = self.repo_root / ".gitignore"
        if not router_policy_path.exists():
            raise SmokeError("Default recursive-mode bootstrap did not create /.recursive/config/recursive-router.json.")
        if router_discovery_path.exists():
            raise SmokeError("Default recursive-mode bootstrap should not create /.recursive/config/recursive-router-discovered.json before probe.")
        if not gitignore_path.exists():
            raise SmokeError("Default recursive-mode bootstrap did not create .gitignore for device-local router discovery state.")
        gitignore = gitignore_path.read_text(encoding="utf-8")
        if "/.recursive/config/recursive-router-discovered.json" not in gitignore:
            raise SmokeError("Default recursive-mode bootstrap did not gitignore /.recursive/config/recursive-router-discovered.json.")
        self.run_command(
            self.python_command("recursive-router-probe.py", "--repo-root", str(self.repo_root), "--json"),
            cwd=self.repo_root,
        )
        if not router_discovery_path.exists():
            raise SmokeError("recursive-router probe did not create /.recursive/config/recursive-router-discovered.json.")

        self.run_command([str(self.python_exe), "-m", "unittest", "-q"], cwd=self.repo_root)
        self.git("add", "-A")
        self.git("commit", "-m", "Base tiny tasks app with recursive-mode scaffold")
        self.git("branch", "-M", self.base_branch)
        self.base_commit = self.git("rev-parse", "HEAD").stdout.strip()
        self.git("checkout", "-b", self.feature_branch)
        self.summary.append("Bootstrap success: disposable repo initialized and recursive-mode installer completed.")

    def write_base_fixture(self) -> None:
        write_text(
            self.repo_root / "tiny_tasks.py",
            dedent_block(
                """
                def summarize_tasks(tasks):
                    return f"{len(tasks)} total"
                """
            ),
        )
        write_text(
            self.repo_root / "test_tiny_tasks.py",
            dedent_block(
                """
                import unittest

                from tiny_tasks import summarize_tasks


                class TinyTasksTests(unittest.TestCase):
                    def test_summary_reports_total_only(self):
                        tasks = [
                            {"title": "Write docs", "completed": False},
                            {"title": "Ship fix", "completed": True},
                        ]
                        self.assertEqual(summarize_tasks(tasks), "2 total")


                if __name__ == "__main__":
                    unittest.main()
                """
            ),
        )

    def init_run(self) -> None:
        primary = self.primary_toolchain()
        self.log(f"Scaffolding run {self.run_id} with {primary}.")
        if primary == "python":
            self.run_command(
                self.script_command(
                    "python",
                    "recursive-init",
                    "--repo-root",
                    str(self.repo_root),
                    "--run-id",
                    self.run_id,
                    "--template",
                    "feature",
                )
            )
        else:
            self.run_command(
                self.script_command(
                    "powershell",
                    "recursive-init",
                    "-RepoRoot",
                    str(self.repo_root),
                    "-RunId",
                    self.run_id,
                    "-Template",
                    "feature",
                )
            )
        worktree_path = self.run_dir / "00-worktree.md"
        if not worktree_path.exists():
            raise SmokeError("recursive-init did not generate 00-worktree.md.")
        scaffold = worktree_path.read_text(encoding="utf-8")
        expected_snippets = [
            "## Diff Basis For Later Audits",
            f"- Baseline reference: {quote_md(self.base_commit)}",
            "- Comparison reference: `working-tree`",
            f"- Normalized baseline: {quote_md(self.base_commit)}",
            f"- Normalized diff command: {quote_md(f'git diff --name-only {self.base_commit}')}",
        ]
        for snippet in expected_snippets:
            if snippet not in scaffold:
                raise SmokeError(f"recursive-init did not prefill the expected Phase 0 diff-basis snippet: {snippet}")
        requirements_scaffold = (self.run_dir / "00-requirements.md").read_text(encoding="utf-8")
        if "Workflow version:" in requirements_scaffold:
            raise SmokeError("recursive-init retained a superseded workflow-profile field.")
        self.summary.append("Run scaffold success: recursive-init produced a reusable Phase 0 diff basis.")

    @property
    def run_dir(self) -> Path:
        return self.repo_root / ".recursive" / "run" / self.run_id

    def perform_red_green_cycle(self) -> None:
        write_text(
            self.repo_root / "test_tiny_tasks.py",
            dedent_block(
                """
                import unittest

                from tiny_tasks import summarize_tasks


                class TinyTasksTests(unittest.TestCase):
                    def test_summary_reports_total_completed_and_active_counts(self):
                        tasks = [
                            {"title": "Write docs", "completed": False},
                            {"title": "Ship fix", "completed": True},
                        ]
                        self.assertEqual(
                            summarize_tasks(tasks),
                            "2 total, 1 completed, 1 active",
                        )


                if __name__ == "__main__":
                    unittest.main()
                """
            ),
        )

        red_result = self.run_command(
            [str(self.python_exe), "-m", "unittest", "-q"],
            cwd=self.repo_root,
            allowed_returncodes=(1,),
        )
        red_path = self.run_dir / "evidence" / "logs" / "red" / "red-cycle-01.log"
        write_text(red_path, self.format_failure("Expected RED failure", red_result))
        self.red_log = self.repo_rel(red_path)

        write_text(
            self.repo_root / "tiny_tasks.py",
            dedent_block(
                """
                def summarize_tasks(tasks):
                    total = len(tasks)
                    completed = sum(1 for task in tasks if task.get("completed"))
                    active = total - completed
                    return f"{total} total, {completed} completed, {active} active"
                """
            ),
        )

        green_result = self.run_command([str(self.python_exe), "-m", "unittest", "-q"], cwd=self.repo_root)
        green_path = self.run_dir / "evidence" / "logs" / "green" / "green-cycle-01.log"
        write_text(
            green_path,
            "\n".join(
                [
                    "Expected GREEN pass",
                    f"Command: {quote_md('python -m unittest -q')}",
                    green_result.stdout.strip() or "OK",
                    green_result.stderr.strip(),
                ]
            ),
        )
        self.green_log = self.repo_rel(green_path)

    def perform_agent_qa(self) -> None:
        qa_result = self.run_command(
            [
                str(self.python_exe),
                "-c",
                (
                    "from tiny_tasks import summarize_tasks; "
                    "tasks=[{'title':'Write docs','completed':False},{'title':'Ship fix','completed':True}]; "
                    "print(summarize_tasks(tasks))"
                ),
            ],
            cwd=self.repo_root,
        )
        qa_path = self.run_dir / "evidence" / "logs" / "manual-qa-agent.log"
        write_text(
            qa_path,
            "\n".join(
                [
                    "Agent-operated manual QA",
                    f"Command: {quote_md('python -c summarize_tasks smoke check')}",
                    qa_result.stdout.strip(),
                ]
            ),
        )
        self.qa_log = self.repo_rel(qa_path)
        preview_path = self.run_dir / "evidence" / "logs" / "preview-server.log"
        self.preview_url = "http://127.0.0.1:4175/"
        write_text(
            preview_path,
            "\n".join(
                [
                    "> tiny-tasks preview",
                    f"Local:   {self.preview_url}",
                    "Network: use --host to expose",
                ]
            ),
        )
        self.preview_log = self.repo_rel(preview_path)

    def generate_review_bundle(self, toolchain: str, output_name: str, *, artifact_name: str = "03.5-code-review.md", pass_id: str = "0001", extra_evidence: list[str] | None = None) -> str:
        phase_key = AUDITED_PHASE_KEYS[artifact_name]
        review_id = Path(output_name).stem
        artifact_path = f"/.recursive/run/{self.run_id}/{artifact_name}"
        code_refs = ["tiny_tasks.py", "test_tiny_tasks.py"]
        artifact_index = ARTIFACT_SEQUENCE.index(artifact_name)
        upstream = [f".recursive/run/{self.run_id}/{name}" for name in ARTIFACT_SEQUENCE[:artifact_index] if (self.run_dir / name).is_file()]
        addenda: list[str] = []
        if artifact_index > ARTIFACT_SEQUENCE.index("02-to-be-plan.md") and self.plan_addendum_path:
            addenda.append(self.plan_addendum_path.lstrip("/"))
        if artifact_index > ARTIFACT_SEQUENCE.index("04-test-summary.md") and self.test_upstream_gap_addendum_path:
            addenda.append(self.test_upstream_gap_addendum_path.lstrip("/"))
        evidence = [self.red_log.lstrip("/"), self.green_log.lstrip("/"), *(path.lstrip("/") for path in (extra_evidence or []))]
        questions = [
            f"Does {artifact_name} satisfy R1 and its effective upstream artifacts?",
            "Do the reviewed paths align with the phase-owned diff surface?",
            "Is the cited evidence concrete and sufficient?",
        ]

        if toolchain == "python":
            command = self.script_command(
                "python",
                "recursive-review-bundle",
                "--repo-root",
                str(self.repo_root),
                "--run-id",
                self.run_id,
                "--phase",
                artifact_name,
                "--role",
                "code-reviewer",
                "--artifact-path",
                artifact_path,
                "--review-id",
                review_id,
                "--pass",
                pass_id,
            )
            for item in upstream:
                command.extend(["--upstream-artifact", item])
            for item in addenda:
                command.extend(["--addendum", item])
            command.append("--no-auto-addenda")
            command.extend(["--control-doc", ".recursive/RECURSIVE.md"])
            for code_ref in code_refs:
                command.extend(["--code-ref", code_ref])
            for evidence_ref in evidence:
                command.extend(["--evidence-ref", evidence_ref])
            for question in questions:
                command.extend(["--audit-question", question])
        else:
            command = self.powershell_splat_command(
                "recursive-review-bundle.ps1",
                {
                    "RepoRoot": str(self.repo_root),
                    "RunId": self.run_id,
                    "Phase": artifact_name,
                    "Role": "code-reviewer",
                    "ArtifactPath": artifact_path,
                    "ReviewId": review_id,
                    "ReviewPass": pass_id,
                    "UpstreamArtifact": upstream,
                    "Addendum": addenda,
                    "NoAutoAddenda": True,
                    "ControlDoc": [".recursive/RECURSIVE.md"],
                    "CodeRef": code_refs,
                    "EvidenceRef": evidence,
                    "AuditQuestion": questions,
                },
            )

        self.run_command(command, cwd=self.repo_root)
        return self.repo_rel(self.run_dir / "evidence" / "review-bundles" / phase_key / review_id / f"{pass_id}.md")

    @staticmethod
    def normalized_review_snapshot_hash(content: str) -> str:
        normalized = content.replace("\r\n", "\n").replace("\r", "\n")
        normalized = re.sub(r"(?m)^[ \t]*- Verified Pass Hash:.*(?:\n|$)", "", normalized)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def create_terminal_review(self, artifact_name: str, review_id: str, *, pass_number: int = 1, extra_evidence: list[str] | None = None) -> str:
        phase_key = AUDITED_PHASE_KEYS[artifact_name]
        pass_id = f"{pass_number:04d}"
        ledger_rel = f"/.recursive/run/{self.run_id}/evidence/reviews/{phase_key}/{review_id}/ledger.md"
        pass_rel = f"/.recursive/run/{self.run_id}/evidence/reviews/{phase_key}/{review_id}/passes/{pass_id}.md"
        expected_bundle_path = f"/.recursive/run/{self.run_id}/evidence/review-bundles/{phase_key}/{review_id}/{pass_id}.md"
        artifact = self.run_dir / artifact_name
        metadata = "\n".join(
            [
                f"- Review ID: {review_id}",
                f"- Review Ledger Path: `{ledger_rel}`",
                f"- Latest Verified Pass: `{pass_rel}`",
                "- Latest Verified Pass Hash: <pending>",
                f"- Review Bundle Path: `{expected_bundle_path}`",
                "- Review Bundle Hash: <pending>",
            ]
        )
        write_text(artifact, replace_section(artifact.read_text(encoding="utf-8"), "Review Metadata", metadata))
        bundle_path = self.generate_review_bundle(self.primary_toolchain(), f"{review_id}.md", artifact_name=artifact_name, pass_id=pass_id, extra_evidence=extra_evidence)
        if bundle_path != expected_bundle_path:
            raise SmokeError(f"Review bundle path mismatch: expected {expected_bundle_path}, generated {bundle_path}")
        bundle_file = self.repo_root / bundle_path.lstrip("/")
        bundle_hash = hashlib.sha256(bundle_file.read_bytes()).hexdigest()
        bundle_content = bundle_file.read_text(encoding="utf-8")
        snapshot_match = re.search(
            r"(?ms)^## Reviewed Surface Snapshot\s*$\n```json\s*\n(.*?)\n```",
            bundle_content,
        )
        if snapshot_match is None:
            raise SmokeError(f"Review bundle omitted its canonical surface snapshot: {bundle_path}")
        surface_snapshot = json.loads(snapshot_match.group(1))
        changed_files = [record["path"] for record in surface_snapshot.get("changed", [])] or ["none"]
        changed_file_lines = "\n".join(f"  - `{path}`" for path in changed_files)
        scope_evidence = [
            bundle_path,
            *(record["path"] for record in surface_snapshot.get("references", [])),
        ]
        scope_evidence_lines = "\n".join(f"  - `{path}`" for path in scope_evidence)
        ledger = self.repo_root / ledger_rel.lstrip("/")
        snapshot = self.repo_root / pass_rel.lstrip("/")
        previous_pass = "none"
        previous_hash = "none"
        if pass_number > 1:
            previous_pass = f"/.recursive/run/{self.run_id}/evidence/reviews/{phase_key}/{review_id}/passes/{pass_number - 1:04d}.md"
            previous_content = (self.repo_root / previous_pass.lstrip("/")).read_text(encoding="utf-8")
            previous_hash = self.normalized_review_snapshot_hash(previous_content)
        content = f"""## Review Scope

- Review ID: {review_id}
- Pass: {pass_id}
- Ledger Path: `{ledger_rel}`
- Previous Pass: {previous_pass if previous_pass == 'none' else f'`{previous_pass}`'}
- Previous Pass Hash: {previous_hash}
- Reviewed Artifact: `{bundle_path}`
- Artifact Hash: {bundle_hash}
- Diff Basis: `{bundle_path}`
- Changed Files:
{changed_file_lines}
- Evidence Basis:
{scope_evidence_lines}

## Findings

- none

## Verdict

- Result: PASS
- Open Findings: none
- Pending Scheduled Handoffs: none
- Controller: smoke-controller
- Verified Pass: `{pass_rel}`
- Verified Pass Hash: <pending>
"""
        snapshot_hash = self.normalized_review_snapshot_hash(content)
        content = content.replace("- Verified Pass Hash: <pending>", f"- Verified Pass Hash: {snapshot_hash}")
        write_text(snapshot, content)
        write_text(ledger, content)

        artifact_content = artifact.read_text(encoding="utf-8")
        artifact_content = re.sub(r"(?m)^- Latest Verified Pass Hash:.*$", f"- Latest Verified Pass Hash: {snapshot_hash}", artifact_content)
        artifact_content = re.sub(r"(?m)^- Review Bundle Hash:.*$", f"- Review Bundle Hash: {bundle_hash}", artifact_content)
        write_text(artifact, artifact_content)
        self.run_command(
            self.script_command(
                self.primary_toolchain(),
                "recursive-review-ledger",
                "--repo-root" if self.primary_toolchain() == "python" else "-RepoRoot",
                str(self.repo_root),
                "--run-id" if self.primary_toolchain() == "python" else "-RunId",
                self.run_id,
                "--phase-artifact" if self.primary_toolchain() == "python" else "-PhaseArtifact",
                artifact_name,
            ),
            cwd=self.repo_root,
        )
        self.review_bundle_paths[artifact_name] = bundle_path
        return bundle_path

    def create_review_receipts(self) -> None:
        primary = self.primary_toolchain()
        self.lock_artifacts(["00-requirements.md", "00-worktree.md"])
        for artifact_name in ("01-as-is.md", "02-to-be-plan.md"):
            phase_key = AUDITED_PHASE_KEYS[artifact_name]
            self.create_terminal_review(artifact_name, f"smoke-{phase_key}")
            self.lock_artifact(primary, artifact_name)
        self.lock_artifact(primary, "addenda/02-to-be-plan.addendum-01.md")
        for artifact_name in ("03-implementation-summary.md", "03.5-code-review.md", "04-test-summary.md"):
            phase_key = AUDITED_PHASE_KEYS[artifact_name]
            review_id = "03-5-code-review-code-reviewer" if artifact_name == "03.5-code-review.md" else f"smoke-{phase_key}"
            self.create_terminal_review(artifact_name, review_id)
            self.lock_artifact(primary, artifact_name)
        self.lock_artifacts(["addenda/04-test-summary.upstream-gap.02-to-be-plan.addendum-01.md", "05-manual-qa.md"])
        for artifact_name in ("06-decisions-update.md", "07-state-update.md", "08-memory-impact.md"):
            phase_key = AUDITED_PHASE_KEYS[artifact_name]
            self.create_terminal_review(artifact_name, f"smoke-{phase_key}")
            self.lock_artifact(primary, artifact_name)
        self.bundle_path = self.review_bundle_paths["03.5-code-review.md"]

    def update_control_plane_docs(self) -> None:
        append_text(
            self.repo_root / ".recursive" / "DECISIONS.md",
            dedent_block(
                f"""
                ## {self.run_id}

                - Use detailed task summaries that include completed and active counts.
                - Keep the smoke fixture stdlib-only so the regression harness stays offline and fast.
                """
            ),
        )
        append_text(
            self.repo_root / ".recursive" / "STATE.md",
            dedent_block(
                f"""
                ## Smoke State Update: {self.run_id}

                - Tiny Tasks now reports total, completed, and active counts.
                - The fixture app remains a two-file Python example with unittest coverage.
                """
            ),
        )
        append_text(
            self.repo_root / ".recursive" / "memory" / "MEMORY.md",
            dedent_block(
                f"""
                ## Recent Updates

                - {self.run_id}: Tiny Tasks reporting behavior and review-bundle coverage were revalidated by the smoke harness.
                """
            ),
        )

        domain_path = self.repo_root / ".recursive" / "memory" / "domains" / "TINY-TASKS.md"
        write_text(
            domain_path,
            dedent_block(
                f"""
                Type: `domain`
                Status: `CURRENT`
                Scope: `Tiny Tasks fixture behavior used by the recursive-mode smoke harness.`
                Owns-Paths: `tiny_tasks.py`, `test_tiny_tasks.py`
                Watch-Paths: `.recursive/run/`, `.recursive/memory/`
                Source-Runs: `{self.run_id}`
                Validated-At-Commit: `WORKTREE-UNCOMMITTED`
                Last-Validated: `{datetime.now(timezone.utc).strftime("%Y-%m-%d")}`
                Tags: `smoke`, `tiny-tasks`, `regression`

                ## Summary

                - The fixture app reports total, completed, and active task counts.
                - The smoke harness uses this domain doc during Phase 8 memory review.
                """
            ),
        )
        self.memory_domain_path = self.repo_rel(domain_path)

    def header_block(self, phase_name: str, *, inputs: list[str], outputs: list[str], scope_note: str) -> str:
        return "\n".join(
            [
                f"Run: `/.recursive/run/{self.run_id}/`",
                f"Phase: `{phase_name}`",
                "Status: `DRAFT`",
                "Inputs:",
                list_block([quote_md(item) for item in inputs]),
                "Outputs:",
                list_block([quote_md(item) for item in outputs]),
                f"Scope note: {scope_note}",
                "",
            ]
        )

    def todo_section(self, items: list[str]) -> str:
        return "## TODO\n\n" + list_block([f"[x] {item}" for item in items]) + "\n"

    def gate_section(self, heading: str, gate_name: str, note: str) -> str:
        return dedent_block(
            f"""
            ## {heading}

            - {note}
            {gate_name}: PASS
            """
        )

    def traceability_section(self, details: list[str]) -> str:
        return "## Traceability\n\n" + list_block(details) + "\n"

    def requirement_status_line(
        self,
        requirement_id: str,
        *,
        status: str,
        changed_files: list[str] | None = None,
        implementation_evidence: list[str] | None = None,
        verification_evidence: list[str] | None = None,
        rationale: str | None = None,
        blocking_evidence: list[str] | None = None,
        deferred_by: list[str] | None = None,
        scope_decision: list[str] | None = None,
        addendum: str | None = None,
    ) -> str:
        parts = [requirement_id, f"Status: {status}"]
        if changed_files:
            parts.append(
                "Changed Files: "
                + ", ".join(quote_md(item.lstrip("/")) if item.startswith("/") else quote_md(item) for item in changed_files)
            )
        if implementation_evidence:
            parts.append("Implementation Evidence: " + ", ".join(quote_md(item.lstrip("/")) if item.startswith("/") else quote_md(item) for item in implementation_evidence))
        if verification_evidence:
            parts.append("Verification Evidence: " + ", ".join(quote_md(item.lstrip("/")) if item.startswith("/") else quote_md(item) for item in verification_evidence))
        if rationale:
            parts.append(f"Rationale: {rationale}")
        if blocking_evidence:
            parts.append("Blocking Evidence: " + ", ".join(quote_md(item.lstrip("/")) if item.startswith("/") else quote_md(item) for item in blocking_evidence))
        if deferred_by:
            parts.append("Deferred By: " + ", ".join(quote_md(item.lstrip("/")) if item.startswith("/") else quote_md(item) for item in deferred_by))
        if scope_decision:
            parts.append("Scope Decision: " + ", ".join(quote_md(item.lstrip("/")) if item.startswith("/") else quote_md(item) for item in scope_decision))
        if addendum:
            parts.append(f"Addendum: {quote_md(addendum.lstrip('/')) if addendum.startswith('/') else quote_md(addendum)}")
        return " | ".join(parts)

    def audit_sections(
        self,
        *,
        reread: list[str],
        reviewed_paths: list[str],
        reconciliation: list[str],
        prior: list[str] | None = None,
        requirement_statuses: list[str] | None = None,
        subagent_records: list[str] | None = None,
    ) -> str:
        lines: list[str] = [
            "## Audit Context",
            "",
            "- Audit Execution Mode: self-audit",
            "- Subagent Availability: unavailable",
            "- Subagent Capability Probe: `No delegated subagent capability was available in the disposable smoke environment.`",
            "- Delegation Decision Basis: `Self-audit remained mandatory because no subagent/task execution surface was available.`",
            "- Audit Inputs Provided: local artifact draft, upstream artifacts, and current git diff basis",
            "",
            "## Effective Inputs Re-read",
            "",
            *[f"- {quote_md(path)}" for path in reread],
            "",
        ]
        if prior is not None:
            lines.extend(["## Prior Recursive Evidence Reviewed", "", *[f"- {item}" for item in prior], ""])
        lines.extend(
            [
                "## Earlier Phase Reconciliation",
                "",
                *[f"- {item}" for item in reconciliation],
                "",
                "## Subagent Contribution Verification",
                "",
                *[f"- {item}" for item in (subagent_records or ["No subagent work materially contributed to this phase."])],
                "",
                "## Worktree Diff Audit",
                "",
                "- Baseline type: `local commit`",
                f"- Baseline reference: {quote_md(self.base_commit)}",
                "- Comparison reference: `working-tree`",
                f"- Normalized baseline: {quote_md(self.base_commit)}",
                "- Normalized comparison: `working-tree`",
                f"- Normalized diff command: {quote_md(f'git diff --name-only {self.base_commit}')}",
                "- Reviewed changed paths:",
            ]
        )
        if reviewed_paths:
            lines.extend([f"  - {quote_md(path)}" for path in reviewed_paths])
        else:
            lines.append("  - No phase-owned final changed paths beyond the recorded diff basis.")
        lines.extend(
            [
                "",
                "## Requirement Completion Status",
                "",
                *[
                    f"- {item}"
                    for item in (
                        requirement_statuses
                        or [
                            self.requirement_status_line(
                                "R1",
                                status="verified",
                                changed_files=["tiny_tasks.py", "test_tiny_tasks.py"],
                                implementation_evidence=["tiny_tasks.py", "test_tiny_tasks.py"],
                                verification_evidence=[self.green_log],
                            )
                        ]
                    )
                ],
                "",
                "## Review Metadata",
                "",
                "- Review ID: <review-id>",
                "- Review Ledger Path: `/.recursive/run/<run-id>/evidence/reviews/<phase-key>/<review-id>/ledger.md`",
                "- Latest Verified Pass: `/.recursive/run/<run-id>/evidence/reviews/<phase-key>/<review-id>/passes/<NNNN>.md`",
                "- Latest Verified Pass Hash: <sha256>",
                "- Review Bundle Path: `/.recursive/run/<run-id>/evidence/review-bundles/<phase-key>/<review-id>/<NNNN>.md`",
                "- Review Bundle Hash: <sha256>",
                "",
            ]
        )
        return "\n".join(lines)

    def extract_generated_section(self, content: str, heading: str) -> str:
        match = re.search(rf"(?ms)^##\s+{re.escape(heading)}\s*$\n?(.*?)(?=^##\s+|\Z)", content, re.MULTILINE)
        if not match:
            raise SmokeError(f"Generated scaffold is missing section: ## {heading}")
        return match.group(1).strip()

    def apply_generated_audit_sections(self, content: str, audit_block: str, *, include_prior: bool = False) -> str:
        headings = [
            "Audit Context",
            "Effective Inputs Re-read",
        ]
        if include_prior:
            headings.append("Prior Recursive Evidence Reviewed")
        headings.extend(
            [
                "Earlier Phase Reconciliation",
                "Subagent Contribution Verification",
                "Worktree Diff Audit",
                "Requirement Completion Status",
                "Review Metadata",
            ]
        )
        updated = content
        for heading in headings:
            updated = replace_section(updated, heading, self.extract_generated_section(audit_block, heading))
        return updated

    def scaffold_closeout_phase(self, phase: str, *, preview_log: str = "", preview_url: str = "") -> Path:
        toolchain = self.primary_toolchain()
        if toolchain == "python":
            command = self.script_command(
                "python",
                "recursive-closeout",
                "--repo-root",
                str(self.repo_root),
                "--run-id",
                self.run_id,
                "--phase",
                phase,
                "--force",
            )
            if preview_log:
                command.extend(["--preview-log", preview_log.lstrip("/")])
            if preview_url:
                command.extend(["--preview-url", preview_url])
        else:
            command = self.script_command(
                "powershell",
                "recursive-closeout",
                "-RepoRoot",
                str(self.repo_root),
                "-RunId",
                self.run_id,
                "-Phase",
                phase,
                "-Force",
            )
            if preview_log:
                command.extend(["-PreviewLog", preview_log.lstrip("/")])
            if preview_url:
                command.extend(["-PreviewUrl", preview_url])
        self.run_command(command, cwd=self.repo_root)
        phase_map = {
            "04": self.run_dir / "04-test-summary.md",
            "05": self.run_dir / "05-manual-qa.md",
            "06": self.run_dir / "06-decisions-update.md",
            "07": self.run_dir / "07-state-update.md",
            "08": self.run_dir / "08-memory-impact.md",
        }
        return phase_map[phase]

    def write_artifacts(self) -> None:
        run_prefix = f".recursive/run/{self.run_id}"
        product_paths = ["tiny_tasks.py", "test_tiny_tasks.py"]
        plan_addendum_file = self.run_dir / "addenda" / "02-to-be-plan.addendum-01.md"
        test_gap_addendum_file = self.run_dir / "addenda" / "04-test-summary.upstream-gap.02-to-be-plan.addendum-01.md"
        self.plan_addendum_path = self.repo_rel(plan_addendum_file)
        self.test_upstream_gap_addendum_path = self.repo_rel(test_gap_addendum_file)

        write_text(
            self.run_dir / "00-requirements.md",
            "\n\n".join(
                [
                    self.header_block(
                        "00 Requirements",
                        inputs=["chat requirement summary", "references/fixtures/tiny-tasks-smoke-recipe.md"],
                        outputs=[f"{run_prefix}/00-requirements.md"],
                        scope_note="Defines the stable requirement IDs for the disposable Tiny Tasks smoke run.",
                    ),
                    self.todo_section(
                        [
                            "Define requirement identifiers and acceptance criteria",
                            "Capture out-of-scope items, constraints, and assumptions",
                            "Pass Coverage and Approval gates",
                        ]
                    ),
                    dedent_block(
                        """
                        ## Requirements

                        ### `R1` Detailed task summary

                        Description:
                        Tiny Tasks must report total, completed, and active task counts for a list of task dictionaries.

                        Acceptance criteria:
                        - A two-task list with one completed task returns `2 total, 1 completed, 1 active`.
                        - The behavior is covered by unittest evidence captured during the smoke run.

                        ## Out of Scope

                        - `OOS1`: Persistence, UI rendering, and network behavior.

                        ## Constraints

                        - Use only the Python standard library.
                        - Keep the fixture limited to `tiny_tasks.py` and `test_tiny_tasks.py`.
                        """
                    ),
                    self.gate_section("Coverage Gate", "Coverage", "R1 and its acceptance criteria are fully specified."),
                    self.gate_section("Approval Gate", "Approval", "The disposable smoke requirement is ready for execution."),
                ]
            ),
        )

        write_text(
            self.run_dir / "00-worktree.md",
            "\n\n".join(
                [
                    self.header_block(
                        "00 Worktree",
                        inputs=[f"{run_prefix}/00-requirements.md"],
                        outputs=[f"{run_prefix}/00-worktree.md"],
                        scope_note="Records the disposable branch context and git diff basis for later audits.",
                    ),
                    self.todo_section(
                        [
                            "Record repo root, base branch, feature branch, and base commit",
                            "Confirm baseline tests pass before the feature change",
                            "Document the diff basis used by later audit phases",
                        ]
                    ),
                    dedent_block(
                        f"""
                        ## Directory Selection

                        - Repo root: {quote_md(str(self.repo_root))}

                        ## Safety Verification

                        - Disposable repo created under {quote_md(str(self.temp_dir))}
                        - No existing user worktree or source repository was modified.

                        ## Worktree Creation

                        - Feature branch created locally: {quote_md(self.feature_branch)}

                        ## Main Branch Protection

                        - Base branch remains {quote_md(self.base_branch)} at {quote_md(self.base_commit)}.

                        ## Project Setup

                        - recursive-mode installer completed before the base commit.
                        - The smoke fixture uses only stdlib Python files.

                        ## Test Baseline Verification

                        - {quote_md('python -m unittest -q')} passed before introducing the feature request.

                        ## Worktree Context

                        - Base branch: {quote_md(self.base_branch)}
                        - Worktree branch: {quote_md(self.feature_branch)}

                        ## Diff Basis For Later Audits

                        - Baseline type: `local commit`
                        - Baseline reference: {quote_md(self.base_commit)}
                        - Comparison reference: `working-tree`
                        - Normalized baseline: {quote_md(self.base_commit)}
                        - Normalized comparison: `working-tree`
                        - Normalized diff command: {quote_md(f'git diff --name-only {self.base_commit}')}
                        - Base branch: {quote_md(self.base_branch)}
                        - Worktree branch: {quote_md(self.feature_branch)}
                        - Diff basis notes: `The smoke harness audits the working tree against the base commit that existed before the feature request.`
                        """
                    ),
                    self.traceability_section(["- R1 -> branch and diff basis recorded for all later audited phases."]),
                    self.gate_section("Coverage Gate", "Coverage", "All branch and diff-basis metadata needed by later audits is present."),
                    self.gate_section("Approval Gate", "Approval", "The disposable branch context is safe to use for the smoke run."),
                ]
            ),
        )

        audited_common = {
            "reread": [f"{run_prefix}/00-requirements.md", f"{run_prefix}/00-worktree.md"],
            "prior": ["None relevant because this disposable repo has no earlier recursive runs or durable memory history to re-read."],
        }

        write_text(
            self.run_dir / "01-as-is.md",
            "\n\n".join(
                [
                    self.header_block(
                        "01 As-Is",
                        inputs=[f"{run_prefix}/00-requirements.md", f"{run_prefix}/00-worktree.md"],
                        outputs=[f"{run_prefix}/01-as-is.md"],
                        scope_note="Captures the pre-change Tiny Tasks behavior and evidence needed for the later plan.",
                    ),
                    self.todo_section(
                        [
                            "Record novice-runnable reproduction steps",
                            "Describe current behavior for R1 before the feature change",
                            "Record code pointers and baseline evidence",
                        ]
                    ),
                    dedent_block(
                        """
                        ## Reproduction Steps (Novice-Runnable)

                        - Run `python -m unittest -q`.
                        - Observe that the base fixture passes while only reporting total task count.

                        ## Current Behavior by Requirement

                        - `R1`: Before implementation, `summarize_tasks()` only returned the total count, so completed and active counts were missing.

                        ## Source Requirement Inventory

                        - `R1 | Source Quote: Tiny Tasks must report total, completed, and active task counts for a list of task dictionaries. | Summary: The task summary must expose total, completed, and active counts. | Disposition: in-scope`

                        ## Relevant Code Pointers

                        - `tiny_tasks.py`
                        - `test_tiny_tasks.py`

                        ## Known Unknowns

                        - No additional edge cases are modeled in the disposable fixture.

                        ## Evidence

                        - Baseline unittest pass was observed before the feature branch changes.
                        """
                    ),
                    self.audit_sections(
                        reread=audited_common["reread"],
                        prior=audited_common["prior"],
                        reviewed_paths=product_paths,
                        reconciliation=["The as-is description remains consistent with the pre-change code and the current requirement."],
                    ),
                    self.traceability_section(["- R1 -> current behavior documented as missing completed and active counts."]),
                    self.gate_section("Coverage Gate", "Coverage", "The current state and baseline evidence are sufficient to plan the change."),
                    self.gate_section("Approval Gate", "Approval", "The as-is analysis is ready for planning."),
                ]
            ),
        )

        write_text(
            self.run_dir / "02-to-be-plan.md",
            "\n\n".join(
                [
                    self.header_block(
                        "02 To-Be Plan",
                        inputs=[f"{run_prefix}/01-as-is.md"],
                        outputs=[f"{run_prefix}/02-to-be-plan.md"],
                        scope_note="Defines the minimal implementation and validation plan for the fixture feature change.",
                    ),
                    self.todo_section(
                        [
                            "Name each product file that will change",
                            "Define the RED-GREEN testing strategy",
                            "Describe manual QA and recovery expectations",
                        ]
                    ),
                    dedent_block(
                        """
                        ## Planned Changes by File

                        - `tiny_tasks.py`: add completed and active count reporting.
                        - `test_tiny_tasks.py`: add a failing test that asserts the detailed summary output.

                        ## Requirement Mapping

                        - `R1 | Coverage: direct | Source Quote: Tiny Tasks must report total, completed, and active task counts for a list of task dictionaries. | Implementation Surface: tiny_tasks.py, test_tiny_tasks.py | Verification Surface: test_tiny_tasks.py, /.recursive/run/<run-id>/04-test-summary.md | QA Surface: /.recursive/run/<run-id>/05-manual-qa.md`

                        ## Implementation Steps

                        - Write a failing unittest for the new summary string.
                        - Update the implementation to count completed and active tasks.
                        - Re-run unittest to capture GREEN evidence.

                        ## Testing Strategy

                        - Use strict RED/GREEN unittest logs captured under the run evidence directory.

                        ## Test Surface

                        - `TS-001` | Requirement: `R1` | Behavior: reports total, completed, and active task counts | Seam: `summarize_tasks(tasks) -> str` | Level: integration | Real Dependencies: none | Replaced Dependencies: none | Expected From: `R1` acceptance criterion for a two-task list

                        ## Playwright Plan (if applicable)

                        - Not applicable for the stdlib fixture app.

                        ## Manual QA Scenarios

                        - Run a direct Python smoke command that prints the updated summary for a two-task list.

                        ## Idempotence and Recovery

                        - Re-running the harness rewrites the fixture files and run artifacts from scratch in a disposable repo.

                        ## Implementation Sub-phases

                        - `SP1`: failing test
                        - `SP2`: implementation update
                        - `SP3`: review, test, and closeout

                        ## Plan Drift Check

                        - No source obligations were merged, deferred, or narrowed in the Phase 2 plan.
                        - The source quote for `R1` is preserved directly in `## Requirement Mapping`.
                        """
                    ),
                    self.audit_sections(
                        reread=[f"{run_prefix}/00-requirements.md", f"{run_prefix}/01-as-is.md"],
                        prior=audited_common["prior"],
                        reviewed_paths=product_paths,
                        reconciliation=["The plan is still consistent with the recorded as-is behavior and the narrow fixture scope."],
                        requirement_statuses=[
                            (
                                "R1 | Status: planned | Implementation Surface: `tiny_tasks.py`, `test_tiny_tasks.py` "
                                f"| Verification Surface: `test_tiny_tasks.py`, `{run_prefix}/04-test-summary.md` "
                                f"| QA Surface: `{run_prefix}/05-manual-qa.md`"
                            )
                        ],
                    ),
                    self.traceability_section(["- R1 -> both planned file edits and the validation path are explicit."]),
                    self.gate_section("Coverage Gate", "Coverage", "The planned file changes and test strategy cover the full requirement."),
                    self.gate_section("Approval Gate", "Approval", "The plan is concrete enough to execute without widening scope."),
                ]
            ),
        )

        write_text(
            plan_addendum_file,
            "\n\n".join(
                [
                    self.header_block(
                        "02 To-Be Plan Addendum",
                        inputs=[f"{run_prefix}/02-to-be-plan.md"],
                        outputs=[self.plan_addendum_path],
                        scope_note="Supplements the locked plan with an explicit implementation constraint that downstream audited phases must still reread and reconcile.",
                    ),
                    self.todo_section(
                        [
                            "Record the plan supplement explicitly",
                            "State the rationale for the added constraint",
                            "Pass Coverage and Approval gates for downstream use",
                        ]
                    ),
                    dedent_block(
                        """
                        ## Addendum Content

                        - Preserve `summarize_tasks()` as a pure function that derives `active` as `total - completed`.
                        - Keep the fixture implementation single-purpose and stdlib-only even after the summary format changes.

                        ## Coverage Gate

                        - The downstream implementation, review, and test artifacts must reread this addendum as part of their effective inputs.
                        Coverage: PASS

                        ## Approval Gate

                        - The plan supplement is explicit and ready for downstream consumption.
                        Approval: PASS
                        """
                    ),
                ]
            ),
        )

        write_text(
            self.run_dir / "03-implementation-summary.md",
            "\n\n".join(
                [
                    self.header_block(
                        "03 Implementation Summary",
                        inputs=[f"{run_prefix}/02-to-be-plan.md", self.plan_addendum_path, self.red_log, self.green_log],
                        outputs=[f"{run_prefix}/03-implementation-summary.md"],
                        scope_note="Records the applied code changes and strict TDD evidence for the Tiny Tasks feature.",
                    ),
                    self.todo_section(
                        [
                            "Capture applied code changes and their evidence",
                            "Record strict RED and GREEN evidence paths",
                            "Confirm plan deviations are either absent or documented",
                        ]
                    ),
                    dedent_block(
                        f"""
                        ## Changes Applied

                        - Updated `tiny_tasks.py` to compute total, completed, and active task counts.
                        - Updated `test_tiny_tasks.py` to assert the detailed summary string.

                        ## TDD Compliance Log

                        - TDD Mode: strict
                        - Test Surface: TS-001
                        - RED Evidence: {quote_md(self.red_log)}
                        - GREEN Evidence: {quote_md(self.green_log)}
                        - REFACTOR Evidence: No separate refactor step was needed for this small fixture.
                        TDD Compliance: PASS

                        ## Plan Deviations

                        - No plan deviations were required.

                        ## Implementation Evidence

                        - Product files changed: {quote_md('tiny_tasks.py')}, {quote_md('test_tiny_tasks.py')}
                        - GREEN evidence confirms the new summary output.
                        """
                    ),
                    self.audit_sections(
                        reread=[f"{run_prefix}/02-to-be-plan.md", self.plan_addendum_path, self.red_log, self.green_log],
                        reviewed_paths=product_paths,
                        reconciliation=[
                            "The implementation stayed within the planned files and matched the recorded testing strategy.",
                            f"Reviewed addendum: {quote_md(self.plan_addendum_path)} to preserve the pure-function and stdlib-only constraints.",
                        ],
                    ),
                    self.traceability_section(["- R1 -> implementation and test changes directly satisfy the detailed summary requirement."]),
                    self.gate_section("Coverage Gate", "Coverage", "The implementation and evidence cover the full planned change."),
                    self.gate_section("Approval Gate", "Approval", "The implementation is ready for code review and downstream validation."),
                ]
            ),
        )

        anticipated_bundle_path = f"/.recursive/run/{self.run_id}/evidence/review-bundles/phase-3-5/03-5-code-review-code-reviewer/0001.md"

        write_text(
            self.run_dir / "03.5-code-review.md",
            "\n\n".join(
                [
                    self.header_block(
                        "03.5 Code Review",
                        inputs=[f"{run_prefix}/02-to-be-plan.md", self.plan_addendum_path, f"{run_prefix}/03-implementation-summary.md", anticipated_bundle_path],
                        outputs=[f"{run_prefix}/03.5-code-review.md"],
                        scope_note="Records the bundle-backed review of the Phase 3 implementation before test closeout.",
                    ),
                    self.todo_section(
                        [
                            "Capture the canonical review metadata pointers",
                            "Keep findings in the lossless ledger rather than this receipt",
                            "Pass Coverage and Approval only after whole-ledger PASS",
                        ]
                    ),
                    dedent_block(
                        """
                        ## Review Coordination

                        - The canonical ledger owns review scope, findings, controller verification, and verdict.
                        - This phase receipt records only workflow evidence, traceability, and pointers to the immutable review artifacts.
                        """
                    ),
                    self.audit_sections(
                        reread=[f"{run_prefix}/02-to-be-plan.md", self.plan_addendum_path, f"{run_prefix}/03-implementation-summary.md", anticipated_bundle_path],
                        reviewed_paths=product_paths,
                        reconciliation=[
                            "The review confirms that the implementation remains aligned with the plan and owned product diff.",
                            f"Re-read plan addendum: {quote_md(self.plan_addendum_path)} and confirmed the implementation stayed pure and stdlib-only.",
                        ],
                    ),
                    self.traceability_section(["- R1 -> the review confirmed that the changed files satisfy the requirement without widening scope."]),
                    self.gate_section("Coverage Gate", "Coverage", "The review bundle and written verdict cover the full product diff."),
                    self.gate_section("Approval Gate", "Approval", "The reviewed implementation is approved for downstream validation."),
                ]
            ),
        )

        write_text(
            test_gap_addendum_file,
            "\n\n".join(
                [
                    self.header_block(
                        "04 Test Summary Upstream Gap Addendum",
                        inputs=[f"{run_prefix}/02-to-be-plan.md", f"{run_prefix}/04-test-summary.md"],
                        outputs=[self.test_upstream_gap_addendum_path],
                        scope_note="Records a discovered planning gap that the Phase 4 test receipt compensates for without reopening locked history.",
                    ),
                    self.todo_section(
                        [
                            "Describe the upstream planning gap precisely",
                            "Record the compensating validation now captured in Phase 4",
                            "Pass Coverage and Approval gates for downstream audit use",
                        ]
                    ),
                    dedent_block(
                        """
                        ## Gap Statement

                        - The locked Phase 2 plan did not explicitly say that the final test receipt should preserve the exact RED and GREEN command/evidence references.

                        ## Discovery Evidence

                        - The Phase 4 authoring pass needed those exact evidence paths to make the final audited test summary reproducible.

                        ## Impact

                        - The current phase must compensate by recording the exact command/evidence pair directly in the test receipt.

                        ## Compensation Plan

                        - Phase 4 captures the exact unittest command plus RED and GREEN log paths even though Phase 2 stated the testing strategy more generally.

                        ## Traceability Impact

                        - Affected requirements: `R1`

                        ## Coverage Gate

                        - The upstream gap and downstream compensation are explicit.
                        Coverage: PASS

                        ## Approval Gate

                        - The addendum is ready to be cited by Phase 4 audit and downstream status/lint checks.
                        Approval: PASS
                        """
                    ),
                ]
            ),
        )

        phase4_path = self.scaffold_closeout_phase("04")
        phase4_content = phase4_path.read_text(encoding="utf-8")
        phase4_content = replace_section(
            phase4_content,
            "TODO",
            "\n".join(
                [
                    "- [x] Record pre-test audit and environment details",
                    "- [x] Capture exact commands and resulting evidence",
                    "- [x] Pass the audited test summary gate",
                ]
            ),
        )
        phase4_content = replace_section(phase4_content, "Pre-Test Implementation Audit", "- Re-read the implementation summary and code review before finalizing the test receipt.")
        phase4_content = replace_section(phase4_content, "Environment", f"- Python executable: {quote_md(str(self.python_exe))}")
        phase4_content = replace_section(phase4_content, "Execution Mode", "- Local automated unittest execution inside the disposable repo.")
        phase4_content = replace_section(
            phase4_content,
            "Commands Executed (Exact)",
            "\n".join(
                [
                    f"- {quote_md('python -m unittest -q')} for RED",
                    f"- {quote_md('python -m unittest -q')} for GREEN",
                ]
            ),
        )
        phase4_content = replace_section(
            phase4_content,
            "Results Summary",
            "\n".join(
                [
                    "- RED captured the missing summary behavior before the implementation change.",
                    "- GREEN passed after the implementation update.",
                ]
            ),
        )
        phase4_content = replace_section(
            phase4_content,
            "Evidence and Artifacts",
            "\n".join([f"- {quote_md(self.red_log)}", f"- {quote_md(self.green_log)}"]),
        )
        phase4_content = replace_section(
            phase4_content,
            "Failures and Diagnostics (if any)",
            "- Expected RED failure only; no unexpected failures remained after GREEN.",
        )
        phase4_content = replace_section(phase4_content, "Flake/Rerun Notes", "- No reruns were required.")
        phase4_audit = self.audit_sections(
            reread=[f"{run_prefix}/02-to-be-plan.md", self.plan_addendum_path, f"{run_prefix}/03-implementation-summary.md", f"{run_prefix}/03.5-code-review.md", self.test_upstream_gap_addendum_path],
            prior=["None relevant because this disposable repo still has no earlier recursive runs beyond the current in-run artifacts."],
            reviewed_paths=product_paths,
            reconciliation=[
                "The test summary stays aligned with the implementation summary, review verdict, and owned product diff.",
                f"Reviewed addendum: {quote_md(self.plan_addendum_path)} so the Phase 4 receipt preserves the pure-function and stdlib-only constraints.",
                f"Phase 4 compensated for a locked-plan omission via {quote_md(self.test_upstream_gap_addendum_path)} without editing Phase 2 history.",
            ],
        )
        phase4_content = self.apply_generated_audit_sections(phase4_content, phase4_audit, include_prior=True)
        phase4_content = replace_section(phase4_content, "Traceability", "- R1 -> RED and GREEN evidence prove the updated summary behavior.")
        phase4_content = replace_section(phase4_content, "Coverage Gate", "- The recorded commands and evidence cover the full requirement behavior.\nCoverage: PASS")
        phase4_content = replace_section(phase4_content, "Approval Gate", "- Automated verification is complete and ready for manual QA.\nApproval: PASS")
        write_text(phase4_path, phase4_content)

        phase5_path = self.scaffold_closeout_phase("05", preview_log=self.preview_log, preview_url=self.preview_url)
        phase5_content = phase5_path.read_text(encoding="utf-8")
        if self.preview_url not in phase5_content:
            raise SmokeError("recursive-closeout did not capture the actual preview URL into the Phase 5 scaffold.")
        phase5_content = replace_section(
            phase5_content,
            "TODO",
            "\n".join(
                [
                    "- [x] Record the QA execution mode and supporting evidence",
                    "- [x] Capture the manual smoke scenario result",
                    "- [x] Pass Coverage and Approval gates for downstream closeout",
                ]
            ),
        )
        phase5_content = replace_section(
            phase5_content,
            "QA Execution Record",
            "\n".join(
                [
                    "- QA Execution Mode: agent-operated",
                    "- Agent Executor: recursive smoke harness",
                    "- Tools Used: python",
                    f"- Preview URL: {quote_md(self.preview_url)}",
                    f"- Preview Log: {quote_md(self.preview_log)}",
                    f"- Evidence Path: {quote_md(self.qa_log)}",
                ]
            ),
        )
        phase5_content = replace_section(
            phase5_content,
            "QA Scenarios and Results",
            "- Printed the summary for a two-task list and observed `2 total, 1 completed, 1 active`.",
        )
        phase5_content = replace_section(
            phase5_content,
            "Evidence and Artifacts",
            "\n".join([f"- {quote_md(self.qa_log)}", f"- {quote_md(self.preview_log)}"]),
        )
        phase5_content = replace_section(
            phase5_content,
            "User Sign-Off",
            "- Approved by: N/A (agent-operated)\n- Date: N/A (agent-operated)",
        )
        phase5_content = replace_section(phase5_content, "Traceability", "- R1 -> manual smoke output matched the required summary string.")
        phase5_content = replace_section(phase5_content, "Coverage Gate", "- The agent-operated QA scenario exercised the full requirement output.\nCoverage: PASS")
        phase5_content = replace_section(phase5_content, "Approval Gate", "- Phase 5 is complete for agent-operated closeout.\nApproval: PASS")
        write_text(phase5_path, phase5_content)

        self.update_control_plane_docs()

        phase6_path = self.scaffold_closeout_phase("06")
        phase6_content = phase6_path.read_text(encoding="utf-8")
        phase6_content = replace_section(
            phase6_content,
            "TODO",
            "\n".join(
                [
                    "- [x] Record the decision delta applied during closeout",
                    "- [x] Reference the updated decisions ledger entry",
                    "- [x] Pass the audited late-phase decision gate",
                ]
            ),
        )
        phase6_content = replace_section(phase6_content, "Decisions Changes Applied", "- Added a run-specific decision entry to `.recursive/DECISIONS.md`.")
        phase6_content = replace_section(
            phase6_content,
            "Rationale",
            "- The smoke harness should preserve why the fixture remains stdlib-only and why detailed task summaries are required.",
        )
        phase6_content = replace_section(phase6_content, "Resulting Decision Entry", f"- See `.recursive/DECISIONS.md` under heading `{self.run_id}`.")
        phase6_audit = self.audit_sections(
            reread=[f"{run_prefix}/05-manual-qa.md", self.plan_addendum_path, ".recursive/DECISIONS.md"],
            reviewed_paths=product_paths + [".recursive/DECISIONS.md"],
            reconciliation=[
                "The decisions delta is limited to the final ledger update plus the owned product diff.",
                f"Late closeout re-read the plan addendum {quote_md(self.plan_addendum_path)} so the decision ledger preserved the narrowed fixture constraints.",
            ],
        )
        phase6_content = self.apply_generated_audit_sections(phase6_content, phase6_audit, include_prior=False)
        phase6_content = replace_section(phase6_content, "Traceability", "- R1 -> the decisions ledger now records the detailed summary expectation and fixture constraints.")
        phase6_content = replace_section(phase6_content, "Coverage Gate", "- The decision receipt covers both the ledger delta and the final product scope.\nCoverage: PASS")
        phase6_content = replace_section(phase6_content, "Approval Gate", "- The decisions ledger update is complete.\nApproval: PASS")
        write_text(phase6_path, phase6_content)

        phase7_path = self.scaffold_closeout_phase("07")
        phase7_content = phase7_path.read_text(encoding="utf-8")
        phase7_content = replace_section(
            phase7_content,
            "TODO",
            "\n".join(
                [
                    "- [x] Record the final state delta for the fixture app",
                    "- [x] Reference the updated state ledger summary",
                    "- [x] Pass the audited late-phase state gate",
                ]
            ),
        )
        phase7_content = replace_section(phase7_content, "State Changes Applied", "- Added a state update entry to `.recursive/STATE.md`.")
        phase7_content = replace_section(
            phase7_content,
            "Rationale",
            "- The run changed the observable behavior of the Tiny Tasks fixture and should record that final state explicitly.",
        )
        phase7_content = replace_section(
            phase7_content,
            "Resulting State Summary",
            "- `.recursive/STATE.md` now notes that Tiny Tasks reports total, completed, and active task counts.",
        )
        phase7_audit = self.audit_sections(
            reread=[f"{run_prefix}/06-decisions-update.md", ".recursive/STATE.md"],
            prior=["None relevant because this disposable repo still has no earlier recursive runs or prior memory episodes for state closeout."],
            reviewed_paths=product_paths + [".recursive/STATE.md"],
            reconciliation=["The state delta reflects the same final behavior already captured in product code and the decisions receipt."],
        )
        phase7_content = self.apply_generated_audit_sections(phase7_content, phase7_audit, include_prior=True)
        phase7_content = replace_section(phase7_content, "Traceability", "- R1 -> the state ledger now reflects the final detailed summary behavior.")
        phase7_content = replace_section(phase7_content, "Coverage Gate", "- The state receipt covers the final fixture behavior and owned state delta.\nCoverage: PASS")
        phase7_content = replace_section(phase7_content, "Approval Gate", "- The state ledger update is complete.\nApproval: PASS")
        write_text(phase7_path, phase7_content)

        phase8_path = self.scaffold_closeout_phase("08")
        phase8_content = phase8_path.read_text(encoding="utf-8")
        phase8_content = replace_section(
            phase8_content,
            "TODO",
            "\n".join(
                [
                    "- [x] Review memory docs affected by the final changed paths",
                    "- [x] Document router and domain updates",
                    "- [x] Pass the audited memory closeout gate",
                ]
            ),
        )
        phase8_content = replace_section(phase8_content, "Diff Basis", "- Final memory review used the recorded Phase 0 diff basis from `00-worktree.md`.")
        phase8_content = replace_section(phase8_content, "Changed Paths Review", "- Product paths reviewed: `tiny_tasks.py`, `test_tiny_tasks.py`")
        phase8_content = replace_section(
            phase8_content,
            "Affected Memory Docs",
            "\n".join(
                [
                    "- `.recursive/memory/MEMORY.md`",
                    "- `.recursive/memory/skills/SKILLS.md`",
                    f"- `{self.memory_domain_path}`",
                ]
            ),
        )
        phase8_content = replace_section(
            phase8_content,
            "Run-Local Skill Usage Capture",
            "\n".join(
                [
                    "- Skill Usage Relevance: relevant",
                    "- Available Skills: `recursive-mode`, `recursive-subagent`, `find-skills`",
                    "- Skills Sought: `recursive-subagent`",
                    "- Skills Attempted: `recursive-subagent`",
                    "- Skills Used: `recursive-subagent`",
                    "- Worked Well: bundle-backed delegated review and durable action-record validation were exercised successfully in the disposable run",
                    "- Issues Encountered: none",
                    "- Future Guidance: prefer `recursive-subagent` for bounded delegated review; use `find-skills` before improvising a missing specialized capability",
                    "- Promotion Candidates: delegated-review fit guidance; capability-discovery guidance",
                ]
            ),
        )
        phase8_content = replace_section(
            phase8_content,
            "Skill Memory Promotion Review",
            "\n".join(
                [
                    "- Durable Skill Lessons Promoted: none",
                    "- Generalized Guidance Updated: `.recursive/memory/skills/SKILLS.md` was reviewed as the router for future durable promotion",
                    "- Run-Local Observations Left Unpromoted: the disposable run keeps its session-specific observations local to the run artifacts",
                    "- Promotion Decision Rationale: this disposable smoke run validates the promotion workflow and router behavior, but its environment-specific observations should remain run-local rather than becoming durable repo truth",
                ]
            ),
        )
        phase8_content = replace_section(phase8_content, "Uncovered Paths", "- None. The new domain doc now owns the Tiny Tasks fixture paths.")
        phase8_content = replace_section(
            phase8_content,
            "Router and Parent Refresh",
            "- Refreshed the memory router, confirmed the skill-memory router remains current, and added a domain doc for the fixture.",
        )
        phase8_content = replace_section(
            phase8_content,
            "Final Status Summary",
            "- The memory plane now contains current fixture guidance aligned with the final code and state, and the skill-memory router remains available for delegated-review retrieval.",
        )
        phase8_audit = self.audit_sections(
            reread=[f"{run_prefix}/07-state-update.md", self.plan_addendum_path, ".recursive/memory/MEMORY.md", ".recursive/memory/skills/SKILLS.md", self.memory_domain_path.lstrip("/")],
            prior=["None relevant because this disposable repo still has no earlier recursive runs or prior promoted skill-memory lessons to consult."],
            reviewed_paths=product_paths + [".recursive/memory/MEMORY.md", ".recursive/memory/skills/SKILLS.md", self.memory_domain_path.lstrip("/")],
            reconciliation=[
                "The memory updates are limited to the owned memory plane paths plus the final product diff.",
                f"Phase 8 re-read the plan addendum {quote_md(self.plan_addendum_path)} so durable memory preserved the pure-function and stdlib-only fixture constraints.",
            ],
        )
        phase8_content = self.apply_generated_audit_sections(phase8_content, phase8_audit, include_prior=True)
        phase8_content = replace_section(phase8_content, "Traceability", "- R1 -> durable memory now records the final summary behavior and fixture ownership paths.")
        phase8_content = replace_section(phase8_content, "Coverage Gate", "- The memory closeout covers all affected memory-plane paths.\nCoverage: PASS")
        phase8_content = replace_section(phase8_content, "Approval Gate", "- The memory plane is updated and ready for final verification.\nApproval: PASS")
        write_text(phase8_path, phase8_content)

    def lock_artifact(self, toolchain: str, artifact_name: str) -> None:
        if toolchain == "python":
            command = self.script_command(
                "python",
                "recursive-lock",
                "--repo-root",
                str(self.repo_root),
                "--run-id",
                self.run_id,
                "--artifact",
                artifact_name,
            )
        else:
            command = self.script_command(
                "powershell",
                "recursive-lock",
                "-RepoRoot",
                str(self.repo_root),
                "-RunId",
                self.run_id,
                "-Artifact",
                artifact_name,
            )
        self.run_command(command, cwd=self.repo_root)

    def run_lint(self, toolchain: str, *, expect_success: bool) -> CommandResult:
        if toolchain == "python":
            command = self.script_command(
                "python",
                "lint-recursive-run",
                "--repo-root",
                str(self.repo_root),
                "--run-id",
                self.run_id,
            )
        else:
            command = self.script_command(
                "powershell",
                "lint-recursive-run",
                "-RepoRoot",
                str(self.repo_root),
                "-RunId",
                self.run_id,
            )
        if expect_success:
            return self.run_command(command, cwd=self.repo_root)
        return self.run_command(command, cwd=self.repo_root, allowed_returncodes=(1,))

    def run_status(self, toolchain: str) -> CommandResult:
        if toolchain == "python":
            command = self.script_command(
                "python",
                "recursive-status",
                "--repo-root",
                str(self.repo_root),
                "--run-id",
                self.run_id,
            )
        else:
            command = self.script_command(
                "powershell",
                "recursive-status",
                "-RepoRoot",
                str(self.repo_root),
                "-RunId",
                self.run_id,
            )
        return self.run_command(command, cwd=self.repo_root)

    def run_verify(self, toolchain: str) -> CommandResult:
        if toolchain == "python":
            command = self.script_command(
                "python",
                "verify-locks",
                "--repo-root",
                str(self.repo_root),
                "--run-id",
                self.run_id,
            )
        else:
            command = self.script_command(
                "powershell",
                "verify-locks",
                "-RepoRoot",
                str(self.repo_root),
                "-RunId",
                self.run_id,
            )
        return self.run_command(command, cwd=self.repo_root)

    def lock_artifacts(self, artifacts_to_lock: list[str]) -> None:
        primary = self.primary_toolchain()
        for artifact in artifacts_to_lock:
            self.lock_artifact(primary, artifact)

    def lock_all(self) -> None:
        self.lock_artifacts(
            [
                "00-requirements.md",
                "00-worktree.md",
                "01-as-is.md",
                "02-to-be-plan.md",
                "addenda/02-to-be-plan.addendum-01.md",
                "03-implementation-summary.md",
                "03.5-code-review.md",
                "04-test-summary.md",
                "addenda/04-test-summary.upstream-gap.02-to-be-plan.addendum-01.md",
                "05-manual-qa.md",
                "06-decisions-update.md",
                "07-state-update.md",
                "08-memory-impact.md",
            ]
        )

    def assert_positive_path(self, *, require_subagent_review: bool = False) -> None:
        primary = self.primary_toolchain()
        if require_subagent_review:
            self.lock_artifacts(
                [
                    "03.5-code-review.md",
                    "04-test-summary.md",
                    "addenda/04-test-summary.upstream-gap.02-to-be-plan.addendum-01.md",
                    "05-manual-qa.md",
                    "06-decisions-update.md",
                    "07-state-update.md",
                    "08-memory-impact.md",
                ]
            )
        else:
            self.create_review_receipts()
        bundle_content = (self.repo_root / self.bundle_path.lstrip("/")).read_text(encoding="utf-8")
        if self.plan_addendum_path.lstrip("/") not in bundle_content and self.plan_addendum_path not in bundle_content:
            raise SmokeError("Generated review bundle did not include the expected plan addendum.")
        for expected_skill_ref in (
            ".recursive/memory/skills/SKILLS.md",
        ):
            if expected_skill_ref not in bundle_content:
                raise SmokeError(f"Generated review bundle did not include expected skill-memory ref: {expected_skill_ref}")
        for toolchain in self.validation_toolchains():
            if toolchain != primary:
                self.parity_bundle_path = self.generate_review_bundle(toolchain, "03-5-code-review-parity.md")
                parity_bundle_content = (self.repo_root / self.parity_bundle_path.lstrip("/")).read_text(encoding="utf-8")
                if self.plan_addendum_path.lstrip("/") not in parity_bundle_content and self.plan_addendum_path not in parity_bundle_content:
                    raise SmokeError("Parity review bundle did not include the expected plan addendum.")
                for expected_skill_ref in (
                    ".recursive/memory/skills/SKILLS.md",
                ):
                    if expected_skill_ref not in parity_bundle_content:
                        raise SmokeError(f"Parity review bundle did not include expected skill-memory ref: {expected_skill_ref}")
            lint_result = self.run_lint(toolchain, expect_success=True)
            status_result = self.run_status(toolchain)
            verify_result = self.run_verify(toolchain)
            if "Current Phase: COMPLETE" not in status_result.stdout:
                raise SmokeError(self.format_failure(f"{toolchain} status did not report completion", status_result))
            if require_subagent_review:
                review_content = (self.run_dir / "03.5-code-review.md").read_text(encoding="utf-8")
                if "Audit Execution Mode: subagent" not in review_content:
                    raise SmokeError("Subagent scenario regressed: Phase 3.5 is no longer marked Audit Execution Mode: subagent.")
                if not self.subagent_action_record_path:
                    raise SmokeError("Subagent scenario regressed: no canonical action record path was preserved.")
                action_record_file = self.repo_root / self.subagent_action_record_path.lstrip("/")
                if not action_record_file.exists():
                    raise SmokeError(f"Subagent scenario regressed: action record missing: {action_record_file}")
                self.summary.append(f"Subagent-backed smoke passed for {toolchain}.")
            else:
                self.summary.append(f"Positive smoke passed for {toolchain}.")
            self.summary.append(f"Lint duration {toolchain}: {lint_result.duration_seconds:.2f}s")
            self.summary.append(f"Verify duration {toolchain}: {verify_result.duration_seconds:.2f}s")
        self.summary.append("Positive addenda case passed.")

    def assert_subagent_review_path(self) -> None:
        primary = self.primary_toolchain()
        self.lock_artifacts(["00-requirements.md", "00-worktree.md"])
        for artifact_name in ("01-as-is.md", "02-to-be-plan.md"):
            self.create_terminal_review(artifact_name, f"smoke-{AUDITED_PHASE_KEYS[artifact_name]}")
            self.lock_artifact(primary, artifact_name)
        self.lock_artifact(primary, "addenda/02-to-be-plan.addendum-01.md")
        self.create_terminal_review("03-implementation-summary.md", "smoke-phase-3")
        self.lock_artifact(primary, "03-implementation-summary.md")

        review_id = "03-5-code-review-code-reviewer"
        review_ledger = f"/.recursive/run/{self.run_id}/evidence/reviews/phase-3-5/{review_id}/ledger.md"
        anticipated_bundle = f"/.recursive/run/{self.run_id}/evidence/review-bundles/phase-3-5/{review_id}/0001.md"
        record_name = "delegated-review-action-record.md"
        action_record_path = f"/.recursive/run/{self.run_id}/subagents/{record_name}"
        target = self.run_dir / "03.5-code-review.md"
        delegated = target.read_text(encoding="utf-8")
        delegated = replace_field(delegated, "Audit Execution Mode", "subagent")
        delegated = replace_field(delegated, "Subagent Availability", "available")
        delegated = replace_field(delegated, "Subagent Capability Probe", quote_md("The disposable harness generated and validated a canonical delegated-review action record."))
        delegated = replace_field(delegated, "Delegation Decision Basis", quote_md("The dedicated scenario exercises controller verification of a real persisted review action."))
        delegated = replace_section(
            delegated,
            "Subagent Contribution Verification",
            "\n".join(
                [
                    f"- Reviewed Action Records: {quote_md(action_record_path)}",
                    f"- Main-Agent Verification Performed: {quote_md('tiny_tasks.py')}, {quote_md('test_tiny_tasks.py')}, {quote_md(anticipated_bundle)}",
                    "- Acceptance Decision: accepted",
                    "- Refresh Handling: The final delegated-review receipt was bundled before controller verification and required no later author-owned change.",
                    "- Repair Performed After Verification: none",
                ]
            ),
        )
        write_text(target, delegated)
        self.bundle_path = self.create_terminal_review("03.5-code-review.md", review_id)
        upstream_artifacts = [
            f"/.recursive/run/{self.run_id}/00-requirements.md",
            f"/.recursive/run/{self.run_id}/00-worktree.md",
            f"/.recursive/run/{self.run_id}/01-as-is.md",
            f"/.recursive/run/{self.run_id}/02-to-be-plan.md",
            f"/.recursive/run/{self.run_id}/03-implementation-summary.md",
        ]
        reviewed_files = ["tiny_tasks.py", "test_tiny_tasks.py"]
        if primary == "python":
            action_command = self.script_command(
                "python",
                "recursive-subagent-action",
                "--repo-root",
                str(self.repo_root),
                "--run-id",
                self.run_id,
                "--subagent-id",
                "reviewer-01",
                "--phase",
                "03.5 Code Review",
                "--purpose",
                "Delegated review smoke scenario",
                "--execution-mode",
                "review",
                "--artifact-path",
                f"/.recursive/run/{self.run_id}/03-implementation-summary.md",
                "--review-bundle",
                self.bundle_path,
                "--review-ledger",
                review_ledger,
                "--action-taken",
                "Reviewed the immutable bundle, upstream artifacts, and changed product files.",
                "--artifact-read",
                f"/.recursive/run/{self.run_id}/03.5-code-review.md",
                "--audit-question",
                "Does the implementation satisfy R1 without widening scope?",
                "--verification-path",
                "tiny_tasks.py",
                "--verification-item",
                "Controller verified the action against the immutable bundle, ledger, and product diff.",
                "--output-name",
                record_name,
            )
            for upstream_artifact in upstream_artifacts:
                action_command.extend(["--upstream-artifact", upstream_artifact])
            for reviewed_file in reviewed_files:
                action_command.extend(["--reviewed-file", reviewed_file])
        else:
            action_command = self.powershell_splat_command(
                "recursive-subagent-action.ps1",
                {
                    "RepoRoot": str(self.repo_root),
                    "RunId": self.run_id,
                    "SubagentId": "reviewer-01",
                    "Phase": "03.5 Code Review",
                    "Purpose": "Delegated review smoke scenario",
                    "ExecutionMode": "review",
                    "ArtifactPath": f"/.recursive/run/{self.run_id}/03-implementation-summary.md",
                    "ReviewBundle": self.bundle_path,
                    "ReviewLedger": review_ledger,
                    "ActionTaken": [
                        "Reviewed the immutable bundle, upstream artifacts, and changed product files."
                    ],
                    "ArtifactRead": [
                        f"/.recursive/run/{self.run_id}/03.5-code-review.md"
                    ],
                    "AuditQuestion": [
                        "Does the implementation satisfy R1 without widening scope?"
                    ],
                    "VerificationPath": ["tiny_tasks.py"],
                    "VerificationItem": [
                        "Controller verified the action against the immutable bundle, ledger, and product diff."
                    ],
                    "OutputName": record_name,
                    "UpstreamArtifact": upstream_artifacts,
                    "ReviewedFile": reviewed_files,
                },
            )
        self.run_command(action_command, cwd=self.repo_root)
        self.subagent_action_record_path = action_record_path
        self.lock_artifact(primary, "03.5-code-review.md")

        self.create_terminal_review("04-test-summary.md", "smoke-phase-4")
        self.lock_artifact(primary, "04-test-summary.md")
        self.lock_artifacts(["addenda/04-test-summary.upstream-gap.02-to-be-plan.addendum-01.md", "05-manual-qa.md"])
        for artifact_name in ("06-decisions-update.md", "07-state-update.md", "08-memory-impact.md"):
            self.create_terminal_review(artifact_name, f"smoke-{AUDITED_PHASE_KEYS[artifact_name]}")
            self.lock_artifact(primary, artifact_name)

        for toolchain in self.validation_toolchains():
            self.run_lint(toolchain, expect_success=True)
            status_result = self.run_status(toolchain)
            self.run_verify(toolchain)
            if "Current Phase: COMPLETE" not in status_result.stdout:
                raise SmokeError(self.format_failure(f"{toolchain} status did not report completion", status_result))
        review_content = target.read_text(encoding="utf-8")
        if "Audit Execution Mode: subagent" not in review_content or not (self.repo_root / action_record_path.lstrip("/")).is_file():
            raise SmokeError("Subagent scenario did not preserve its delegated execution evidence.")
        self.summary.append("Dedicated subagent review scenario passed.")

    def negative_strict_tdd_case(self) -> None:
        target = self.run_dir / "03-implementation-summary.md"
        red_log_path = self.repo_root / self.red_log.lstrip("/")
        red_log_backup = red_log_path.with_suffix(red_log_path.suffix + ".bak")
        original = target.read_text(encoding="utf-8")
        broken = strip_lock_metadata(original)
        broken = remove_field(broken, "RED Evidence")
        tdd_match = re.search(r"(?s)## TDD Compliance Log(.*?)(?=^##\s+|\Z)", broken, re.MULTILINE)
        if not tdd_match:
            raise SmokeError("Failed to locate ## TDD Compliance Log while preparing the strict-TDD negative case.")
        tdd_body = tdd_match.group(1)
        if "RED Evidence:" in tdd_body or self.red_log in tdd_body or self.red_log.lstrip("/") in tdd_body:
            raise SmokeError("Strict-TDD negative case still contains RED evidence after rewrite.")
        write_text(target, broken)
        if not red_log_path.exists():
            raise SmokeError(f"Expected RED evidence file is missing before the negative case: {red_log_path}")
        if red_log_backup.exists():
            red_log_backup.unlink()
        red_log_path.rename(red_log_backup)
        try:
            for toolchain in self.validation_toolchains():
                lint_result = self.run_command(
                    self.script_command(
                        toolchain,
                        "lint-recursive-run",
                        "--repo-root" if toolchain == "python" else "-RepoRoot",
                        str(self.repo_root),
                        "--run-id" if toolchain == "python" else "-RunId",
                        self.run_id,
                    ),
                    cwd=self.repo_root,
                    allowed_returncodes=(0, 1),
                )
                if lint_result.returncode == 0:
                    raise SmokeError(self.format_failure(f"{toolchain} lint unexpectedly passed missing RED evidence", lint_result))
                if "Strict TDD" not in (lint_result.stdout + lint_result.stderr):
                    raise SmokeError(self.format_failure(f"{toolchain} lint missed strict TDD failure", lint_result))
                try:
                    self.lock_artifact(toolchain, "03-implementation-summary.md")
                except SmokeError:
                    pass
                else:
                    raise SmokeError(f"{toolchain} recursive-lock unexpectedly succeeded with missing RED evidence.")
            self.summary.append("Negative strict-TDD case passed.")
        finally:
            write_text(target, original)
            if red_log_backup.exists():
                red_log_backup.rename(red_log_path)

    def negative_phase0_diff_basis_case(self) -> None:
        target = self.run_dir / "00-worktree.md"
        original = target.read_text(encoding="utf-8")
        broken = strip_lock_metadata(original)
        broken = replace_field(broken, "Normalized baseline", quote_md("deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"))
        broken = replace_field(broken, "Normalized diff command", quote_md("git diff --name-only deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"))
        write_text(target, broken)
        try:
            for toolchain in self.validation_toolchains():
                lint_result = self.run_lint(toolchain, expect_success=False)
                combined = lint_result.stdout + lint_result.stderr
                if "diff basis" not in combined.lower():
                    raise SmokeError(self.format_failure(f"{toolchain} lint missed Phase 0 diff-basis failure", lint_result))
                status_result = self.run_status(toolchain)
                status_text = status_result.stdout + status_result.stderr
                if "diff basis" not in status_text.lower():
                    raise SmokeError(self.format_failure(f"{toolchain} status missed Phase 0 diff-basis blocker", status_result))
                try:
                    self.lock_artifact(toolchain, "00-worktree.md")
                except SmokeError:
                    pass
                else:
                    raise SmokeError(f"{toolchain} recursive-lock unexpectedly succeeded with an invalid Phase 0 diff basis.")
            self.summary.append("Negative Phase 0 diff-basis case passed.")
        finally:
            write_text(target, original)

    def negative_requirement_proof_case(self) -> None:
        target = self.run_dir / "04-test-summary.md"
        original = target.read_text(encoding="utf-8")
        broken = strip_lock_metadata(original)
        updated = re.sub(r"\s*\|\s*Changed Files:\s*`tiny_tasks\.py`,\s*`test_tiny_tasks\.py`", "", broken, count=1)
        if updated == broken:
            raise SmokeError("Failed to remove Changed Files from the requirement-proof negative case.")
        write_text(target, updated)
        try:
            for toolchain in self.validation_toolchains():
                lint_result = self.run_lint(toolchain, expect_success=False)
                combined = (lint_result.stdout + lint_result.stderr).lower()
                if "changed files" not in combined:
                    raise SmokeError(self.format_failure(f"{toolchain} lint missed requirement-proof failure", lint_result))
                status_result = self.run_status(toolchain)
                status_text = (status_result.stdout + status_result.stderr).lower()
                if "changed files" not in status_text:
                    raise SmokeError(self.format_failure(f"{toolchain} status missed requirement-proof blocker", status_result))
                try:
                    self.lock_artifact(toolchain, "04-test-summary.md")
                except SmokeError:
                    pass
                else:
                    raise SmokeError(f"{toolchain} recursive-lock unexpectedly succeeded with weak requirement proof.")
            self.summary.append("Negative requirement-proof case passed.")
        finally:
            write_text(target, original)

    def negative_source_inventory_case(self) -> None:
        target = self.run_dir / "01-as-is.md"
        original = target.read_text(encoding="utf-8")
        broken = strip_lock_metadata(original)
        broken = replace_section(broken, "Source Requirement Inventory", "- none")
        write_text(target, broken)
        try:
            for toolchain in self.validation_toolchains():
                lint_result = self.run_lint(toolchain, expect_success=False)
                combined = (lint_result.stdout + lint_result.stderr).lower()
                if "source requirement inventory" not in combined:
                    raise SmokeError(self.format_failure(f"{toolchain} lint missed source-inventory failure", lint_result))
                status_result = self.run_status(toolchain)
                status_text = (status_result.stdout + status_result.stderr).lower()
                if "source requirement inventory" not in status_text:
                    raise SmokeError(self.format_failure(f"{toolchain} status missed source-inventory blocker", status_result))
                try:
                    self.lock_artifact(toolchain, "01-as-is.md")
                except SmokeError:
                    pass
                else:
                    raise SmokeError(f"{toolchain} recursive-lock unexpectedly succeeded without a valid source requirement inventory.")
            self.summary.append("Negative source-inventory case passed.")
        finally:
            write_text(target, original)

    def negative_phase2_mapping_case(self) -> None:
        target = self.run_dir / "02-to-be-plan.md"
        original = target.read_text(encoding="utf-8")
        broken = strip_lock_metadata(original)
        broken = replace_section(broken, "Requirement Mapping", "- none")
        write_text(target, broken)
        try:
            for toolchain in self.validation_toolchains():
                lint_result = self.run_lint(toolchain, expect_success=False)
                combined = (lint_result.stdout + lint_result.stderr).lower()
                if "requirement mapping" not in combined:
                    raise SmokeError(self.format_failure(f"{toolchain} lint missed phase-2 mapping failure", lint_result))
                status_result = self.run_status(toolchain)
                status_text = (status_result.stdout + status_result.stderr).lower()
                if "requirement mapping" not in status_text:
                    raise SmokeError(self.format_failure(f"{toolchain} status missed phase-2 mapping blocker", status_result))
                try:
                    self.lock_artifact(toolchain, "02-to-be-plan.md")
                except SmokeError:
                    pass
                else:
                    raise SmokeError(f"{toolchain} recursive-lock unexpectedly succeeded without a valid Phase 2 requirement mapping.")
            self.summary.append("Negative Phase 2 mapping case passed.")
        finally:
            write_text(target, original)

    def negative_review_bundle_case(self) -> None:
        target = self.run_dir / "03.5-code-review.md"
        original = target.read_text(encoding="utf-8")
        broken = strip_lock_metadata(original)
        broken = replace_field(
            broken,
            "Review Bundle Path",
            quote_md(f"/.recursive/run/{self.run_id}/evidence/review-bundles/missing-review-bundle.md"),
        )
        write_text(target, broken)
        try:
            for toolchain in self.validation_toolchains():
                lint_result = self.run_lint(toolchain, expect_success=False)
                if "Review Bundle Path" not in (lint_result.stdout + lint_result.stderr):
                    raise SmokeError(self.format_failure(f"{toolchain} lint missed review bundle failure", lint_result))
                status_result = self.run_status(toolchain)
                if "Review Bundle Path" not in status_result.stdout and "review bundle" not in status_result.stdout.lower():
                    raise SmokeError(self.format_failure(f"{toolchain} status missed review bundle blocker", status_result))
            self.summary.append("Negative review-bundle case passed.")
        finally:
            write_text(target, original)

    def negative_addenda_case(self) -> None:
        target = self.run_dir / "03-implementation-summary.md"
        original = target.read_text(encoding="utf-8")
        broken = strip_lock_metadata(original)
        broken = remove_path_references(broken, self.plan_addendum_path)
        write_text(target, broken)
        try:
            for toolchain in self.validation_toolchains():
                lint_result = self.run_lint(toolchain, expect_success=False)
                combined = lint_result.stdout + lint_result.stderr
                if "addenda" not in combined.lower():
                    raise SmokeError(self.format_failure(f"{toolchain} lint missed effective-input addenda failure", lint_result))
                status_result = self.run_status(toolchain)
                status_text = status_result.stdout + status_result.stderr
                if "addenda" not in status_text.lower():
                    raise SmokeError(self.format_failure(f"{toolchain} status missed effective-input addenda blocker", status_result))
                try:
                    self.lock_artifact(toolchain, "03-implementation-summary.md")
                except SmokeError:
                    pass
                else:
                    raise SmokeError(f"{toolchain} recursive-lock unexpectedly succeeded while required addenda were omitted.")
            self.summary.append("Negative addenda-omission case passed.")
        finally:
            write_text(target, original)

    def negative_review_bundle_tamper_case(self) -> None:
        bundle_file = self.repo_root / self.bundle_path.lstrip("/")
        original = bundle_file.read_text(encoding="utf-8")
        broken = replace_section(bundle_file.read_text(encoding="utf-8"), "Targeted Code References", "- `README.md`")
        write_text(bundle_file, broken)
        try:
            for toolchain in self.validation_toolchains():
                lint_result = self.run_lint(toolchain, expect_success=False)
                combined = (lint_result.stdout + lint_result.stderr).lower()
                if "bundle hash" not in combined and "immutable bundle" not in combined:
                    raise SmokeError(self.format_failure(f"{toolchain} lint missed immutable review-bundle tampering", lint_result))
                status_result = self.run_status(toolchain)
                status_text = (status_result.stdout + status_result.stderr).lower()
                if "bundle hash" not in status_text and "immutable bundle" not in status_text:
                    raise SmokeError(self.format_failure(f"{toolchain} status missed immutable review-bundle tampering", status_result))
            self.summary.append("Negative immutable review-bundle tamper case passed.")
        finally:
            write_text(bundle_file, original)

    def positive_subagent_action_record_case(self) -> None:
        record_name = "positive-review-action-record.md"
        review_ledger = f"/.recursive/run/{self.run_id}/evidence/reviews/phase-3-5/03-5-code-review-code-reviewer/ledger.md"
        command = self.script_command(
            self.primary_toolchain(),
            "recursive-subagent-action",
            "--repo-root" if self.primary_toolchain() == "python" else "-RepoRoot",
            str(self.repo_root),
            "--run-id" if self.primary_toolchain() == "python" else "-RunId",
            self.run_id,
            "--subagent-id" if self.primary_toolchain() == "python" else "-SubagentId",
            "reviewer-01",
            "--phase" if self.primary_toolchain() == "python" else "-Phase",
            "03.5 Code Review",
            "--purpose" if self.primary_toolchain() == "python" else "-Purpose",
            "Validate the completed review evidence",
            "--execution-mode" if self.primary_toolchain() == "python" else "-ExecutionMode",
            "review",
            "--artifact-path" if self.primary_toolchain() == "python" else "-ArtifactPath",
            f"/.recursive/run/{self.run_id}/03.5-code-review.md",
            "--review-bundle" if self.primary_toolchain() == "python" else "-ReviewBundle",
            self.bundle_path,
            "--review-ledger" if self.primary_toolchain() == "python" else "-ReviewLedger",
            review_ledger,
            "--reviewed-file" if self.primary_toolchain() == "python" else "-ReviewedFile",
            "tiny_tasks.py",
            "--verification-item" if self.primary_toolchain() == "python" else "-VerificationItem",
            "Controller should compare the action record with the immutable bundle and ledger.",
            "--output-name" if self.primary_toolchain() == "python" else "-OutputName",
            record_name,
        )
        self.run_command(command, cwd=self.repo_root)
        action_record_file = self.run_dir / "subagents" / record_name
        try:
            validation = self.run_command(
                [str(self.python_exe), str(self.runtime_dir / "recursive_review_action.py"), "--repo-root", str(self.repo_root), "--action-record", self.repo_rel(action_record_file)],
                cwd=self.repo_root,
            )
            self.summary.append(f"Positive subagent-action-record case passed ({validation.duration_seconds:.2f}s).")
        finally:
            if action_record_file.exists():
                action_record_file.unlink()

    def negative_subagent_action_record_case(self) -> None:
        record_name = "negative-empty-action-record.md"
        review_ledger = f"/.recursive/run/{self.run_id}/evidence/reviews/phase-3-5/03-5-code-review-code-reviewer/ledger.md"
        action_command = self.script_command(
            self.primary_toolchain(),
            "recursive-subagent-action",
            "--repo-root" if self.primary_toolchain() == "python" else "-RepoRoot",
            str(self.repo_root),
            "--run-id" if self.primary_toolchain() == "python" else "-RunId",
            self.run_id,
            "--subagent-id" if self.primary_toolchain() == "python" else "-SubagentId",
            "reviewer-01",
            "--phase" if self.primary_toolchain() == "python" else "-Phase",
            "03.5 Code Review",
            "--purpose" if self.primary_toolchain() == "python" else "-Purpose",
            "Negative action-record coverage check",
            "--execution-mode" if self.primary_toolchain() == "python" else "-ExecutionMode",
            "review",
            "--artifact-path" if self.primary_toolchain() == "python" else "-ArtifactPath",
            f"/.recursive/run/{self.run_id}/03.5-code-review.md",
            "--review-bundle" if self.primary_toolchain() == "python" else "-ReviewBundle",
            self.bundle_path,
            "--review-ledger" if self.primary_toolchain() == "python" else "-ReviewLedger",
            review_ledger,
            "--output-name" if self.primary_toolchain() == "python" else "-OutputName",
            record_name,
        )
        self.run_command(action_command, cwd=self.repo_root)
        action_record_file = self.run_dir / "subagents" / record_name
        tampered = action_record_file.read_text(encoding="utf-8").replace("- Claims: none", "- Claims: none\n- Disposition: fixed")
        write_text(action_record_file, tampered)
        try:
            validation = self.run_command(
                [str(self.python_exe), str(self.runtime_dir / "recursive_review_action.py"), "--repo-root", str(self.repo_root), "--action-record", self.repo_rel(action_record_file)],
                cwd=self.repo_root,
                allowed_returncodes=(1,),
            )
            if "Disposition" not in validation.stdout and "schema" not in validation.stdout.lower():
                raise SmokeError(self.format_failure("Action validator missed terminal-field tampering", validation))
            self.summary.append("Negative subagent-action-record tamper case passed.")
        finally:
            if action_record_file.exists():
                action_record_file.unlink()

    def runtime_noise_case(self) -> None:
        pycache_dir = self.repo_root / "__pycache__"
        pytest_cache_dir = self.repo_root / ".pytest_cache"
        pycache_dir.mkdir(parents=True, exist_ok=True)
        pytest_cache_dir.mkdir(parents=True, exist_ok=True)
        write_text(pycache_dir / "smoke.cpython-311.pyc", "transient-runtime-noise")
        write_text(pytest_cache_dir / "state", "runtime-noise")
        try:
            for toolchain in self.validation_toolchains():
                lint_result = self.run_lint(toolchain, expect_success=True)
                status_result = self.run_status(toolchain)
                if "Current Phase: COMPLETE" not in status_result.stdout:
                    raise SmokeError(self.format_failure(f"{toolchain} status regressed under runtime noise", status_result))
                self.summary.append(f"Runtime-noise filtering passed for {toolchain} ({lint_result.duration_seconds:.2f}s).")
        finally:
            shutil.rmtree(pycache_dir, ignore_errors=True)
            shutil.rmtree(pytest_cache_dir, ignore_errors=True)

    def negative_human_qa_case(self) -> None:
        target = self.run_dir / "05-manual-qa.md"
        original = target.read_text(encoding="utf-8")
        broken = strip_lock_metadata(original)
        broken = replace_field(broken, "QA Execution Mode", "human")
        broken = replace_field(broken, "Approved by", "N/A")
        broken = replace_field(broken, "Date", "N/A")
        write_text(target, broken)
        try:
            for toolchain in self.validation_toolchains():
                lint_result = self.run_lint(toolchain, expect_success=False)
                if "Approved by" not in (lint_result.stdout + lint_result.stderr):
                    raise SmokeError(self.format_failure(f"{toolchain} lint missed human QA sign-off failure", lint_result))
                try:
                    self.lock_artifact(toolchain, "05-manual-qa.md")
                except SmokeError:
                    pass
                else:
                    raise SmokeError(f"{toolchain} recursive-lock unexpectedly succeeded without human QA sign-off.")
            self.summary.append("Negative human-QA case passed.")
        finally:
            write_text(target, original)

    def run_full_regression_suite(self) -> None:
        self.negative_phase0_diff_basis_case()
        self.negative_strict_tdd_case()
        self.negative_source_inventory_case()
        self.negative_phase2_mapping_case()
        self.negative_requirement_proof_case()
        self.negative_review_bundle_case()
        self.negative_review_bundle_tamper_case()
        self.negative_addenda_case()
        self.positive_subagent_action_record_case()
        self.negative_subagent_action_record_case()
        self.negative_human_qa_case()
        self.runtime_noise_case()

    def run(self) -> None:
        self.run_stage("preflight", self.record_preflight)
        self.run_stage("bootstrap", self.create_base_repo)
        self.run_stage("run scaffold", self.init_run)
        self.run_stage("red/green cycle", self.perform_red_green_cycle)
        self.run_stage("agent-operated qa evidence", self.perform_agent_qa)
        self.run_stage("artifact authoring", self.write_artifacts)
        if self.scenario == "subagent":
            self.run_stage("subagent positive path", self.assert_subagent_review_path)
            self.summary.append("Overall smoke result: full delegated-review path completed successfully.")
        else:
            self.run_stage("positive smoke path", self.assert_positive_path)
        if self.scenario == "full":
            self.run_stage("negative regression suite", self.run_full_regression_suite)
            self.summary.append("Overall smoke result: full smoke completed successfully end-to-end.")
        elif self.scenario == "quick":
            self.summary.append("Overall smoke result: quick smoke completed successfully end-to-end.")

    def print_summary(self) -> None:
        print()
        print("Smoke Summary")
        print("=============")
        for item in self.summary:
            print(f"- {item}")
        print(f"- Temp repo: {self.repo_root}")
        print(f"- Run ID: {self.run_id}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run recursive-mode maintainer smoke tests in a disposable repository.")
    parser.add_argument("--scenario", choices=["quick", "full", "subagent"], default="quick", help="Smoke scenario to run.")
    parser.add_argument(
        "--toolchain",
        choices=["python", "powershell", "mixed", "both"],
        default="mixed",
        help="Toolchain path to exercise. 'both' is kept as a compatibility alias for 'mixed'.",
    )
    parser.add_argument("--temp-root", default="", help="Optional directory to hold disposable smoke repos.")
    parser.add_argument("--keep-temp", action="store_true", help="Keep the disposable repo on success.")
    parser.add_argument("--command-timeout", type=int, default=30, help="Per-command timeout in seconds.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    harness = SmokeHarness(
        requested_toolchain=args.toolchain,
        scenario=args.scenario,
        temp_root=args.temp_root,
        keep_temp=args.keep_temp,
        command_timeout=args.command_timeout,
    )

    succeeded = False
    try:
        harness.run()
        harness.print_summary()
        succeeded = True
        return 0
    except SmokeError as exc:
        print(f"[FAIL] Stage: {harness.current_stage}")
        print(f"[FAIL] {exc}")
        print(f"[FAIL] Temp repo preserved at: {harness.repo_root}")
        return 1
    finally:
        if succeeded and not harness.keep_temp:
            shutil.rmtree(harness.temp_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
