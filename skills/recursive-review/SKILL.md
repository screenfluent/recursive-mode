---
name: recursive-review
description: 'Run a lossless technical review ledger. Use to review or audit a diff, handle review findings through repair and re-audit, or when recursive-mode audited work needs controller-verified closure.'
---

# Recursive Review

A review is a **lossless ledger**, not advice for a human author. Every technical issue is a stable record; a repair agent may **claim** an outcome; only **controller verification** closes it.

Before writing or accepting review output, load [references/finding-protocol.md](references/finding-protocol.md). It owns the exact record, snapshot, disposition, and multipass contract.

## Choose context

- Every audited phase → `/.recursive/run/<run-id>/evidence/reviews/<phase-key>/<review-id>/ledger.md`; immutable passes live beside it under `passes/<NNNN>.md`, and each pass reviews its immutable per-pass bundle.
- Standalone review → `/.recursive/local/reviews/<review-id>/ledger.md`; immutable local passes use the same sibling path. The entire local review tree is Git-ignored.

Delegated and `self-audit` execution use the same ledger and exact `## Review Scope`, `## Findings`, `## Verdict` output. A self-audit starts or advances the canonical pass, preserves all prior `F-*` IDs, and gives terminal authority only to the controller verification step.

For standalone review, `scheduled` is unavailable. A deferred obligation needs a human-selected tracked pointer and owner; otherwise keep it open or fix it now.

Complete when one canonical ledger path is selected and named in the review scope.

## Review

1. Identify the exact artifact, diff basis, changed files, and evidence basis.
2. Create Pass `0001` or transition from the immediately preceding immutable pass as defined by the reference.
3. When the reviewed surface includes source code, tests, executable configuration, schemas or migrations, or runtime wiring, load [references/code-review-inspection.md](references/code-review-inspection.md). Reviews limited to requirements, plans, design artifacts, ledgers, or evidence do not load it.
4. Inspect the real repository, apply every loaded lens independently, and emit exactly `## Review Scope`, `## Findings`, and `## Verdict`.
5. Record each falsifiable issue under `## Findings` as a new append-only `F-*` record. Derive it from an owning contract, a currently supported surface, or an observable risk in the declared operating context. A hypothetical future environment does not create a finding.
6. Return FAIL while any finding is open.

Complete when the whole ledger accounts for the reviewed snapshot and contains no finding-bearing free prose.

## Repair

Give the repair agent the ledger path and bounded open `F-*` IDs. The agent records only:

- `Claimed outcome: none | fixed | blocked`
- concrete claimed changed paths
- reproducible claimed verification

A claim never changes `Disposition`. Human effort, duration, and perceived author workload are not repair inputs. Dependencies point from a blocked repair to the prerequisite finding; independent findings use `none`. Satisfy repair prerequisites first, then choose among ready findings by stable `F-*` order.

Complete when every assigned finding has a structured claim or concrete blocking evidence.

## Controller verification

For each claim, the controller inspects the actual diff, code or artifact, owning contract, and verification evidence. Independently run the named check or accept a trusted runner/CI log. Only the controller writes a terminal disposition.

Treat delegated success, commit messages, action records, and test reports as claims until checked against the repository. Verify every row; do not accept a summary in place of the ledger. Reject permanent system complexity, maintenance burden, or regression surface that has no contracted benefit.

Complete when each terminal disposition has row-specific controller evidence and every remaining finding is explicitly open.

## Re-audit

Any change to the reviewed diff, artifact, or evidence basis invalidates the reviewed snapshot. Start the next pass before repair, preserve all earlier IDs and immutable fields, reset claims only for open findings, refresh the bundle, re-review the whole ledger, and append repair-induced findings.

PASS requires the whole ledger to be terminal and every due scheduled handoff to be consumed. Open repair returns to the phase that owns the reviewed surface.

Complete when the latest immutable pass is controller-verified, the ledger matches it, and its Verdict is derived from the whole ledger.

## Composes

- `recursive-review-bundle` prepares the reproducible input package; it does not own findings or repair.
- `recursive-subagent` transports bounded review and repair claims; it does not accept them.
- `recursive-mode` owns audited-phase placement and phase-artifact pointers.

## Mechanical validation

Run from repository root:

```bash
python3 ./.recursive/scripts/recursive-review-ledger.py --repo-root . --ledger "/.recursive/local/reviews/<review-id>/ledger.md"
python3 ./.recursive/scripts/recursive-review-ledger.py --repo-root . --run-id "<run-id>" --phase-artifact "<audited-artifact>.md"
```

The shared validator owns schema, pass history and hashes, stable findings, legal states, dependency graphs, scheduled inventories, phase pointers, and whole-ledger PASS. Lint, status, lock, and lock verification consume that interface.
