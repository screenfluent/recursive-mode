---
name: recursive-grilling
description: 'Grill and stress-test a draft relentlessly by resolving its decision tree one human choice at a time. Use when the user asks to challenge a plan, requirements, design, or proposal, or when another skill reaches an unresolved human decision.'
---

# Recursive Grilling

Relentlessly close human decisions in an agreed scope. Treat grilling as a shared conversational method, not a lifecycle stage.

## Build the decision tree

Read the active draft and relevant repo sources. Separate repo facts from human decisions: research repo facts yourself and leave product, scope, and trade-off choices to the human.

Identify the relevant branches and dependencies between decisions. Start with the earliest unresolved decision on which later choices depend.

Completion criterion: every relevant branch in the agreed scope has a known dependency order and one next human decision.

## Resolve one decision

For the next decision:

1. State your recommendation and the reasoning behind it.
2. Ask one question at a time.
3. Wait for the human answer.
4. Record a confirmed decision in the current draft when the human wants a durable write.

Do not ask the next question in the same turn. After the answer, update the decision tree and continue with its next dependency.

Completion criterion: the current decision is resolved, durably deferred, or ruled out of scope before another question is asked.

## Close the grill

Continue until every discovered decision in the agreed scope is:

- resolved;
- deferred with rationale, impact, and a pointer to an existing durable destination; or
- ruled out of scope.

A deferral without a destination pointer remains unresolved. To place it on a Wayfinder map, the human selects the map id and discovery unit; never infer an owner from whichever map is active. Without that selection, the deferral remains in the current draft under `Deferred` and points to that section.

When a decision changes domain language, route the proposed wording through `recursive-domain-modeling`. Until the glossary mutation is approved and written, preserve the proposal under `Deferred language proposals` in the current draft. Do not create or mutate `GLOSSARY.md` from this skill.

Finish only when the human confirms shared understanding. Until then, do not carry out the resulting decisions.

## Boundaries

- Grilling does not create a recursive run and does not implement code.
- Keep requirements ownership with `recursive-spec` and module, seam, and dependency design with `recursive-codebase-design`.
- Propose an ADR only when the decision is hard to reverse, surprising without context, and a real trade-off. Write it only after explicit human approval.
