---
name: recursive-handoff
description: 'Prepare a temporary cross-session handoff. Use only when the user explicitly asks to continue work in a fresh session or transfer it to another agent or model.'
---

# Recursive Handoff

Compact the current conversation into one handoff document for a fresh session without turning it into durable project truth. Load [references/handoff-contract.md](references/handoff-contract.md) before writing the document.

## Invoke explicitly

Begin only after the user explicitly asks for a handoff. A context limit, phase or run completion, delivery creation, model switch, transport switch, or the existence of a run alone does not trigger one. Another skill may suggest a handoff, but never starts it.

Choose one context:

- **recursive-run** — the work is actually bound to one active Recursive run. The handoff is a thin operational pointer; the run remains the complete durable source.
- **standalone** — the live work is outside a Recursive run. Transfer only the context that no durable repository owner already carries.

State the context, exact working directory and next-session objective. Ask one short question only when any of them is ambiguous. Complete this step when all three are explicit rather than inferred from a directory name.

For standalone work, tailor the whole document to the stated next-session objective.

## Account before transfer

For a recursive-run handoff, apply the reference's phase-aware owner checklist. Every category must be accounted for. A missing owner blocks the handoff: name the gap and route it back to the current phase or artifact owner. This skill does not change the worktree or repair canonical artifacts.

For standalone work, separate the live thread from settled knowledge. Point to ordinary repository owners for settled material. When no durable owner exists, either block for one or obtain an explicit human decision to carry the item as a marked claim rather than truth; this skill creates no durable owner.

Complete the preflight only when every relevant category is classified and the next session can distinguish canonical facts, live context and unresolved claims.

## Write outside the workspace

Create a uniquely named Markdown file in the operating system's temporary directory, always outside the workspace. Render the exact context-specific shape from the reference. Never create a repository handoff store.

For recursive-run work, include only the run pointer, current execution state, canonical resume command and workspace revalidation procedure. For standalone work, compact the live thread, reference settled artifacts by path or public URL, name bounded next actions and suggest only the skills the next session needs.

Complete writing when the document contains no duplicate source of truth and no context from unrelated work.

## Verify and return

Read the complete document after writing it. Verify local paths and public URLs separately, then verify current Git and run metadata, drift instructions, cleanup instructions and secret redaction. Do not read or copy credential stores or secret-bearing environment files merely to search for values. The exact working directory is permitted as same-host operational metadata.

If verification passes, return the exact temporary path and one instruction: read that file in a fresh session and continue. The handoff does not change the worktree. If verification fails, remove the partial temporary file and report the blocking gap.

Complete when the verified path and ingestion instruction are delivered.

## Boundaries

This skill owns temporary session transfer only. It does not own subagent delegation, phase closeout, delivery DAGs, training, memory, a launcher, a generator or repository storage, and does not change central runtime validation. A future transport adapter may launch or transmit an already prepared handoff, but it owns any additional redaction and transport policy.
