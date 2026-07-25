---
name: recursive-residue-sweep
description: 'Residue cleanup or inspection for text and names that require session or previous-version context. Use when the user asks to clean AI/session/changelog-like residue, asks for a read-only fresh-clone inspection, or the current implementation or another skill holds an accepted change set containing prose, comments, private names, or alternate code that may depend on that context.'
---

# Recursive Residue Sweep

**Residue** is text addressed to a reader who was there: someone who remembers the chat session, the previous version of the code, or the request that produced the change. Every future reader — human or agent — arrives from a **fresh clone**, with no memory of any of that. To them residue is noise, and worse: agents imitate the prose they find, so residue breeds residue.

**The fresh-clone test:** would this sentence carry the same meaning for someone who just cloned the repo and never saw an earlier version or any conversation? If understanding it requires remembering what the code *used to be* or what somebody *asked for*, it is residue.

## Where displaced content belongs

Residue is usually true information in the wrong place. Relocate before deleting:

| Content | Owner |
| --- | --- |
| What changed, and from what | Pending commit message |
| Why this approach over alternatives | ADR or PR description |
| A constraint the code cannot show | Timeless code comment |
| What the system does | Present-tense docs with no comparison |
| Praise, summaries, next-step promises | Nowhere — delete |

## Residue catalog

Each entry is a tell → fix pair.

- **Change narration** — "now handles X", "updated to use Y", "no longer throws", "this replaces the old parser". → State current behavior timelessly ("handles X"); the change story lives in the pending commit message.
- **Conversation deixis** — "as discussed", "per your request", "as requested", references to "the previous approach" that exists only in a chat. → Delete; if a real decision hides inside, record it in an authorized ADR or ticket first.
- **Reviewer-facing comments** — comments arguing the change is correct or safe: "this is fine because we already validated above", "fixed the off-by-one". → Delete; if the safety argument is a genuine invariant, state the invariant itself.
- **Temporal deixis** — "currently", "for now", "recently", "going forward", "new", "legacy" (with no counterpart). → The qualifier is either meaningless (delete it) or hides a known limitation (state the limitation timelessly; report the intended change to its tracker owner).
- **Comparative naming** — `parserV2`, `enhancedAuth`, `newClient`, `handleLoginFixed`, `utils_old`, `auth-new.ts`. Names that rank versions instead of describing behavior. → Rename to what the thing does. If the counterpart is gone, the qualifier is pure residue; if both still exist, that is an unfinished expand–contract — name each by role, not by age.
- **Fossilized alternatives** — commented-out blocks, `_old` functions kept "just in case", two implementations of the same thing left in the tree. → Delete the dead one; Git remembers.
- **Assistant voice** — "Note: I also added…", "Key improvements:", closing summaries, ✅/🎉, emoji section markers, enthusiasm ("robust", "seamless", "comprehensive") that describes no behavior. → Delete.
- **Demo hedging in production paths** — "in a real application you would…", "for simplicity we skip…", "this is just an example". → State the limitation timelessly, with its consequence, and report the gap; closing it is feature work for a ticket, never part of the sweep.

**Exempt:** the *historical narration* in files whose purpose is history or record — `CHANGELOG.md`, migration guides for external users, ADRs, tracker artifacts (tickets, PRDs, maps); there, "previously" is content, not residue. Conversation deixis pointing at an unrecorded chat ("as discussed") stays residue even in those files. Also exempt: files that are data rather than prose — test fixtures, snapshots, generated files, lockfiles. "Legacy" naming a real external format or compatibility path is a domain term, not residue.

## Process

### 1. Pin mode and scope

Select the mode from invocation intent and scope authority:

- **Inspection mode:** use when the caller requests report or review only, mutation authority is absent, or editable ownership cannot be separated. It makes no edits.
- **Cleanup mode:** use when the user names an editable scope, or when the current implementing agent or another authorized implementation owner holds its accepted change set. Fix safe residue in that scope.

Candidate classification never changes the mode. In cleanup mode, continue to fix safe residue while a semantic candidate, sealed artifact, or uncertain consumer surface is reported.

