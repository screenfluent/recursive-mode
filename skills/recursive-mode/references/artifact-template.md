# recursive-mode Artifact Writing Guide

Use this reference when authoring or repairing files under `/.recursive/run/<run-id>/` or durable memory shards under `/.recursive/memory/`. The installed runtime owns machine-enforced headings, review metadata, locking, and validation; `/.recursive/RECURSIVE.md` owns workflow semantics. This guide explains how to fill those structures without duplicating the runtime's generated output.

If this guide and an installed script disagree, follow the script and treat the disagreement as a contract defect to repair. Do not preserve an obsolete example merely because it appears here.

## Start with the runtime

Generate structures instead of hand-copying templates when a generator exists:

```bash
python3 ./.recursive/scripts/recursive-init.py --repo-root . --run-id "<run-id>"
python3 ./.recursive/scripts/recursive-closeout.py --repo-root . --run-id "<run-id>" --phase 04
python3 ./.recursive/scripts/recursive-closeout.py --repo-root . --run-id "<run-id>" --phase 05
python3 ./.recursive/scripts/recursive-closeout.py --repo-root . --run-id "<run-id>" --phase 06
python3 ./.recursive/scripts/recursive-closeout.py --repo-root . --run-id "<run-id>" --phase 07
python3 ./.recursive/scripts/recursive-closeout.py --repo-root . --run-id "<run-id>" --phase 08
```

Use `recursive-worktree` for `00-worktree.md`, the phase-owning skill for Phases 1 through 3.5, and `recursive-closeout` for Phases 4 through 8. A generated scaffold is a starting state, not evidence that the phase is complete.

## Artifact sequence

| Artifact | Purpose | Lossless review ledger |
| --- | --- | --- |
| `00-requirements.md` | Approved requirements, scope and constraints | No |
| `00-worktree.md` | Isolation, baseline and executable diff basis | No |
| `01-as-is.md` | Current behavior and source-requirement inventory | Yes |
| `01.5-root-cause.md` | Root-cause evidence when debugging is required | Yes |
| `02-to-be-plan.md` | Approved implementation and verification plan | Yes |
| `03-implementation-summary.md` | Implementation, TDD and deviation receipt | Yes |
| `03.5-code-review.md` | Optional review receipt pointing to the canonical ledger | Yes |
| `04-test-summary.md` | Exact automated verification receipt | Yes |
| `05-manual-qa.md` | Human, agent-operated or hybrid QA receipt | No |
| `06-decisions-update.md` | Compact `DECISIONS.md` delta receipt | Yes |
| `07-state-update.md` | Compact `STATE.md` delta receipt | Yes |
| `08-memory-impact.md` | Memory freshness and promotion receipt | Yes |

The audited artifacts are exactly Phases 1, 1.5, 2, 3, 3.5, 4, 6, 7 and 8. Phase 5 is QA-only and never receives `## Review Metadata`.

## Required header

Every phase artifact and addendum starts with this shape:

```md
Run: `/.recursive/run/<run-id>/`
Phase: `<number> <name>`
Status: `DRAFT`
Inputs:
- `/<repo-relative-input>`
Outputs:
- `/<repo-relative-output>`
Scope note: <what this artifact decides or enables>
```

List the effective inputs actually read, including matching stage-local addenda and relevant current-phase upstream-gap addenda. Do not add a workflow-version field.

Lock through `recursive-lock`; do not hand-author lock metadata. A locked header adds:

```md
LockedAt: `<ISO8601 timestamp>`
LockHash: `<sha256>`
```

## Common completion sections

All downstream artifacts include `## Traceability`. Every artifact ends with `## Coverage Gate` followed by `## Approval Gate`.

```md
## Traceability

- `R1` -> <where this artifact addresses the requirement> | Evidence: <concrete paths, commands or observations>

## Coverage Gate

- <phase-specific coverage proof>
Coverage: FAIL

## Approval Gate

- <phase-specific readiness proof>
Approval: FAIL
```

Replace `FAIL` only when the evidence supports it. For audited phases, whole-ledger PASS must already exist before either gate can pass. An unmapped in-scope requirement, incomplete upstream reconciliation, unresolved finding, unexplained diff drift or placeholder keeps the relevant gate red.

