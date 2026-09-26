# Deployment Gate V2 — Authorization Quickstart

This example documents the V2 AtlaSent action strings for deployment
authorization and shows how to migrate from V1.

## V1 → V2 migration

| V1 action string | V2 action string |
|-----------------|-----------------|
| `production.deploy` | `deployment.production.execute` |
| (new in V2) | `deployment.staging.execute` |
| (new in V2) | `deployment.rollback.execute` |

V2 expands the deployment context with:
- `deploymentId` — unique deployment run identifier
- `buildSha` — full commit SHA being deployed
- `approvedBy` — human actor who approved the deployment
- `rollbackPlan` — rollback procedure documented before deploy
- `changeTicket` — change management ticket reference

### Why migrate to V2?

V2 action strings provide richer context, enabling:
- **Change ticket enforcement** — production deploys require `changeTicket`
- **Rollback authorization** — dedicated `deployment.rollback.execute` with
  incident commander requirement
- **Risk-level gates** — HIGH risk deployments require dual approval
- **Staging separation** — `deployment.staging.execute` has looser controls
  than production

## Run

### Rollback demo (Python)

```bash
pip install -r requirements.txt

# Full rollback demo (3 scenarios, offline stub, no API key required)
python rollback.py

# With live AtlaSent API
ATLASENT_API_KEY=ask_live_... python rollback.py
```

### GitHub Actions

Copy `.github/workflows/deploy-v2.yml` to your repository. Add these secrets:

| Secret | Purpose |
|--------|---------|
| `ATLASENT_API_KEY` | AtlaSent API key |
| `ATLASENT_API_URL` | Optional; defaults to `https://api.atlasent.io/functions/v1` |

Optional environment variables in the workflow:

| Variable | Purpose |
|----------|---------|
| `CHANGE_TICKET` | Change management ticket reference (required for production) |
| `ROLLBACK_PLAN` | Rollback procedure (defaults to `git revert HEAD`) |
| `INCIDENT_ID` | Incident ID for rollback job |

## Rollback scenarios

| # | Outcome | Reason |
|---|---------|--------|
| 1 | ALLOW | Incident commander authorizes rollback with full context |
| 2 | DENY | Engineer does not have `incident_commander` role |
| 3 | DENY | `incidentId` missing — fail-closed requires incident reference |

## Context fields

### `deployment.production.execute`
| Field | Type | Description |
|-------|------|-------------|
| `deploymentId` | string | Unique deployment identifier |
| `buildSha` | string | Git commit SHA |
| `approvedBy` | string | Approver email |
| `rollbackPlan` | string | Documented rollback procedure |
| `changeTicket` | string | Change ticket reference (required) |
| `riskLevel` | string | `LOW` \| `MEDIUM` \| `HIGH` (HIGH requires `secondApprovedBy`) |

### `deployment.staging.execute`
| Field | Type | Description |
|-------|------|-------------|
| `buildSha` | string | Git commit SHA |
| `approvedBy` | string | Approver email |

### `deployment.rollback.execute`
| Field | Type | Description |
|-------|------|-------------|
| `incidentId` | string | Incident identifier (required) |
| `rollbackTarget` | string | Target ref/SHA to roll back to |
| `authorizedBy` | string | Incident commander email |
| `reason` | string | Reason for rollback |

## Policy

Load `policies/deployment-v2.yaml` into your AtlaSent org:

> ⚠️ **WARNING**: This endpoint (`v1-policy-bundles`) is disabled in production and will return 404. See `atlasent-api/supabase/runtime-functions-disabled.json`.

```bash
curl -X POST https://api.atlasent.io/functions/v1/v1-policy-bundles \
  -H "Authorization: Bearer $ATLASENT_API_KEY" \
  -H "Content-Type: application/yaml" \
  --data-binary @policies/deployment-v2.yaml
```
