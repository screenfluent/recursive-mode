---
name: recursive-prototype
description: 'Build a throwaway prototype to answer a design question. Use when the user wants to sanity-check whether a state model or logic feels right, explore what a UI should look like, or give recursive-codebase-design empirical evidence before Phase 2 lock.'
---

# Recursive Prototype

A prototype is **throwaway code that answers a question**. The question decides the shape.

## Pick a branch

Identify which question is being answered — from the user's prompt, the surrounding code, or by asking if the user is around:

- **"Does this logic / state model feel right?"** → [references/logic.md](references/logic.md). Build a tiny interactive terminal app that pushes the state machine through cases that are hard to reason about on paper.
- **"What should this look like?"** → [references/ui.md](references/ui.md). Generate several radically different UI variations on a single route, switchable via a URL search param and a floating bottom bar.

The two branches produce very different artifacts — getting this wrong wastes the whole prototype. If the question is genuinely ambiguous and the user isn't reachable, default to whichever branch better matches the surrounding code (a backend module → logic; a page or component → UI) and state the assumption at the top of the prototype.

Complete this step when the question is explicit and one branch is selected.

## Isolate first

Create a throwaway branch and worktree before writing prototype source:

- active run: `prototype/<run-id>-<slug>`;
- standalone: `prototype/<slug>`.

Prototype source is **throwaway from day one, and clearly marked as such**. Base the branch on the current product/run `HEAD`. Follow the repository worktree convention without invoking `recursive-worktree` or creating Phase 0 ceremony. Locate prototype code close to where it will actually be used inside the throwaway worktree so context is obvious, but name it so a casual reader can see it is a prototype rather than production. Keep prototype source and commits off the product/run worktree, its comparison branch, and `main`.

Complete this step when the throwaway ref and worktree exist and prototype source cannot alter the product/run diff basis.

## Rules that apply to both

1. **One command to run.** Whatever the project's existing task runner supports — `pnpm <name>`, `python <path>`, `bun <path>`, etc. The user must be able to start it without thinking.
2. **No persistence by default.** State lives in memory. Persistence is the thing the prototype is _checking_, not something it should depend on. If the question explicitly involves a database, hit a scratch DB or a local file with a clear "PROTOTYPE — wipe me" name.
3. **Skip the polish.** No tests, no error handling beyond what makes the prototype _runnable_, no abstractions. The point is to learn something fast.
4. **Surface the state.** After every action (logic) or on every variant switch (UI), print or render the full relevant state so the user can see what changed.

Give the human the command and, for UI, the URL and variant keys. Extend the prototype when the experiment needs another action or variant to answer its question.

Complete this step when the human can drive the prototype with one command and has enough observable behavior to form a verdict.

## Capture it when done

Commit the complete prototype on the throwaway branch and record its reachable immutable commit.

For an active run, write the capture to:

`/.recursive/run/<run-id>/evidence/prototypes/<slug>.md`

For a human-selected Wayfinder map and discovery unit, write the same capture to:

`/.recursive/maps/<map-id>/evidence/<unit-id>/prototype/<slug>.md`

Map evidence contains the report and pointer only; prototype source stays on its throwaway branch.

Include only:

- Question
- Branch: `logic` or `ui`
- Run commands
- Prototype pointer: branch and commit
- Verdict
- Design consequence

Prototype source never enters evidence, the product/run worktree, or `main`. Hand the verdict and design consequence to `recursive-codebase-design`, which owns the accepted design and any ADR.

Outside an active run or selected map unit, return the same capture to the human. Persist it only at a location the human selects; create no default documentation plane.

After the commit pointer resolves, remove the throwaway worktree and keep its ref reachable while the capture is retained.

Complete this step when the verdict is durable, the commit pointer resolves, the throwaway worktree is removed, and the product/run plane contains only the capture rather than prototype source.

## Production handoff

Close the question before Phase 2 lock. After the lock, route new design uncertainty back to planning instead of opening a prototype through an addendum or as a Phase 3 side quest.

Hand production implementation to `recursive-tdd`, which owns the RED-before-lift contract. Treat prototype logic as an untrusted candidate until the production seam is red; rewrite UI directions under the production TDD cycle rather than promoting a variant directly.

## Done when

- the design question has a `logic` or `ui` verdict;
- the recorded command runs the prototype;
- the prototype commit is reachable through the recorded pointer;
- the active-run capture contains report, commands, and pointer but no source;
- for an active run, the design consequence is handed to `recursive-codebase-design` before Phase 2 lock;
- outside a run, the capture is returned to the human with no Phase 2 dependency;
- prototype source introduced no change to the product/run worktree or `main`.

## Composes

- Use `recursive-grilling` when the prototype surfaces a human choice that observation cannot resolve.

## Boundaries

- `recursive-prototype` owns the isolated experiment, its source ref, and its capture.
- `recursive-codebase-design` owns accepted interfaces, seams, execution shape, and ADR decisions.
- `recursive-tdd` owns the RED-before-lift contract, production GREEN, refactoring, and verification.
- This skill creates neither a recursive run nor a recursive phase.
