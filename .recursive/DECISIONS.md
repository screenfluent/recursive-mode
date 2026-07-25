# DECISIONS.md

## Recursive Run Index

- No run history is intentionally checked into this reusable skill repository.

## Product Decisions

- Keep `/.recursive/RECURSIVE.md` as the sole workflow source of truth. Installable skills and bridge documents may route into that contract but do not duplicate or override it.
- Maintain one unversioned workflow contract. Runtime and model-facing surfaces do not detect, emit or branch on historical profile names; a compatibility path requires an explicit human decision and evidence of a live consumer that cannot migrate atomically.
- Ship `recursive-mode` and its installable subskills as the default package surface while keeping `recursive-benchmark` outside that surface as an optional add-on.
- Keep Python as the canonical implementation surface for complex enforcement logic and use PowerShell wrappers where that materially reduces parity drift.
- Treat Python and Bash as first-class bootstrap paths on macOS and Linux; PowerShell remains optional and must preserve wrapper parity where available.
- Treat subagent availability as environment-dependent and require a concrete capability probe before choosing delegated review.
- Treat delegated output as a claim until the controller verifies its bundle, ledger, action record, actual files, recursive artifacts and diff basis. Model votes, severity ranking and secondary advice lists do not replace the canonical finding ledger.
- Require every audited phase to use an immutable per-pass bundle and one lossless `recursive-review` ledger through controller-verified closure; keep Phase 5 QA-only and outside the ledger protocol.
- Prefer `mixed` as the documented smoke mode when cross-toolchain parity is desired, while keeping `python` independently runnable in environments without PowerShell.
- Require status-specific evidence fields in `## Requirement Completion Status` so audited artifacts cannot pass on vague prose-only completion claims.
- Keep router setup, discovery and reconfiguration opt-in. Reuse an active configured route for its delegated role without asking again, and preserve explicit fallback plus controller verification.
- Route every glossary mutation through `recursive-domain-modeling` and explicit human approval. Phase 8 may report semantic drift but does not edit the human-authoritative glossary autonomously.
- Treat training memory and `/.recursive/memory/skills/` as optional durable surfaces. Promote only generalized, reusable knowledge and retrieve only shards relevant to the task.
- Keep explicit-request-only skills explicit: workflow events, context pressure and the mere existence of a run do not start architecture surveys, cross-session handoffs or Wayfinder maps.
- Keep permanent repository tests at executable boundaries such as runtime behavior, parsers, formats and installed package surfaces; do not pin skill instructions, reference prose or example wording in Markdown tests.
- Keep this reusable repository free of self-run history, review evidence, temp paths and generated residue unless a file is an intentional product fixture.
