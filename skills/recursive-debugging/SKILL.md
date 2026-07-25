---
name: recursive-debugging
description: 'Debug hard bugs and performance regressions through a tight diagnosis loop. Use when the user says "diagnose" or "debug this", reports something broken, throwing, failing, or slow, or a recursive-mode requirement needs root-cause analysis before any fix.'
---

# Recursive Debugging

A discipline for hard bugs. The tight feedback loop is the debugging method; bisection, hypothesis testing, and instrumentation consume it. Phase 1.5 is the single local owner for root-cause evidence.

Spend disproportionate effort on the loop. **Be aggressive. Be creative. Refuse to give up.**

```text
NO FIXES WITHOUT A RED-CAPABLE COMMAND AND A CONFIRMED ROOT CAUSE
```

## Establish Phase 1.5

Insert `01.5-root-cause.md` between locked Phase 1 and Phase 2 for a bug, test failure, unexpected behavior, integration failure, or performance regression. Use [references/phase-1-5-artifact.md](references/phase-1-5-artifact.md) for the artifact contract and preserve the canonical review metadata.

Read the relevant repository instructions, `CONTEXT.md` when present, local ADRs, Phase 1 evidence, and the reported symptom. Read errors, warnings, and stack traces completely and record exact locations. Inspect relevant commits, dependencies, configuration, and environment without turning recency into a causal claim.

Complete when Phase 1.5 has a declared artifact, inputs, and exact symptom.

## Build the loop before causal theory

Load [references/tight-feedback-loop.md](references/tight-feedback-loop.md) and follow it in order. Before causal theory, name one command already run and preserve its invocation plus red output. The command must detect the reported symptom, not a nearby failure.

Use the cheapest viable loop from the reference. A human-driven loop is the last resort and uses [scripts/hitl-loop.template.sh](scripts/hitl-loop.template.sh); keep the agent responsible for running the script and capturing its structured result.

Complete when the command is red-capable, deterministic or has a pinned high reproduction rate, fast enough for repeated probes, and agent-runnable.

## Reproduce and minimise

Run the loop repeatedly, confirm the exact symptom, and remove inputs, callers, configuration, data, and steps one at a time. Retain only what changes the verdict.

Complete when every remaining element is load-bearing and the artifact records the reproduction command, output, rate, and minimal scenario.

## Trace the failure

Use the artifact's Error Analysis, Recent Changes Analysis, Evidence Gathering, Data Flow Trace, and Pattern Analysis sections before ranking causes. In a multi-component path, capture input, output, configuration, and state at each boundary until the failure boundary is visible. For a deep error, trace the bad value or state backward to its source. Compare working and broken examples, relevant dependencies, and every difference that could explain the symptom.

Complete when the failure boundary or source is evidenced and every material working/broken difference is accounted for without becoming an untested causal claim.

## Test ranked hypotheses

Generate 3–5 ranked hypotheses with a falsifiable prediction for each, show the ranking to the human without blocking an AFK run, then activate one hypothesis at a time. Map every probe to its prediction and change one variable. If the ranking is exhausted, regenerate it from the new evidence or tighten the loop; do not stack speculative changes.

Use a debugger first, then tagged targeted diagnostics. Performance work uses measurement, profiling or query plans, and bisection rather than general logs.

Complete when one hypothesis explains the red signal, its prediction is confirmed by the loop, and the competing explanations are rejected strongly enough to state the causal chain.

## Record the root cause

Record the confirmed cause, source location, causal chain, evidence, Phase 2 fix strategy, and regression-test seam. If no correct seam can reproduce the real bug pattern, record that absence as an architectural finding for planning and review; a shallow test that cannot catch the bug is not a substitute.

Phase 1.5 diagnoses and preserves evidence. Before its lock, remove every tagged diagnostic and delete each throwaway harness or preserve it as bounded evidence. Phase 2 owns the fix plan, and Phase 3 with `recursive-tdd` writes the regression test red before changing production behavior. After the fix, re-run both the original unminimised loop and the regression test. The implementation handoff carries two post-fix obligations: state the confirmed hypothesis in the pending commit or PR message so the next debugger learns, then ask what would have prevented the bug and route concrete architecture work to `recursive-codebase-design` only after the fix has supplied the missing evidence.

Complete when `01.5-root-cause.md` passes Coverage and Approval, is reviewed through the canonical lossless ledger, and can be locked before Phase 2.

## Routing awareness

Before delegated log inspection or diagnosis, re-read the current recursive router configuration and transport only bounded evidence. Delegated conclusions remain claims until the controller checks the command, output, and repository.
