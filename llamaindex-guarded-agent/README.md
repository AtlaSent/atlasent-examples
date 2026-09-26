> **Later-phase reference.** This document is not part of the Deploy Gate V1 pilot. Keep first pilots focused on GitHub Actions + `production.deploy` + `/v1-evaluate` + `/v1-verify-permit`.

# AtlaSent + LlamaIndex Guarded Agent (TypeScript, v1.6.0)

Demonstrates AtlaSent authorization for LlamaIndex tools using a small local guard, [`guard.ts`](guard.ts), built on the published `@atlasent/sdk`.

> `@atlasent/llamaindex` is not published to npm yet, so this example carries the same pattern itself. The action is the canonical `agent.tool.invoke`, with the tool name in `context.tool`.

The `withToolGuard` wrapper runs `evaluate → verifyPermit → execute` before each tool call. Object results are annotated with `_atlasent_permit_id`; non-object results pass through unchanged.

## Tools guarded

- `vector_search` — semantic search over the knowledge base (read)
- `upsert_document` — add or update a document in the knowledge base (write)

Both are configured with `onDeny: "tool-result"` so the agent receives a structured denial rather than an exception.

## Setup

```bash
npm install
export ATLASENT_API_KEY=your-key
# Optional (this is the default): export ATLASENT_URL=https://api.atlasent.io/functions/v1
```

## Run

```bash
npm run demo
```

## What to expect

Each tool call is evaluated against your AtlaSent policy. Allowed calls print the result with a permit ID annotation. Denied calls print the denial reason and evaluation ID.

See the [AtlaSent documentation](https://docs.atlasent.io) for the full TypeScript integration guide.
