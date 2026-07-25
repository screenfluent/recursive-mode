#!/usr/bin/env python3
"""
Initialize a recursive-mode run folder and requirements scaffold.

Python equivalent to scripts/recursive-init.ps1.
"""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path


EVIDENCE_SUBDIRECTORIES = ("screenshots", "logs", "perf", "traces", "reviews", "review-bundles", "router", "other")
import re
import stat
import subprocess
import sys

RUN_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
WINDOWS_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def write_utf8_no_bom(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")


def ensure_directory(path: Path) -> None:
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
        print(f"[OK] Created directory: {path}")
    else:
        print(f"[OK] Directory exists: {path}")


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def is_link_or_reparse_point(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    if callable(is_junction) and is_junction():
        return True
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return bool(attributes & WINDOWS_REPARSE_POINT)


def run_directory_error(repo_root: Path, run_root: Path, run_dir: Path) -> str | None:
    recursive_root = repo_root / ".recursive"
    evidence_dir = run_dir / "evidence"
    checks = [
        (recursive_root, repo_root, ".recursive control directory"),
        (run_root, recursive_root, "run root directory"),
        (run_dir, run_root, "run directory"),
        (run_dir / "addenda", run_dir, "addenda directory"),
        (run_dir / "subagents", run_dir, "subagents directory"),
        (run_dir / "router-prompts", run_dir, "router-prompts directory"),
        (evidence_dir, run_dir, "evidence directory"),
    ]
    checks.extend(
        (evidence_dir / subdirectory, evidence_dir, f"evidence/{subdirectory} directory")
        for subdirectory in EVIDENCE_SUBDIRECTORIES
    )
    for path, parent, label in checks:
        if is_link_or_reparse_point(path):
            return f"{label} must be a real directory and cannot be a symlink or reparse point."
        if path.exists() and not path.is_dir():
            return f"{label} must be a real directory and cannot be a symlink or reparse point."
        if not is_within(path.resolve(), parent.resolve()):
            return f"{label} must remain within its canonical parent directory."
    return None


def phase_zero_path_error(paths: tuple[Path, ...]) -> str | None:
    for path in paths:
        if is_link_or_reparse_point(path):
            return f"target {path.name} must be a regular file and cannot be a symlink or reparse point."
        if not path.exists():
            continue
        if not path.is_file():
            return f"target {path.name} must be a regular file and cannot be a symlink or reparse point."
        try:
            link_count = path.stat().st_nlink
        except OSError as exc:
            return f"target {path.name} could not be validated safely: {exc}."
        if link_count != 1:
            return f"target {path.name} must not have multiple hard links."
    return None


def load_lint_module():
    module_path = Path(__file__).with_name("lint-recursive-run.py")
    spec = importlib.util.spec_from_file_location("recursive_mode_lint", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load lint module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def force_replacement_error(paths: tuple[Path, ...]) -> str | None:
    lint = load_lint_module()
    for path in paths:
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8", errors="replace")
        status_fields = re.findall(r"(?m)^[ \t]*(?:[-*][ \t]+)?Status:[ \t]*(.+?)\s*$", content)
        if len(status_fields) != 1:
            return f"--force target {path.name} must contain exactly one Status field; found {len(status_fields)}."
        status = lint.get_md_field_value(content, "Status")
        if status == "DRAFT":
            continue
        if status == "LOCKED":
            return (
                f"--force may replace only DRAFT scaffolds; {path.name} is LOCKED. "
                "Reopen it with recursive-lock --reopen before regenerating the scaffold."
            )
        rendered_status = status or "missing"
        return (
            f"--force may replace only DRAFT scaffolds; {path.name} has Status: {rendered_status}. "
            "Repair the artifact status before regenerating the scaffold."
        )
    return None


def run_git(repo_root: Path, *args: str) -> tuple[str | None, str | None]:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        return None, f"Unable to execute git: {exc}"
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or f"git {' '.join(args)} failed"
        return None, message
    return result.stdout.strip(), None


def detect_git_context(repo_root: Path) -> tuple[dict[str, str], str | None]:
    head_sha, head_error = run_git(repo_root, "rev-parse", "--verify", "HEAD^{commit}")
    if head_error or not head_sha:
        return {}, f"Unable to resolve HEAD commit for Phase 0 diff basis prefill: {head_error or 'git rev-parse returned no output'}"

    branch_name, branch_error = run_git(repo_root, "symbolic-ref", "--quiet", "--short", "HEAD")
    if branch_error or not branch_name:
        branch_name = "(detached HEAD)"

    diff_command = f"git diff --name-only {head_sha}"
    return {
        "baseline_type": "local commit",
        "baseline_reference": head_sha,
        "comparison_reference": "working-tree",
        "normalized_baseline": head_sha,
        "normalized_comparison": "working-tree",
        "normalized_diff_command": diff_command,
        "base_branch": branch_name,
        "worktree_branch": branch_name,
        "base_commit": head_sha,
        "notes": "recursive-init prefilled this executable diff basis from the current HEAD commit. If Phase 0 later changes the chosen baseline, update every diff-basis field and rerun lint before locking.",
    }, None


def validate_phase0_diff_basis(repo_root: Path, run_dir: Path) -> str | None:
    lint = load_lint_module()
    diff_basis = lint.get_run_diff_basis(run_dir)
    _normalized_basis, error = lint.normalize_diff_basis(repo_root, diff_basis)
    return error


def build_training_loader_query(run_id: str, template: str, from_issue: str) -> str:
    run_phrase = re.sub(r"[-_]+", " ", run_id).strip()
    parts = [f"{template.strip()} recursive run".strip()]
    if run_phrase:
        parts.append(run_phrase)
    if from_issue.strip():
        parts.append(from_issue.strip())
    return " ".join(part for part in parts if part)


def run_training_loader(repo_root: Path, run_id: str, template: str, from_issue: str) -> int:
    loader_script = repo_root / ".recursive" / "scripts" / "recursive-training-loader.py"
    if not loader_script.exists():
        print("[INFO] recursive-training loader not installed; skipping experiential memory load.")
        return 0

    query = build_training_loader_query(run_id, template, from_issue)
    command = [
        sys.executable,
        str(loader_script),
        "--repo-root",
        str(repo_root),
        "--query",
        query,
    ]
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip() or "no diagnostics emitted"
        print(f"[WARN] recursive-training loader failed: {details}")
        print("[WARN] Continuing without loaded experiential memory.")
        return 0

    print("[OK] Loaded repository memory context via recursive-training.")
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip())
    return 0


def requirements_content(run_id: str, template: str, from_issue: str) -> str:
    inputs = ["- [chat summary or source notes if captured in repo]"]
    if from_issue.strip():
        inputs.append(f"- Source: {from_issue.strip()}")
    inputs_block = "\n".join(inputs)

    return f"""Run: `/.recursive/run/{run_id}/`
Phase: `00 Requirements`
Status: `DRAFT`
Inputs:
{inputs_block}
Outputs:
- `/.recursive/run/{run_id}/00-requirements.md`
Scope note: This document defines stable requirement identifiers and acceptance criteria. (Template: {template})

## TODO

- [ ] Elicit requirements from user/context
- [ ] Define requirement identifiers (R1, R2, ...)
- [ ] Write acceptance criteria for each requirement
- [ ] Document out of scope items (OOS1, OOS2, ...)
- [ ] List constraints and assumptions
- [ ] Complete Coverage Gate checklist
- [ ] Complete Approval Gate checklist

## Requirements

### `R1` <short title>

Description:
Acceptance criteria:
- [observable condition 1]
- [observable condition 2]

## Out of Scope

- `OOS1`: ...

## Constraints

- ...

## Coverage Gate
...
Coverage: FAIL

## Approval Gate
...
Approval: FAIL
"""


def worktree_content(run_id: str, repo_root: Path, git_context: dict[str, str], prefill_error: str | None) -> str:
    base_branch = git_context.get("base_branch", "(resolve during Phase 0)")
    worktree_branch = git_context.get("worktree_branch", "(resolve during Phase 0)")
    base_commit = git_context.get("base_commit", "<resolve-before-locking>")
    baseline_type = git_context.get("baseline_type", "local commit")
    baseline_reference = git_context.get("baseline_reference", "<resolve-before-locking>")
    comparison_reference = git_context.get("comparison_reference", "working-tree")
    normalized_baseline = git_context.get("normalized_baseline", "<resolve-before-locking>")
    normalized_comparison = git_context.get("normalized_comparison", "working-tree")
    normalized_diff_command = git_context.get("normalized_diff_command", "git diff --name-only <resolve-before-locking>")
    notes = git_context.get(
        "notes",
        "Populate an executable diff basis before locking Phase 0. Lint and lock will fail until the normalized basis matches live git state.",
    )
    setup_note = "recursive-init detected the current repository context and prefilled the Phase 0 diff basis."
    if prefill_error:
        setup_note = f"recursive-init could not prefill the Phase 0 diff basis automatically: {prefill_error}"

    return f"""Run: `/.recursive/run/{run_id}/`
Phase: `00 Worktree`
Status: `DRAFT`
Inputs:
- `/.recursive/run/{run_id}/00-requirements.md`
- Current git repository state
Outputs:
- `/.recursive/run/{run_id}/00-worktree.md`
Scope note: This document records the Phase 0 worktree context and the executable diff basis that all later audited phases must reuse.

## TODO

- [ ] Confirm the selected worktree location and isolation approach
- [ ] Confirm the base branch and worktree branch values
- [ ] Run setup and verify the clean test baseline
- [ ] Confirm the diff basis fields still match live git state
- [ ] Complete Coverage Gate checklist
- [ ] Complete Approval Gate checklist

## Directory Selection

- Repository root: `{repo_root}`
- Preferred worktree location: `.worktrees/{run_id}/`
- Update this section with the actual selected location before locking Phase 0.

## Safety Verification

- Original branch / repo state observed at init time: `{base_branch}`
- Isolation still must be confirmed after the actual worktree is created.

## Worktree Creation

- Intended worktree branch: `{worktree_branch}`
- Record the actual worktree creation command and output before locking.

## Main Branch Protection

- Base branch source of truth at init time: `{base_branch}`
- Explicitly document any deviation from isolated worktree execution before locking.

## Project Setup

- Init-time note: {setup_note}
- Replace this section with the actual setup commands and results during Phase 0.

## Test Baseline Verification

- Record the baseline commands and results after setup completes.

## Worktree Context

- Base branch: `{base_branch}`
- Worktree branch: `{worktree_branch}`
- Base commit: `{base_commit}`

## Diff Basis For Later Audits

- Baseline type: `{baseline_type}`
- Baseline reference: `{baseline_reference}`
- Comparison reference: `{comparison_reference}`
- Normalized baseline: `{normalized_baseline}`
- Normalized comparison: `{normalized_comparison}`
- Normalized diff command: `{normalized_diff_command}`
- Base branch: `{base_branch}`
- Worktree branch: `{worktree_branch}`
- Diff basis notes: `{notes}`

## Traceability

- Recursive workflow safety -> Phase 0 records a reusable executable diff basis before audited phases begin.

## Coverage Gate

- [ ] Worktree location and branch context are recorded
- [ ] Setup and clean baseline verification are recorded
- [ ] Diff basis fields are executable against live git state

Coverage: FAIL

## Approval Gate

- [ ] Phase 0 context is ready for downstream audited phases
- [ ] No unresolved setup or diff-basis inconsistencies remain

Approval: FAIL
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize a recursive-mode run folder and requirements template.")
    parser.add_argument("--run-id", required=True, help="Run ID (folder name under .recursive/run/).")
    parser.add_argument("--repo-root", default=".", help="Repository root path.")
    parser.add_argument(
        "--template",
        choices=["feature", "bugfix", "refactor"],
        default="feature",
        help="Requirements template flavor.",
    )
    parser.add_argument("--from-issue", default="", help="Optional issue/ticket/source reference.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing 00-requirements.md.")
    args = parser.parse_args()

    if not RUN_ID_RE.fullmatch(args.run_id):
        print("[FAIL] Run ID must be a canonical kebab-case directory name.")
        return 1

    repo_root = Path(args.repo_root).resolve()
    print(f"[INFO] Repo root: {repo_root}")

    run_root = repo_root / ".recursive" / "run"
    run_dir = run_root / args.run_id
    requirements_path = run_dir / "00-requirements.md"
    worktree_path = run_dir / "00-worktree.md"

    directory_error = run_directory_error(repo_root, run_root, run_dir)
    if directory_error:
        print(f"[FAIL] {directory_error}")
        return 1

    path_error = phase_zero_path_error((requirements_path, worktree_path))
    if path_error:
        print(f"[FAIL] {path_error}")
        return 1

    if args.force:
        replacement_error = force_replacement_error((requirements_path, worktree_path))
        if replacement_error:
            print(f"[FAIL] {replacement_error}")
            return 1

    ensure_directory(run_root)
    ensure_directory(run_dir)
    ensure_directory(run_dir / "addenda")
    ensure_directory(run_dir / "subagents")
    ensure_directory(run_dir / "router-prompts")

    evidence_dir = run_dir / "evidence"
    ensure_directory(evidence_dir)
    for sub in EVIDENCE_SUBDIRECTORIES:
        ensure_directory(evidence_dir / sub)

    if requirements_path.exists() and not args.force:
        print(f"[INFO] Requirements file exists, not overwriting: {requirements_path}")
    else:
        write_utf8_no_bom(requirements_path, requirements_content(args.run_id, args.template, args.from_issue))
        print(f"[OK] Wrote requirements template: {requirements_path}")

    git_context, prefill_error = detect_git_context(repo_root)
    if prefill_error:
        print(f"[WARN] {prefill_error}")

    if worktree_path.exists() and not args.force:
        print(f"[INFO] Worktree file exists, not overwriting: {worktree_path}")
    else:
        write_utf8_no_bom(worktree_path, worktree_content(args.run_id, repo_root, git_context, prefill_error))
        print(f"[OK] Wrote Phase 0 worktree template: {worktree_path}")

    diff_basis_error = validate_phase0_diff_basis(repo_root, run_dir)
    if diff_basis_error:
        print(f"[FAIL] 00-worktree.md diff basis is not executable yet: {diff_basis_error}")
        print("       Fix the Phase 0 diff-basis fields before locking or relying on downstream audit tooling.")
        return 1
    print("[OK] Phase 0 diff basis is executable against live git state.")

    training_status = run_training_loader(repo_root, args.run_id, args.template, args.from_issue)
    if training_status != 0:
        return training_status

    print()
    print("Next steps:")
    print(f"1) Edit: .recursive/run/{args.run_id}/00-requirements.md")
    print(f"2) Edit: .recursive/run/{args.run_id}/00-worktree.md")
    print(f"3) Run:  Implement requirement '{args.run_id}'")
    print("4) Complete the run through the audited Phase 8 closeout before considering it done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
