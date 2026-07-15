# Phase 1.5 root-cause artifact

Use this complete draft template for `/.recursive/run/<run-id>/01.5-root-cause.md`. It combines the phase-specific diagnosis surface with the shared audited-phase scaffold required by the current Recursive Mode linter; replace every placeholder and keep failed gates until their checks actually pass.

## Contents

- Run and review metadata
- Diagnostic evidence
- Hypotheses and root cause
- Gates and locking

```markdown
Run: `/.recursive/run/<run-id>/`
Phase: `01.5 Root Cause Analysis`
Status: `DRAFT`
Inputs:
- `/.recursive/run/<run-id>/00-requirements.md`
- `/.recursive/run/<run-id>/00-worktree.md`
- `/.recursive/run/<run-id>/01-as-is.md`
- <relevant addenda>
Outputs:
- `/.recursive/run/<run-id>/01.5-root-cause.md`
Scope note: Root-cause evidence only; production fixes remain in Phase 3.

## TODO

- [ ] Replace every placeholder with observed evidence.

## Audit Context

Audit Execution Mode: self-audit / subagent
Subagent Availability: available / unavailable
Subagent Capability Probe: <what proved availability or unavailability>
Delegation Decision Basis: <why self-audit or delegation was chosen>
Delegation Override Reason: none / <required when subagents are available but self-audit is selected>
Audit Inputs Provided:
- `/.recursive/run/<run-id>/00-requirements.md`
- `/.recursive/run/<run-id>/00-worktree.md`
- `/.recursive/run/<run-id>/01-as-is.md`
- Diff basis: `<normalized diff command from 00-worktree.md>`
- Changed files: <none yet or exact paths>
- Targeted code references: `<path:line-or-symbol>`

## Effective Inputs Re-read

- `/.recursive/run/<run-id>/00-requirements.md`
- `/.recursive/run/<run-id>/00-worktree.md`
- `/.recursive/run/<run-id>/01-as-is.md`
- <relevant addenda or none>

## Earlier Phase Reconciliation

- `00-requirements.md`: <requirement and acceptance criteria carried forward>
- `00-worktree.md`: <normalized diff basis carried forward>
- `01-as-is.md`: <reported symptom, current behavior, and evidence reconciled>
- Addenda: <effect on the diagnosis or none>

## Review Metadata

- Review ID: <review-id>
- Review Ledger Path: `/.recursive/run/<run-id>/evidence/reviews/phase-1-5/<review-id>/ledger.md`
- Latest Verified Pass: `/.recursive/run/<run-id>/evidence/reviews/phase-1-5/<review-id>/passes/<NNNN>.md`
- Latest Verified Pass Hash: <sha256>
- Review Bundle Path: `/.recursive/run/<run-id>/evidence/review-bundles/phase-1-5/<review-id>/<NNNN>.md`
- Review Bundle Hash: <sha256>

## Error Analysis

- Reported symptom: <exact user-observed behavior>
- Errors and warnings: <verbatim output>
- Complete stack trace: <trace or none>
- Locations: `<path:line-or-symbol>`

## Feedback Loop

- Command: `<already-run command>`
- Red output: <captured exact symptom>
- Duration: <seconds>
- Reproduction rate: <runs/failures>
- Red-capable: yes / no
- Agent-runnable: yes / no

## Reproduction Verification

- Original scenario: <steps and observed result>
- Repeated result: <runs/failures>
- Minimal scenario: <only load-bearing inputs, callers, config, data, and steps>

## Recent Changes Analysis

- Relevant diff or commits: <evidence>
- Dependencies: <relevant changes or none>
- Configuration and environment: <relevant changes or none>
- Causal status: unproven / supported / excluded

## Evidence Gathering (Multi-Layer if applicable)

| Boundary | Input | Output | Configuration or state | Verdict |
| --- | --- | --- | --- | --- |
| <component A -> B> | <observed> | <observed> | <observed> | working / broken |

## Data Flow Trace

- Failure location: `<path:line-or-symbol>`
- Bad value or state: <observed>
- Backward trace: <caller-by-caller evidence>
- Evidenced source: `<path:line-or-symbol>` / unresolved

## Pattern Analysis

- Working comparison: `<path:line-or-symbol>` / none
- Broken comparison: `<path:line-or-symbol>`
- Material differences: <complete relevant list>
- Dependency assumptions: <config, state, environment, or collaborators>

## Hypothesis Testing

| Rank | Hypothesis | Falsifiable prediction | Probe | Status | Evidence |
| --- | --- | --- | --- | --- | --- |
| 1 | <cause> | <predicted change> | <one variable> | queued / active / rejected / confirmed | <result> |
| 2 | <cause> | <predicted change> | <one variable> | queued / active / rejected / confirmed | <result> |
| 3 | <cause> | <predicted change> | <one variable> | queued / active / rejected / confirmed | <result> |

Add ranks 4–5 only when they remain distinct and falsifiable.

- User checkpoint: <response, re-ranking, or AFK continuation>
- Exhaustion action: none / regenerated / loop tightened

## Root Cause Summary

- Confirmed cause: <one sentence>
- Location: `<path:line-or-symbol>`
- Causal chain: <why it produces the exact symptom>
- Phase 2 fix strategy: <bounded approach>
- Regression-test seam: `<seam>` / no correct seam — architectural finding `<pointer>`
- Post-fix verification: `<original loop>` plus `<regression test>`
- Diagnostic cleanup: <tag search proving removal and throwaway-harness accounting>
- Commit-message handoff: <confirmed cause and why the fix exists>
- Post-fix prevention handoff: <question to ask after the fix and possible `recursive-codebase-design` route>

## Subagent Contribution Verification

- Reviewed Action Records: `none` / `/.recursive/run/<run-id>/subagents/<record>.md`
- Main-Agent Verification Performed: `<code, evidence, artifact, or diff-owned paths checked by the controller>`
- Acceptance Decision: `accepted|partially accepted|rejected` / `not applicable — no delegated contribution`
- Refresh Handling: <whether the action record was refreshed after repairs or why no refresh was needed>
- Repair Performed After Verification: `none` / <concrete repair paths or artifact updates performed after verification>

## Worktree Diff Audit

- Baseline type: local commit / local branch / remote ref / merge-base derived
- Baseline reference: `<human-facing source ref from 00-worktree.md>`
- Comparison reference: working-tree / HEAD / `<branch-or-ref>`
- Normalized baseline: `<commit-sha>`
- Normalized comparison: working-tree / `<commit-sha>`
- Normalized diff command: `git diff --name-only <normalized-basis>`
- Planned or claimed changed files: none yet / `<path>`
- Actual changed files reviewed: none yet / `<path>`
- Unexplained drift: none / <explanation>

## Gaps Found

- none / <unresolved in-scope gaps, missing evidence, or drift>

## Repair Work Performed

- none / <repairs made before re-audit>

## Requirement Completion Status

- `R1 | Status: blocked | Rationale: Root cause is confirmed, but production behavior remains unchanged until Phase 2 owns the fix plan and Phase 3 owns regression RED plus implementation. | Blocking Evidence: /.recursive/run/<run-id>/01.5-root-cause.md`

## Audit Verdict

- Summary: <why the audit remains failed or can pass>
Audit: FAIL

## Traceability

- R1 -> <root cause and fix strategy> | Evidence: <section>

## Coverage Gate

- [ ] One already-run red-capable command captures the exact symptom
- [ ] Errors, stack trace, recent changes, data flow, and relevant pattern differences are accounted for
- [ ] Minimal repro retains only load-bearing elements
- [ ] 3–5 hypotheses carry falsifiable predictions
- [ ] One-variable probes account for the ranking
- [ ] Root cause and regression seam are evidenced

Coverage: FAIL

## Approval Gate

- [ ] Root cause is confirmed rather than guessed
- [ ] Phase 2 has a bounded fix strategy
- [ ] Regression test and post-fix loop are concrete
- [ ] Temporary diagnostics are removed and throwaway harnesses are accounted for

Approval: FAIL

LockedAt: <timestamp>
LockHash: <sha256>
```
