# Tiny Tasks Smoke Recipe

Use this fixture for disposable maintainer smoke tests of `recursive-mode`.

It is intentionally small, deterministic, and standard-library only. This file owns the observable fixture and evidence contract; `scripts/test-recursive-mode-smoke.py` owns the execution mechanics.

## Fixture App

- Language: Python
- Test runner: `python -m unittest -q`
- Product files:
  - `tiny_tasks.py`
  - `test_tiny_tasks.py`

## Base Behavior

The base commit contains a tiny summary helper that reports only the total task count.

Expected base output:

```text
2 total
```

## Feature Change Under Test

Add completed and active counts to the summary output.

Expected post-change output:

```text
2 total, 1 completed, 1 active
```

Expected changed product files:

- `tiny_tasks.py`
- `test_tiny_tasks.py`

## Harness Modes

Scenarios:

- `quick` completes the positive self-audit path.
- `full` completes the positive self-audit path, then exercises the negative and resilience cases below.
- `subagent` completes the positive path with a persisted delegated-review action record.

Toolchains:

- `python` uses Python for authoring, locking, linting, status and lock verification.
- `powershell` requires PowerShell and uses the PowerShell wrappers for the same path.
- `mixed` uses Python as the primary toolchain and adds PowerShell parity when PowerShell is available.
- `both` is a compatibility alias for `mixed`.

## Required Run Evidence

Expected RED evidence path:

- `/.recursive/run/<run-id>/evidence/logs/red/red-cycle-01.log`

Expected GREEN evidence path:

- `/.recursive/run/<run-id>/evidence/logs/green/green-cycle-01.log`

Expected manual QA evidence path:

- `/.recursive/run/<run-id>/evidence/logs/manual-qa-agent.log`

Expected preview log path used for Phase 5 scaffolding:

- `/.recursive/run/<run-id>/evidence/logs/preview-server.log`

Expected locked addenda:

- `/.recursive/run/<run-id>/addenda/02-to-be-plan.addendum-01.md`
- `/.recursive/run/<run-id>/addenda/04-test-summary.upstream-gap.02-to-be-plan.addendum-01.md`

Every audited artifact present in this feature run has a controller-verified ledger and immutable pass with a matching bundle:

- Bundle: `/.recursive/run/<run-id>/evidence/review-bundles/<phase-key>/<review-id>/<NNNN>.md`
- Ledger: `/.recursive/run/<run-id>/evidence/reviews/<phase-key>/<review-id>/ledger.md`
- Verified pass: `/.recursive/run/<run-id>/evidence/reviews/<phase-key>/<review-id>/passes/<NNNN>.md`

The Phase 3.5 code-review paths are:

- Bundle: `/.recursive/run/<run-id>/evidence/review-bundles/phase-3-5/03-5-code-review-code-reviewer/0001.md`
- Ledger: `/.recursive/run/<run-id>/evidence/reviews/phase-3-5/03-5-code-review-code-reviewer/ledger.md`
- Verified pass: `/.recursive/run/<run-id>/evidence/reviews/phase-3-5/03-5-code-review-code-reviewer/passes/0001.md`

Expected delegated-review action-record path for the dedicated subagent scenario:

- `/.recursive/run/<run-id>/subagents/delegated-review-action-record.md`

## Expected Workflow Shape

- No legacy workflow-profile field.
- TDD mode: `strict`
- QA execution mode: `agent-operated`
- Optional review phase present: `03.5-code-review.md`
- The plan addendum and upstream-gap addendum remain independently locked and are re-read by affected downstream phases.
- Every audited artifact present in the run reaches whole-ledger PASS before it locks.
- Late receipts are compact delta receipts:
  - `06-decisions-update.md`
  - `07-state-update.md`
  - `08-memory-impact.md`

## Late-Phase Control-Plane Changes

The smoke run should update:

- `/.recursive/DECISIONS.md`
- `/.recursive/STATE.md`
- `/.recursive/memory/MEMORY.md`
- `/.recursive/memory/domains/TINY-TASKS.md`

## Positive Assertions

- The run reaches locked Phase 8 and reports `Current Phase: COMPLETE` without custom lock helpers.
- The generated review bundle preserves the plan addendum and stable skill-memory pointer.
- Each selected validation toolchain passes `lint`, `status`, and `verify-locks` on the same completed disposable repo.
- In the dedicated `subagent` scenario, `03.5-code-review.md` remains `Audit Execution Mode: subagent` through lock and final completion, and the canonical action record remains present under `subagents/`.

## Negative Assertions For Full Smoke

- An invalid Phase 0 diff basis blocks lint, status and lock.
- Removing RED evidence causes strict Phase 3 lint and lock failure.
- Removing the source requirement inventory blocks Phase 1.
- Removing the Phase 2 requirement mapping blocks Phase 2.
- Weakening the Phase 4 requirement proof blocks lint, status and lock.
- Breaking `Review Bundle Path` causes Phase 3.5 lint and status failure.
- Mutating an immutable review bundle causes lint and status failure.
- Omitting a required addendum from downstream effective inputs causes lint, status and lock failure.
- A malformed delegated-review action record is rejected clearly by the shared validator.
- Switching Phase 5 to `human` without sign-off causes lock failure.
- A valid generated action record passes the shared validator.
- Ignored runtime cache directories do not change the completed run status.
