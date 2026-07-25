# recursive-training phase8 and loading

## Phase 8 handoff

`08-memory-impact.md` is where a single run records what it learned.

Training then reads **many** completed runs and turns those run-local observations into cross-run memory.

That flow is:

```text
run completes Phase 8
  -> Phase 8 locks
  -> recursive-training-phase8-trigger.py runs
  -> recursive-training-grpo.py extracts memory
  -> memory files update under /.recursive/memory/
  -> later runs load only the relevant items through recursive-training-loader.py
```

## Trigger behavior

`recursive-training-phase8-trigger.py` is intentionally thin.

It should:

1. check whether enough completed runs exist
2. skip clearly when they do not
3. print the grpo command when `--auto` is not requested
4. run grpo immediately when `--auto` is requested

Examples:

```bash
python .recursive/scripts/recursive-training-phase8-trigger.py --repo-root . --run-id <run-id>
python .recursive/scripts/recursive-training-phase8-trigger.py --repo-root . --run-id <run-id> --auto
```

## Canonical commands

Full training:

```bash
python .recursive/scripts/recursive-training-grpo.py --repo-root .
```

Incremental training:

```bash
python .recursive/scripts/recursive-training-grpo.py --repo-root . --incremental --run-id <run-id>
```

Sync-only guidance:

```bash
python .recursive/scripts/recursive-training-sync.py --repo-root .
```

## Progressive disclosure

Training memory should load in three steps:

1. Read `/.recursive/memory/MEMORY.md`.
2. Run `recursive-training-loader.py` with the current task description and file paths.
3. Apply only the returned items that match the current task.

This keeps the system from stuffing all historical memory into every session.

## Loader timing

Call the loader after reading `/.recursive/RECURSIVE.md` and `/.recursive/memory/MEMORY.md`, but before planning or implementation starts.

Typical loader call:

```bash
python .recursive/scripts/recursive-training-loader.py \
  --repo-root . \
  --query "implementing frontend feature with react and tanstack router" \
  --files "apps/web/src/App.tsx,apps/web/src/stores/ui-store.ts" \
  --max-docs 3 \
  --max-items 10
```

## Integration guidance

The loader returns formatted text on stdout. Inject that into context as:

- system-prompt context
- a pre-task context message
- a tool result in a tool-aware caller

If the loader finds nothing relevant, continue normally rather than fabricating memory.

## Loader and MCP relationship

- `recursive-training-loader.py` is the canonical path because it works everywhere
- `recursive-training-mcp.py` is an optional convenience layer for MCP-aware environments
- both read the same memory files

Use one or the other, not both for the same retrieval step.

## Failure handling

Common outcomes:

- no training scripts installed -> explain that recursive-mode bootstrap must run first
- fewer than 2 Phase-8-locked runs -> trigger exits `3` and explains that extraction needs more evidence
- extractor unavailable -> exit `2`; do not claim memory updates
- no learnings extracted / insufficient groups -> exit `3`; do not claim memory updates
- successful write -> exit `0` and refresh the MEMORY.md training registry markers

## Extractor contract

`recursive-training-grpo.py` never embeds an LLM client. It always delegates prompt evaluation to `recursive-training-extract.py`.

Wire extraction with one of:

```bash
# Agent/offline response
python .recursive/scripts/recursive-training-extract.py \
  --repo-root . --prompt-file prompt.txt --response-file items.json

# External command (placeholders: {prompt_file}, {repo_root})
set RECURSIVE_TRAINING_EXTRACTOR_CMD=my-extractor --prompt {prompt_file}
```

## Incremental mode

`--incremental --run-id <id>` keeps the target run **and** other Phase-8-locked peers that share its inferred subsystem. It does not train on a single-run group alone.

`recursive-training-phase8-trigger.py --auto` tries incremental first; if that returns exit `3` (zero items), it falls back to full Phase-8-locked training before giving up.

## Closeout hook

Re-running `recursive-closeout --phase 08` after Phase 8 is already locked invokes `recursive-training-phase8-trigger.py --auto`. First lock via `recursive-lock` does not auto-train; agents should run the trigger (or that closeout re-run) explicitly.
