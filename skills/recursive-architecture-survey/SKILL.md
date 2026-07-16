---
name: recursive-architecture-survey
description: 'Survey architecture health and deepening opportunities. Use when the user explicitly asks for an architecture survey, architecture health check, or deepening scan.'
---

# Recursive Architecture Survey

Surface architectural friction and evidence-supported deepening opportunities that improve testability and AI-navigability, then stop before design. Load [references/survey-contract.md](references/survey-contract.md) before scanning or writing the report.

## Start only on an explicit survey request

Require an explicit architecture-survey, architecture-health, or deepening-scan request. An ordinary code review, refactor request, phase or run closeout, one shallow module, or a generic request to improve code does not trigger a repository survey.

State the exact working directory and proposed scope in conversational terms. Ask one short question only when the scope is ambiguous. Complete this step when the snapshot, scope, exclusions, and governing owners are explicit.

## Trace organic friction

Build the reference's subsystem inventory to orient the scope and record exclusions, then use its organic exploration method; search hits are leads, not candidates. Read repository instructions, the glossary when it exists, relevant ADRs, and the architecture vocabulary owner named in the reference.

Apply the deletion test to every supported opportunity. Verify friction at actual call sites, tests, interfaces, or dependency paths. Delegation may help with bounded read-only exploration, but it is optional and its claims require controller verification.

Complete inspection when the scope and exclusions are accounted for and every reported candidate satisfies the reference's evidence schema. Zero supported candidates is a valid result.

## Render the temporary report

Write one offline HTML report in the operating system's temporary directory, outside the workspace. Use the exact report and candidate contract from the reference. Show current structure in a before diagram and only the desired responsibility concentration in an outcome diagram.

Open the report when the environment supports it; otherwise return its exact path. Summarize only the candidate count and, when one exists, the top recommendation, then ask which candidate, if any, the user wants to explore.

Complete reporting when the report is verified offline, every local pointer resolves, and the worktree is unchanged.

## Route one selected candidate

Use `recursive-grilling` to decide whether a selected opportunity should become work and what outcome matters. Route language changes through `recursive-domain-modeling`. Send an approved change to `recursive-spec`; only the resulting Recursive Phase 2 may use `recursive-codebase-design` to propose concrete interfaces, seams, modules, or migration steps.

An ADR may be offered only through the existing local ADR gate and explicit human approval. A deferred candidate needs a human-selected durable owner. The temporary report is not a backlog and creates no obligation.

Complete selection when the candidate is rejected, durably deferred, or routed to its existing owner without design or repository mutation by this skill.

## Boundaries

This skill does not create a run, requirements, design, findings ledger, glossary entry, ADR, tracker item, memory record, or repository report. It does not implement or refactor code. Recommendation strength belongs only to the temporary opportunity survey; it is not review severity or an `F-*` finding.
