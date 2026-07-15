---
name: recursive-domain-modeling
description: 'Actively sharpen project domain language and maintain the human-authoritative glossary. Use when a term is unclear, overloaded, or conflicts with the glossary or code; when the user asks to model the domain or edit the glossary; or when another skill proposes adding, changing, or removing a glossary definition.'
---

# Recursive Domain Modeling

Actively build and sharpen the project's domain language. This is the active discipline: challenge terms, invent edge-case scenarios, and capture definitions when they crystallise.

Merely *reading* `GLOSSARY.md` for vocabulary is a one-line habit any skill can follow. Use this skill when changing the domain model, not just consuming it. `recursive-domain-modeling` owns the mutation workflow for `/.recursive/memory/GLOSSARY.md`.

## Glossary location and format

- Canonical file: `/.recursive/memory/GLOSSARY.md`
- Lazy-create the file only when the first definition is **approved** by the human
- Before drafting an add, change, or removal of a glossary definition, load [references/GLOSSARY-FORMAT.md](references/GLOSSARY-FORMAT.md)
- Glossary metadata type is `glossary` (see `/.recursive/RECURSIVE.md` and `/.recursive/memory/MEMORY.md`)

`GLOSSARY.md` is a glossary and nothing else: project-specific terms, tight definitions, optional `_Avoid_` synonyms. No implementation detail, file paths, specs, scratch notes, or design decisions.

## During the session

### Challenge against the glossary

When the user uses a term that conflicts with `GLOSSARY.md`, call it out immediately. Example: the glossary defines cancellation as X, but they seem to mean Y — which is it?

### Sharpen fuzzy language

When the user uses vague or overloaded terms, propose one precise canonical term and list rejected synonyms under `_Avoid_`. Example: "account" — Customer or User?

### Discuss concrete scenarios

When domain relationships are under discussion, stress-test them with specific edge-case scenarios so boundaries between concepts become precise.

### Cross-reference with code

When the user states how something works, check whether the code agrees. Surface contradictions explicitly; do not treat conversation or code as automatically authoritative.

### Human gate before every mutation

For every **add, change, or remove** of a glossary definition:

1. State the proposed wording (and `_Avoid_` list if any).
2. Wait for **explicit human approval**.
3. Only then write `GLOSSARY.md` and set/update `Last-Approved`.
4. Record optional `Source-Runs` when the mutation comes from a recursive run.

Other skills (spec, grilling, design, Wayfinder, Phase 8) may **detect** language problems and **propose** wording, but they route the write through this skill. They must not mutate `GLOSSARY.md` themselves.

### After an approved mutation

- If an active `DRAFT` run artifact uses the old wording, update its terminology and re-audit that draft.
- If a `LOCKED` run artifact is affected, leave it locked and record an **addendum** (lock is immutable).
- Do not create `GLOSSARY.md` for unapproved proposals; leave them in the active draft under a clear proposal disposition if needed.

### Offer ADRs sparingly

Only offer to create an ADR when all three are true:

1. **Hard to reverse** — the cost of changing your mind later is meaningful
2. **Surprising without context** — a future reader will wonder "why did they do it this way?"
3. **The result of a real trade-off** — there were genuine alternatives and you picked one for specific reasons

If any of the three is missing, skip the ADR. Use the format in [references/ADR-FORMAT.md](references/ADR-FORMAT.md).

ADR authorship is shared: domain modeling, design, grilling, or another owner may propose one. Write the file only after explicit human approval.

## Done when

- every in-scope language conflict has a canonical resolution or an explicit unresolved disposition;
- concrete scenarios and relevant code agree with the proposed meaning, or the conflict is surfaced;
- each **approved** mutation is written to `GLOSSARY.md` using glossary-only language;
- every rejected or deferred mutation has a recorded disposition.

## Boundaries

- This skill does not create a recursive run and does not implement product code.
- Keep requirements ownership with `recursive-spec` and module/seam design with `recursive-codebase-design`.
- Use `recursive-grilling` when a language choice is a human trade-off that needs the decision-tree interview.
- Phase 8 may flag term drift and request this skill; Phase 8 never rewrites the glossary autonomously.

## Composes

- Called by: grilling, spec, design, Wayfinder (when present), Phase 8 language proposals
- Calls: codebase read; optional grilling; glossary write after approval; optional ADR after approval
