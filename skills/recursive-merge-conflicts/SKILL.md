---
name: recursive-merge-conflicts
description: 'Resolve active Git merge or rebase conflicts by recovering source intent and completing the operation. Use only when Git is currently stopped on conflicts during a merge or rebase.'
---

# Recursive Merge Conflicts

Treat the conflict as an intent problem, not a text problem. Resolve it hunk by hunk, preserve both sides where their purposes are compatible, surface real trade-offs, and carry the active merge or rebase to verified completion.

## Bind the active operation

Run `git status`, `git diff --name-only --diff-filter=U`, and `git ls-files -u`. Confirm Git is stopped inside an active merge or rebase; this skill does not start a merge or rebase. Cherry-pick conflicts are deliberately excluded.

Record the operation type, branch, HEAD, source refs, merge base, stated goal, every unmerged path and conflict type, plus unrelated staged, unstaged, and untracked changes. Treat those unrelated changes as user-owned.

Complete when every unmerged path and unrelated change has an explicit owner and the operation's source refs are known.

## Recover both intents

Each side of a hunk exists because someone wanted something. For every unmerged path and textual hunk, read the introducing commits, commit messages, merge base, pull requests, issues, requirements, plans, ADRs, repository instructions, and surrounding code and tests that actually exist. Use primary sources; absence remains a gap rather than an inferred purpose.

During rebase, do not infer intent from `ours/theirs`: stage 2 is the so-far rebased series at current HEAD, beginning at upstream, while stage 3 is the commit currently being replayed and identified by `REBASE_HEAD`. Name sides by those roles and by their source commits.

Account internally for each side's intent and evidence, shared invariants, compatibility, and the required final outcome. Every assigned intent has evidence.

Complete when every conflict is either evidence-resolvable or names the exact missing human decision.

## Reconcile each path

Preserve both intents when compatible. When they conflict, use the stated goal to select an evidence-supported outcome and note the trade-off out loud. The result does not invent new behavior absent from both sides. Accepted contracts may constrain or choose between evidence-supported outcomes; they do not authorize a third behavior during conflict resolution.

Whole-file selection is legal only when evidence shows the entire path belongs to one intent. Read every resolved file in full and stage exact resolved paths.

For generated files and lockfiles, reconcile their source of truth and then use the repository's canonical generator. Resolve binary, symlink, submodule, rename/delete, and file-mode conflicts from owner and intent evidence rather than pretending they are text hunks.

Complete when each resolved path implements its accounted outcome and no unrelated content changed.

## Pause on a real decision

Resolve every evidence-supported conflict first. For the earliest remaining ambiguity, leave the path unmerged and unstaged, preserve the active operation, and route one human decision through `recursive-grilling` with both intents, their evidence, and the evidence-supported options.

The agent never aborts on its own. An explicit human command may authorize the matching merge or rebase abort. Before abort, report what resolution work will be discarded. If abort fails, stop without `reset --hard`, `git clean`, or another destructive fallback.

When unrelated changes block continuation, route their disposition as a human decision. The agent never stashes, commits, moves, or removes them without that explicit authority.

Complete only when the decision lands or the operation remains safely paused with one precise question.

## Verify the reconciliation

Require zero unmerged entries. Account for every conflict-marker hit in changed files, inspect the final diff against both recovered intents, and run `git diff HEAD --check -- <resolved-paths>` so staged resolutions are checked without attributing unrelated paths to this operation. Discover and run the repository checks, normally typecheck, tests, and format or lint. A failed check returns to intent evidence; an unsupported repair pauses for the human instead of inventing behavior.

Accept a known failing check only from existing durable baseline evidence. If none exists, reproduce that exact check in a detached temporary worktree at the applicable pre-operation ref. The agent does not commit there. Remove only the verification worktree it created. If creation, reproduction, or cleanup is unsafe, the failure remains a blocker.

Complete when all checks pass or the identical accepted baseline failure is independently reproduced without changing the conflicted worktree.

## Finish the operation

For merge, create the merge commit under repository message policy. For rebase, run `rebase --continue` and repeat this process for every later conflict until Git reports completion. Recheck status, final HEAD, operation metadata, unrelated changes, and repository checks.

Return the final HEAD, recovered intents, trade-offs, checks, and preserved unrelated state. A paused result names the unresolved path, evidence, and one human decision. This skill does not push or force-push.

Complete only when the whole merge/rebase is finished and verified, or is safely paused at an irreducible human choice.

## Boundaries

`recursive-worktree` owns implementation workspace creation; the detached baseline worktree above is disposable verification only. Active Recursive artifacts retain requirements and decision ownership. Use `recursive-debugging` for unexplained behavior after Git has completed the operation. This skill creates no workflow phase, ledger, report artifact, memory, or compatibility surface.
