---
name: recursive-wayfinder
description: 'Map a foggy multi-session effort until a clear slice can reach recursive-spec.'
disable-model-invocation: true
---

# Recursive Wayfinder

Find a route through **fog of war** without delivering the destination. Keep a local map as an index of discovery, then hand a human-approved slice to `recursive-spec`.

## Open the map

Work only from an explicit human invocation. Use `/.recursive/maps/<map-id>/` and load [references/map-contract.md](references/map-contract.md) before reading or writing the map.

Choose exactly one mode:

- **Chart** a new map: load [references/chart.md](references/chart.md).
- **Advance** an existing map: load [references/advance.md](references/advance.md).
- **Promote** a clear slice: load [references/promote.md](references/promote.md).

State the mode and map id. Complete this step when one map and one mode are unambiguous.

## Preserve the unit boundary

Resolve exactly one discovery unit per invocation. Charting resolves no unit; promotion resolves no unit. A second unit requires another invocation.

Keep human-in-the-loop decisions with the human. Use `recursive-research`, `recursive-prototype`, or `recursive-grilling` for their matching unit kinds; route domain-language mutations through `recursive-domain-modeling`.

## Validate before close

Run from repository root with the available Python 3 launcher; use `python3` on macOS/Linux and `python` on Windows. The helper is read-only.

```sh
python3 "<SKILL_DIR>/scripts/wayfinder_map.py" validate ./.recursive/maps/<map-id>
python3 "<SKILL_DIR>/scripts/wayfinder_map.py" frontier ./.recursive/maps/<map-id>
```

```powershell
python "<SKILL_DIR>/scripts/wayfinder_map.py" validate ./.recursive/maps/<map-id>
python "<SKILL_DIR>/scripts/wayfinder_map.py" frontier ./.recursive/maps/<map-id>
```

`validate` is the skill's merge gate for map changes. It is not a Recursive phase lock and never routes through `recursive-lock`.

Complete the invocation only when validation passes, the changed map links resolve, and the mode-specific completion criterion holds.

## Boundaries

- The map owns pre-run discovery; it is an index, not requirements, product code, or an execution tracker.
- Product delivery leaves the map through a promotion record, human approval, and `recursive-spec`.
- A promoted map records one handoff pointer and never tracks run implementation.
- This skill creates neither a recursive run nor a recursive phase.
