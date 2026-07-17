Type: `pattern`
Status: `CURRENT`
Scope: `How the main agent verifies delegated review or audit work before accepting it as lockable evidence.`
Owns-Paths:
Watch-Paths:
- `/.recursive/RECURSIVE.md`
- `/.recursive/memory/skills/SKILLS.md`
- `/.recursive/run/`
- `/skills/`
Source-Runs:
- `none (generic repository guidance)`
Validated-At-Commit: `generic-repository-guidance`
Last-Validated: `2026-07-17T00:00:00Z`
Tags:
- `skills`
- `subagent`
- `verification`
- `review-bundle`

# Delegated Verification And Refresh

Delegated work is optional helper output, not autonomous authority.

## Main-Agent Acceptance Rules

Before accepting meaningful delegated work, the main agent should verify:

- claimed file impact against the actual diff-owned file set
- claimed artifact reads or updates against files that actually exist
- review-bundle contents against the current reviewed artifact and artifact hash
- requirement, plan, addenda, and prior recursive docs that materially informed acceptance
- whether any post-review repair made the delegated context stale

## Record In The Phase Artifact

When delegated work materially contributes, `## Subagent Contribution Verification` should record:

- `Reviewed Action Records`
- `Main-Agent Verification Performed`
- `Acceptance Decision`
- `Refresh Handling`
- `Repair Performed After Verification`

## Refresh Rule

Any reviewed-surface change to the artifact, changed-file scope, or evidence basis refreshes the immutable bundle, action record when used, and next ledger pass before relying on review evidence.

## Forward-Test Model-Facing Skills

A structural contract test proves files and declared rules, not model behavior. When a run adds or materially changes a model-facing skill:

- give a fresh subagent a task-style prompt and the installed skill path;
- omit the intended answer, suspected failure, and expected response shape;
- preserve the exact prompt and raw response under run evidence;
- have the controller check the response against the skill's observable interaction contract; and
- refresh the review bundle and action records before re-audit when the forward test repairs missing evidence.

## Rejection Rule

If the main agent cannot verify delegated claims against actual files, actual artifacts, and the actual diff scope, reject the delegated result and fall back to self-audit for lockable completion evidence.

The controller must verify every finding row against the real diff, artifacts, owning contract, and named check. Delegated reports and repair results are candidate claims, never terminal proof.

Memory is not a backlog and is not a deferral target. Known review obligations remain open, are fixed now, or use the protocol's human-approved tracked destination.
