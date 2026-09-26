# Infrastructure Actions — Authorization Quickstart

AtlaSent enforces non-bypassable authorization for destructive infrastructure
operations. This example consolidates infra action patterns with full policy
context.

> **Related** — These actions are also demonstrated in
> [`atlasent-examples/protected-actions/`](../protected-actions/) (the original
> protected actions examples). This example adds full policy context, backup
> verification gates, and the `classifyToolRisk()` integration pattern.

## The 5-step flow

1. **Classify** — call `classifyToolRisk(action)` to determine risk level
   (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`) before calling `protect()`.
2. **Evaluate** — call `atlasent.protect()` with full infra context.
3. **Gate by role** — terminate/delete require `incident_commander`;
   stop requires `on_call_engineer` minimum.
4. **Backup gate** — data-destructive actions (`database.table.drop`,
   `database.volume.delete`) require `backupVerified=true`.
5. **Verify and execute** — permit verified server-side before the infra
   mutation is issued to the cloud/database API.

## Run

```bash
pip install -r requirements.txt

# Full demo (5 scenarios, offline stub, no API key required)
python main.py

# With live AtlaSent API
ATLASENT_API_KEY=ask_live_... python main.py
```

TypeScript (shows `classifyToolRisk()` usage):

```bash
npm install
npx @atlasent/sdk mock &
ATLASENT_API_URL=http://127.0.0.1:4747 ATLASENT_API_KEY=mock npx tsx main.ts
```

## Scenarios

| # | Action | Outcome | Reason |
|---|--------|---------|--------|
| 1 | `aws.ec2.stop_instance` | ALLOW | On-call engineer, `changeTicket` present |
| 2 | `aws.ec2.terminate_instance` | DENY | Actor has `on_call_engineer` role only — `incident_commander` required |
| 3 | `github.repos.delete` | DENY | `machine_executable=false` — human review always required |
| 4 | `database.table.drop` | DENY | `backupVerified=false` |
| 5 | `database.volume.delete` | ALLOW | Incident commander, `backupVerified=true`, `changeTicket` present |

## classifyToolRisk() pattern

```typescript
import { classifyToolRisk } from "@atlasent/sdk";

const risk = classifyToolRisk("aws.ec2.terminate_instance");
// => "CRITICAL"

// Use to conditionally add logging or pre-flight checks:
if (risk === "CRITICAL") {
  console.log("Warning: CRITICAL risk action — additional review recommended");
}

const permit = await atlasent.protect({
  agent: actor,
  action: "aws.ec2.terminate_instance",
  context: { ...infraContext, riskLevel: risk },
});
```

## Context fields by action type

### `aws.ec2.*`
| Field | Type | Description |
|-------|------|-------------|
| `instanceId` | string | EC2 instance ID |
| `region` | string | AWS region |
| `authorizedBy` | string | Actor email |
| `changeTicket` | string | Change ticket reference |
| `reason` | string | Reason for action |

### `github.repos.delete`
| Field | Type | Description |
|-------|------|-------------|
| `repoFullName` | string | `org/repo` format |
| `deletedBy` | string | Actor email |
| `changeTicket` | string | Change ticket reference |
| `reason` | string | Reason for deletion |

### `database.table.drop` / `database.volume.delete`
| Field | Type | Description |
|-------|------|-------------|
| `objectName` | string | Table or volume name |
| `database` | string | Database identifier |
| `authorizedBy` | string | Incident commander email |
| `backupVerified` | boolean | Backup has been verified (required `true`) |
| `changeTicket` | string | Change ticket reference |

## Risk classification

| Risk level | Actions | Minimum role |
|------------|---------|--------------|
| `CRITICAL` | terminate, delete, drop, destroy | `incident_commander` |
| `HIGH` | stop, disable, drain | `on_call_engineer` |
| `MEDIUM` | restart, reboot, scale | On-call engineer |
| `LOW` | read, describe, list | Authenticated user |

## Policy

Load `policies/infra-actions.yaml` into your AtlaSent org:

> ⚠️ **WARNING**: This endpoint (`v1-policy-bundles`) is disabled in production and will return 404.

```bash
curl -X POST https://api.atlasent.io/functions/v1/v1-policy-bundles \
  -H "Authorization: Bearer $ATLASENT_API_KEY" \
  -H "Content-Type: application/yaml" \
  --data-binary @policies/infra-actions.yaml
```
