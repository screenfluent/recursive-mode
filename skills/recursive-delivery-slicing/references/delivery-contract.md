# Delivery contract

## Contents

- [spec.md](#specmd)
- [manifest.md](#manifestmd)
- [Slice file](#slice-file)
- [Update and retention](#update-and-retention)

Use one delivery tree after the human approves both multi-run routing and the proposed split:

```text
/.recursive/deliveries/<delivery-id>/
├── spec.md
├── manifest.md
└── slices/<NN>-<slug>.md
```

`<delivery-id>` and `<slug>` are kebab-case. `<NN>` is a two-digit dependency-aware sequence number. The tree is a delivery index, not a Recursive phase, a copy of its runs or a work queue.

## spec.md

`spec.md` is the approved delivery-level requirements source produced by `recursive-spec`. It keeps the user outcome, requirements and acceptance criteria, testing decisions, pre-agreed seams, constraints and explicit out of scope boundary. Keep volatile file paths and code snippets out. A delivery spec creates no umbrella run.

Use `## Requirements`, `## Testing Decisions`, `## Out of Scope` and `## Constraints`. Each requirement retains observable acceptance criteria; Testing Decisions names the pre-agreed seams.

For an active delivery, append each approved requirement or scope change under `## Amendments`. Each dated amendment names its evidence, affected requirements or scope, replacement wording and human approval record. Preserve the prior approved text. The effective delivery specification is the base text plus its amendments in recorded order.

## manifest.md

Use this exact shape:

```markdown
# <Delivery name>
Status: ACTIVE | COMPLETED
Spec: [<spec title>](spec.md)
Human approval: <approval record>

## Slices
- [<NN — title>](slices/<NN>-<slug>.md) | Status: planned | active | completed | Blocked by: none | <NN>, ... | Run: none | `/.recursive/run/<run-id>/`
```

The DAG consists only of real blocking edges: keep an edge only when its blocker's outcome must exist before the dependent slice can begin. The frontier is derived, never cached: every `planned` slice whose blockers are all `completed`. The derived views are disjoint: `active` and `completed` retain their manifest statuses, frontier contains ready `planned` slices, and blocked contains `planned` slices with at least one incomplete blocker. Human approval covers the split and every edge.

Changing a planned slice or any edge after approval requires renewed human approval before the manifest changes. Active and completed slice records are immutable; repair their owning run or create a newly approved follow-up slice instead of rewriting delivery history.

Remove a planned slice only with renewed human approval and only when every affected requirement remains covered by another planned or completed slice. A claim that the requirement was already delivered requires a verified completed run. When the accepted requirement and scope remain unchanged, update the remaining Spec coverage and blocking edges without amending `spec.md`.

When a requirement or scope changes, obtain an approved amendment through `recursive-spec`: amend the delivery spec first, then revalidate the DAG and present the resulting planned-slice and edge changes for renewed human approval. The slicer does not amend requirements itself.

Before approval, account for every delivery requirement in at least one slice's Spec coverage and reject slice outcomes that have no accepted requirement. Coverage may span slices, but no requirement or scope addition may disappear between the spec and the DAG.

Set one slice `active` only after its run exists. Set it `completed` only after the skill revalidates that run. A completed slice keeps its run pointer and cannot return to `planned` or `active`. `Status: COMPLETED` is terminal and cannot be reactivated.

Materializing a slice adds its exact source delivery and source slice paths to the run's `00-requirements.md` under `## Constraints`. The manifest's `Run` pointer, those two source pointers and the selected slice must agree before an Update can accept the run.

## Slice file

Use this shape:

```markdown
# <NN> — <Slice title>
Kind: tracer-bullet | prefactor | expand | migrate | contract | integration
Blocked by: none | <NN>, ...

## Outcome

<One end-to-end user-visible or independently verifiable outcome.>

## Acceptance criteria

- <Observable criterion>

## Spec coverage

<Pointers to the delivery requirements covered; do not copy the spec.>
```

A normal slice is a complete, demonstrable tracer bullet sized for one fresh agent context. It cuts a narrow but complete path through every layer needed for its outcome—schema, API, UI, and tests where those layers exist—rather than completing one horizontal layer.

Keep volatile implementation paths and code snippets out of slice files. When a prototype produced a decision-rich snippet that is more precise than prose, include only that trimmed decision and identify it as prototype evidence.

Here, one fresh agent context means a fresh agent can understand and materialize the slice from durable artifacts. It does not require its run to finish in one chat session. Once materialized, the run may resume across sessions and use the implementation sub-phases owned by `/.recursive/RECURSIVE.md` while remaining the slice's one acceptance and closeout unit.

A prefactor precedes the behavior it unlocks and has an independently verifiable enabling outcome. Do not use prefactoring as a container for general cleanup.

For a wide mechanical refactor whose blast radius cannot land as a green tracer bullet, use expand, bounded migrate batches, then contract. Expand adds the new form beside the old so behavior remains green; each migrate batch is blocked by expand; contract deletes the old form after every batch and is blocked by all of them. Use an integration exception only when no batch can remain green independently: keep the sequence and add a final integration slice where green is verified.

## Update and retention

Before recording completion, run:

```sh
python3 .recursive/scripts/verify-locks.py --repo-root . --run-id "<run-id>"
python3 .recursive/scripts/recursive-status.py --repo-root . --run-id "<run-id>"
```

On Windows use the available Python 3 launcher:

```powershell
python ".recursive/scripts/verify-locks.py" --repo-root . --run-id "<run-id>"
python ".recursive/scripts/recursive-status.py" --repo-root . --run-id "<run-id>"
```

Require lock verification to pass plus exact `Current Phase: COMPLETE` and `Status: LOCKED` status output. Then add the pointer to the completed run and mark its owning slice completed.

After the completion checks pass and before reporting or materializing the next frontier, progressively revalidate the delivery. Read the completed run's delivered outcome and decisions in `00-requirements.md`, `03-implementation-summary.md`, `06-decisions-update.md`, and `07-state-update.md`; the current repository state; the delivery spec; and every planned slice and edge. The result is exactly one of:

- `still valid` — the remaining outcomes and blockers agree with that evidence; recompute the frontier and report it;
- an evidence-backed change proposal — identify the contradicted outcome, coverage, or edge and wait for the required human approval before changing the manifest or materializing another slice.

Complete revalidation only when every planned slice and edge is accounted for as `still valid` or included in the change proposal. A failed run check leaves the manifest unchanged; unresolved revalidation leaves the next materialization blocked.

On delivery completion retain only the approved spec, final manifest, short slice summaries and run pointers: no logs and no copies of runs. This frozen index serves the slicer's later historical query, such as what happened to a named delivery, while preventing accidental reactivation.

Apply the repository retention policy. Retain the completed tree when the product repository retains workflow instances. A reusable skill or workflow repository does not commit delivery instances, just as it does not commit current-session run artifacts.
