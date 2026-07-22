# plans-canonical bridge

The single canonical workflow specification lives in `/.recursive/RECURSIVE.md`.

This file remains a compatibility locator plus a compact mirror of the hard requirements so older references still point at the current behavior. It does not own a second workflow profile or duplicate the exact artifact, review-ledger, bundle, or action-record formats. When this summary and the installed canonical workflow differ, follow `/.recursive/RECURSIVE.md` and the installed runtime.

## Current workflow contract

Recursive Mode has one current contract. Git history preserves superseded contracts; runtime tools do not carry compatibility branches for them. Introduce versioning, migration scaffolding, aliases, shims, or dual paths only after an explicit human decision, evidence of a live consumer of the superseded contract, and evidence that the consumer cannot be migrated atomically. Ordinary refactors that introduce no protective mechanism do not trigger this compatibility gate.

## Workflow mirror

The current workflow requires:

- repo documents are the source of truth; prompts issue commands and point at paths rather than carrying substantive requirements
- phases advance one way; repair a locked earlier-phase gap through a current-phase addendum instead of rewriting locked history
- exactly one phase is active at a time; delegated work does not permit parallel phase advancement
- read-only audit or review and independent test execution stay inside the active phase; write-capable delegation is limited to explicitly independent sub-phases with disjoint write scopes
- missing `/.recursive/` scaffolding and bridge docs are bootstrapped automatically when a supported runtime is available
- every phase ends with Coverage and Approval gates
- audited phases are Phase 1, Phase 1.5 when present, Phase 2, Phase 3, Phase 3.5 when present, Phase 4, Phase 6, Phase 7, and Phase 8
- Phase 5 is QA-only, is not an audited ledger phase, and never receives `## Review Metadata`
- audited phases use `draft -> audit -> repair -> re-audit -> whole-ledger PASS -> Coverage -> Approval -> lock`
- meaningful delegated work leaves a durable action record under `/.recursive/run/<run-id>/subagents/`, and the controller verifies its claims against actual files, artifacts, bundles, and evidence before acceptance
- reusable skill or workflow repositories keep shipped history clean; current-session run artifacts, evidence, temp output, and generated residue are not durable product content unless they are intentional fixtures

## Canonical review mirror

Every audited artifact points to one canonical current review ledger, its latest immutable verified snapshot, and the same-pass immutable input bundle. `recursive-review` and the installed review runtime own the exact metadata, reviewer-output, finding, claim, disposition, history, and hash schemas; this bridge does not restate them.

Every technical issue remains an append-only stable `F-*` record. Repair agents make claims; only the controller assigns terminal dispositions after checking the actual diff, artifacts, owning contract, and named verification.

PASS is derived from the whole canonical ledger: every finding has a controller-verified terminal disposition, no finding remains open, and no scheduled handoff is due and unconsumed. There is no secondary advice list, severity gate, model vote, or prose verdict that overrides ledger state.

`scheduled` is available only inside an active run for work already owned by a strictly later canonical phase. The full obligation is copied into `/.recursive/run/<run-id>/evidence/reviews/scheduled/<owner-phase-key>/inventory.md`, and final verification rejects any due record that remains unconsumed. Standalone review cannot schedule work.

Use the installed `recursive-review`, `recursive-review-bundle`, and `recursive-subagent` skills plus the installed runtime generators for the exact ledger, bundle, finding, and action-record formats. Do not copy those formats into this bridge.

## Delegation mirror

Every audited phase records the concrete capability check, whether subagents were available, whether execution used delegation or self-audit, the decision basis, any required override reason, and the exact inputs supplied.

If subagents are available and a complete context bundle can be assembled, delegated audit or review is the default. If they are unavailable, the controller performs the same audit itself. If the bundle is incomplete, do not delegate.

A canonical review bundle includes the audited artifact and hash, upstream artifacts, relevant addenda, prior recursive evidence, control-plane documents when needed, the normalized diff basis from `00-worktree.md`, changed files, targeted code references, evidence references, phase-specific questions, and the required output shape. Bundle generation auto-discovers relevant addenda by default, and review output cites the bundle plus the bundle-grounded upstream artifacts, addenda, prior evidence, changed files, and code references it actually used.

After delegated work, the controller records the action records reviewed, the verification performed, the acceptance decision, refresh handling, and any repair performed after verification. Changed artifacts or diff bytes invalidate stale delegated context and require the next working pass and refreshed bundle.

## Artifact and reconciliation mirror

Every audited artifact preserves these author-evidence sections:

- `## Audit Context`
- `## Effective Inputs Re-read`
- `## Earlier Phase Reconciliation`
- `## Subagent Contribution Verification`
- `## Worktree Diff Audit`
- `## Requirement Completion Status`

Each audited artifact separately carries the controller-derived review pointers required by `recursive-review`; their exact metadata schema remains owned by the installed review contract and runtime.

Phase 1, Phase 2, Phase 4, Phase 7, and Phase 8 also include `## Prior Recursive Evidence Reviewed`.

Every phase artifact begins with its run, phase, status, inputs, outputs, and scope note. A locked artifact also records `LockedAt` and `LockHash`. The exact per-phase headings and completion criteria live in `skills/recursive-mode/references/artifact-template.md` and the installed canonical workflow.

Audited phases reconcile against:

- `00-requirements.md`
- `00-worktree.md`
- the immediately previous locked phase artifact
- relevant addenda and sub-phase artifacts
- phase-specific earlier artifacts
- relevant prior recursive runs and durable memory
- the actual changed-file surface and normalized diff basis owned by the current phase

