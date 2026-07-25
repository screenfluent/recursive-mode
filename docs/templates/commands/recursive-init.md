# recursive-init (prompt template)

> Paste this into chat if your agent does not support custom slash commands.

## Usage Pattern

```text
Initialize recursive run: <run-id> [options]
```

## Script

```bash
python "<SKILL_DIR>/scripts/recursive-init.py" --repo-root . --run-id "<run-id>" --template feature
python "<SKILL_DIR>/scripts/recursive-init.py" --repo-root . --run-id "<run-id>" --template bugfix --from-issue "#123"
python3 "<SKILL_DIR>/scripts/recursive-init.py" --repo-root . --run-id "<run-id>" --template feature
```

```powershell
powershell -ExecutionPolicy Bypass -File "<SKILL_DIR>/scripts/recursive-init.ps1" -RepoRoot . -RunId "<run-id>" -Template feature
pwsh -NoProfile -File "<SKILL_DIR>/scripts/recursive-init.ps1" -RepoRoot . -RunId "<run-id>" -Template feature
```

## Options

- Template: `feature`, `bugfix`, or `refactor`; the default is `feature`.
- Source reference: `--from-issue "<reference>"` or `-FromIssue "<reference>"` adds the issue, ticket, or source reference to the requirements input and training-loader query.
- Overwrite: `--force` or `-Force` may replace existing DRAFT scaffolds. Never use it over a LOCKED artifact; first reopen that artifact with `recursive-lock --reopen`, which also invalidates downstream receipts, and replace the reopened scaffold only when that reset is intentional.

## What It Does

1. Creates `/.recursive/run/<run-id>/`
2. Creates DRAFT `00-requirements.md` and `00-worktree.md` scaffolds when they are absent, or replaces existing DRAFT scaffolds when force is explicit
3. Prefills `00-worktree.md` with executable Phase 0 diff-basis fields when git state can be resolved
4. Validates that the recorded Phase 0 diff basis is executable against live git state before returning success
5. Creates `addenda/`, `subagents/`, `router-prompts/`, and `evidence/` subfolders
6. Creates canonical evidence subfolders including `reviews/`, `review-bundles/`, and `router/`
7. If `recursive-training` is installed, calls `/.recursive/scripts/recursive-training-loader.py`; an absent loader emits `[INFO]` and is skipped, while failure of an installed loader emits `[WARN]` and remains nonblocking

Newly written scaffolds remain DRAFT with failing gates until their required work and human approval are recorded. Initialization does not complete or lock Phase 0.

## Output

- `/.recursive/run/<run-id>/00-requirements.md`
- `/.recursive/run/<run-id>/00-worktree.md`
- `/.recursive/run/<run-id>/addenda/`
- `/.recursive/run/<run-id>/subagents/`
- `/.recursive/run/<run-id>/router-prompts/`
- `/.recursive/run/<run-id>/evidence/{screenshots,logs,perf,traces,reviews,review-bundles,router,other}/`

## Diff Basis Notes

- The generated `00-worktree.md` uses the current `HEAD` commit as the safe default baseline when possible.
- `Normalized baseline`, `Normalized comparison`, and `Normalized diff command` are treated as executable source-of-truth fields.
- If you later change the baseline reference during Phase 0, update every diff-basis field and rerun lint before locking.

## Next Step

Complete and approve `00-requirements.md` and `00-worktree.md`, correcting the prefilled diff basis if the actual worktree context differs. Then invoke:

```text
Implement requirement '<run-id>'
```
