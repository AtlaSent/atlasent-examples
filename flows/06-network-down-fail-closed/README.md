# 06 · Network-down boundary regression — contract test

Verifies the **fail-closed boundary** at the transport layer: when
AtlaSent's authority source is unreachable, `fetch()` raises. This
is the *hard floor* every SDK built on `fetch` inherits — if it
breaks, every SDK breaks fail-closed at once.

A security gate that fails open when its authority source is down is
worse than no gate at all. This flow is the canary that catches any
future regression of that property.

## Run it (<2 s, no network egress, no SDK install)

```bash
npm install
npm start
```

No `ATLASENT_API_KEY` needed. The flow points at `http://127.0.0.1:1`
(RFC-reserved port, always closed) and asserts that `fetch()` itself
raises.

## What it asserts

| Property                                         | Verifies                              |
|--------------------------------------------------|---------------------------------------|
| `fetch(unreachable)` raises `TypeError`          | Node transport surfaces the failure   |
| The error reaches the caller (not swallowed)    | An SDK wrapping `fetch` can raise too |

If `fetch()` returns silently from an unreachable host, the test exits
**non-zero with a `SECURITY REGRESSION` message**. Wireable into CI as
a regression canary.

## Why this is dependency-free

The example used to import `@atlasent/sdk` and exercise
`client.evaluate()` + `protect()`. That made the test fragile in CI
because `@atlasent/sdk` is not yet on npm — installs would 404. The
SDK-level tests cover those surfaces in their own suites:

- **TypeScript** — `atlasent-sdk/typescript/test/` (vitest)
- **Python** — `atlasent-sdk/python/tests/test_with_permit.py`

This flow stays at the **transport contract** layer — a property
that's universally true for every SDK built on `fetch`. If this test
ever returns `0` without seeing a `TypeError`, every SDK in the org
just lost fail-closed at the same time, and CI catches it
immediately.

## Why this exists

Closes ledger row **C5** of `LAST_20_EXECUTION_PLAN`. Companion to:

- atlasent-sdk #123 / #124 — `withPermit` / `with_permit` (the
  per-SDK fail-closed surface that wraps this transport behaviour)
- atlasent-action #22 — gate consumes permit via verify-permit (B5)

## Exit codes

| Code | Meaning                                                    |
|------|------------------------------------------------------------|
| 0    | Boundary held: `fetch()` raised on the unreachable host.   |
| 1    | Test environment broken (`fetch()` returned 200, or the harness errored). |
