# recursive-status (prompt template)

> Paste this into chat if your agent does not support custom slash commands.

## Usage Pattern

```text
Check recursive-mode status: [run-id]
```

## Script

```bash
python "<SKILL_DIR>/scripts/recursive-status.py" --repo-root . --run-id "<run-id>"
python3 "<SKILL_DIR>/scripts/recursive-status.py" --repo-root . --run-id "<run-id>"
python3 "<SKILL_DIR>/scripts/recursive-status.py" --repo-root . --run-id "<run-id>" --show-hashes
```

```powershell
powershell -ExecutionPolicy Bypass -File "<SKILL_DIR>/scripts/recursive-status.ps1" -RepoRoot . -RunId "<run-id>"
pwsh -NoProfile -File "<SKILL_DIR>/scripts/recursive-status.ps1" -RepoRoot . -RunId "<run-id>"
pwsh -NoProfile -File "<SKILL_DIR>/scripts/recursive-status.ps1" -RepoRoot . -RunId "<run-id>" -ShowHashes
```

Omit the run ID to inspect the run directory with the newest directory modification time; pass the run ID explicitly whenever selection matters. Use `--show-hashes` or `-ShowHashes` to print the stored `LockHash` for every lock-valid phase.

## What It Shows

- Every phase artifact, including `SKIPPED`, `PENDING`, `DRAFT`, `LOCKED`, or invalid `LOCKED*` states, with a blocker preview.
- The validated lock chain, optional hashes, and any stale downstream lock receipts.
- `Next Legal Phase` and `Current Phase` from the same semantic validation, including invalid scheduled-phase activations.
- Full blockers for the current phase, including incomplete TODOs, failing gates, review-ledger requirements, TDD evidence, review bundles, and QA evidence where applicable.
- Evidence and executable diff-basis summaries, followed by phase-appropriate next steps and the quick command for resuming the run.

## Example Output Shape

```text
Recursive Run: <run-id>
===================================

Phase Status:
  Phase 0 (Requirements)     [LOCKED]
  Phase 0 (Worktree)         [LOCKED]
  Phase 1 (AS-IS)            [DRAFT]
    blockers: <first blocker>; <second blocker>; ...
  Phase 2 (TO-BE Plan)       [SKIPPED] (not needed)
  Phase 8 (Memory)           [PENDING]

Lock Chain:
  [OK]  .recursive/run/<run-id>/00-requirements.md
  [OK]  .recursive/run/<run-id>/00-worktree.md
  [DRAFT]   .recursive/run/<run-id>/01-as-is.md

Next Legal Phase: 01-as-is.md

Current Phase: 1 (AS-IS)
Status: DRAFT

Audit Blockers:
  - <blocker>

Evidence:
  Path:   .recursive/run/<run-id>/evidence/
  Exists: Yes
  Files:  <count>

Diff Audit:
  Changed files reviewed from git diff basis: <count>

Next Steps:
  1. Update .recursive/run/<run-id>/01-as-is.md so the audit sections are complete and grounded in upstream artifacts plus the recorded diff basis.
  2. Repair any in-scope gaps or unexplained drift, then rerun the audit.
  3. Only after whole-ledger PASS may Coverage/Approval pass and the phase lock.

Quick Command:
  Implement requirement '<run-id>'
```

## Implementation

1. Select the requested run or the run directory with the newest directory modification time under `/.recursive/run/`.
2. Resolve the recorded Phase 0 diff basis against live Git state and derive the phase-owned changed files.
3. Evaluate every phase artifact through the installed phase, ledger, gate and lock contracts.
4. Report the first non-skipped, non-lock-valid phase as current and next legal, block the next phase when a scheduled activation record is invalid, or report completion when every required phase is lock-valid.
5. Attribute diff blockers to the phase that owns them instead of retroactively blaming earlier locked phases for late control-plane or memory files.
