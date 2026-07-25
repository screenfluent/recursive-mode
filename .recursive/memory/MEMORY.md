# MEMORY.md

<!-- RECURSIVE-MODE-MEMORY:START -->
## Memory Router

This file is the durable memory router for the repository.
It is not a knowledge dump. Store durable memory in sharded docs under `domains/`, `patterns/`, `incidents/`, `episodes/`, `training/`, `skills/`, or `archive/`, plus the human-authoritative glossary file below.

Control-plane docs are not memory docs:
- `/.recursive/RECURSIVE.md`
- `/.recursive/STATE.md`
- `/.recursive/DECISIONS.md`
- `/.codex/AGENTS.md`
- `/AGENTS.md`
- `/.agent/PLANS.md`

## Retrieval Rules

- Read this file before loading any other memory docs.
- Load only the memory docs relevant to the current task.
- When authoring or reviewing requirements, design, plans, or tests that use domain terms, consult `/.recursive/memory/GLOSSARY.md` if it exists and keep wording aligned with approved definitions.
- If the task may benefit from prior recursive-mode experiential learnings, use this index to identify the relevant docs under `/.recursive/memory/training/` and `/.recursive/memory/domains/`.
- The optional `recursive-training-sync.py` helper is read-only; it prints startup guidance about what to read, but does not modify `MEMORY.md` or the memory plane.
- If the task plans delegated review, subagent help, review bundles, smoke-harness portability work, or capability-sensitive execution, read `/.recursive/memory/skills/SKILLS.md` and then load only the relevant skill-memory shards that are actually present.
- If Phase 8 will need to promote durable lessons, first capture run-local skill usage in the run artifact and only then promote generalized conclusions into skill-memory shards.
- Prefer `Status: CURRENT` docs for planning and execution.
- `Status: SUSPECT` docs may be used as leads, but revalidate them before trust.
- Exclude `STALE` and `DEPRECATED` docs from default retrieval unless doing historical analysis.

## Registry

- `GLOSSARY.md` - human-authoritative domain language (`Type: glossary`). Create it lazily on the first approved definition. Route every change through `recursive-domain-modeling` and explicit human approval. It owns no code paths, and code changes do not automatically make it `SUSPECT`.
- `domains/` - stable functional-area knowledge with `Owns-Paths` (code ownership knowledge, not the domain glossary)
- `patterns/` - reusable playbooks and solution patterns
- `incidents/` - recurring failure signatures and fixes
- `episodes/` - distilled lessons from specific runs
- `training/` - extracted experiential learnings promoted from completed recursive-mode runs
- `skills/` - durable skill and capability memory, routed via `skills/SKILLS.md`
- `archive/` - historical or deprecated memory docs

## Freshness Rules

- Durable memory docs must declare the metadata defined in `skills/recursive-mode/references/artifact-template.md`, except `GLOSSARY.md`, which uses the glossary metadata profile in `/.recursive/RECURSIVE.md`.
- Any doc whose `Owns-Paths` or `Watch-Paths` overlaps final changed code paths must be reviewed in Phase 8.
- Affected `CURRENT` docs should be downgraded to `SUSPECT` until revalidated against final code, `STATE.md`, and `DECISIONS.md`.
- `GLOSSARY.md` is exempt from path-based `SUSPECT` downgrades. Phase 8 may flag semantic term drift, but it must route corrections through `recursive-domain-modeling` and human approval. It must never edit the glossary autonomously.
- If an approved glossary meaning change affects a run artifact, re-audit the artifact while it is `DRAFT`; if it is already `LOCKED`, leave it locked and record an addendum.
- If changed paths have no owning domain doc, create one or record the uncovered-path follow-up in `08-memory-impact.md`.
- Training memory docs should keep their canonical content under `/.recursive/memory/training/`, use the memory index as the discovery surface, and record source runs plus watch-path or applicability guidance.
- Skill-memory docs should record source runs, last validated date, environment notes, and current trust/fit guidance.
- If a run materially teaches the repo something about skill availability, delegated-review quality, review-bundle usage, or toolchain fallback behavior, Phase 8 must either create/refresh a skill-memory shard or record why no durable lesson was promoted.
- If the repo itself is a reusable skill/workflow distribution, durable memory must remain generalized. Do not store current-session run residue or temp-environment observations as if they were universal truth.
<!-- RECURSIVE-MODE-MEMORY:END -->
