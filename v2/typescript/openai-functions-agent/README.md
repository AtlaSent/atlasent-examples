# openai-functions-agent (TypeScript)

Minimal OpenAI Chat Completions agent that gates each tool call through
AtlaSent using **`@atlasent/sdk@^2`**. Demonstrates the `evaluateMany`
batch path when `ATLASENT_V2_BATCH=true`, with a transparent per-call
fallback to `/v1-evaluate` when the flag is off.

## Run (live)

```bash
bun install
export ATLASENT_API_URL=https://api.atlasent.io/functions/v1
export ATLASENT_API_KEY=ask_live_xx
export OPENAI_API_KEY=sk-...
export ATLASENT_V2_BATCH=true   # optional; falls back to per-call loop when unset
bun run index.ts
```

## Run (dry-run / smoke — no API keys needed)

```bash
bun install
bun run smoke
# or: ATLASENT_DRY_RUN=true bun run index.ts
```

In dry-run mode the AtlaSent and OpenAI calls are stubbed. The agent
simulates two tool calls (`get_weather`, `send_email`), runs them through
the mock evaluator (always `allow`), and executes the stub implementations.
This is the mode used by CI.

## Flow

1. Send the user prompt to OpenAI with the two tool defs registered
   (`get_weather`, `send_email`).
2. If the model returns tool calls, fan them out as a single
   `sdk.evaluateMany` call (batch) or per-call `sdk.evaluate` loop.
3. Execute only the allowed tool calls; report denied ones with their reason.

## SDK usage

```typescript
import { AtlasentClient } from "@atlasent/sdk";

const sdk = new AtlasentClient({
  apiUrl: process.env.ATLASENT_API_URL,
  apiKey: process.env.ATLASENT_API_KEY,
});

// Batch authorize all tool calls in one round-trip
const { results } = await sdk.evaluateMany({ items });
```

If `@atlasent/sdk` is not installed the example falls back to raw `fetch`
automatically so you can read and run the file without the package.

## Why this lives under `v2/`

The batch path is gated by the `v2_batch` per-tenant flag, which AtlaSent
enables per organization on request.
When that flag is off, the example transparently falls back to per-call
`/v1-evaluate`, so it keeps running against the production v1 API today.
