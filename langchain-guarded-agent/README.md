> **Later-phase reference.** This document is not part of the Deploy Gate V1 pilot. Keep first pilots focused on GitHub Actions + `production.deploy` + `/v1-evaluate` + `/v1-verify-permit`.

# AtlaSent + LangChain Guarded Agent (v1.6.0)

Demonstrates AtlaSent authorization for LangChain tools using a small local guard, [`guard.ts`](guard.ts), built on the published `@atlasent/sdk`.

> `@atlasent/langchain` is not published to npm yet, so this example carries the same pattern itself. The action is the canonical `agent.tool.invoke`, with the tool name in `context.tool`.

The `withToolGuard` wrapper runs `evaluate → verifyPermit → execute` before each tool call. If the policy denies the action, either an `AtlaSentDeniedError` is thrown or a structured denial object is returned (depending on `onDeny`).

## Tools guarded

- `delete_user` — permanently delete a user account (high-impact)
- `export_audit_log` — export the full audit log for a date range

Both are configured with `onDeny: "tool-result"` so the LLM receives a structured denial rather than an exception.

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
