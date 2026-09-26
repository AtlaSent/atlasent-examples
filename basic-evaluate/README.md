# Basic Evaluate — Raw HTTP

The simplest possible AtlaSent integration: a raw `POST /v1-evaluate` call with
`httpx`. No SDK, no decorators — just one HTTP request and a decision check.

## What this teaches

- The shape of the AtlaSent evaluate request body (`agent`, `action`, `context`)
  and response (`decision`, `reason`).
- How to fail-close on any non-`allow` decision — including `deny`, `hold`, and
  `escalate` — by string-comparing a lowercased `decision`.
- That AtlaSent's HTTP API is reachable from any language with an HTTP client;
  the Python and TypeScript SDKs are conveniences on top of this same call.

Reach for this example when you want to integrate AtlaSent from a runtime that
doesn't have a first-party SDK yet, or when you just want to see what's on the
wire before adopting the SDK.

## Required environment variables

Copy `.env.example` to `.env` (or export the vars directly) and fill in:

| Variable | Required | Default | Description |
|---|---|---|---|
| `ATLASENT_API_KEY` | yes | — | API key for your AtlaSent tenant. Create one in the AtlaSent console under **Settings → API Keys**. |
| `ATLASENT_BASE_URL` | no | `https://api.atlasent.io/functions/v1` | Override only if you're pointing at staging or a self-hosted control plane. |

## Run

```bash
pip install -r requirements.txt
export ATLASENT_API_KEY=your_key_here
python main.py
```

## Expected output

With a key whose policy allows `documents.read` for agent `assistant` at
`classification=internal`:

```
Decision: allow
Reason:   matched rule allow-internal-reads

Access granted — proceeding.
```

If the policy denies (or holds/escalates), the script exits non-zero with the
full response body, e.g.:

```
Decision: deny
Reason:   classification 'internal' not permitted for agent 'assistant'
Traceback (most recent call last):
  ...
SystemExit: Access denied: {'decision': 'deny', 'reason': '...'}
```

The non-zero exit is the point: this script is meant to be a copyable pattern
for a fail-closed gate in shell pipelines and CI jobs.

## Next steps

- See [`../python-sdk-quickstart`](../python-sdk-quickstart) for the same flow
  using the `atlasent` SDK and the `@atlasent_guard` decorator.
- See [`../flows/01-deploy-gate`](../flows/01-deploy-gate) for an end-to-end
  deployment-gating scenario built on top of this primitive.
