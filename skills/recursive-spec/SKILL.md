---
name: recursive-spec
description: 'Approval-gated, repo-aware requirements authoring. Use when the user says "create a plan", "help me plan", "create a spec", "write requirements", "spec this out", or "scope this" for a new Recursive run; when settled context should become a spec without another interview; when an approved delivery slice is ready to materialize; or when an active delivery specification needs an amendment between slice runs.'
---

# recursive-spec

Own requirements before a run starts or between delivery slice runs. Produce a repo-aware `00-requirements.md` for an ordinary run or an approved delivery-level `spec.md` for cross-run work.

Do not replace `/.recursive/RECURSIVE.md`, skip ahead to Phase 2 planning, or start Phase 3 implementation.

## Check the installed branch

Interview and Synthesize can draft requirements with this skill alone. Writing an ordinary run also requires the `recursive-mode` runtime. Materialize and Amend require both `recursive-mode` and `recursive-delivery-slicing`; delegated routed help additionally requires `recursive-router` and `recursive-subagent`.

If the selected branch's dependency is unavailable, stop and name the missing skill. Do not claim the integrated branch from a standalone `recursive-spec` installation.

## Choose the authoring branch

Choose one branch from the available evidence:

- **Interview** — when intent or requirements remain unsettled, confirm the user wants spec help, ask one focused question at a time, and co-author the draft.
- **Synthesize** — when the conversation or an approved Wayfinder promotion is settled context, synthesize what is already known without re-interviewing the user or asking them to restate the goal. Confirm the resulting requirements and testing seams.
- **Materialize** — turn one approved ready slice from `recursive-delivery-slicing` into `/.recursive/run/<run-id>/00-requirements.md` without re-interviewing or reopening the approved delivery DAG. Read the current manifest and require every blocker to be completed before creating the run; a stale readiness claim is not sufficient.
- **Amend** — amend an active delivery specification between slice runs when current evidence requires a requirement or scope change. Draft only the delta, preserve the prior approved text, append the approved amendment to `spec.md`, and return to `recursive-delivery-slicing` before its DAG is revalidated. Do not change slices or edges from this branch.

Do not write an artifact before the user confirms the branch's draft. Before executing Materialize or Amend, load the slicer's [delivery contract](../recursive-delivery-slicing/references/delivery-contract.md).

## Keep drafts outside the repository

Until the user explicitly approves the spec, keep the draft in temporary session storage outside the worktree. Do not create `/.recursive/run/<run-id>/`, write `00-requirements.md`, or modify an active delivery `spec.md`.

If the user rejects the draft, revise or discard it. Do not leave behind a half-approved run folder or delivery amendment.

Complete this guardrail when no repository artifact exists before approval.

## Read the owning context

Before drafting requirements, read:

1. `/.recursive/STATE.md`
2. `/.recursive/DECISIONS.md`
3. `/.recursive/memory/MEMORY.md`
4. `/.recursive/memory/GLOSSARY.md` when it exists; use approved domain terms rather than inventing conflicting names
5. relevant ADRs for the requested area
6. relevant memory shards only when they matter
7. the most relevant code and tests for the requested area

For Amend, also read the active delivery spec and manifest, the completed run's delivery-relevant outcome and decisions, and the current repository state.

Be repo-aware, not a blind questionnaire. Use the control-plane documents to understand current truth and the codebase to understand actual surfaces, coupled modules, existing tests, and likely boundaries. For the Interview branch, load [authoring patterns](references/patterns.md) when examples or the exact `00-requirements.md` shape would help.

If the attempt reveals a foggy multi-session effort whose route is not visible, stop spec authoring and ask whether to invoke `recursive-wayfinder`. Do not create a map automatically. When the human returns with an approved promotion record, read it and its linked discovery units as authoring inputs; re-derive and approve the requirements here rather than treating the map as requirements.

If a requirements draft needs a new or changed domain term, propose wording and route the mutation through `recursive-domain-modeling` after human approval. Do not edit `GLOSSARY.md` from this skill.

Complete when every required source has been read and every evidence gap is named.

## Choose one run or a delivery

Default to one Recursive run. Keep one coherent acceptance and closeout unit in that run, using the implementation sub-phases owned by `/.recursive/RECURSIVE.md` when execution spans sessions or contexts. Session or context capacity alone is not evidence for delivery.

