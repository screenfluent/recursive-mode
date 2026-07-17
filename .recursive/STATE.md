# STATE.md

## Current State

- `/.recursive/RECURSIVE.md` is the single canonical, unversioned workflow specification; runtime and model-facing surfaces do not select historical workflow profiles.
- The default package surface contains `recursive-mode` plus the 20 installable subskills listed in `README.md`; `recursive-benchmark` remains a separate optional add-on.
- `skills/recursive-mode/` is the self-contained installable root skill. Its installer bootstraps the canonical control plane, bridges, router policy and memory plane, then copies the packaged runtime into target repositories under `/.recursive/scripts/`.
- Nine phase artifacts own lossless review ledgers and immutable per-pass bundles. Phase 5 remains a QA-only, non-ledger phase.
- Executable diff-basis normalization is implemented across lint, status, review-bundle generation, and lock-time validation.
- Audited phases require status-specific, machine-checkable `Requirement Completion Status` entries. Phase 2 owns the planned `Test Surface`, and Phase 3 records the matching RED/GREEN or pragmatic-exception evidence.
- Delegated review is grounded by canonical review bundles, one lossless finding ledger, prior recursive evidence, and durable subagent action records under `/.recursive/run/<run-id>/subagents/`, with explicit controller verification recorded in the phase artifact.
- Routed delegation uses the repo policy under `/.recursive/config/recursive-router.json`; setup and discovery require explicit opt-in, while an active configured route is reused for its delegated role without another prompt.
- The memory plane includes a lazily created, human-authoritative `GLOSSARY.md`, experiential training memory and optional skill/capability memory, all reached through `/.recursive/memory/MEMORY.md` and their owning skills.
- The maintained smoke harness lives in `scripts/test-recursive-mode-smoke.py` and `scripts/test-recursive-mode-smoke.ps1`, supports `python`, `powershell`, and `mixed` toolchain modes, and records lazy PowerShell fallback/skip behavior.

## Notes

- Reusable workflow docs in this repository should remain generic. Do not check in self-run control-plane history, run artifacts, or run-derived memory unless that is an intentional product requirement.
