# 08 · Batch Evaluate (Fan-out)

This flow demonstrates how to evaluate multiple items concurrently using the
`evaluateMany` method, which fans out requests in parallel and collects results.

## When to use batch evaluation

- **Bulk moderation queues** — process a backlog of pending items without
  serialising requests.
- **Nightly policy sweeps** — re-evaluate a cohort of users or actions after a
  policy change.
- **Load testing / benchmarking** — measure latency distribution across a
  representative sample of requests.

## How `evaluateMany` works

`client.evaluateMany(items)` submits all items concurrently (fan-out) and waits
for every response before returning. Each item in the input array produces one
corresponding result in the output array, preserving order.

```
items[0] ─────────────────┐
items[1] ──────────────┐  │   AtlaSent
items[2] ───────────┐  │  │  evaluate API
   ...               ├──┼──┤──────────────▶ results[]
items[N] ───────┐   │  │  │
                └───┴──┴──┘
```

Results carry the same fields as a single `evaluate` response:
`decision`, `confidence`, `ruleId`, `permitId`, and `metadata`.

## Run it

```bash
export ATLASENT_API_KEY=ask_test_...
npm install
npm start
```

## Expected output

```
Submitting batch of 5 items...

Batch results:
────────────────────────────────────────────────────────────
✓ user-001      → allow      (confidence: 0.95)
✗ user-002      → deny       (confidence: 0.88)
✓ user-003      → allow      (confidence: 0.91)
⚠ user-004      → escalate   (confidence: 0.61)
✓ user-005      → allow      (confidence: 0.97)
────────────────────────────────────────────────────────────
Summary: 3 allowed, 1 denied, 1 escalated
```

## Extending the example

- Replace the hardcoded `items` array with a database query or CSV import.
- Add retry logic around individual failed items using `Promise.allSettled`.
- Write results to an audit log or downstream queue.
