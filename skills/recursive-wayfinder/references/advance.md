# Advance a map

1. Read `MAP.md` at low resolution and run `wayfinder_map.py frontier`.
2. Use the human-named unit, or the first frontier result in lexical unit-id/filename order. Claim it before any work by setting Status, claimant, and timestamp.
3. Resolve exactly one unit through its owning skill. A HITL unit remains unresolved until the human speaks for themselves.
4. Record Resolution, Outcome, Evidence, and Consequences. Clear the claim and set the lifecycle Status.
5. Add one gist and pointer under `Decisions so far` only for a resolved route decision. Put an out-of-scope unit only under `Out of scope` as a link with a short gist and the reason it is out of scope.
6. Graduate newly sharp fog into new units, remove each graduated patch from `Not yet specified`, wire blockers after creating the units, update or supersede invalidated map entries, validate, and stop.

Complete when exactly one claimed unit has a legal disposition, its map consequences are indexed without duplicated detail, and `validate` passes.
