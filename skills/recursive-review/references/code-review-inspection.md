# Code-review inspection profile

Load this profile after the review pass exists when the reviewed surface includes implementation behavior: source code, tests, executable configuration, schemas or migrations, or runtime wiring. It owns inspection coverage only; [finding-protocol.md](finding-protocol.md) remains the sole output, disposition, and closure contract.

## Pin the comparison

Use the immutable review bundle's basis or a fixed comparison point supplied by the caller. When a bundle already binds the changed surface, verify and use that basis rather than reconstructing it. Otherwise, before inspection:

1. Resolve it with `git rev-parse <fixed-point>`.
2. Record the three-dot basis `git diff <fixed-point>...HEAD` and the commit list from `git log <fixed-point>..HEAD --oneline` in the review evidence.
3. When the scope includes work in progress, also bind `git diff HEAD` plus `git ls-files --others --exclude-standard`; the committed three-dot diff alone does not contain working-tree changes.
4. Confirm the combined comparison is non-empty and matches the declared changed files.

An unresolved or missing fixed comparison point is missing review input, not something to infer silently.

## Discover the owners

Find repository standards in the actual instruction and contribution surfaces that govern the changed files. Find the originating specification in this order:

1. Issue or change references in commit messages. Use the repository's actual issue-tracker workflow when one exists; otherwise record the reference and ask the caller for an accessible source rather than inventing its contents.
2. A path supplied by the caller.
3. A requirements, PRD, or specification file under `docs/`, `specs/`, or `.scratch/` that matches the branch, feature, or changed surface.
4. Ask the caller where the specification lives. If the caller confirms there is none, record the exact `no spec available` evidence required below.

Establish whether each source exists before applying its lens; do not invent it. Until the caller supplies a specification or confirms its absence, the Spec lens is missing review input.

Inspect the **Standards lens** and **Spec lens** independently. Delegation may run them in parallel, but separation of the lenses is required even in a self-audit. One passing lens never suppresses a finding from the other.

## Standards lens

Apply documented repository standards first. The repository rules override the smell baseline when they deliberately endorse a local shape. Skip checks that tooling already enforces.

Use this Fowler smell baseline as a set of judgment calls, not hard violations. A smell becomes a finding only when the diff supplies an observable risk or violated owner:

- **Mysterious Name** — a name hides what a value or operation means; rename it, or clarify the design when no honest name exists.
- **Duplicated Code** — the same logic shape appears more than once; extract and reuse the shared shape.
- **Feature Envy** — behavior reaches into another owner's data more than its own; move it toward the data owner.
- **Data Clumps** — the same values repeatedly travel together; introduce the type they imply.
- **Primitive Obsession** — a primitive substitutes for a domain concept; give the concept a focused type.
- **Repeated Switches** — repeated branching on the same discriminator appears across the change; centralize the choice or use role-specific behavior.
- **Shotgun Surgery** — one logical change requires scattered edits; co-locate what changes together.
- **Divergent Change** — one module changes for unrelated reasons; separate those responsibilities.
- **Speculative Generality** — abstraction or hooks serve no accepted requirement; remove or inline them until a real need exists.
- **Message Chains** — callers navigate a dependency's internals; place the traversal behind the owning interface.
- **Middle Man** — an abstraction mostly forwards calls; use the actual owner unless the seam has contracted value.
- **Refused Bequest** — an inheritor rejects most inherited behavior; replace the inheritance with the narrower relationship.

For a documented-standard breach, cite the owning file and rule. For a smell, name the smell and cite the relevant diff location plus its observable consequence.

## Spec lens

Compare the diff to the originating specification without importing conclusions from the Standards lens. Inspect behavior that is missing, partial, incorrect, or scope-crept. Quote the owning spec text for each finding and identify the mismatching implementation surface.

When the caller confirms that no originating specification exists, record the exact `no spec available` item under `Review Scope` → `Evidence Basis` and run the Standards lens normally. If the owning review contract requires a spec, its absence is also a `missing-evidence` finding; otherwise the Spec lens has no issues to emit. Absence of a spec does not authorize invented requirements.

## Compatibility lens

Inspect versioning, migrations, aliases, shims, dual paths, and compatibility branches for a cited accepted transition and contracted benefit. Apply the repository's owning `/.recursive/RECURSIVE.md` → `Current workflow contract` gate without copying its criteria into this profile. Unsupported protection is a finding; an uncertain consumer surface is evidence to investigate, not permission to declare that no consumer exists.

## Residue lens

When the reviewed surface contains prose, comments, private names, or alternate code, load [recursive-residue-sweep](../../recursive-residue-sweep/SKILL.md) and apply its inspection mode to the exact reviewed surface. Inspection mode makes no edits. Keep its catalog with that owner and translate every supported review issue directly into the canonical `F-*` record.

## Emit through the ledger

Translate every supported issue directly into the canonical `F-*` record. Keep the two lens origins explicit in `Contract` or `Observed`, while preserving the exact schema. Do not create an advice list, secondary ranking, or vote between lenses. The whole ledger, not a per-lens summary, determines PASS or FAIL.
