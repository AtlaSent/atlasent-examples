> **Later-phase reference.** This document is not part of the Deploy Gate V1 pilot. Keep first pilots focused on GitHub Actions + `production.deploy` + `/v1-evaluate` + `/v1-verify-permit`.

# Webhook Receiver Example

A minimal Express server that receives AtlaSent enforcement and governance webhook events, verifies HMAC-SHA256 signatures, and logs events to stdout.

## What it demonstrates

- Reading the raw request body before JSON parsing (required for correct HMAC)
- Verifying `X-AtlaSent-Signature` using the `@atlasent/sdk` helper
- Routing on `event_type` to handle different event types
- Returning `200` quickly and processing asynchronously

## Setup

```bash
cd webhook-receiver
npm install
```

Create a `.env` file:

```
ATLASENT_WEBHOOK_SECRET=whsec_your_signing_secret_here
PORT=3000
```

Get your `signing_secret` from the AtlaSent console under **Settings → Enforcement Webhooks → Add Webhook**, or from the `POST /v1/enforcement-webhooks` API response.

## Run

```bash
npm start
```

Expose locally with a tunnel for testing:

```bash
npx localtunnel --port 3000
# Use the printed URL as your webhook endpoint in AtlaSent
```

Then send a test ping from the console or:

```bash
curl -X POST https://api.atlasent.io/v1/enforcement-webhooks/wh_YOUR_ID/test \
  -H "X-AtlaSent-Key: ask_live_abc123"
```

## Extending

Swap the `console.log` calls in `src/handlers.ts` for your real alerting logic:

- Post to Slack via `@slack/bolt`
- Create a PagerDuty incident via their API
- Write to a SIEM via HTTP or syslog
- Store in a database for a custom dashboard
