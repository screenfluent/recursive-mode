---
name: recursive-codebase-design
description: 'Design deep modules and material program flow inside Recursive Phase 2. Use when the user wants a module interface or seam designed, code deepened or made more testable or AI-navigable, cross-interface execution shaped, or when another skill needs codebase design.'
---

# Recursive Codebase Design

Design **deep modules**: a lot of behaviour behind a small interface, placed at a clean seam, testable through that interface. The aim is leverage for callers, locality for maintainers, and testability for everyone. Shape cross-interface program flow when the design requires it, and write the accepted design into `02-to-be-plan.md` before mapping it to files, commands, tests, and QA.

## Applicability

Run `recursive-codebase-design` when a scoped change creates or materially changes any of:

- an interface, seam, module split, or dependency placement;
- an important contract or signature;
- state or object ownership;
- a complex or critical call path;
- error propagation or side-effect placement;
- overlapping responsibilities or another material factoring risk.

Also run when the user explicitly asks how to structure the system, cut modules, place seams, deepen interfaces, or design a program flow. Edits that preserve these shapes stay in ordinary Phase 2 execution planning.

## Process

1. Read requirements, AS-IS, the approved glossary when present, relevant ADRs, and the real code.
2. When applicability fires, load [references/module-design.md](references/module-design.md) and shape the interface before execution mapping.
3. When the change merges shallow modules or moves a seam around dependencies, load [references/deepening.md](references/deepening.md).
4. Confirm every new or changed test-surface seam with the human before tests are planned there.
5. Map the agreed design to files, commands, tests, and QA in the execution-planning portion of `02-to-be-plan.md`.

### Design It Twice

For a costly or hard-to-reverse interface, or on explicit human request, follow [references/design-it-twice.md](references/design-it-twice.md).

### Program design

When design must specify cross-interface execution flow, state ownership, data or error propagation, or side-effect placement, load [references/program-design.md](references/program-design.md).

### Observability

When design must specify runtime diagnosability, load the conditional observability contract in [references/program-design.md](references/program-design.md).

## Done when

For every in-scope R# that needs design:

- applicable system, module, and program shapes are concrete enough to plan files and commands;
- each new or changed test-surface seam is human-confirmed;
- dependency and testing strategies are stated;
- important contracts, invariants, ownership, flows, and failure behaviour are explicit where applicable;
- design maps back to R# without duplicating requirements;
- open decisions are resolved via `recursive-grilling`, durably deferred, or ruled out of scope;
- Phase 2 can finish execution planning without reopening the agreed design.

## Writes

| Target | Condition |
|---|---|
| Design sections in `02-to-be-plan.md` | Applicability fires; use the existing Phase 2 audit, gates, lock, and addenda. |
| Glossary-change proposal | Route through `recursive-domain-modeling` and its human gate. |
| `docs/adr/*` | All three ADR criteria hold and the human approves. |

## ADR gate

Propose an ADR only when all three hold: hard to reverse, surprising without context, and a real trade-off. Write only after explicit human approval.

## Composes

- Use `recursive-prototype` before Phase 2 lock when a design question needs an empirical answer.
- Use `recursive-grilling` for open human decisions.
- Route language mutation through `recursive-domain-modeling`.
- Hand agreed seams and testing surfaces to Phase 2 execution planning and `recursive-tdd`.

## Boundaries

- Write design into the existing Phase 2 artifact, audit, gates, lock, and addenda.
- Phase 3 owns implementation and TDD RED/GREEN.
- This skill does not create a recursive run.
- It does not create a separate design artifact or design phase.
- Observability remains a contract consumed by existing phases.