When the draft instead supplies concrete evidence of independently deliverable and separately closeable outcomes with real cross-run dependencies, present that evidence and ask whether to create a delivery plane. Never classify the work as multi-run on the user's behalf. Only explicit approval routes the approved draft to `recursive-delivery-slicing`; a refusal keeps the single-run path.

Complete when the human has approved one-run or delivery topology and every claimed dependency is real.

## Author the requirements

For Interview, ask one focused question at a time only when repo evidence or the conversation does not already answer it. For Synthesize, write from the settled context instead of reopening the interview.

Invoke `recursive-grilling` only when an unresolved human decision blocks a sound requirements draft and repository facts cannot settle it. Keep requirements ownership here: return every confirmed answer to the active draft, then continue authoring. Grilling is not an unconditional stage.

Shape the draft around:

1. goal and user outcome
2. task type: feature, bugfix, refactor, migration, or investigation
3. affected subsystem
4. in-scope requirements (`R#`)
5. observable acceptance criteria for every requirement
6. edge cases, failure paths, and exclusions
7. constraints, settled decisions, and boundaries
8. unknowns that must be resolved before Phase 0 locks

Prefer proposed wording that the user can confirm or correct over asking them to author the document from scratch.

Apply these rules:

- start with user intent and desired outcome
- separate settled decisions from open questions
- define deterministic, observable acceptance criteria
- include exceptions and failure paths, not only the happy path
- make boundaries concrete enough for later AS-IS analysis and planning
- keep out-of-scope items explicit
- record settled testing decisions and pre-agreed seams; prefer few existing seams while preserving fast tests and useful fault locality, choose the highest stable and diagnostic seam, and obtain human confirmation for every new or changed seam
- keep volatile file paths and code snippets out of requirements; if a prototype produced a snippet that encodes an approved decision more precisely than prose can, inline only its decision-rich parts
- before placing versioning, migration scaffolding, aliases, shims, dual paths, or another protected transition into a draft, apply the canonical Compatibility gate in `/.recursive/RECURSIVE.md`; require atomic replacement or cite an accepted transition decision, and route an unresolved human choice through `recursive-grilling` before returning it to the active draft; ordinary refactors that introduce no protective mechanism do not trigger this gate

Do not introduce a separate `.spec` DSL or second workflow format.

Complete when every `R#` has a clear description and observable acceptance criteria, scope and constraints are explicit, testing decisions are recorded, and no unresolved choice is disguised as a requirement.

## Write the approved artifact

The branch determines the output:

- a single run or approved ready slice writes `/.recursive/run/<run-id>/00-requirements.md`
- an approved multi-run route hands its approved requirements content to `recursive-delivery-slicing`, which persists that content unchanged as `/.recursive/deliveries/<delivery-id>/spec.md` while materializing the approved manifest and slices
- an approved active-delivery amendment appends to the existing delivery `spec.md` without creating a run or changing the manifest

A run's `00-requirements.md` preserves the scaffolded header and required `## TODO` section from `recursive-init`, replacing placeholder checklist items rather than deleting the heading. It contains `## Requirements`, `## Out of Scope`, and `## Constraints`; each `R#` has a short title, clear description, and observable acceptance criteria. Carry relevant settled testing decisions into the run requirements.

A delivery spec contains `## Requirements`, `## Testing Decisions`, `## Out of Scope`, and `## Constraints`. Keep a new delivery draft outside the repository until the slicer obtains approval for the split and edges; the delivery creates no umbrella run. Keep an amendment draft outside the repository until its wording is approved, then append it and return to the slicer; effective requirements are the base spec plus approved amendments in order.

For a single run or ready slice, create the run with `.recursive/scripts/recursive-init.py` or `.recursive/scripts/recursive-init.ps1`, then replace the scaffolded `00-requirements.md`. A materialized slice records its exact source delivery and source slice paths in `## Constraints`.

Complete when the approved artifact exists at its canonical path, preserves its native scaffold or amendment history, and points back to any source delivery slice.

## Route delegated help

Immediately before choosing a CLI or model for delegated critique or review, re-read `/.recursive/config/recursive-router.json` and `/.recursive/config/recursive-router-discovered.json`, then route through `recursive-router` rather than inventing an ad hoc model choice.

## Boundaries

- This skill authors and owns the requirements content in `spec.md`, including approved amendments. `recursive-delivery-slicing` may persist the approved content while materializing the delivery tree, but owns only slice decomposition, edges, and cross-run DAG state and must not rewrite requirements.
- Phase 2 owns planning and Phase 3 owns implementation.
- Repository artifacts receive only approved drafts.
