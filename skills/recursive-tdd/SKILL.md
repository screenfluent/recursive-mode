---
name: recursive-tdd
description: 'Test-driven development for every Recursive Phase 3 code change. Use when implementing code in Recursive Phase 3, including features, bug fixes, behavior changes, and planned refactoring; or when the user asks for test-first development, mentions RED-GREEN-REFACTOR, or wants integration tests.'
---

# Recursive TDD

TDD is the RED → GREEN loop. Run one approved behavior at a time as a tracer bullet, then perform a bounded REFACTOR while green. This skill makes that loop produce tests worth keeping and records the evidence required by Recursive Phase 3.

Preserve the Iron Law:

```text
NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST
```

## Orient on the approved surface

Read the effective `02-to-be-plan.md`, including its addenda, and locate the `Test Surface` records for the active R#. Use the run's approved requirements, glossary terms, plan, and decisions so test names match the project's domain language.

- Work one `TS-*` record at a time.
- Use its observable behavior, approved seam, test level, dependency choices, and independent expected-value source.
- Phase 3 may not invent a seam. Route a newly required or changed seam through the normal plan/design addendum and human gate before implementation.

Before selecting, writing, or revising a test, load [references/test-quality.md](references/test-quality.md). It owns behavior-test examples, anti-patterns, assertion quality, test-level selection, and mocking guidance.

Complete orientation when one active `TS-*` record and its exact focused test command are known.

## Declare the mode

Use `TDD Mode: strict` by default. Strict mode requires observed RED and GREEN evidence under `/.recursive/run/<run-id>/evidence/logs/`.

Use `TDD Mode: pragmatic` only when strict RED-first execution is genuinely infeasible. Record a concrete `## Pragmatic TDD Exception`, compensating validation, evidence paths, and every `Test Surface: TS-*` covered by the exception. Treat this as a visible deviation, never a shortcut.

Complete mode selection when the Phase 3 artifact names the mode and its required evidence path.

## Run one tracer-bullet cycle

### RED

1. Write the narrowest behavior test for the active `TS-*` record.
2. Run its focused command.
3. Confirm a failing assertion, not setup noise or a syntax error.
4. Confirm the failure is caused by the missing behavior.
5. Record the `TS-*` ID, test, exact command, expected failure, actual failure, and RED evidence path in `## TDD Compliance Log`.

If the test passes immediately or fails for the wrong reason, revise the test and recapture RED before touching production code.

Complete RED only after personally observing the relevant failure and writing its evidence.

### GREEN

1. Implement only the behavior named by the active `TS-*` record.
2. Re-run the focused command and confirm it passes.
3. Run any adjacent checks needed to show the slice did not regress.
4. Record the minimal change, command, result, and GREEN evidence path.

Complete GREEN only when the approved behavior passes at the approved seam.

### Bounded REFACTOR

After GREEN, improve names, remove local duplication, or simplify the just-green path. Keep the suite green and stay inside the approved seam and plan.

A change to behavior, seam, interface, dependency placement, module ownership, or plan scope is broader than a bounded refactor. Route it through the appropriate design/addendum owner or create a lossless review finding.

Record the cleanup and verification command, or record `N/A` when the minimal GREEN needs no cleanup. Complete REFACTOR only while the same behavior remains green at the same seam.

Then select the next ready `TS-*` record and repeat. Do not batch imagined tests horizontally before implementing the first vertical tracer bullet.

### Prototype handoff

Derive the production test from the accepted requirement and human-confirmed seam. Record actual RED before consulting or lifting prototype logic. After RED, prototype logic may inform minimal GREEN. Keep lifted logic untrusted until the bounded refactor, all planned test suites, and review pass.

## Record the canonical artifact

Use the Phase 3 `## TDD Compliance Log` schema and gates owned by `/.recursive/RECURSIVE.md`. For every strict cycle, include:

- the canonical `RED Evidence` and `GREEN Evidence` paths;
- Requirement ID and `Test Surface: TS-*`;
- test path and test name;
- exact RED command, expected/actual failure, and RED evidence;
- minimal GREEN change, command, result, and GREEN evidence;
- bounded REFACTOR or `N/A`, plus green verification.

Keep `## Review Metadata`, `## Requirement Completion Status`, Coverage, TDD Compliance, and Approval gates aligned with the canonical phase contract. Do not duplicate the full scaffold in this skill.

The review block must retain `Review Ledger Path` and `Review Bundle Path` so the common lossless ledger remains mechanically reachable from this specialized TDD artifact.

### Routing awareness

Before delegated TDD execution, re-read:

- `/.recursive/config/recursive-router.json`
- `/.recursive/config/recursive-router-discovered.json`

Use the routed policy or its explicit fallback. The controller still verifies RED, GREEN, the diff, and every claimed outcome.

## Recovery

- Production code before RED: remove that implementation and restart from the approved `TS-*` record.
- RED passes: strengthen or correct the test until the missing behavior fails.
- RED is setup noise: repair setup and recapture RED.
- The test or seam is wrong: stop; route the decision back through the plan or addendum rather than silently changing the oracle.
- Exploration is needed: throw it away, then start the production cycle fresh.
- "I'll keep exploratory code as reference": leave it isolated until actual RED exists; prototype handoff governs any later consultation.

## Done when

- every planned `TS-*` record is referenced by a completed strict cycle or an approved pragmatic exception;
- every strict cycle has relevant RED and GREEN evidence;
- every bounded refactor stayed inside its approved seam and plan;
- focused, adjacent, and planned full-suite commands are green;
- TDD Compliance, Coverage, review, and Approval gates pass.
