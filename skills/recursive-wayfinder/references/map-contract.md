# Wayfinder map contract

Use one tracked discovery tree:

The canonical map document is `/.recursive/maps/<map-id>/MAP.md`.

```text
/.recursive/maps/<map-id>/
├── MAP.md
├── units/<unit-id>.md
├── evidence/<unit-id>/
└── promotions/<slice-id>.md
```

Every `<map-id>`, `<unit-id>`, and `<slice-id>` is a unique kebab-case slug. A Markdown link uses the target document's `#` title as its text; narration refers to that title rather than a bare id.

The `promotions` directory appears with the first promotion record; a map with no promotions does not need an empty directory.

## MAP.md

The map is an index, not a store. A decision's detail lives in its unit; slice readiness lives in its promotion record. Keep `MAP.md` at low resolution:

```markdown
# <Map name>
Status: active | complete | stopped
Created: <YYYY-MM-DD>
Updated: <YYYY-MM-DD>

## Destination
<What clear enough to hand off looks like.>

## Notes
<Domain; skills every session should consult; standing preferences for this effort.>

## Decisions so far
- [<resolved unit name>](units/<unit-id>.md) — <one-line gist>

## Candidate slices
- [<slice name>](promotions/<slice-id>.md) — <outcome gist>

## Not yet specified
<In-scope fog whose question is not sharp yet.>

## Out of scope
<Work beyond the destination, never future fog.>
```

`complete` means no useful wayfinding remains. It is not product completion. `stopped` records a discovery effort the human deliberately stopped, abandoned, or parked.

The frontier is computed from unit files; do not cache it in `MAP.md`.

## Discovery unit

A discovery unit is one sharp question sized to one invocation. If the question cannot yet be stated precisely, keep it under `Not yet specified`. Use:

```markdown
# <Unit name>
Kind: research | prototype | grilling | unblocker
Mode: HITL | AFK
Status: open | claimed | resolved | out-of-scope
Claimed by: none | <agent-or-human label>
Claimed at: none | <claim timestamp profile>
Blocked by: none | [<unit name>](<unit-id>.md), ...

## Question
<One decision or investigation.>

## Resolution
<Answer or work performed.>
Outcome: pending | resolved | inconclusive

## Evidence
<Pointers to assets and authorization.>

## Consequences
<What becomes sharp, graduates from fog, or changes on the map.>
```

Status owns lifecycle and out-of-scope. Outcome is epistemic: use `pending` unless Status is `resolved`; a resolved unit uses `resolved` or `inconclusive`. Claim before work. An `open` unit is unclaimed; a `claimed` unit has both claimant and a timestamp in the claim timestamp profile: full date, `T`, hour `00`–`23`, minute and second `00`–`59`, optional fractional seconds, and a required `Z` or `±HH:MM` timezone. This profile is based on RFC3339 but deliberately excludes leap seconds. Closed statuses clear both claim fields. A stale claim is cleared only by the human.

The frontier is every `open`, unclaimed unit whose blockers are all `resolved`, ordered lexically by unit id/filename. Resolve at most one frontier unit per invocation.

Kinds route work:

- `research` / AFK → `recursive-research`;
- `prototype` / HITL → `recursive-prototype`;
- `grilling` / HITL → `recursive-grilling`; the human speaks for themselves;
- `unblocker` / HITL or AFK → perform only work needed to unblock a decision.

An unblocker delivers no R# or feature. Change tracked files only on explicit human instruction, record that instruction in the unit's Resolution or Evidence, and keep the change strictly enabling—never product delivery.

For a prototype unit, `evidence/<unit-id>/prototype/<slug>.md` contains the report and pointer only. Prototype source stays on its throwaway branch and never enters the map tree. Research reports belong under `evidence/<unit-id>/research/<slug>.md`.

## Promotion record

Use a separate `promotions/<slice-id>.md`:

```markdown
# <Slice name>
Status: proposed | approved | promoted | rejected | superseded
Source map: ../MAP.md
Source units:
- [<unit name>](../units/<unit-id>.md)

## Outcome boundary
<One run-sized user outcome.>

## Settled inputs
<Gists with pointers; not copied requirements.>

## Evidence
<Pointers.>

## Remaining unknowns
Blocking: none | <explicit blockers>
Non-blocking:
<Known residual fog acceptable beyond this slice.>

## Out of scope
<Inherited boundary.>

## Spec handoff
Human approval: pending | <human and approval record>
Suggested run id: <slug | none>
Promoted to: none | <kebab-case run-id> | /.recursive/deliveries/<delivery-id>/spec.md
```

Only a record with `Blocking: none` may become `approved` or `promoted`. Human approval owns the transition to `approved`. Every record has exactly one `Promoted to` field: non-promoted records use `none`, while `promoted` uses either one kebab-case run id or one canonical `/.recursive/deliveries/<delivery-id>/spec.md` pointer. Multiple fields or values, URLs, and other paths are invalid. The record seeds `recursive-spec`; it does not create a run, write requirements, or track implementation.