Default scope is what the current session changed. When another skill invokes the sweep, that accepted change set is the scope. Standalone, derive it from `git diff HEAD --name-only --diff-filter=d` plus `git ls-files --others --exclude-standard`, skipping symlinks — and if the working tree may hold work from before the session, confirm with the user what is editable before touching anything. If a file mixes the session's work with earlier work and the two cannot be separated, treat the ambiguous text as pre-existing. Read each scope file whole — residue only shows against its surroundings — but edit only text the session introduced (present in the diff, or anywhere in a new file). Pre-existing residue you notice on the way goes in the report, not the edit. When the user names paths or says the whole repo, that set is the scope and everything in it is editable.

Complete when every scoped path has a known mode and edit boundary.

### 2. Bait, then read

Bait with searches, but treat hits as candidates, never verdicts. Prefer `rg` (respects `.gitignore`); fall back to `git grep -iE` over tracked files:

```sh
rg -ni '\b(as discussed|as requested|per your|as mentioned|previously|no longer|now (uses|handles|supports|returns|correctly)|updated to|refactored to|renamed from|moved from|this replaces|going forward|for now|key improvements|note that)\b' <scope files>
rg -n '\b\w+(V2|_old|_new|_final|Enhanced|Improved|Fixed|Legacy|Temp)\b' <scope files>
```

Then read every scope file in full — the worst residue (assistant voice, closing summaries, fossilized blocks) matches no pattern. Apply the fresh-clone test sentence by sentence, comment by comment, name by name. Re-run the bait patterns after cleanup.

Complete when every scoped file was read and every bait hit is exempt, fixed, or reported with a one-line reason it stays.

### 3. Fix per catalog

Apply the catalog fix for each finding: delete, rewrite timelessly, or relocate to its owner. Relocate only into artifacts within the authorized scope or the pending commit message; when the owner lives elsewhere, report the suggested destination instead of writing there. **The sweep preserves behavior** — it edits prose, comments, private names, and dead text, never semantics. Public or exported names, serialized fields, persisted data, configuration keys, wire formats, uncertain dynamic names, and session-new forms of those surfaces are semantic and report-only. Rename or delete only repo-private identifiers, and first find every static, string, and dynamic reference; any remaining doubt means report instead of edit. When a sentence might carry an undocumented decision with no owner artifact yet, surface it to the user instead of guessing. After code or name edits, run the relevant typecheck and tests covering the touched files.

Use these cleanup-mode dispositions:

| Candidate | Disposition |
| --- | --- |
| Pure private comparative names with both implementations live | Rename each by role after reference accounting; never rank by age. |
| Demonstrably dead private fossil | Delete it; Git retains history. |
| Accepted protected transition or real external compatibility/domain term | Exempt from cleanup. |
| Compatibility/versioning machinery without a cited accepted transition | Report to its requirements, design, or review owner; neither delete it nor declare that no consumer exists. |
| Live semantic compatibility path or uncertain consumer surface | Report-only; never rename or delete it in the sweep. |
| Content sealed by its owning contract or explicit metadata | Report; infer sealing from that authority, never from ordinary wording alone. |

Complete when every actual finding is deleted, rewritten, relocated, or reported, and fixable authorized residue is fixed rather than parked.

### 4. Return durable accounting

Report every finding with path, evidence, and exactly one disposition: deleted, rewritten, relocated, or reported. Exemptions are accounted for but are not findings. "Reported" is reserved for pre-existing residue and genuinely blocked items.

Keep a report-only design candidate in the owning caller's normal durable channel: an `F-*` during review, the active requirements or design artifact during authoring, or the implementation handoff before commit. In standalone use, return it explicitly to the human with a proposed owner; create no owner artifact without authorization.

Finish only when every scoped file was read, every session-introduced sentence, comment, and name passes the fresh-clone test or is exempt, every pre-existing observation is reported unchanged, every bait hit is accounted for, and every actual finding has exactly one disposition.
