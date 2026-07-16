# Promote a slice

1. Select one coherent, run-sized outcome supported by resolved units. State remaining blocking and non-blocking unknowns explicitly.
2. Create one promotion record with Status `proposed | approved | promoted | rejected | superseded`. A proposal begins as `proposed`.
3. Run `validate`. Promotion readiness requires `Blocking: none` and resolved source units.
4. Ask for human approval. Only the human moves the record to `approved`.
5. Hand the approved promotion record and its linked units to `recursive-spec`. It is a seed: `recursive-spec` re-derives and obtains approval for requirements.
6. After the approved spec creates a run, move the record to `promoted` and write its one `Promoted to` pointer.

Promotion does not create a run or requirements. The map never tracks the run's phases or implementation.

Complete when the slice is rejected/superseded with a disposition, approved for spec handoff, or promoted with one handoff pointer, and `validate` passes.
