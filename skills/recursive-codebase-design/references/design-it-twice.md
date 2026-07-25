# Design It Twice

For a costly or hard-to-reverse interface, or on explicit human request, use this parallel subagent pattern. Based on "Design It Twice" (Ousterhout) — your first idea is unlikely to be the best.

Use the vocabulary in [module-design.md](module-design.md) — **module**, **interface**, **seam**, **adapter**, **leverage** — plus approved terms from `/.recursive/memory/GLOSSARY.md` when it exists.

## Process

### 1. Frame the problem space

Before spawning subagents, write a user-facing explanation of the problem space:

- The constraints any new interface would need to satisfy
- The dependencies it would rely on, and which category they fall into (see [deepening.md](deepening.md))
- A rough illustrative code sketch to ground the constraints — not a proposal, just a way to make the constraints concrete

Show this to the human, then immediately proceed to Step 2. The human reads and thinks while the subagents work in parallel.

Complete when every material constraint and dependency is classified and the grounding sketch introduces no proposed solution.

### 2. Spawn subagents

Spawn 3+ independent subagents in parallel. A controller or harness may co-start them; independence of context and brief is the requirement. Each must produce a **radically different** interface.

Prompt each subagent with a separate technical brief (file paths, coupling details, dependency category from [deepening.md](deepening.md), what sits behind the seam). The brief is independent of the user-facing problem-space explanation in Step 1. Give each agent a different design constraint:

- Agent 1: "Minimize the interface — aim for 1–3 entry points max. Maximise leverage per entry point."
- Agent 2: "Maximise flexibility — support many use cases and extension."
- Agent 3: "Optimise for the most common caller — make the default case trivial."
- Agent 4 (if applicable): "Design around ports & adapters for cross-seam dependencies."

Include both [module-design.md](module-design.md) vocabulary and approved GLOSSARY vocabulary in the brief so each subagent names things consistently with the architecture language and the project's domain language. Treat competing loose substitutes for approved vocabulary as findings and repair them before comparison.

Each subagent outputs:

1. Interface (types, methods, params — plus invariants, ordering, error modes)
2. Usage example showing how callers use it
3. What the implementation hides behind the seam
4. Dependency strategy and adapters (see [deepening.md](deepening.md))
5. Trade-offs — where leverage is high, where it's thin

If the controller cannot start three independent agents in parallel, report the branch as blocked and return control. Do not substitute sequential rewrites from the same context.

Complete when at least three independently produced alternatives contain all five required elements and use the approved vocabulary.

### 3. Present and compare

Present designs sequentially so the human can absorb each one, then compare them in prose. Contrast by **depth** (leverage at the interface), **locality** (where change concentrates), and **seam placement**.

After comparing, give your own recommendation: which design you think is strongest and why. If elements from different designs would combine well, propose a hybrid. Be opinionated — the human wants a strong read, not a menu. Route any unresolved human decision through `recursive-grilling`.

Complete when one design or hybrid is recommended with explicit reasons and every unresolved human decision has a route.
