# agent-guard (TypeScript)

TypeScript example showing how to use the AtlaSent `agentGuard` factory from
`@atlasent/action/connectors` to gate LangChain-style tool calls before they
execute. Every tool call goes through the evaluate → verify → verifyPermit
contract. Blocked calls throw `AgentGuardError`.

## Run (live)

```bash
bun install
export ATLASENT_API_KEY=ask_live_xx
bun run index.ts
```

## Run (dry-run / smoke — no API keys needed)

```bash
bun install
bun run smoke
# or: ATLASENT_DRY_RUN=true bun run index.ts
```

## What it demonstrates

| API | Description |
|---|---|
| `agentGuard(config)` | Create a guard factory. |
| `guard.wrap(tool, ctx)` | Wrap a single tool — returns a proxy with the same interface. |
| `guard.wrapAll(tools, ctx)` | Wrap an entire toolkit in one call. |
| `guard.call(tool, args, ctx)` | One-shot guarded call without a proxy. |
| `AgentGuardError` | Thrown on deny / hold / escalate / infra error. |

## Setup

```typescript
import { agentGuard, AgentGuardError } from '@atlasent/action/connectors';

const guard = agentGuard({
  apiKey:         process.env.ATLASENT_API_KEY!,
  blockOnHold:    true,                    // throw on hold (default)
  defaultActorId: 'agent:planner-v1',     // fallback actor
  environment:    'production',
});
```

## guard.wrap(tool) — single tool

```typescript
const guardedTool = guard.wrap(myTool, { agentId: 'planner-v1', sessionId: 'abc' });

try {
  const result = await guardedTool.call(args);
} catch (err) {
  if (err instanceof AgentGuardError) {
    console.warn(`blocked — decision=${err.decision} tool=${err.toolName}`);
    // err.evaluationId is set when the API returned an evaluation id
  }
}
```

## guard.wrapAll(tools) — entire toolkit

```typescript
const [search, execute, email] = guard.wrapAll(
  [searchTool, executeTool, emailTool],
  { agentId: 'executor-v2', sessionId: 'def456' },
);

// Pass the wrapped array to your agent framework instead of the originals.
```

## AgentGuardError fields

```typescript
err.decision:     'deny' | 'hold' | 'escalate' | 'error'
err.toolName:     string   // the blocked tool's name
err.evaluationId: string | undefined  // for audit lookup
err.message:      string   // human-readable reason
```

## Actor resolution

The guard derives the actor id from the per-call context in priority order:

1. `ctx.agentId` → `'agent:<agentId>'`
2. `ctx.userId` → `'user:<userId>'`
3. `config.defaultActorId` (set at factory creation time)
4. `'agent:unknown'` (library default)

```typescript
// agentId wins for the AtlaSent actor; userId is still forwarded as context.
const ctx: AgentCallContext = {
  agentId:   'planner-v1',      // → actor = 'agent:planner-v1'
  userId:    'alice@corp.com',  // forwarded as context.user_id
  sessionId: 'session-abc',
};
```

## Config options

| Option | Default | Description |
|---|---|---|
| `apiKey` | — | AtlaSent API key (`ask_live_*` / `ask_test_*`). Required. |
| `blockOnHold` | `true` | Throw `AgentGuardError` when the decision is `hold`. Set `false` to let held calls through (the caller then decides). |
| `defaultActorId` | `'agent:unknown'` | Fallback actor id when no `agentId` / `userId` is in the call context. |
| `environment` | — | Optional environment string forwarded to AtlaSent for policy evaluation. |
| `apiUrl` | `https://api.atlasent.io/functions/v1` | Override for self-hosted or staging. |
