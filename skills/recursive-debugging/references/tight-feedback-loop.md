# Tight feedback loop

This reference owns diagnostic coverage. The parent skill owns Phase 1.5 placement and the artifact; `recursive-tdd` owns implementation-time RED and the fix.

## 1. Build a red-capable command

**This is the skill.** Everything else is mechanical. If you have a **tight** pass/fail signal for the bug — one that goes red on *this* bug — you will find the cause; bisection, hypothesis-testing, and instrumentation all just consume it. If you don't have one, no amount of staring at code will save you.

Spend disproportionate effort here. **Be aggressive. Be creative. Refuse to give up.**

Try these loops in roughly this order:

1. **Failing test** at whatever seam reaches the bug — unit, integration, e2e.
2. **Curl / HTTP script** against a running dev server.
3. **CLI invocation** with a fixture input, diffing stdout against a known-good snapshot.
4. **Headless browser script** (Playwright / Puppeteer) — drives the UI, asserts on DOM/console/network.
5. **Replay a captured trace.** Save a real network request / payload / event log to disk; replay it through the code path in isolation.
6. **Throwaway harness.** Spin up a minimal subset of the system (one service, mocked deps) that exercises the bug code path with a single function call.
7. **Property / fuzz loop.** If the bug is "sometimes wrong output", run 1000 random inputs and look for the failure mode.
8. **Bisection harness.** If the bug appeared between two known states (commit, dataset, version), automate "boot at state X, check, repeat" so you can `git bisect run` it.
9. **Differential loop.** Run the same input through old-version vs new-version (or two configs) and diff outputs.
10. **HITL bash script.** Last resort. If a human must click, drive *them* with `../scripts/hitl-loop.template.sh` so the loop is still structured. Captured output feeds back to you.

Build the right feedback loop, and the bug is 90% fixed.

### Tighten the loop

Treat the loop as a product. Once you have *a* loop, **tighten** it:

- Can I make it faster? (Cache setup, skip unrelated init, narrow the test scope.)
- Can I make the signal sharper? (Assert on the specific symptom, not "didn't crash".)
- Can I make it more deterministic? (Pin time, seed RNG, isolate filesystem, freeze network.)

A 30-second flaky loop is barely better than no loop; a 2-second deterministic one is tight — a debugging superpower.

### Non-deterministic bugs

The goal is not a clean repro but a **higher reproduction rate**. Loop the trigger 100×, parallelise, add stress, narrow timing windows, inject sleeps. A 50%-flake bug is debuggable; 1% is not — keep raising the rate until it's debuggable.

### When you genuinely cannot build a loop

Stop and say so explicitly. List what you tried. Ask the user for: (a) access to whatever environment reproduces it, (b) a captured artifact (HAR file, log dump, core dump, screen recording with timestamps), or (c) permission to add temporary production instrumentation. Do **not** proceed to hypothesise without a loop.

### Completion criterion — a tight loop that goes red

The loop step is done when you can name **one command** that you have **already run at least once**, preserve its invocation and output, and prove that it is:

- **Red-capable** — it drives the actual bug code path and asserts the **user's exact symptom**, so it can go red on this bug and green once fixed. Not "runs without erroring" — it must be able to catch this specific bug.
- **Deterministic** — same verdict every run; for a flaky bug, use a pinned high reproduction rate.
- **Fast** — seconds, not minutes.
- **Agent-runnable** — the agent can run it unattended; a human participates only through `../scripts/hitl-loop.template.sh`.

If you catch yourself reading code to build a theory before this command exists, **stop — jumping straight to a hypothesis is the exact failure this skill prevents.** No red-capable command, no causal theory.

## 2. Reproduce and minimise

Run the loop. Watch it go red — the bug appears.

Confirm:

- The loop produces the failure mode the **user** described — not a different failure that happens to be nearby. Wrong bug = wrong fix.
- The failure is reproducible across multiple runs, or reproducible at a high enough rate to debug against.
- You have captured the exact symptom (error message, wrong output, slow timing) so later phases can verify the fix actually addresses it.

Once it's red, shrink the repro to the **smallest scenario that still goes red**. Cut inputs, callers, config, data, and steps **one at a time**, re-running the loop after each cut — keep only what's load-bearing for the failure.

A minimal repro shrinks the hypothesis space and identifies the clean regression seam.

Complete when **every remaining element is load-bearing** — removing any one of them makes the loop go green or stops it from exercising the real bug path.

## 3. Rank, then probe

Generate **3–5 ranked hypotheses** before testing any of them. Single-hypothesis generation anchors on the first plausible idea.

Each hypothesis must be **falsifiable**: state the prediction it makes.

> Format: "If <X> is the cause, then <changing Y> will make the bug disappear / <changing Z> will make it worse."

If you cannot state the prediction, the hypothesis is a vibe — discard or sharpen it.

**Show the ranked list to the user before testing.** They often have domain knowledge that re-ranks instantly, or know hypotheses they've already ruled out. Cheap checkpoint, big time saver. Don't block on it — proceed with your ranking if the user is AFK.

After ranking, activate one hypothesis at a time. Each probe maps to that hypothesis's prediction and changes one variable. A rejected hypothesis advances to the next ranked entry without accumulating its diagnostic mutation. If all entries are rejected, regenerate the ranking from the new evidence or tighten and minimise the loop again.

Complete when the loop confirms one prediction and rejects the competing explanations strongly enough to state the causal chain.

## 4. Instrument at discriminating boundaries

Each probe must map to a specific prediction. **Change one variable at a time.**

Tool preference:

1. **Debugger / REPL inspection** if the environment supports it. One breakpoint beats ten logs.
2. **Targeted logs** at the boundaries that distinguish hypotheses.
3. Never "log everything and grep".

**Tag every debug log** with a unique prefix, e.g. `[DEBUG-a4f2]`. Remove every tagged diagnostic that the investigation introduced before the Phase 1.5 lock.

Untagged logs survive; tagged logs die.

**Perf branch.** For performance regressions, logs are usually wrong. Instead: establish a baseline measurement (timing harness, `performance.now()`, profiler, query plan), then bisect. Measure first, fix second.

Complete when every probe has one prediction, one changed variable, and captured evidence, with temporary instrumentation accounted for.

## 5. Preserve the regression seam

Write the regression test **before the fix** — but only if there is a **correct seam** for it.

A correct seam is one where the test exercises the **real bug pattern** as it occurs at the call site. If the only available seam is too shallow (single-caller test when the bug needs multiple callers, unit test that can't replicate the chain that triggered the bug), a regression test there gives false confidence.

**If no correct seam exists, that itself is the finding.** The codebase architecture is preventing the bug from being locked down. Carry the concrete gap into Phase 2 and the review ledger.

Phase 1.5 records the exact future failing test and its expected red signal. Phase 3 writes it before the fix through `recursive-tdd`, then re-runs the original unminimised loop after GREEN.

Complete when the regression seam is concrete or its architectural absence is durably owned, and the original loop remains the end-to-end verification.
