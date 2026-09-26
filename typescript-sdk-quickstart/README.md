# TypeScript SDK Quickstart

Uses `@atlasent/sdk`'s canonical execution-boundary surface —
`atlasent.protect(...)` mints and verifies a Permit end-to-end and
returns it on success. On any non-allow outcome (deny / hold /
escalate / verify failure) it throws `AtlaSentDeniedError`; on
transport / 5xx / timeout it throws `AtlaSentError`. The code after
`protect()` is unreachable without a verified Permit.

Mirror of `../python-sdk-quickstart/`. See also
[`../with-permit-ts/`](../with-permit-ts/) for the lexically-scoped
`withPermit()` form.

## Run

```bash
npm install
export ATLASENT_API_KEY=ask_test_...
# AtlaSent API base URL (this is also the example's default; self-hosted:
# your own deployment's https://<project-ref>.supabase.co/functions/v1)
export ATLASENT_BASE_URL=https://api.atlasent.io/functions/v1
npx tsx main.ts
```

## What it demonstrates

- `atlasent.protect(...)` — the canonical fail-closed execution-boundary primitive
- The Permit as a first-class artifact, persisted alongside your
  record so the audit chain stays two-way navigable
- `AtlaSentDeniedError` and `AtlaSentError` as the two-axis error model
