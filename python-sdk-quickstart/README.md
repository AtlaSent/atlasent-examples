# Python SDK Quickstart

Uses the `atlasent` Python SDK's canonical execution-boundary surface —
`protect()` mints and verifies a Permit end-to-end and returns it on
success. On any non-allow outcome (deny / hold / escalate / verify
failure) it raises `AtlaSentDeniedError`; on transport / 5xx /
timeout it raises `AtlaSentError`. The action body is unreachable
without a verified Permit.

Mirror of `../typescript-sdk-quickstart/`. See also
[`../with-permit-py/`](../with-permit-py/) for the lexically-scoped
`with_permit()` form.

## Run

```bash
pip install -r requirements.txt
export ATLASENT_API_KEY=ask_test_...
# AtlaSent API base URL (this is also the example's default; self-hosted:
# your own deployment's https://<project-ref>.supabase.co/functions/v1)
export ATLASENT_BASE_URL=https://api.atlasent.io/functions/v1
python main.py
```

## What it demonstrates

- `protect()` — the canonical fail-closed execution-boundary primitive
- The Permit as a first-class artifact, persisted alongside your
  record so the audit chain stays two-way navigable
- Async sibling via `AsyncAtlaSentClient.protect()` (the `aio` namespace currently only ships `with_permit`; the async `protect` lives on the async client)
- `AtlaSentDeniedError` and `AtlaSentError` as the two-axis error model
