# Program design and conditional observability

Shape execution below system diagrams and above private-function pseudocode. Use the interfaces and seams defined by [module-design.md](module-design.md); this file owns execution across them.

## Execution shape

Specify only the material flow:

- critical call path and allowed variants;
- cross-interface invariants and ordering;
- ownership and lifecycle of objects and state;
- data flow and transformations;
- error propagation, mapping, and recovery between seams;
- placement of unavoidable side effects;
- transaction or commit points when they matter;
- responsibilities inside execution;
- testing consequences caused by the flow that the interface does not already determine.

Route interface changes and weak seams back through [module-design.md](module-design.md). Route competing domain language through `recursive-domain-modeling`.

## Factoring risks

Evaluate only risks evidenced by the current flow; use repository standards for technology-specific conventions:

- poorly factored responsibilities;
- tramp data;
- scattered error handling;
- implicit shared state;
- leaky abstractions revealed by the flow.

Treat overloaded interfaces and weak seams as module-design findings. Treat inconsistent domain language as a domain-modeling finding.

## Conditional observability contract

Select observability points among system edges, external calls, critical operations, nondeterministic steps, and declared failure paths.

For each selected point, record:

- the diagnostic question it answers;
- expected execution invariants;
- required spans, events, or metrics;
- allowed variants under retry, concurrency, or nondeterminism;
- redaction for secrets, credentials, headers, environment values, and PII;
- limits for cost, cardinality, payload, sampling, storage, and performance.

Instrument proportionately; every observation must answer a stated diagnostic question. Compare expected and actual invariants and required observations without demanding an identical call stack.

Phase 3 implements planned instrumentation. Phase 3.5 checks it against the design. Phase 4/5 may capture actual traces as evidence. Phase 8 promotes only durable or repeated mismatches into memory.
