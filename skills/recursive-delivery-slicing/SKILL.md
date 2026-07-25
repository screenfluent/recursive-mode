---
name: recursive-delivery-slicing
description: "Shape delivery DAGs across Recursive runs. Use to split an approved multi-run specification, continue a delivery from its current frontier, or account for a completed slice run."
---

# Recursive Delivery Slicing

Turn one approved multi-run specification into complete tracer-bullet slices, then keep their cross-run dependency graph honest. Load [references/delivery-contract.md](references/delivery-contract.md) before reading or writing a delivery.

## Choose one branch

- **Shape** — draft slices and real blocking edges from an approved multi-run specification. Keep the draft outside the repository until the human approves both granularity and edges; then create the delivery tree.
- **Resume** — agent locates the named delivery, reads its manifest and reports its derived frontier. Resolve ambiguity conversationally; the human need not supply ids or paths.
- **Update** — agent locates a completed slice run, verifies its current state, records completion and recomputes the frontier.

State the branch and delivery. Complete this step when both are unambiguous. Shape requires an approved multi-run spec draft; route missing or unsettled requirements to `recursive-spec` before proposing slices.

## Shape the DAG

Read the approved delivery-spec draft, governing repository instructions, domain language, relevant code and existing test seams. Prefer complete, demonstrable tracer bullets that fit one fresh agent context. Look for prefactoring—make the change easy, then make the easy change—but use a prefactor or the wide-refactor sequence only when the reference's evidence test applies.

Present a numbered proposal with each slice's outcome and blockers. Ask the human whether the granularity feels right, every blocker genuinely gates its dependent slice, and any slices should merge or split. Require approval of the split and every edge; conversational answers such as `yes`, `continue`, and `stop` are sufficient. Create no delivery artifact from an unapproved proposal.

Complete when the approved files match the proposal and every slice is either on the frontier or blocked by an incomplete prerequisite, with every delivery requirement covered by at least one slice.

## Resume a delivery

Locate `/.recursive/deliveries/*/manifest.md` from the user's natural delivery name; ask only when more than one tree matches. For `ACTIVE`, derive and report completed, active, blocked and frontier slices. For `COMPLETED`, answer the historical query from the frozen index without changing it.

Complete Resume when the user has the current state, derived frontier and the next decision in conversational terms rather than ids or paths.

## Update verified completion

Treat a run pointer as a claim. From repository root, run the reference's read-only installed-runtime completion checks.

Require the first command to pass and the second to report both `Current Phase: COMPLETE` and `Status: LOCKED`. Then mark only its owning slice completed and add the pointer to the completed run. A failed check leaves the manifest unchanged.

Require the run's `00-requirements.md` to cite this exact source delivery and source slice before accepting it as the owner. When every slice is verified, set terminal `Status: COMPLETED`. A completed delivery cannot be reactivated; Resume may answer historical queries from its frozen index.

After completion validation, apply the reference's progressive revalidation before reporting or materializing the next frontier. Complete Update only when the manifest records the verified run and revalidation returns `still valid`, or the human-approved changes are recorded and the frontier is derived from the resulting current slice states.

## Hand off one ready slice

Give one approved ready slice to `recursive-spec`. It materializes the slice as `/.recursive/run/<run-id>/00-requirements.md` without re-interviewing. There is one Recursive run per ready slice and no umbrella run.

After the run exists, record its pointer and set that slice `active` before the handoff completes.

Complete handoff when the run requirements cite the source delivery and slice, the manifest records the selected slice as active, and this handoff started no second run.

This skill owns the cross-run DAG and never dispatches a run. It stops after reporting the frontier; the user's later `continue` starts the next handoff. Wayfinder retains discovery, each Recursive run retains implementation, and external request triage retains tracker policy.
