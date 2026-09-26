# AtlaSent + OpenAI — Guarded Agent Demo

This demo shows how to wrap OpenAI function-calling tools with AtlaSent execution authorization.

Every tool call goes through: **evaluate → permit → verify → execute**.

The guard (`guard.ts`) is ~90 lines on the published `@atlasent/sdk`
(`withPermit`); `@atlasent/agent` is not on npm yet. A tool body runs only
after evaluate returned allow **and** the permit verified — deny, hold,
network error, or failed verification all mean it does not run.

## Setup

```bash
npm install
```

Set environment variables:

```bash
export ATLASENT_API_KEY="ask_live_..."        # Your AtlaSent API key
export ATLASENT_API_URL="https://api.atlasent.io/functions/v1"   # optional; this is the example's default
```

## Run

```bash
npx tsx index.ts
```

## What happens

1. An agent (OpenAI `tool_calls` in a real app; fixed calls in this demo so it runs without an OpenAI key) selects `delete_user` or `export_data`
2. **AtlaSent evaluates** the mapped action type (`user.delete`, `data.export`) against your published policy
3. If **allow** → permit issued → permit verified → tool executes
4. Otherwise → tool blocked; `AtlaSentDeniedError` carries the decision, reason, and evaluation id

## Key concepts

- `withToolGuard()` wraps tools so `execute` only runs behind a verified permit
- Every tool needs an explicit dot-notation action type; an unmapped tool is refused, not guessed
- Fail-closed: transport and verification errors block the tool too