## Audited artifact scaffold

The audited lifecycle is:

`draft -> audit -> repair -> re-audit -> whole-ledger PASS -> Coverage -> Approval -> lock`

Findings live only in the canonical `recursive-review` ledger. Do not add `Gaps Found`, `Repair Work Performed`, `Audit Verdict`, `Issues Found`, severity buckets, positive findings or a second advice list to a phase artifact.

Every audited artifact contains the following shared sections before `Traceability` and the two terminal gates.

### Audit Context

```md
## Audit Context

- Audit Execution Mode: <subagent|self-audit>
- Subagent Availability: <available|unavailable>
- Subagent Capability Probe: <concrete probe result>
- Delegation Decision Basis: <why the selected mode follows from the probe>
- Delegation Override Reason: <required only when available subagents were not used>
- Audit Inputs Provided:
  - `/<artifact-or-code-path>`
```

Record exact artifacts, diff basis, changed files and targeted code references used by the audit. Do not preselect `self-audit` or claim that subagents are unavailable before probing.

### Effective Inputs Re-read

```md
## Effective Inputs Re-read

- `/<base-input>`
- `/<matching-addendum>`
```

List what was actually re-read, not merely what appears in the header.

### Earlier Phase Reconciliation

```md
## Earlier Phase Reconciliation

- Upstream artifact: `/<path>`
  - Claim carried forward: <claim>
  - Current reconciliation: <result>
```

Reconcile locked upstream claims and approved addenda with the current evidence. Repair current work or write a current-phase upstream-gap addendum; never edit locked history.

### Subagent Contribution Verification

```md
## Subagent Contribution Verification

- Reviewed Action Records: <none or concrete paths>
- Main-Agent Verification Performed: <actual files, diffs, bundles and artifacts checked>
- Acceptance Decision: <accepted|partially accepted|rejected>
- Refresh Handling: <whether changed evidence required a refreshed bundle or action record>
- Repair Performed After Verification: <none or concrete repair paths>
```

These are controller checks, not delegated claims. Every cited path must resolve, and meaningful delegated work must have a canonical action record under `/.recursive/run/<run-id>/subagents/`.

### Worktree Diff Audit

```md
## Worktree Diff Audit

- Baseline type: <local commit|local branch|remote ref|merge-base derived>
- Baseline reference: <human-facing ref>
- Comparison reference: <working-tree|HEAD|ref>
- Normalized baseline: <commit>
- Normalized comparison: <working-tree or commit>
- Normalized diff command: <executable command>
- Planned or claimed changed files:
  - `path/to/file`
- Actual changed files reviewed:
  - `path/to/file`
- Unexplained drift: <none or explanation>
```

`00-worktree.md` owns the executable diff basis. Phase 2 owns the expected product surface; Phases 3, 3.5 and 4 own the actual product diff; Phases 6, 7 and 8 additionally own their respective control-plane or memory changes.

### Requirement Completion Status

Use one machine-checkable row for every in-scope `R#` or source-inventory ID. Do not mix fields from conflicting statuses.

```md
## Requirement Completion Status

- `R1 | Status: implemented | Changed Files: /path/to/file | Implementation Evidence: /path/to/file, /path/to/artifact`
- `R2 | Status: verified | Changed Files: /path/to/file | Implementation Evidence: /path/to/file | Verification Evidence: /path/to/test-summary.md`
- `R3 | Status: deferred | Rationale: <why> | Deferred By: /.recursive/run/<run-id>/addenda/...`
- `R4 | Status: out-of-scope | Rationale: <why> | Scope Decision: /.recursive/run/<run-id>/addenda/...`
- `R5 | Status: blocked | Rationale: <why> | Blocking Evidence: /path/to/log`
- `R6 | Status: superseded by approved addendum | Addendum: /.recursive/run/<run-id>/addenda/...`
```

Phase 2 uses planning dispositions instead:

