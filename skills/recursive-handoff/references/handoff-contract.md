# Cross-session handoff contract

## Contents

- [Owner accounting](#owner-accounting)
- [Recursive-run handoff](#recursive-run-handoff)
- [Standalone handoff](#standalone-handoff)
- [Drift](#drift)
- [Security and cleanup](#security-and-cleanup)

## Owner accounting

Before a recursive-run handoff, inspect the actual run and classify every phase-relevant category as exactly `present and durably owned`, `not yet applicable`, or `missing owner`:

1. Effective `00-requirements.md`, including every relevant requirements addendum.
2. Effective `02-to-be-plan.md`, including its addenda, when it exists.
3. The current phase artifact and actual worktree state.
4. `04-test-summary.md` when it exists; before Phase 4, use test evidence owned by the current phase artifact.
5. `06-decisions-update.md` when it exists; before Phase 6, use the current phase artifact or addenda together with `/.recursive/DECISIONS.md`.
6. The canonical review ledger for the current audited phase when applicable.
7. Source delivery pointers in `00-requirements.md` when this is a slice run; verify the pointers without copying the delivery DAG.

Checking one convenient artifact is not sufficient. A category is `present and durably owned` only when its current information is recoverable from the named canonical owner without this handoff. A `missing owner` blocks generation and returns the gap to the owning phase or artifact. The handoff must never conceal that gap by carrying missing requirements, decisions, findings, progress or test evidence itself.

The recursive-run preflight is complete only when all seven categories are accounted for and the run is resumable without the handoff.

## Recursive-run handoff

This branch is a thin pointer to current operational state. It contains no substantive plan, findings, decision narrative or copied artifact content.

### Recursive-run template

```markdown
# Recursive run handoff

- Created: <UTC timestamp>
- Context: recursive-run
- Working Directory: <exact absolute path>
- Recursive Run: <run-id>
- Current Phase: <canonical phase name>
- Phase Status: <current status>
- Git Branch: <branch>
- Git HEAD: <full commit>
- Git State: clean | dirty
- Resume Command: `Implement requirement '<run-id>'`

## Resume procedure

1. Revalidate the working directory, Git HEAD and state, run status, and the canonical artifacts named by Recursive Mode.
2. When no drift exists, execute `Implement requirement '<run-id>'`.

## Cleanup

- After successful ingestion, delete this temporary handoff.
- Retain it only after an explicit user decision.
```

The resume procedure names only workspace revalidation and the canonical command. All substantive next work remains owned by the current phase and its artifacts.

## Standalone handoff

Standalone work may transfer a compact live thread because no Recursive run owns its resume state. Settled material still stays with an ordinary repository owner such as a specification, plan, ADR, `DECISIONS.md`, issue or commit. Where no owner is appropriate, an explicit human decision may leave the item in the document only as a marked claim awaiting confirmation. The handoff does not create a durable owner.

### Standalone template

```markdown
# Standalone cross-session handoff

- Created: <UTC timestamp>
- Context: standalone
- Working Directory: <exact absolute path>
- Git Branch: <branch>
- Git HEAD: <full commit>
- Git State: clean | dirty
- Next-session focus: <bounded objective>

## Resume objective

<One observable outcome for the next session.>

## Live thread

<What is in flight and why, in the conversation's own terms, limited to context that no durable artifact already owns. Mark unresolved claims.>

## Current workspace snapshot

<Changed paths and reproducible checks; do not copy the diff.>

## Next actions

1. <Bounded next action>

## Open decisions and blockers

- <Decision or blocker, its owner, and whether it is a claim.>

## References

- <path-or-public-URL> — <what this artifact owns and why it must be read>

## Suggested skills

- `<skill>` — <why the next objective needs it>

## Cleanup

- After successful ingestion, delete this temporary handoff.
- Retain it only after an explicit user decision.
```

Compress only the live thread. Reference specifications, plans, ADRs, commits, diffs, ledgers and maps instead of duplicating them. A reference explanation names only what the artifact owns. It must not summarize, select, or re-rank findings, restate conclusions, or substitute for reading the artifact.

Every local path must exist when the handoff is created or be explicitly marked as missing or expected. Every public URL must be verified as reachable without private credentials. Suggested skills are limited to the next objective and each includes one operational reason.

## Drift

The receiving session revalidates before acting.

- For recursive-run work, any changed HEAD, worktree, run status or canonical artifact makes the pointer stale. Delete the stale handoff and fall back to native recursive-mode auto-resume from the current repository state with `Implement requirement '<run-id>'`. Do not repair or reinterpret the drift from the handoff.
- For standalone work, drift means stop without executing the recorded next actions. Ask the user to regenerate the handoff or confirm a new objective against the current workspace.

## Security and cleanup

Write a unique local file in the operating system's temporary directory, outside the workspace. Do not copy `.env` content, credential stores, tokens, passwords, keys, private URLs or personally identifying data. Replace necessary mentions in the live thread with a marker such as `[REDACTED: token]`.

After writing, read the complete document and inspect it for secrets, stale metadata, duplicate truth and invalid references. The exact working directory is allowed because the artifact remains local on the same host. A future transport adapter owns any stronger redaction required before external transmission.

The receiving session deletes the file after successful ingestion and reference access. Retain it only after an explicit user decision. Loss of the temporary file must not prevent a Recursive run from resuming through its canonical artifacts.
