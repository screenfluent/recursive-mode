# Lossless Finding Protocol

Load this reference before producing, repairing, or accepting a review. This installed reference is the sole owner of finding records, dispositions, snapshots, and multipass closure.

## Review output

Output has exactly these top-level sections in this order:

```markdown
## Review Scope

## Findings

## Verdict
```

All technical review content belongs inside an `F-*` record. Severity, human effort, duration, story points, and perceived author workload are absent from the schema. A finding derives from an owning contract, a currently supported surface, or an observable risk in the declared operating context. A hypothetical future environment does not create a finding.

### Review Scope

```markdown
## Review Scope

- Review ID: <review-id>
- Pass: <NNNN>
- Ledger Path: `/<canonical-ledger-path>`
- Previous Pass: none | `/<canonical-pass-snapshot>`
- Previous Pass Hash: none | <normalized-sha256>
- Reviewed Artifact: `/<path>`
- Artifact Hash: <sha256>
- Diff Basis: <executable basis or canonical bundle pointer>
- Changed Files:
  - `/<path>`
- Evidence Basis:
  - `/<path>`
```

Every field is required. Pass numbers are zero-padded and consecutive. Pass `0001` alone uses `none` for previous-pass fields. Use `none` for lists only when the owning review contract proves the list is empty. Evidence Basis normally contains paths. When the code-review inspection profile exhausts repository discovery and the caller confirms that no originating specification exists, include the exact `no spec available` item in this list; it is structured scope accounting, not a finding or free prose.

### Finding

```markdown
### F-001

- Discovered in pass: 0001
- Kind: contract-violation
- Location: `path:line-or-symbol`
- Observed: <falsifiable current state>
- Expected: <falsifiable required state>
- Contract: <owning source or technical invariant>
- Technical impact: <system effect, regression risk, complexity, or maintenance consequence>
- Required outcome: <observable repaired state>
- Verification: <command, assertion, artifact, or inspection>
- Depends on: none
- Disposition: open
- Claimed outcome: none
- Claimed changes: none
- Claimed verification: none
- Controller verification: none
```

IDs are protocol-level append-only and are never deleted, renumbered, reused, or regenerated in a valid later ledger. Fixed technical fields are `Discovered in pass`, `Kind`, `Kind justification` when present, `Location`, `Observed`, `Expected`, `Contract`, `Technical impact`, `Required outcome`, `Verification`, and `Depends on`. While a finding is `open`, only `Claimed outcome`, `Claimed changes`, and `Claimed verification` are mutable claim fields. After `Disposition` becomes anything other than `open`, the entire finding record, including every disposition-specific, claim, destination, ownership, approval, decision, and controller-verification field, is fixed in every valid later working ledger and pass. Corrections become new findings or controller rejection; terminal records are never rewritten under the protocol.

Every nonblank line inside an `F-*` record is one field from the exact disposition-specific schema. Free prose, nested headings, malformed bullets, and unrecognized fields make the ledger invalid.

Legal `Kind` values are:

- `contract-violation`
- `missing-evidence`
- `plan-drift`
- `test-gap`
- `security`
- `contract-ambiguity`
- `other`, with `Kind justification`

The reviewer performs enough legwork to fill `Observed`, `Expected`, and `Verification`. A genuine conflict between authorities is `contract-ambiguity` and remains open until one authority is established.

`Depends on` names only a true repair prerequisite: the referenced finding's required outcome must land before this finding can be repaired. It never records mere relationship, shared location, or a preferred sequence. Independent findings use `none`. When production code must not change before a missing regression or contract test is established, the code-fix finding depends on the test-gap finding, not the reverse. A finding may become `fixed` only when every dependency is itself `fixed`; another terminal label does not prove the prerequisite outcome landed. Satisfy repair prerequisites first, then choose among ready findings by stable `F-*` order. Slice 2 mechanically validates missing references, self-dependencies, cycles, and prerequisite completion.

### Verdict

```markdown
## Verdict

- Result: PASS|FAIL
- Open Findings: none | F-001, F-002
- Pending Scheduled Handoffs: none | F-003
- Controller: none | <controller identity>
- Verified Pass: none | `/<canonical-pass-snapshot>`
- Verified Pass Hash: none | <normalized-sha256>
```

Working ledgers use FAIL and `none` for Controller, Verified Pass, and Verified Pass Hash. A working FAIL may have zero open findings when a next-pass transition copies an all-terminal prior snapshot. A completed snapshot names the controller, itself, and its hash; completed FAIL must identify at least one open finding. PASS requires no open finding and no due unconsumed scheduled handoff.

## Claims and dispositions

The reviewer creates `Disposition: open`. A repair agent may update only claim fields:

- `none` requires changes and verification to remain `none`.
- `fixed` requires concrete changed paths and reproducible verification.
- `blocked` requires concrete blocking evidence and is not terminal.

Only the controller assigns a terminal disposition after checking the real repository and evidence per row. The controller may reject a proposed outcome when permanent system complexity, maintenance burden, or regression surface is not justified by contracted benefit.