```md
- `R1 | Status: planned | Implementation Surface: /path/to/file | Verification Surface: /path/to/test-or-artifact | QA Surface: /path/to/scenario`
- `SRC-001 | Status: planned-via-merge | Implementation Surface: /path/to/file | Verification Surface: /path/to/test-or-artifact | QA Surface: not-applicable-with-rationale | Rationale: <why the merge is lossless>`
- `SRC-002 | Status: planned-indirectly | Implementation Surface: /path/to/file | Verification Surface: /path/to/test-or-artifact | QA Surface: not-applicable-with-rationale | Rationale: <why the obligation is satisfied indirectly>`
```

### Review Metadata

Every audited artifact has exactly one six-field pointer section in this order:

```md
## Review Metadata

- Review ID: <review-id>
- Review Ledger Path: `/.recursive/run/<run-id>/evidence/reviews/<phase-key>/<review-id>/ledger.md`
- Latest Verified Pass: `/.recursive/run/<run-id>/evidence/reviews/<phase-key>/<review-id>/passes/<NNNN>.md`
- Latest Verified Pass Hash: <sha256>
- Review Bundle Path: `/.recursive/run/<run-id>/evidence/review-bundles/<phase-key>/<review-id>/<NNNN>.md`
- Review Bundle Hash: <sha256>
```

Generate review bundles with `recursive-review-bundle`; maintain findings with `recursive-review`; generate delegated action records through `recursive-subagent` and the installed `recursive-subagent-action` runtime. Those owners define the current bundle, ledger and claim schemas. Do not copy their full formats into this file or hand-author a substitute.

### Prior Recursive Evidence Reviewed

Phases 1, 2, 4, 7 and 8 also include:

```md
## Prior Recursive Evidence Reviewed

- `/<relevant earlier run or memory path>`
```

Use `None relevant: <reason>` only after checking `DECISIONS.md`, the memory router and relevant earlier runs.

## Phase-specific content

The linter owns exact required headings. The lists below identify the phase-specific material to complete before adding the audited scaffold, `Traceability` and the two terminal gates.

### `00-requirements.md`

Use `recursive-init`, then complete:

- `TODO`
- `Requirements` with stable `R#` identifiers and observable acceptance criteria
- `Out of Scope` with stable `OOS#` identifiers
- `Constraints`
- `Coverage Gate`
- `Approval Gate`

Completion criterion: the human-approved scope is unambiguous enough that downstream phases can prove coverage without reconstructing intent.

### `00-worktree.md`

Use `recursive-worktree`, then complete:

- `TODO`
- `Directory Selection`
- `Safety Verification`
- `Worktree Creation`
- `Main Branch Protection`
- `Project Setup`
- `Test Baseline Verification`
- `Worktree Context`
- `Diff Basis For Later Audits`
- `Traceability`
- `Coverage Gate`
- `Approval Gate`

Completion criterion: the isolated worktree, clean baseline and normalized diff command are executable and verified before Phase 1 begins.

### `01-as-is.md`

Complete the shared audited scaffold plus:

- `TODO`
- `Reproduction Steps (Novice-Runnable)`
- `Current Behavior by Requirement`
- `Source Requirement Inventory`
- `Relevant Code Pointers`
- `Known Unknowns`
- `Evidence`
- `Prior Recursive Evidence Reviewed`

Completion criterion: every source obligation is inventoried, current behavior is evidenced and the unknowns are explicit enough to plan without guessing.

### `01.5-root-cause.md`

Use `recursive-debugging`. Complete the shared audited scaffold plus:

- `TODO`
- `Error Analysis`
- `Reproduction Verification`
- `Recent Changes Analysis`
- `Evidence Gathering (Multi-Layer if applicable)`
- `Data Flow Trace`
- `Pattern Analysis`
- `Hypothesis Testing`
- `Root Cause Summary`

Completion criterion: the observed failure is reproduced and the selected cause survives attempts to falsify it.

### `02-to-be-plan.md`

Use `recursive-spec` and the relevant design or delivery skills. Complete the shared audited scaffold plus:

- `TODO`
- `Planned Changes by File`
- `Requirement Mapping`
- `Implementation Steps`
- `Testing Strategy`
- `Playwright Plan (if applicable)`
- `Manual QA Scenarios`
- `Idempotence and Recovery`
- `Implementation Sub-phases`
- `Plan Drift Check`
- `Test Surface`
- `Prior Recursive Evidence Reviewed`

