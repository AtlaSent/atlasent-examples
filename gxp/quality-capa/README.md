# GxP Quality CAPA Lifecycle — Authorization Quickstart

AtlaSent enforces non-bypassable authorization for the full CAPA (Corrective
and Preventive Action) lifecycle across five action types using fail-closed,
role-gated enforcement.

## The 5-step flow

1. **Initiate** — `quality.capa.initiate`: QA manager opens the CAPA record;
   `initiatedBy` must have the `qa_manager` role.
2. **Assign** — `quality.capa.assign`: QA staff assigns an owner and due date.
3. **Progress** — `quality.capa.progress`: Owner records notes and percent
   complete; any authenticated staff member may update.
4. **Effectiveness check** — `quality.capa.effectiveness_check`: QA manager
   performs 90-day verification; `checkedBy` must have `qa_manager` role and
   provide an evidence URI.
5. **Close** — `quality.capa.close`: Dual approval required — `closedBy` and
   `secondClosedBy` must be distinct and both in `qa_staff`.

## Run

```bash
pip install -r requirements.txt

# Full demo (3 flows, offline stub, no API key required)
python main.py

# With live AtlaSent API
ATLASENT_API_KEY=ask_live_... python main.py
```

TypeScript:

```bash
npm install
npx @atlasent/sdk mock &   # start offline mock server
ATLASENT_API_URL=http://127.0.0.1:4747 ATLASENT_API_KEY=mock npx tsx main.ts
```

## Flows

| # | Flow | Outcome |
|---|------|---------|
| 1 | Full happy-path: initiate → assign → progress → effectiveness check → close | 5 × ALLOW |
| 2 | Closure blocked: `secondClosedBy` absent | DENY — `DENY_DUAL_APPROVER_MISSING` |
| 3 | Effectiveness check denied: reviewer not in `qa_manager` role | DENY — `DENY_AUTHORITY` |

## Context fields by action

### `quality.capa.initiate`
| Field | Type | Description |
|-------|------|-------------|
| `capaId` | string | Unique CAPA identifier |
| `initiatedBy` | string | QA manager email (must have `qa_manager` role) |
| `source` | string | Source reference (e.g. deviation report ID) |
| `severity` | string | `minor` \| `major` \| `critical` |
| `description` | string | CAPA description |

### `quality.capa.assign`
| Field | Type | Description |
|-------|------|-------------|
| `capaId` | string | CAPA identifier |
| `assignedBy` | string | QA staff member doing the assignment |
| `assignedTo` | string | Owner email |
| `dueDate` | string | ISO 8601 date |

### `quality.capa.progress`
| Field | Type | Description |
|-------|------|-------------|
| `capaId` | string | CAPA identifier |
| `updatedBy` | string | Author of the update |
| `progressNote` | string | Free-text progress note |
| `percentComplete` | integer | 0–100 |

### `quality.capa.effectiveness_check`
| Field | Type | Description |
|-------|------|-------------|
| `capaId` | string | CAPA identifier |
| `checkedBy` | string | QA manager email (must have `qa_manager` role) |
| `effectivenessScore` | float | 0.0–1.0 |
| `evidenceUri` | string | URI to evidence document |

### `quality.capa.close`
| Field | Type | Description |
|-------|------|-------------|
| `capaId` | string | CAPA identifier |
| `closedBy` | string | Primary closer (must be in `qa_staff`) |
| `secondClosedBy` | string | Second approver (distinct from `closedBy`, must be in `qa_staff`) |
| `closureRationale` | string | Rationale for closure |

## Policy

Load `policies/quality-capa.yaml` into your AtlaSent org:

> ⚠️ **WARNING**: This endpoint (`v1-policy-bundles`) is disabled in production and will return 404.

```bash
curl -X POST https://api.atlasent.io/functions/v1/v1-policy-bundles \
  -H "Authorization: Bearer $ATLASENT_API_KEY" \
  -H "Content-Type: application/yaml" \
  --data-binary @policies/quality-capa.yaml
```

## Regulatory context

| Requirement | Reference |
|-------------|-----------|
| CAPA procedures | 21 CFR Part 820.100 |
| Electronic records / signatures | 21 CFR Part 11 |
| CAPA system | ICH Q10 §3.2.3 |
| Improvement / CAPA | ISO 13485:2016 §8.5 |
| Audit trail (10-year retention) | 21 CFR Part 820 |
