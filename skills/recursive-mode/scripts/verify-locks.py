#!/usr/bin/env python3
"""
Verify recursive-mode artifact lock integrity.

Python equivalent to scripts/verify-locks.ps1.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import recursive_review_ledger as review_ledger


def load_phase_rules_module():
    module_path = Path(__file__).with_name("recursive_phase_rules.py")
    spec = importlib.util.spec_from_file_location("recursive_phase_rules", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load phase rules module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except FileNotFoundError:
        raise RuntimeError(f"Phase rules module not found: {module_path}")
    return module


STATUS_RE = re.compile(r'(?m)^[ \t]*Status:\s*(?:`|")?(\w+)(?:`|")?\s*$')
LOCK_HASH_RE = re.compile(r'(?m)^[ \t]*LockHash:\s*(?:`|")?([a-fA-F0-9]{64})(?:`|")?\s*$')
LOCKED_AT_RE = re.compile(r'(?m)^[ \t]*LockedAt:\s*(?:`|")?([^`"\r\n]+)(?:`|")?\s*$')
LOCK_HASH_LINE_RE = re.compile(r'(?m)^[ \t]*LockHash:.*(?:\n|$)')


@dataclass
class LockResult:
    valid: bool
    error: str | None = None
    stored_hash: str | None = None
    actual_hash: str | None = None
    locked_at: str | None = None
    fixed: bool = False
    new_locked_at: str | None = None
    new_hash: str | None = None


def write_status(status: str, message: str) -> None:
    print(f"[{status}] {message}")


def normalize_for_lock_hash(content: str) -> str:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    normalized = LOCK_HASH_LINE_RE.sub("", normalized)
    return normalized


def lock_hash_from_content(content: str) -> str:
    normalized = normalize_for_lock_hash(content)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def test_lock_valid(artifact_path: Path, fix: bool = False) -> LockResult:
    if not artifact_path.exists():
        return LockResult(valid=False, error="File not found")

    content = artifact_path.read_text(encoding="utf-8")

    status_match = STATUS_RE.search(content)
    if not status_match:
        return LockResult(valid=False, error="No Status field found")
    status = status_match.group(1)
    if status != "LOCKED":
        return LockResult(valid=False, error=f"Status is '{status}', expected 'LOCKED'")

    hash_match = LOCK_HASH_RE.search(content)
    if not hash_match:
        return LockResult(valid=False, error="No LockHash field found")
    stored_hash = hash_match.group(1).lower()

    locked_at_match = LOCKED_AT_RE.search(content)
    if not locked_at_match:
        return LockResult(valid=False, error="No LockedAt field found")
    locked_at = locked_at_match.group(1)

    actual_hash = lock_hash_from_content(content)
    if stored_hash == actual_hash:
        return LockResult(valid=True, locked_at=locked_at, stored_hash=stored_hash)

    result = LockResult(
        valid=False,
        error="Hash mismatch",
        stored_hash=stored_hash,
        actual_hash=actual_hash,
        locked_at=locked_at,
    )

    if fix:
        new_locked_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        content_with_new_locked_at = re.sub(
            r"(?m)^[ \t]*LockedAt:.*$",
            f"LockedAt: `{new_locked_at}`",
            content,
        )
        new_hash = lock_hash_from_content(content_with_new_locked_at)
        new_content = re.sub(
            r"(?m)^[ \t]*LockHash:.*$",
            f"LockHash: `{new_hash}`",
            content_with_new_locked_at,
        )
        artifact_path.write_text(new_content, encoding="utf-8", newline="")

        result.fixed = True
        result.new_locked_at = new_locked_at
        result.new_hash = new_hash

    return result


def test_gate(content: str, name: str) -> tuple[bool, str | None]:
    pass_re = re.compile(rf"{name}:\s*PASS")
    fail_re = re.compile(rf"{name}:\s*FAIL")
    if pass_re.search(content):
        return True, None
    if fail_re.search(content):
        return False, f"{name} gate shows FAIL"
    return False, f"No {name} gate result found"


def collect_recursive_review_issues(repo_root: Path, run_dir: Path, artifact_name: str, content: str) -> list[str]:
    """Thin adapter to the shared Recursive Review validation interface."""
    return review_ledger.collect_phase_issues(repo_root, run_dir, artifact_name, content)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify recursive-mode artifact lock integrity.")
    parser.add_argument("--run-id", default=None, help="Run ID to verify. If omitted, scans all runs.")
    parser.add_argument("--repo-root", default=".", help="Repository root path.")
    parser.add_argument("--fix", action="store_true", help="Fix incorrect lock hashes (updates LockedAt + LockHash).")
    parser.add_argument("--show-hashes", action="store_true", help="Show valid lock hashes in output.")
    args = parser.parse_args()

    resolved_repo_root = Path(args.repo_root).resolve()
    phase_rules = load_phase_rules_module()
    if args.run_id is not None and not phase_rules.is_canonical_run_id(args.run_id):
        write_status("FAIL", phase_rules.CANONICAL_RUN_ID_ERROR)
        return 1
    print("\nRecursive Lock Verification")
    print("=====================\n")
    print(f"Repository: {resolved_repo_root}")
    print(f"Run ID: {args.run_id if args.run_id is not None else '(scanning all runs)'}\n")

    run_base_dir = resolved_repo_root / ".recursive" / "run"
    if not run_base_dir.exists():
        write_status("FAIL", f"recursive run directory not found: {run_base_dir}")
        return 1

    if args.run_id is not None:
        runs = [args.run_id]
    else:
        runs = sorted([d.name for d in run_base_dir.iterdir() if d.is_dir()])

    artifacts = [
        {"file": "00-requirements.md", "name": "Requirements", "optional": False},
        {"file": "00-worktree.md", "name": "Worktree Setup", "optional": False},
        {"file": "01-as-is.md", "name": "AS-IS Analysis", "optional": True},
        {"file": "01.5-root-cause.md", "name": "Root Cause", "optional": True},
        {"file": "02-to-be-plan.md", "name": "TO-BE Plan", "optional": True},
        {"file": "03-implementation-summary.md", "name": "Implementation", "optional": True},
        {"file": "03.5-code-review.md", "name": "Code Review", "optional": True},
        {"file": "04-test-summary.md", "name": "Test Summary", "optional": True},
        {"file": "05-manual-qa.md", "name": "Manual QA", "optional": True},
        {"file": "06-decisions-update.md", "name": "Decisions Update", "optional": False},
        {"file": "07-state-update.md", "name": "State Update", "optional": False},
        {"file": "08-memory-impact.md", "name": "Memory Impact", "optional": False},
    ]

    total_runs = 0
    valid_runs = 0
    fixed_runs = 0
    failed_runs = 0
    stale_chain_runs = 0

    for run in runs:
        total_runs += 1
        run_dir = run_base_dir / run
        print(f"Checking run: {run}")
        print("-" * 50)

        run_valid = True
        run_fixed = False

        for artifact in artifacts:
            artifact_path = run_dir / artifact["file"]
            is_required = not artifact["optional"]
            if not artifact_path.exists():
                if not is_required:
                    write_status("INFO", f"{artifact['name']}: Not found (optional)")
                else:
                    write_status("FAIL", f"{artifact['name']}: Missing (required)")
                    run_valid = False
                continue

            content = artifact_path.read_text(encoding="utf-8")
            if not re.search(r'(?m)^[ \t]*Status:\s*(?:`|")?LOCKED(?:`|")?\s*$', content):
                write_status("WARN", f"{artifact['name']}: Not locked (DRAFT)")
                run_valid = False
                continue

            review_issues = collect_recursive_review_issues(resolved_repo_root, run_dir, artifact["file"], content)
            for issue in review_issues:
                write_status("FAIL", f"{artifact['name']}: {issue}")
                run_valid = False
            result = test_lock_valid(artifact_path, fix=args.fix and not review_issues)
            if result.valid:
                write_status("PASS", f"{artifact['name']}: Valid (locked at {result.locked_at})")
                if args.show_hashes and result.stored_hash:
                    print(f"         Hash: {result.stored_hash}")
            else:
                if result.fixed:
                    write_status("WARN", f"{artifact['name']}: Fixed hash mismatch (was tampered)")
                    if result.stored_hash:
                        print(f"         Old hash: {result.stored_hash}")
                    if result.new_hash:
                        print(f"         New hash: {result.new_hash}")
                    if result.new_locked_at:
                        print(f"         Updated at: {result.new_locked_at}")
                    run_fixed = True
                else:
                    write_status("FAIL", f"{artifact['name']}: {result.error}")
                    if result.stored_hash and result.actual_hash:
                        print(f"         Stored: {result.stored_hash}")
                        print(f"         Actual: {result.actual_hash}")
                    run_valid = False

            # Gate checks
            updated_content = artifact_path.read_text(encoding="utf-8")
            coverage_ok, coverage_reason = test_gate(updated_content, "Coverage")
            approval_ok, approval_reason = test_gate(updated_content, "Approval")
            if not coverage_ok:
                write_status("FAIL", f"{artifact['name']}: Coverage gate - {coverage_reason}")
                run_valid = False
            if not approval_ok:
                write_status("FAIL", f"{artifact['name']}: Approval gate - {approval_reason}")
                run_valid = False

        addenda_dir = run_dir / "addenda"
        if addenda_dir.exists():
            addenda_files = sorted(addenda_dir.glob("*.md"))
            if addenda_files:
                print("\nAddenda:")
                for addendum in addenda_files:
                    result = test_lock_valid(addendum, fix=args.fix)
                    if result.valid:
                        write_status("PASS", f"  {addendum.name}: Valid")
                    elif result.fixed:
                        write_status("WARN", f"  {addendum.name}: Fixed")
                        run_fixed = True
                    else:
                        write_status("FAIL", f"  {addendum.name}: {result.error}")
                        run_valid = False

        # Stale-chain detection: check whether any prerequisite hash in a receipt
        # no longer matches the current artifact content.
        stale_entries = phase_rules.get_all_stale_receipts(run_dir)
        run_stale = False
        if stale_entries:
            print("\nStale lock-chain receipts:")
            for entry in stale_entries:
                write_status("WARN", f"  {entry['artifact']}: {entry['reason']}")
                run_stale = True

        print()
        if run_stale:
            stale_chain_runs += 1
            run_valid = False
            write_status("WARN", f"Run '{run}': Stale lock-chain receipts detected (re-lock in phase order)")
        elif run_valid and not run_fixed:
            valid_runs += 1
            write_status("PASS", f"Run '{run}': All locks valid")
        elif run_fixed:
            fixed_runs += 1
            write_status("WARN", f"Run '{run}': Locks fixed (tampering detected)")
        else:
            failed_runs += 1
            write_status("FAIL", f"Run '{run}': Lock verification failed")
        print()

    print("=====================")
    print("Summary")
    print("=====================\n")
    print(f"Total runs checked: {total_runs}")
    write_status("PASS", f"Valid runs: {valid_runs}")
    if stale_chain_runs > 0:
        write_status("WARN", f"Stale-chain runs: {stale_chain_runs}")
    if fixed_runs > 0:
        write_status("WARN", f"Fixed runs (tampered): {fixed_runs}")
    if failed_runs > 0:
        write_status("FAIL", f"Failed runs: {failed_runs}")
    print()

    if failed_runs == 0 and stale_chain_runs == 0:
        write_status("PASS", "All locks verified successfully")
        return 0
    if failed_runs == 0:
        write_status("WARN", "Lock hashes valid but stale-chain receipts detected")
        return 1
    write_status("FAIL", "Some locks failed verification")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