Completion criterion: every accepted requirement and source-inventory row has an implementation, verification and QA disposition, and the plan can be executed without inventing missing decisions.

### `03-implementation-summary.md`

Use `recursive-tdd`. Complete the shared audited scaffold plus:

- `TODO`
- `Changes Applied`
- `TDD Compliance Log`
- `Plan Deviations`
- `Implementation Evidence`

Completion criterion: every implemented requirement is tied to the real changed files and RED/GREEN/REFACTOR evidence, with every deviation reconciled against the approved plan or addenda.

### `03.5-code-review.md`

Use `recursive-review`. Complete:

- `TODO`
- the shared audited scaffold
- `Traceability`
- `Coverage Gate`
- `Approval Gate`

This artifact is a compact receipt and pointer surface. Review scope, findings and verdict live in the canonical ledger, not in duplicated artifact sections.

Completion criterion: the ledger has controller-verified whole-ledger PASS for the actual reviewed surface and the artifact points to the matching bundle, pass and hashes.

### `04-test-summary.md`

Use `recursive-closeout --phase 04`, then complete the shared audited scaffold plus:

- `TODO`
- `Pre-Test Implementation Audit`
- `Environment`
- `Execution Mode`
- `Commands Executed (Exact)`
- `Results Summary`
- `Evidence and Artifacts`
- `Failures and Diagnostics (if any)`
- `Flake/Rerun Notes`
- `Prior Recursive Evidence Reviewed`

Completion criterion: another operator can rerun every command and distinguish final passes, expected failures, diagnostics and reruns from prose summaries.

### `05-manual-qa.md`

Use `recursive-closeout --phase 05`, optionally with `--preview-log` or `--preview-url`. Complete:

- `TODO`
- `QA Execution Record`
- `QA Scenarios and Results`
- `Evidence and Artifacts`
- `User Sign-Off`
- `Traceability`
- `Coverage Gate`
- `Approval Gate`

Human and hybrid QA require real human sign-off. Agent-operated QA requires the actual executor, tools and evidence. Phase 5 has no review ledger or `Review Metadata`.

Completion criterion: every approved QA scenario has an observed result and the declared execution mode has the evidence or sign-off it requires.

### `06-decisions-update.md`

Use `recursive-closeout --phase 06`, then complete the shared audited scaffold plus:

- `TODO`
- `Decisions Changes Applied`
- `Rationale`
- `Resulting Decision Entry`

Completion criterion: `DECISIONS.md` contains the durable decision, while this receipt records only the exact delta and its owner.

### `07-state-update.md`

Use `recursive-closeout --phase 07`, then complete the shared audited scaffold plus:

- `TODO`
- `State Changes Applied`
- `Rationale`
- `Resulting State Summary`
- `Prior Recursive Evidence Reviewed`

Completion criterion: `STATE.md` reflects the current product and workflow facts without copying run history, while this receipt records the exact delta.

### `08-memory-impact.md`

Use `recursive-closeout --phase 08` and `recursive-training` when completed runs contain reusable experiential lessons. Complete the shared audited scaffold plus:

- `TODO`
- `Diff Basis`
- `Changed Paths Review`
- `Affected Memory Docs`
- `Run-Local Skill Usage Capture`
- `Skill Memory Promotion Review`
- `Uncovered Paths`
- `Router and Parent Refresh`
- `Final Status Summary`
- `Prior Recursive Evidence Reviewed`

Completion criterion: every final changed path is accounted for by memory ownership or an explicit uncovered-path outcome, affected memory is revalidated, and only generalized skill lessons are promoted.

## Addenda

Addenda preserve locked history. Store them under `/.recursive/run/<run-id>/addenda/`.

Use `<base>.addendum-<NN>.md` for a stage-local supplement and `<current-base>.upstream-gap.<prior-base>.addendum-<NN>.md` when the current phase discovers a gap in a locked earlier phase.

