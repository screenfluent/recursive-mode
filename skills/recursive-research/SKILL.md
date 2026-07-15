---
name: recursive-research
description: 'Investigate a bounded question against high-trust primary sources and capture verified findings in one cited Markdown report. Use when the user wants a topic researched, docs or API facts gathered, or another skill needs reading legwork delegated to a background agent.'
---

# Recursive Research

Investigate a bounded question against high-trust primary sources and leave one cited Markdown report in its owning context. Treat the report as evidence, not authoritative knowledge; promote only accepted conclusions through the artifact or skill that owns them.

## Define the question

State the bounded question and what would count as a sufficient answer. Add included subquestions and explicit exclusions only when the question warrants them. Keep unrelated questions out of the report.

Complete this step when the bounded question and sufficient-answer criterion are explicit, with any needed subquestions and exclusions accounted for.

## Choose the owning context

Route by ownership rather than by the mere existence of a run:

- When the question belongs to a named discovery unit on a human-selected Wayfinder map, write `/.recursive/maps/<map-id>/evidence/<unit-id>/research/<slug>.md`.
- When the question belongs to an active recursive run, write `/.recursive/run/<run-id>/evidence/research/<slug>.md`.
- Otherwise create a real Markdown report outside the repository in the system temporary directory, unless the human selects another path, and return its path to the human.

An active run does not make unrelated research run evidence, and a map does not capture research outside its named unit. Create no default `docs/research/` tree or durable research library.

Complete this step when the path expresses the question's owning context.

## Choose execution

Research is legwork you delegate, not thinking you outsource. **Spin up a background agent** when one is available, so the controller keeps working while it reads. If no bounded delegate is available, the controller may investigate directly and still owns verification.

For delegated work that belongs to an active recursive run, use the existing `recursive-subagent` and router/action-record contracts without restating their protocol here. Standalone research may use an ordinary bounded background agent and creates no run action record.

Give a delegate the exact question, any subquestions and exclusions, required source classes, report path and schema, and the requirement to label inference and unresolved claims.

## Select sources

Investigate against **high-trust primary sources** — official docs, source code, specs, first-party APIs — not a secondary write-up of them. Follow every claim back to the source that owns it.

Choose the high-trust primary source that owns each answer. Depending on the claim, this may be:

- source code, tests, configuration, or versioned repository history for codebase facts;
- official documentation, specifications, standards, or first-party APIs;
- original research papers or first-party datasets;
- direct reproducible observations.

Use secondary sources only as discovery leads. When high-trust primary evidence does not exist, leave the claim unresolved and name the missing source instead of promoting a secondary account. For mutable sources, record the relevant version, commit, release, or access date.

## Investigate and capture

Write the findings to a single Markdown file, citing each claim's source. Keep citations adjacent to the claims they support. Cite repository evidence with a path plus a stable revision; link external evidence to the direct owning URL rather than a search result.

Use this minimal report shape:

```markdown
# <Research question>

Owning context: <run | map | standalone>
Status: <run evidence | map evidence | temporary>
Research mode: <controller | delegated>
Source scope: <versions, commits, releases, dates>

## Answer

<Concise answer, including material uncertainty.>

## Findings

### <Claim>

Evidence status: verified | inference | unresolved | contradicted

<Claim, implication, and adjacent primary-source citation.>

## Conflicts and open questions

- <conflict, missing evidence, or scope limit>

## Promotion candidates

- <small conclusion> → <proposed owning skill or artifact>
```

Complete this step when the question and any included subquestions are verified, identified as inference, contradicted, or unresolved with the missing evidence named.

## Verify

The controller remains responsible for acceptance. Resolve every citation and verify every material claim against its named primary source. Spot-check auxiliary details. Confirm that the cited version or commit applies, separate source fact from inference, and reconcile material conflicts rather than choosing silently.

Downgrade or reject claims whose citation is missing, cannot be resolved, is stale for the applicable version, or supports weaker wording than the report uses.

Complete this step when every material conclusion is verified or carries an accurate weaker evidence status.

## Promote

Present promotion candidates to the human or calling skill. Promote the smallest useful conclusion with its evidence pointer, not the full report. Route accepted meaning through its owner:

- a human choice → `recursive-grilling`;
- a requirements or specification conclusion → `recursive-spec`;
- design or an ADR candidate → `recursive-codebase-design` and its existing gates;
- a term change → `recursive-domain-modeling` and its human gate;
- active-run evidence → the consuming phase artifact.

This skill does not write requirements, design, ADRs, glossary, memory, `STATE`, or `DECISIONS`. The owning workflow performs any authoritative mutation.

Keep in-run reports as audit evidence. After the human reviews a standalone report, remove the temporary report unless they explicitly retain it at a selected location.

## Done when

- the question and any included subquestions have evidence statuses;
- every material conclusion has controller-verified evidence;
- inference, conflicts, and missing evidence are explicit;
- the report resides in its owning context;
- if promotion candidates were proposed, they are accepted, rejected, or deferred through their owners;
- standalone temporary residue is removed or explicitly retained by the human.

## Boundaries

- `recursive-research` owns investigation, citations, temporary capture, and verification handoff.
- A design question requiring empirical code belongs to `recursive-prototype`.
- This skill does not create a recursive run or phase.
