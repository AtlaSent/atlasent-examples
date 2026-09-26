# Python SDK — `with_permit()` lexically-scoped form

Demonstrates the canonical lexically-scoped peer of `protect()`. Same
wire contract (evaluate + verifyPermit), same fail-closed matrix, same
audit-chain entry — but binds the action body to the permit's lifetime
via a callback. The body runs only on a verified Permit.

Mirror of [`../with-permit-ts/`](../with-permit-ts/).

## When to use which form

| Form | Use when |
|---|---|
| `protect(...)` ([`../python-sdk-quickstart/`](../python-sdk-quickstart/)) | You need the verified `Permit` as a value — to pass it across a process boundary, persist it alongside your own record, or interleave it with non-trivial control flow. |
| `with_permit(...)` (this example) | The action body is a single lexical scope and "no permit, no execution" is the only thing the call site needs to express. The verified `Permit` is visible inside the body for audit-chain linkage. |

Both produce identical wire calls, identical audit-chain entries,
and identical fail-closed semantics. Pick the form that fits the
call site.

## Run

```bash
pip install -r requirements.txt
export ATLASENT_API_KEY=your_key_here
python main.py
```

## What it demonstrates

- `with_permit()` — synchronous, lexically-scoped execution under a verified Permit
- `atlasent.aio.with_permit` — async sibling, same contract
- Permit visible inside the callback for two-way audit-chain linkage
- Body errors propagate untouched (the Permit is already consumed by
  the verify step in v1, so there is no compensating revoke)
