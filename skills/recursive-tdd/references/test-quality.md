# Test Quality

## What a good test is

Tests verify behavior through public interfaces, not implementation details. Code can change entirely; tests shouldn't. A good test reads like a specification — "user can checkout with valid cart" tells you exactly what capability exists — and survives refactors because it doesn't care about internal structure.

```typescript
// GOOD: Tests observable behavior
test("user can checkout with valid cart", async () => {
  const cart = createCart();
  cart.add(product);
  const result = await checkout(cart, paymentMethod);
  expect(result.status).toBe("confirmed");
});
```

A good test:

- tests behavior users or callers care about;
- uses the public API named by the approved `Test Surface`;
- survives internal refactors;
- describes WHAT, not HOW;
- proves one logical outcome.

Default to one logical assertion per test. Multiple assertion statements are valid when together they prove one indivisible outcome, such as an atomic state transition and its emitted event.

## Test at the approved surface

Exercise the public interface or observation point named by the approved `Test Surface` record. Assert what a caller observes: a result, state transition, persisted fact, emitted event, permission boundary, side effect, or error.

A private helper normally receives indirect coverage through that surface. Test it directly only when it is an intentionally owned interface or when a failure cannot be diagnosed economically through the outer surface. Prefer the highest stable surface that remains diagnostic.

Phase 3 uses the pre-agreed `TS-*` record rather than asking for a new seam during implementation. A changed or newly required seam returns through the plan/design addendum and human gate.

## Reject implementation-coupled tests

An implementation-coupled test mocks internal collaborators, tests private methods, asserts call counts or order, or verifies through a side channel. The tell: the test breaks when you refactor but behavior has not changed.

```typescript
// BAD: Tests implementation details
test("checkout calls paymentService.process", async () => {
  const mockPayment = jest.mock(paymentService);
  await checkout(cart, payment);
  expect(mockPayment.process).toHaveBeenCalledWith(cart.total);
});
```

Do not bypass the public interface to verify an implementation detail:

```typescript
// BAD: Bypasses interface to verify
test("createUser saves to database", async () => {
  await createUser({ name: "Alice" });
  const row = await db.query("SELECT * FROM users WHERE name = ?", ["Alice"]);
  expect(row).toBeDefined();
});

// GOOD: Verifies through interface
test("createUser makes user retrievable", async () => {
  const user = await createUser({ name: "Alice" });
  const retrieved = await getUser(user.id);
  expect(retrieved.name).toBe("Alice");
});
```

## Derive an independent expected value

A tautological test recomputes the expected value the way the code does, uses a snapshot derived by hand the same way, or asserts a constant equal to itself. It passes by construction and can never disagree with the implementation. Expected values must come from an independent source of truth — a known-good literal, an accepted worked example, a requirement, or a protocol rule.

```typescript
// BAD: Expected value repeats the production calculation
test("calculateTotal sums line items", () => {
  const items = [{ price: 10 }, { price: 5 }];
  const expected = items.reduce((sum, i) => sum + i.price, 0);
  expect(calculateTotal(items)).toBe(expected);
});

// GOOD: Expected value is an independent, known literal
test("calculateTotal sums line items", () => {
  expect(calculateTotal([{ price: 10 }, { price: 5 }])).toBe(15);
});
```

## Grow vertical tracer bullets

Horizontal slicing writes all tests first and then all implementation. Bulk tests verify imagined behavior: they test the shape of things, go insensitive to real changes, and commit to test structure before the implementation teaches you anything.

Work in vertical slices instead — one test → one minimal implementation → bounded REFACTOR → repeat. Each test is a tracer bullet that responds to what the last cycle taught you and crosses the real layers needed to prove one observable behavior.

## Select the test level

- Use a unit-level test when the public surface and outcome are in-process and replacing infrastructure adds no behavioral confidence.
- Use an integration-level test when storage, serialization, transactions, or owned adapters define correctness.
- Use a contract-level test for a stable boundary whose request/response shape is itself the promise.
- Use an end-to-end test when routing, auth, persistence, or a user workflow must work together to establish the behavior.

Choose the narrowest level that still observes the real contract and gives a diagnostic failure.

## Mock at system boundaries only

Prefer real owned collaborators, test databases, and real filesystems when they are practical and deterministic.

Replace only true external or nondeterministic boundaries:

- external APIs such as payment or email;
- databases when a real test database is impractical;
- time or randomness;
- uncontrolled network or filesystem boundaries.

Do not mock your own classes, modules, or internal collaborators merely to isolate a function.

### Use dependency injection

Pass external dependencies in rather than creating them internally:

```typescript
// Easy to replace at the external boundary
function processPayment(order, paymentClient) {
  return paymentClient.charge(order.total);
}

// Hard to replace without reaching into the implementation
function processPayment(order) {
  const client = new StripeClient(process.env.STRIPE_KEY);
  return client.charge(order.total);
}
```

Prefer an SDK-style adapter with one specific operation over a generic conditional fetcher whose fake must reproduce URL routing, branching, retries, and response decoding:

```typescript
// GOOD: Each operation has one external contract
const api = {
  getUser: (id) => fetch(`/users/${id}`),
  getOrders: (userId) => fetch(`/users/${userId}/orders`),
  createOrder: (data) => fetch('/orders', { method: 'POST', body: data }),
};

// BAD: The mock must reproduce routing logic
const api = {
  fetch: (endpoint, options) => fetch(endpoint, options),
};
```

The SDK approach means:

- Each mock returns one specific shape.
- No conditional logic in test setup.
- Easier to see which endpoints a test exercises.
- Type safety per endpoint.

Record real dependencies and replaced dependencies separately in the approved `Test Surface` row so review can challenge unnecessary test doubles.

## Check test strength before GREEN

Confirm that:

- the assertion names a concrete observable outcome;
- the expected value is independent;
- the failure points at the intended behavior;
- the approved surface is stable enough to survive internal refactoring;
- replacements sit only at justified external or nondeterministic boundaries;
- the test would fail for a plausible incorrect implementation.

Complete the check only when each property is demonstrable from the test and its approved `Test Surface` record.
