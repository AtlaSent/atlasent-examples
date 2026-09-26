# TypeScript SDK — `withPermit()` lexically-scoped form

Demonstrates the canonical lexically-scoped peer of `protect()`. Same
wire contract (evaluate + verifyPermit), same fail-closed matrix, same
audit-chain entry — but binds the action body to the permit's lifetime
via a callback. The body runs only on a verified Permit.

Mirror of [`../with-permit-py/`](../with-permit-py/). Requires
`@atlasent/sdk@^2.5.0`, which adds `withPermit` for TS/Python parity.

## When to use which form

| Form | Use when |
|---|---|
| `protect(...)` ([`../typescript-sdk-quickstart/`](../typescript-sdk-quickstart/)) | You need the verified `Permit` as a value — to pass it across a process boundary, persist it alongside your own record, or interleave it with non-trivial control flow. |
| `withPermit(...)` (this example) | The action body is a single lexical scope and "no permit, no execution" is the only thing the call site needs to express. The verified `Permit` is visible inside the body for audit-chain linkage. |

Both produce identical wire calls, identical audit-chain entries,
and identical fail-closed semantics. Pick the form that fits the
call site.

## Run

```bash
npm install
export ATLASENT_API_KEY=your_key_here
npx tsx main.ts
```

## What it demonstrates

- `atlasent.withPermit(request, async (permit) => ...)` — lexically-scoped execution under a verified Permit
- Permit visible inside the callback for two-way audit-chain linkage
- Body errors propagate untouched (the Permit is already consumed by
  the verify step in v1, so there is no compensating revoke)
- Sync-or-async callback bodies; return type preserved generically