- `fixed` — required outcome independently verified.
- `rejected` — false positive, duplicate, supersession, contradiction, or verified system harm.
- `scheduled` — active-run-only transfer to work already owned by a later phase.
- `deferred` — human-approved obligation with owner and human-selected tracked pointer.
- `out-of-scope` — explicit human scope decision with durable pointer.

Disposition-specific fields appear immediately after `Disposition` and before claim fields:

- `open` and `fixed` add no fields.
- `rejected` adds `Disposition rationale`.
- `scheduled` adds `Owner phase`, `Scheduling basis`, `Destination`.
- `deferred` adds `Disposition rationale`, `Owner`, `Human approval`, `Destination`.
- `out-of-scope` adds `Disposition rationale`, `Human decision`, `Destination`.

Labels never close a finding. A delegated PASS, commit message, action record, or test report remains a claim until controller verification.

`/.recursive/scripts/recursive_review_action.py` is the single parser and validator for persisted action-record claims. Every record cites the exact canonical protocol, hash-bound bundle, ledger, and four-digit pass. `## Claimed Findings` has one exact ordered schema: those four metadata fields, followed by either `Claims: none` or sorted `F-*` records containing only `Claimed outcome`, `Claimed changes`, and `Claimed verification` in that order. Residual prose, unknown bullets/headings, terminal disposition/controller fields, duplicate metadata, and reordered fields are invalid. Each claim must exist and remain `open` in that validated ledger/pass; cross-ledger or manually tampered claims are invalid. Generation, lint, and status consume this owner rather than duplicating claim parsing.

Scheduled work follows the exact inventory contract below. Standalone reviews cannot schedule. Local ledgers, chat, memory, and known-repair Wayfinder units are not durable deferral destinations.

## Scheduled work

`scheduled` is legal only inside an active recursive run and only when `RECURSIVE.md` already assigns the required outcome to a phase strictly later than the classified source artifact in the canonical phase rules. Scheduling uses its own complete canonical artifact/key registry, separate from audited-ledger ownership, so non-ledger Phase 5 has the scheduling key `phase-5`. A controller-valid pending inventory activates that owner for this run, including an optional owner whose artifact has not been scaffolded yet. An invalid or falsely consumed record continues to activate its canonical owner while also blocking validation, so corrupting consumption evidence cannot make the obligation disappear. Scheduling cannot move Phase 3 repair into Phase 4 merely because the repair list is long.

A scheduled finding adds `Owner phase`, `Scheduling basis`, and `Destination` immediately after `Disposition: scheduled`. `Owner phase` is a later canonical artifact filename. `Scheduling basis` cites the existing ownership rule in `/.recursive/RECURSIVE.md`. `Source Ledger` and `Destination` are canonical in-repository paths whose complete component chains contain no symlink, reparse point, junction, or lexical escape; validation rejects a noncanonical address before reading it. `Destination` is exactly:

- `/.recursive/run/<run-id>/evidence/reviews/scheduled/<owner-phase-key>/inventory.md`

The inventory has one deterministic record per source finding:

```markdown
# Scheduled Finding Handoff Inventory

## <review-id>/F-001

- Source Ledger: `/.recursive/run/<run-id>/evidence/reviews/<source-phase-key>/<review-id>/ledger.md`
- Finding ID: F-001
- Kind: <copied fixed value>
- Location: <copied fixed value>
- Observed: <copied fixed value>
- Expected: <copied fixed value>
- Contract: <copied fixed value>
- Technical impact: <copied fixed value>
- Required outcome: <copied fixed value>
- Verification: <copied fixed value>
- Owner phase: <later artifact filename>
- Scheduling basis: <copied ownership citation>
- Status: pending | consumed
- Consumed in: none | `/.recursive/run/<run-id>/<owner-phase>`
- Consumption record: none | <review-id>/F-001
- Evidence Path: none | `/<canonical-repo-path>`
- Evidence Hash: none | <sha256>
- Controller verification: none | <target-phase verification>
```

Every copied obligation field equals its source finding. `pending` uses `none` for all five consumption fields: `Consumed in`, `Consumption record`, `Evidence Path`, `Evidence Hash`, and `Controller verification`. `consumed` names an existing canonical regular non-symlink owner artifact, records the exact `<review-id>/F-*` backreference in both the inventory and owner artifact, and cites an existing canonical regular non-symlink evidence file plus its matching SHA-256 and controller verification. `Pending Scheduled Handoffs` records every scheduled finding emitted by the completed hash-bound source pass; later inventory consumption never rewrites that pass under the protocol. A classified audited source phase may PASS with a valid pending handoff. The valid pending record makes its owner required and due in canonical status/prerequisite selection without precreating the artifact; the target cannot lock until the record is consumed, and final verification/closeout rejects every pending record. This dedicated evidence inventory does not propagate the full review ledger to the target phase.

## Canonical paths

Active audited phase:

- ledger: `/.recursive/run/<run-id>/evidence/reviews/<phase-key>/<review-id>/ledger.md`
- passes: `/.recursive/run/<run-id>/evidence/reviews/<phase-key>/<review-id>/passes/<NNNN>.md`
- hash-bound bundle: `/.recursive/run/<run-id>/evidence/review-bundles/<phase-key>/<review-id>/<NNNN>.md`

Standalone:

- ledger: `/.recursive/local/reviews/<review-id>/ledger.md`
- passes: `/.recursive/local/reviews/<review-id>/passes/<NNNN>.md`

The ledger is current operational state. Pass snapshots are hash-bound historical evidence, and a review bundle is only the reproducible review input. This chain is tamper-evident for partial or accidental drift while its hashes and references remain intact, but it is not cryptographically append-only against an actor that can rewrite the entire run. An external anchor, protected Git history, or controller-owned storage would provide that stronger guarantee separately.

`/.recursive/scripts/recursive_phase_rules.py` owns separate audited-ledger and scheduling artifact/key registries. `Review ID` is globally unique within the run, `Reviewed Artifact` and `Diff Basis` are the same-pass canonical hash-bound bundle, and `Artifact Hash` is its byte hash. `Changed Files` exactly equals the bundle snapshot's `changed` path projection (`none` only for an empty projection). `Evidence Basis` exactly equals that bundle followed by the snapshot's ordered reference-path projection; partial overlap is invalid. The bundle's changed-file section and normalized diff basis must themselves exactly agree with the embedded snapshot. For a working-tree comparison, `## Diff Basis` records both fixed JSON argv operations used for membership: `Tracked diff argv` is `["diff","--name-only","-z",<baseline>,"--"]` and `Untracked files argv` is `["ls-files","--others","--exclude-standard","-z"]`; a commit-to-commit comparison records the exact range in the tracked argv and `Untracked files argv: none`. These arrays are arguments to the fixed `git -C <repo-root>` executable boundary and are never shell commands. `Normalized diff command` remains a human-readable summary of only the tracked comparison; the two argv fields are authoritative for complete snapshot membership. The generator refuses bundle overwrite; every historical pass keeps its cited bundle and hash.

Every audited receipt has exactly `## Review Metadata` with fields in this order: `Review ID`, `Review Ledger Path`, `Latest Verified Pass`, `Latest Verified Pass Hash`, `Review Bundle Path`, `Review Bundle Hash`. The generic adapter verifies those pointers plus bundle phase/review/pass, `Artifact Path`, bundle hash, audit payload, and whole-ledger PASS.

Every bundle embeds one deterministic `recursive-review-surface-v1` snapshot. `/.recursive/scripts/recursive_review_surface.py` is the single owner used by bundle generation and validation: it binds changed-file membership (including untracked and deleted paths), file state, mode, bytes, and every local reviewed/evidence reference. Explicit reviewed/evidence references must resolve directly to regular files; directory, symlink, missing, and other non-regular references are invalid. Changed-surface symlinks remain valid link-state records whose target text, mode, and state are bound. It invokes Git only through fixed argument vectors and never executes a bundle-supplied shell command. Current-pass validation recomputes the snapshot, so any membership, byte, mode, deletion, or referenced-evidence change requires a refreshed bundle and next pass. Historical pass validation checks the hash-bound bundle and its hash without comparing old surface records to current repository bytes.

Audit payload profile `recursive-review-audit-payload-v1` normalizes line endings to LF and neutralizes only controller-derived `Status`, `LockedAt`, `LockHash`, exact Review Metadata field values, and exact `Audit`, `Coverage`, and `Approval` PASS/FAIL result lines. Author-owned audit, requirement, and diff content remains hashed. The bundle records raw artifact-content hash, audit payload hash, and profile.

## Pass snapshot hash

Hash the UTF-8 snapshot after normalizing CRLF/CR to LF and removing the entire `Verified Pass Hash` line including its trailing LF. All other content participates. Render the target `Verified Pass`, compute SHA-256, insert the hash, and write the snapshot once.

## Multipass

Initialize Pass `0001` with no previous pass, FAIL, and empty controller verification. Review before repair.

Complete Pass N:

1. Review the current snapshot, preserve prior records, and append new findings.
2. Controller-verify claims and write dispositions.
3. Target `passes/<NNNN>.md`, compute its normalized hash, and write it once.
4. Sync `ledger.md` byte-for-byte from the snapshot.
5. Update the phase artifact pointers. PASS only from whole-ledger state.

Begin Pass N+1 before any repair mutation:

1. Require completed snapshot N and verify its cited hash.
2. Copy it to `ledger.md`; increment Pass and cite snapshot N plus its actual hash.
3. Reset Verdict to FAIL with empty controller verification.
4. Reset claim fields to `none` only for open findings; terminal records retain history.
5. Allow repair claims and reviewed-surface changes.
6. Re-audit every prior ID, append new findings, and complete the new pass.

Any change to the reviewed diff, artifact, or evidence basis requires a new pass and refreshed bundle. A pass appends; it never regenerates the ledger.
