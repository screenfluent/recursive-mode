# GLOSSARY.md Format

Target path: `/.recursive/memory/GLOSSARY.md`

## Metadata (glossary type)

Place the required metadata near the top:

```md
Type: glossary
Authority: human
Status: CURRENT
Last-Approved: YYYY-MM-DD
```

Add optional metadata only when it has a real value; omit empty fields:

```md
Source-Runs:
- <run-id>
Tags:
- <tag>
```

Do not add `Owns-Paths`, `Watch-Paths`, or `Validated-At-Commit`; path-based freshness does not apply to the human-authoritative glossary.

## Body structure

```md
# {Project or domain name}

{One or two sentences: what this domain is and why it exists.}

## Language

**{Canonical Term}**:
{One or two sentences defining what the term is, not what it does.}
_Avoid_: {non-canonical synonym}, {another synonym}
```

Omit `_Avoid_` when there are no rejected synonyms.

## Example entries

```md
**Order**:
A customer's confirmed request for goods or services.
_Avoid_: Purchase, transaction

**Invoice**:
A request for payment sent to a customer after delivery.
_Avoid_: Bill, payment request

**Customer**:
A person or organization that places orders.
_Avoid_: Client, buyer, account
```

## Rules

- **Be opinionated.** When multiple words exist for the same concept, choose one canonical term and list the others under `_Avoid_`.
- **Keep definitions tight.** Use one or two sentences. Define what the concept is, not the operations performed on it.
- **Include only project-specific domain terms.** Before adding a term, ask whether it is unique to this project's domain or a general programming concept. Only the former belongs.
- **Exclude implementation detail.** File paths, libraries, frameworks, specs, scratch notes, and design decisions belong to their existing owners, not the glossary.
- **Group terms under subheadings** when natural clusters emerge. Keep a flat list when the language forms one cohesive area.

## One glossary across domain areas

Use the single canonical `/.recursive/memory/GLOSSARY.md` even when the repository contains multiple domains or bounded contexts. Group terms under domain or context subheadings inside `## Language`. If the same word has different legitimate meanings, qualify each entry by its context instead of forcing one false shared definition. Do not create `CONTEXT-MAP.md` or additional glossary files unless a later approved decision changes this contract.
