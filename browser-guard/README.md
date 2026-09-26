> **Later-phase reference.** This document is not part of the Deploy Gate V1 pilot. Keep first pilots focused on GitHub Actions + `production.deploy` + `/v1-evaluate` + `/v1-verify-permit`.

# browser-guard

A minimal Vite + TypeScript (no framework) application showing how to use
the AtlaSent SDK in a browser without crashing on `process.env`.

## Why this example exists

In a browser or edge runtime (Cloudflare Workers, Deno Deploy, etc.),
`process` is not defined. Any code that accesses `process.env.ANYTHING`
throws a `ReferenceError` and crashes at runtime.

Vite exposes environment variables to the browser using `import.meta.env`.
Only variables prefixed with `VITE_` are included in the bundle — this
prevents accidentally shipping server-only secrets to the browser.

The `@atlasent/enforce` SDK handles this internally when configured for
browser mode. This example shows the explicit pattern so you can verify
your own integration.

## Prerequisites

- Node.js 20+
- An AtlaSent account

## Environment variables

Create a `.env` file in this directory (not committed — see `.gitignore`):

| Variable | Required | Description |
|---|---|---|
| `VITE_ATLASENT_API_KEY` | Yes | Your API key (starts with `sk_`). |
| `VITE_ATLASENT_API_URL` | No | Base URL. Default: `https://api.atlasent.io/functions/v1` |
| `VITE_ATLASENT_ORG_ID` | Yes | Your organisation ID. |

> **Note:** Variables must be prefixed with `VITE_` to be available in the
> browser bundle. Do not use `ATLASENT_API_KEY` directly — it will be
> `undefined` at runtime in the browser.

## Quick start

```bash
cd browser-guard
npm install

# Create .env from the root example
cp ../.env.example .env
# Edit .env: rename the keys with VITE_ prefix, e.g.:
#   VITE_ATLASENT_API_KEY=sk_...
#   VITE_ATLASENT_API_URL=https://api.atlasent.io/functions/v1
#   VITE_ATLASENT_ORG_ID=org_...

npm run dev
```

Open http://localhost:5173 — you will see the decision rendered in the page.

## Build for production

```bash
npm run build
npm run preview
```

## Decision rendering

The app renders the decision with colour-coded styling:

| Decision | Colour | Meaning |
|---|---|---|
| `allow` | Green | Access granted |
| `deny` | Red | Access denied |
| `hold` | Yellow | Pending human approval |
| `escalate` | Pink | Compliance escalation required |

## Auth note

The SDK sends `Authorization: Bearer <key>` automatically. Bad keys
return HTTP 401 (not 403). The app renders a helpful message for 401
and 429 (rate limit) responses.