```md
Run: `/.recursive/run/<run-id>/`
Phase: `<current phase>`
Status: `DRAFT`
Inputs:
- `/<base-or-prior-artifact>`
Outputs:
- `/.recursive/run/<run-id>/addenda/<name>.md`
Scope note: <what this addendum supplements or compensates>

## TODO

- [ ] <checkable action>

## Gap or Addendum Content

- Discovery evidence: <concrete evidence>
- Impact: <affected requirements or downstream work>
- Compensation: <what the current phase will do>

## Traceability

- `R1` -> <effect of this addendum>

## Coverage Gate

Coverage: FAIL

## Approval Gate

Approval: FAIL
```

Lock current-phase addenda when their owning phase locks. List every relevant addendum in downstream `Inputs`, `Effective Inputs Re-read` and `Earlier Phase Reconciliation`.

## Durable memory metadata

`MEMORY.md` and `skills/SKILLS.md` are router/index files and do not use the per-shard metadata block. Every other durable memory shard except the glossary includes:

```md
Type: `domain|pattern|incident|episode|training`
Status: `CURRENT|SUSPECT|STALE|DEPRECATED|DRAFT`
Scope: <what this shard covers>
Owns-Paths:
- `path/or/glob/**`
Watch-Paths:
- `path/or/glob/**`
Source-Runs:
- `/.recursive/run/<run-id>/`
Validated-At-Commit: `<git-sha>`
Last-Validated: `<ISO8601 timestamp>`
Tags:
- `tag`
```

Optional fields are `Parent`, `Children`, `Supersedes` and `Superseded-By`. Empty ownership lists remain explicit when the shard owns no product path.

The glossary uses its own human-authoritative profile:

```md
Type: glossary
Authority: human
Status: CURRENT
Last-Approved: YYYY-MM-DD
```

`Source-Runs` and `Tags` are optional for the glossary. It never receives `Owns-Paths`, `Watch-Paths` or `Validated-At-Commit`; changes route through `recursive-domain-modeling` and explicit human approval.

## Evidence layout

Store non-artifact evidence under `/.recursive/run/<run-id>/evidence/`:

- `logs/` for command, server and CI output
- `screenshots/` for visual evidence
- `perf/` for measurements and profiles
- `traces/` for browser traces or HAR files
- `router/` for routed output, stdout, stderr and invocation metadata
- `review-bundles/<phase-key>/<review-id>/` for immutable review inputs
- `reviews/<phase-key>/<review-id>/` for the working ledger and immutable pass snapshots
- `other/` only when no specific category fits

Canonical subagent action records live in `/.recursive/run/<run-id>/subagents/`. Raw model transcripts and router captures are evidence, not action records.

## Validate and lock

Before locking:

```bash
python3 ./.recursive/scripts/lint-recursive-run.py --repo-root . --run-id "<run-id>" --strict
python3 ./.recursive/scripts/recursive-status.py --repo-root . --run-id "<run-id>"
python3 ./.recursive/scripts/recursive-lock.py --repo-root . --run-id "<run-id>" --artifact "<artifact>.md"
python3 ./.recursive/scripts/verify-locks.py --repo-root . --run-id "<run-id>"
```

On PowerShell-oriented systems, use the matching `.ps1` adapters under `./.recursive/scripts/`. A lock is valid only when the runtime accepts the structure, the canonical ledger has whole-ledger PASS for audited phases, Coverage and Approval pass, prior phases are semantically valid, and the lock receipt matches the normalized artifact.

## Pre-lock failure scan

- Effective inputs or addenda are missing from the header or reconciliation.
- An audited phase duplicates findings or a prose verdict outside the ledger.
- `Review Metadata` has missing, reordered or mismatched fields, paths, pass numbers or hashes.
- Requirement rows do not collectively account for the phase-owned diff.
- Coverage or Approval passes before whole-ledger PASS.
- A generated scaffold still contains placeholder text or unchecked TODOs.
- A delegated claim was accepted without controller verification against real files and artifacts.
- Phase 5 lacks the evidence or sign-off required by its execution mode.
- A prior locked artifact was edited instead of using a current-phase addendum.
- A memory shard is marked `CURRENT` without revalidation against affected final paths.
- The documented command was summarized instead of recorded exactly and rerun.
