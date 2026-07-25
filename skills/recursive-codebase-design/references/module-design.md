# Module design

Design **deep modules**: a lot of behaviour behind a small interface, placed at a clean seam, testable through that interface. This file owns vocabulary and caller-visible contracts; execution across agreed interfaces belongs to [program-design.md](program-design.md).

## Contents

- [Glossary](#glossary)
- [Deep vs shallow](#deep-vs-shallow)
- [Principles](#principles)
- [Designing for testability](#designing-for-testability)
- [Relationships](#relationships)
- [Rejected framings](#rejected-framings)
- [Going deeper](#going-deeper)

## Glossary

Use these terms exactly for the design concepts — don't use "component," "service," "API," or "boundary" as loose substitutes. Those words retain their valid meanings outside this vocabulary. Consistent language is the whole point.

**Module** — anything with an interface and an implementation. Deliberately scale-agnostic: a function, class, package, or tier-spanning slice. _Avoid_: unit, component, service.

**Interface** — everything a caller must know to use the module correctly: the type signature, but also invariants, ordering constraints, error modes, required configuration, and performance characteristics. _Avoid_: API, signature (too narrow — they refer only to the type-level surface).

**Implementation** — what's inside a module, its body of code. Distinct from **Adapter**: a thing can be a small adapter with a large implementation (a Postgres repo) or a large adapter with a small implementation (an in-memory fake). Reach for "adapter" when the seam is the topic; "implementation" otherwise.

**Depth** — leverage at the interface: the amount of behaviour a caller (or test) can exercise per unit of interface they have to learn. A module is **deep** when a large amount of behaviour sits behind a small interface, **shallow** when the interface is nearly as complex as the implementation.

**Seam** _(Michael Feathers)_ — a place where you can alter behaviour without editing in that place. Every seam has an enabling point where the decision to use one behaviour or another is made. A module interface can live at an object seam, but preprocessing, linking, and other substitution mechanisms can also provide seams. Where to place an interface or create a seam is a design decision distinct from what goes behind it. _Avoid_: boundary (overloaded with DDD's bounded context).

**Adapter** — a concrete thing that satisfies an interface at a seam. Describes *role* (what slot it fills), not substance (what's inside).

**Leverage** — what callers get from depth: more capability per unit of interface they learn. One implementation pays back across N call sites and M tests.

**Locality** — what maintainers get from depth: change, bugs, knowledge, and verification concentrate in one place rather than spreading across callers. Fix once, fixed everywhere.

## Deep vs shallow

**Deep module** = small interface + lots of implementation:

```
┌─────────────────────┐
│   Small Interface   │  ← Few methods, simple params
├─────────────────────┤
│                     │
│  Deep Implementation│  ← Complex logic hidden
│                     │
└─────────────────────┘
```

**Shallow module** = large interface + little implementation (avoid):

```
┌─────────────────────────────────┐
│       Large Interface           │  ← Many methods, complex params
├─────────────────────────────────┤
│  Thin Implementation            │  ← Just passes through
└─────────────────────────────────┘
```

When designing an interface, ask:

- Can I reduce the number of methods?
- Can I simplify the parameters?
- Can I hide more complexity inside?

## Principles

- **Depth is a property of the interface, not the implementation.** A deep module can be internally composed of small, mockable, swappable parts — they just aren't part of the interface. A module can have **internal seams** (private to its implementation, used by its own tests) as well as the **external seam** at its interface.
- **The deletion test.** Imagine deleting the module. If complexity vanishes, it was a pass-through. If complexity reappears across N callers, it was earning its keep.
- **The interface is the test surface.** Callers and tests cross the same seam. If you want to test *past* the interface, the module is probably the wrong shape.
- **One adapter is a strong warning of a hypothetical seam. Two adapters usually demonstrate a real one.** Require justification when a single-adapter seam has contracted value rather than treating the adapter count as an absolute law.
- **Prefer existing seams** before inventing new ones.

## Designing for testability

Good interfaces make testing natural:

1. **Accept dependencies, don't create them.**

   ```typescript
   // Testable
   function processOrder(order, paymentGateway) {}

   // Hard to test
   function processOrder(order) {
     const gateway = new StripeGateway();
   }
   ```

2. **Prefer returned results over hidden mutation. Make unavoidable side effects explicit and owned at a seam.**

   ```typescript
   // Testable
   function calculateDiscount(cart): Discount {}

   // Hard to test
   function applyDiscount(cart): void {
     cart.total -= discount;
   }
   ```

3. **Small surface area.** Fewer methods = fewer tests needed. Fewer params = simpler test setup.

## Relationships

- A **Module** has exactly one **conceptual Interface**: the design surface it presents to callers and tests. Several language-level declarations may express that one conceptual interface.
- **Depth** is a property of a **Module**, measured against its **Interface**.
- A **Seam** is a place where behaviour can vary without editing there. An object seam may coincide with a **Module**'s **Interface**, but not every seam is a module interface.
- An **Adapter** sits at a **Seam** and satisfies the **Interface**.
- **Depth** produces **Leverage** for callers and **Locality** for maintainers.

## Rejected framings

- **Depth as a literal ratio of implementation lines to interface lines**: rewards padding the implementation. Ousterhout's principle is a simple interface hiding substantial functionality, not a line-count metric. We use depth-as-leverage instead.
- **"Interface" as the TypeScript `interface` keyword or a class's public methods**: too narrow — interface here includes every fact a caller must know.
- **"Boundary" as a loose substitute for seam or interface**: overloaded with DDD's bounded context.

## Going deeper

- **Deepening a cluster given its dependencies** — see [deepening.md](deepening.md): dependency categories, seam discipline, and replace-don't-layer testing.
- **Exploring alternative interfaces** — see [design-it-twice.md](design-it-twice.md): spin up parallel subagents to design the interface several radically different ways, then compare on depth, locality, and seam placement.
- **Shaping execution across agreed interfaces** — see [program-design.md](program-design.md): critical flow, state ownership, errors, side effects, and conditional observability.
