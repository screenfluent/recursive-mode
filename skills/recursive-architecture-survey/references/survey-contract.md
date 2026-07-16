# Architecture survey contract

## Contents

- [Snapshot and owners](#snapshot-and-owners)
- [Organic friction](#organic-friction)
- [Deletion test](#deletion-test)
- [Candidate gate](#candidate-gate)
- [Offline report](#offline-report)
- [Disposition and cleanup](#disposition-and-cleanup)

## Snapshot and owners

Record the exact working directory, branch and HEAD, clean or dirty state, scope and exclusions. List scoped changed paths when the tree is dirty. Inspect the current visible tree, but label overlapping work in progress as **provisional**; WIP alone cannot support a durable recommendation.

Read the governing repository instructions, relevant code and tests, existing ADRs, and `/.recursive/memory/GLOSSARY.md` when it exists. Read the installed `recursive-codebase-design` skill's [module-design reference](../../recursive-codebase-design/references/module-design.md) for the canonical module, interface, seam, depth, leverage, and locality vocabulary. Architecture vocabulary cites its owner; it does not restate the owning reference.

The survey must not infer project identity from the directory basename. Use canonical repository metadata when it exists; otherwise show only the exact working directory instead of inventing a project name.

Build the in-scope subsystem inventory from the explicit scope, governing architecture documents, package manifests, and actual source roots. When those sources disagree, include every visible root and record the disagreement. When no formal subsystem map exists, use each first-level code root inside the scope. Generated files, vendored code, fixtures, external submodules, and other exclusions remain outside only when the report names the exclusion and reason.

## Organic friction

Do not follow rigid heuristics—explore organically and note where you experience friction. Use the inventory to orient the scan; follow encountered friction through actual caller → interface → implementation paths, nearest tests, and, when relevant, error or diagnostic paths. Look for:

- Where does understanding one concept require bouncing between many small modules?
- Where are modules **shallow** — interface nearly as complex as the implementation?
- Where have pure functions been extracted just for testability, but the real bugs hide in how they're called (no **locality**)?
- Where do tightly-coupled modules leak across their seams?
- Which parts of the codebase are untested, or hard to test through their current interface?
- wiring that obscures the behavior it connects;
- tests reaching past an interface or reproducing internal orchestration;
- modules that must change together for one reason;
- a seam that disperses change, bugs, knowledge, or verification;
- real friction that may justify reopening an existing ADR.

Verify each signal in actual call sites, tests, interfaces, or dependency paths. Search hits are leads, not candidates. Small size alone does not make a module shallow. Tooling and delegation may discover evidence, but delegation is optional and the controller verifies every claim against the repository.

## Deletion test

For each opportunity, imagine removing the current module while retaining accepted behavior:

- If complexity disappears, the module may be pass-through and must still be checked for a contracted seam or other deliberate value.
- If complexity reappears across callers, the module is concentrating knowledge and probably earns its existence.
- If neither outcome is supported by evidence, reject the signal or label it speculative; do not invent a recommendation.

Record the deletion-test result and the callers or behavior that support it. The test judges architectural leverage, not file size or implementation-line ratios.

## Candidate gate

Each supported candidate records:

1. A stable report-local ID and short title.
2. Exact paths or symbols and the observed friction.
3. The current module, interface or seam.
4. The deletion-test result and supporting evidence.
5. The consequence for depth, leverage, locality, or testing.
6. A deepening opportunity stated as a desired concentration of responsibility.
7. A testing consequence at the current seam.
8. Any relevant ADR conflict, clearly marked as a notice rather than a verdict.
9. What would falsify it.
10. Recommendation strength: **Strong**, **Worth exploring**, or **Speculative**.

Recommendation strength is opportunity confidence, not severity, not priority, and not an `F-*` finding. A candidate is not a requirement or implementation obligation. Zero supported candidates is a valid result; render that result instead of padding the report.

The opportunity may name a target effect such as a smaller caller-visible surface, concentrated ownership, improved locality, or a more useful test surface. It does not propose a concrete new interface, module split, adapter, migration plan, file map, or implementation sequence. Those belong to an approved run and `recursive-codebase-design` in Phase 2.

## Offline report

Write a uniquely named file such as:

```text
<system-temp>/recursive-architecture-survey-<UTC-timestamp>.html
```

Resolve the operating system's temporary directory from `$TMPDIR`, falling back to `/tmp` on POSIX or `%TEMP%` on Windows. The report stays outside the workspace. Use semantic HTML, inline CSS, and inline SVG. Use no scripts, external assets, telemetry or network requests.

Render these sections:

1. **Repository snapshot** — the exact basis, scope, exclusions, and WIP note.
2. **Architecture vocabulary** — one pointer to its canonical owner and a one-line statement that the report uses that vocabulary; no copied glossary.
3. **Supported candidates** — one card per candidate.
4. **Rejected signals** — brief evidence-based reasons, not an advice list.
5. **Top recommendation** — only when supported candidates exist.
6. **Next decision** — choose one candidate to explore or finish the survey.

Each candidate card contains its complete candidate-gate fields, a before diagram of current evidence, and an outcome diagram showing desired responsibility concentration. The outcome diagram is not an interface design. Keep prose sparse enough that the diagrams remain useful, while preserving every cited path and falsification condition.

Read the completed HTML in full. Confirm every pointer resolves, no secret or private URL appears, no large code block or copied artifact substitutes for a reference, and no external resource is loaded. Open it with `xdg-open <path>` on Linux, `open <path>` on macOS, or `start <path>` on Windows; when local opening is unavailable, return the exact absolute path.

## Disposition and cleanup

The survey itself does not create a run, mutate the glossary, write an ADR, or change code. A selected candidate first goes through `recursive-grilling`. Language changes route to `recursive-domain-modeling`; approved work routes to `recursive-spec`; concrete architecture belongs to later `recursive-codebase-design`.

Offer an ADR only when the existing three-part ADR gate holds and the human explicitly approves the write. A deferred candidate needs a human-selected durable destination. The temporary report is not a backlog or durable source of truth.

Delete the report after selected dispositions are durably owned or when the user finishes the survey. Retention requires an explicit human decision and an existing appropriate owner; copying the HTML into the repository is not a default retention path. The worktree remains unchanged throughout the survey.
