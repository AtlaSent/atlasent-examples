# Protected Actions — AtlaSent Examples

Demonstrates the `requirePermit` pattern from `@atlasent/sdk`: wrapping
dangerous operations so they can only execute after an explicit permit is
granted by the AtlaSent policy engine.

## The rule

> Dangerous code must not be callable directly — only through an
> AtlaSent-protected wrapper.

```typescript
await requirePermit(action, async () => {
  // dangerous operation happens ONLY here
});
```

Any `db.raw(...)`, `exec(...)`, `railway.volumes.delete(...)`, or
`supabase.from(...).delete()` must live inside `requirePermit(...)`.

## Examples

### 1. Database delete

```typescript
import { requirePermit, type ProtectedAction } from "@atlasent/sdk";

const action: ProtectedAction = {
  action_type: "db.table.delete",
  actor_id: "data-pipeline",
  resource_id: "users",
  environment: "production",
  context: { reason: "GDPR erasure request #4821" },
};

await requirePermit(action, async () => {
  await supabase.from("users").delete().eq("id", userId);
});
```

### 2. Shell command with auto-classification

```typescript
import { classifyCommand, requirePermit, type ProtectedAction } from "@atlasent/sdk";

async function runCommand(cmd: string, actorId: string) {
  const actionType = classifyCommand(cmd);
  if (!actionType) {
    return exec(cmd); // safe — run directly
  }

  const action: ProtectedAction = {
    action_type: actionType,
    actor_id: actorId,
    resource_id: "shell",
    environment: "production",
    context: { command: cmd },
  };

  return requirePermit(action, async () => exec(cmd));
}
```

### 3. Infrastructure deletion

```typescript
import { requirePermit, type ProtectedAction } from "@atlasent/sdk";

async function deleteRailwayVolume(volumeId: string, actorId: string) {
  const action: ProtectedAction = {
    action_type: "infra.volume.delete",
    actor_id: actorId,
    resource_id: volumeId,
    environment: "production",
    context: {},
  };

  return requirePermit(action, async () =>
    railway.volumes.delete(volumeId),
  );
}
```

## `ProtectedAction` shape

| Field | Type | Description |
|---|---|---|
| `action_type` | `string` | What is being done — use `DESTRUCTIVE_ACTION_TYPES` constants from `@atlasent/api` |
| `actor_id` | `string` | Who is doing it (agent / service / user ID) |
| `resource_id` | `string` | What resource is being affected |
| `environment` | `"development" \| "staging" \| "production"` | Deployment tier |
| `context` | `Record<string, unknown>` | Any additional audit context |

## `classifyCommand` patterns

`classifyCommand(cmd)` returns `"destructive.command"` for:

- `rm -rf`
- `DROP TABLE` / `DROP DATABASE`
- `DELETE FROM`
- `TRUNCATE TABLE`
- `railway volume delete`
- `kubectl delete`
- `terraform destroy`

Returns `null` for all other commands (safe to run without a permit).

## Running the example

```bash
npm install
npx tsx index.ts
```

Requires `ATLASENT_API_KEY` in the environment. The SDK is fail-closed:
if the key is missing or the permit is denied, the dangerous operation
never runs.