`00-worktree.md` owns the executable baseline. Later audits reuse its baseline type, human-facing reference, comparison reference, normalized baseline, normalized comparison, and normalized diff command rather than guessing a new basis.

Prior recursive evidence cites real run or memory paths. When none is relevant, the artifact says so with a concrete justification. Diff audit ignores incidental runtime byproducts such as `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.mypy_cache/`, and `.ruff_cache/` unless the repository intentionally tracks them.

No audited phase may reach whole-ledger PASS, Coverage, Approval, or lock while upstream reconciliation is incomplete, an in-scope gap remains, or unexplained diff drift remains.

Phase-scoped diff ownership is forward-only:

- Phase 2 owns planning completeness and the expected product/worktree change surface
- Phase 3, Phase 3.5, and Phase 4 own the actual product/worktree diff
- Phase 6 owns `/.recursive/DECISIONS.md` plus reviewed final product/worktree paths
- Phase 7 owns `/.recursive/STATE.md` plus reviewed final product/worktree paths
- Phase 8 owns `/.recursive/memory/**` plus reviewed final product/worktree paths

Later control-plane or memory churn does not retroactively invalidate an earlier locked planning artifact. A material earlier omission is compensated through the owning downstream artifact or an upstream-gap addendum.

## Requirement and test-surface mirror

Phase 0 defines stable `R#` and `OOS#` identifiers with observable acceptance criteria. Every downstream artifact maps each in-scope `R#` to its implementation, validation, or explicit approved disposition. Traceability alone is not completion proof.

`## Requirement Completion Status` uses machine-checkable entries. Implementation dispositions cite changed files and concrete evidence; `verified` also cites distinct verification evidence. Deferred, out-of-scope, blocked, and superseded work requires the corresponding approved rationale or blocking evidence. Final closeout artifacts leave no in-scope requirement merely `implemented` or `blocked`.

Phase 1 includes `## Source Requirement Inventory`. Phase 2 includes `## Requirement Mapping`, `## Plan Drift Check`, planning dispositions for every requirement or source-inventory item, and compact `## Test Surface` records. Phase 3 references every effective `TS-*` record so test seams and structural traceability remain machine-checkable.

## Phase-specific mirror

- Phase 1 describes current behavior, relevant code, repro evidence, known unknowns, and the source requirement inventory.
- Phase 1.5, when present, establishes root cause before implementation continues.
- Phase 2 produces an executable plan with concrete file, command, test, QA, recovery, requirement-mapping, plan-drift, and test-surface decisions.
- Phase 3 audits implementation against requirements, the locked plan, the actual diff, test evidence, and its declared `TDD Mode: strict|pragmatic`; strict mode cites RED and GREEN evidence, while pragmatic mode records the exception rationale and compensating validation.
- Phase 3.5, when present, reviews requirements, plan, diff scope, maintainability, tests, TDD compliance, and the canonical review bundle.
- Phase 4 performs the pre-test implementation audit and returns unfinished in-scope work to Phase 3 repair.
- Phase 5 declares `QA Execution Mode: human|agent-operated|hybrid`; human and hybrid QA require explicit user sign-off, while agent-operated QA requires tools, execution metadata, observed results, and evidence paths.
- Phase 6, Phase 7, and Phase 8 write concise delta receipts and reconcile `DECISIONS.md`, `STATE.md`, and durable memory respectively against the final validated repository state.
- Phase 8 records run-local skill usage before deciding whether any observation deserves promotion into durable skill memory.

## Capability extension mirror

When a run needs a specialized capability that is not already available, use `find-skills` when installed; otherwise use the Skills CLI (`npx skills find`, `npx skills add`, `npx skills check`, and `npx skills update`). If no suitable skill exists, proceed with built-in capability and record that result. When discovery materially affects the run, capture it in Phase 8 and promote only durable conclusions into skill memory.

## Gates, locks, and tooling mirror

For every artifact, Coverage proves that all relevant inputs and requirement IDs are accounted for, and Approval proves that the output is objectively ready to proceed. For audited phases, neither gate may pass until the canonical review ledger has whole-ledger PASS.

Use `/.recursive/scripts/recursive-lock.py` or `/.recursive/scripts/recursive-lock.ps1` as the supported locking path. The lock command validates the artifact, writes `Status: LOCKED` and `LockedAt`, computes the normalized SHA-256 `LockHash`, and refuses invalid prerequisites or gates.

Before calling a reusable skill or workflow repository handoff-ready, run the packaged `check-reusable-repo-hygiene` helper with `--require-clean-git` (or `-RequireCleanGit` through its PowerShell wrapper).

Use the installed lint, status, review-ledger, closeout, and lock tools as executable owners of the current contract. A bridge sentence, example, delegated PASS, commit message, or test report cannot override their validated state.

## Canonical locations

- Canonical workflow: `/.recursive/RECURSIVE.md`
- Primary Codex AGENTS bridge: `/.codex/AGENTS.md`
- Primary Codex PLANS bridge: `/.agent/PLANS.md`
- Canonical run root: `/.recursive/run/<run-id>/`
- Review ledgers: `/.recursive/run/<run-id>/evidence/reviews/`
- Review bundles: `/.recursive/run/<run-id>/evidence/review-bundles/`
- Durable memory root: `/.recursive/memory/`
- Skill-memory router: `/.recursive/memory/skills/SKILLS.md`
