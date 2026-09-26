# Data Export — AtlaSent Quickstart

AtlaSent enforces non-bypassable authorization for general-purpose customer
data exports and produces an immutable, offline-verifiable audit trail for
every permitted export action.

This quickstart covers **non-PHI, non-clinical** data (customer records,
analytics datasets). For regulated clinical data export see
[`atlasent-examples/regulated/clinical-data-export/`](../regulated/clinical-data-export/).

## The 7-step flow

1. **Install SDK** — add AtlaSent to your data pipeline.
2. **Configure environment** — add your API key and org ID.
3. **Seed the policy pack** — upload `policies/data-export.yaml` to your AtlaSent tenant.
4. **Run the Python quickstart** — 3 enforcement scenarios including row-level batch.
5. **Run the TypeScript quickstart** — batch evaluation loop with SHA-256 bundle sealing.
6. **Review the audit chain** — every permitted export is captured in a hash-linked chain.
7. **Offline bundle verification** — verify the audit evidence with no AtlaSent dependency.

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.11+ | For `main.py` and `batch-authorize.py` |
| Node.js 20+ | For `main.ts` |
| AtlaSent API key | Create one under Settings → API Keys in the console |
| AtlaSent org ID | Settings → Organisation |

## Step 1: Install SDK

**Python:**
```bash
pip install -r requirements.txt
```

**TypeScript:**
```bash
npm install
```

## Step 2: Configure environment

```bash
cp .env.example .env
# Edit .env and fill in ATLASENT_API_KEY, ATLASENT_ORG_ID
```

Without an API key the scripts run in offline stub mode — no network required.

## Step 3: Seed the policy pack

> ⚠️ **WARNING**: This endpoint (`v1-policy-bundles`) is disabled in production and will return 404. See `atlasent-api/supabase/runtime-functions-disabled.json`.

```bash
curl -X POST https://api.atlasent.io/functions/v1/v1-policy-bundles \
  -H "Authorization: Bearer $ATLASENT_API_KEY" \
  -H "Content-Type: application/yaml" \
  --data-binary @policies/data-export.yaml
```

The policy pack enforces:
- PII exports only to verified destinations (`DENY_DESTINATION_UNVERIFIED` on fail)
- PII exports require a documented purpose code (`DENY_PURPOSE_MISSING` on fail)
- Exports exceeding 100,000 rows require escalation

The `${verified_destinations}` placeholder is resolved at evaluation time from
your AtlaSent tenant's verified-destination list (configure under
Settings → Policy Variables).

## Step 4: Run the Python quickstart (3 scenarios)

```bash
python main.py
```

| Scenario | Dataset | Destination | Expected outcome |
|---|---|---|---|
| 1 | PII, 5,000 rows | `snowflake://acme/analytics` (verified) | **ALLOW** |
| 2 | PII, 500 rows | `s3://personal-bucket-bob` (unverified) | **DENY_DESTINATION_UNVERIFIED** |
| 3 | Mixed PII/non-PII batch | Mixed destinations | **PARTIAL** — non-PII rows allowed, PII to unverified denied |

**Scenario 1** shows the approved path: PII dataset to a verified destination
with a documented purpose code. AtlaSent issues a cryptographic permit.

**Scenario 2** shows the destination-blocked path: PII to an unverified
destination is denied regardless of purpose. The evaluation ID is logged
for audit.

**Scenario 3** shows row-level evaluation within a single batch: non-PII rows
are evaluated independently and may be approved even when PII rows in the
same batch are denied.

### Standalone batch authorizer

```bash
# Demo with built-in sample rows
python batch-authorize.py

# Evaluate rows from a JSON file
python batch-authorize.py --rows rows.json

# Output results as JSON (pipeline-friendly)
python batch-authorize.py --json
```

The batch authorizer evaluates each row independently in parallel and returns
allowed rows (with permit IDs and audit hashes) and denied rows (with decision
codes). If the total `rowsRequested` across all rows exceeds 100,000, the
entire batch is denied before row-level evaluation (`BATCH_DENIED_ROW_CAP`,
exit code 2).

## Step 5: Run the TypeScript quickstart

```bash
npx tsx main.ts
```

The TypeScript quickstart demonstrates:
- **`protectDataExport()`** — SDK convenience wrapper for `customer.data.export`
- **Batch evaluation loop** — parallel row evaluation with per-row permit collection
- **SHA-256 bundle sealing** — the allowed-permits bundle is hashed so the
  export can be verified after the fact

## Step 6: Review the audit chain

Every permitted export is appended to the AtlaSent audit chain. With a live
API key:

```bash
curl -H "Authorization: Bearer $ATLASENT_API_KEY" \
  "https://api.atlasent.io/v1/audit/exports?action=customer.data.export&from=2026-05-01" \
  -o audit-export.json
```

## Step 7: Offline bundle verification

```bash
# Verify with the accounting-close verifier (same bundle format)
python ../accounting-close/verify-audit.py --bundle bundle.json
```

## Row-level vs. dataset-level evaluation

**Use row-level evaluation when:**
- Your export batch contains rows with different PII classifications
- Different rows may go to different destinations
- You need per-row permit IDs for lineage tracking
- The batch may be partially approved (some rows allowed, some denied)

**Use dataset-level evaluation when:**
- All rows in the batch have the same classification and destination
- You want a single permit covering the whole export
- The batch is all-or-nothing (any denial blocks the entire export)
- Row count is the primary concern (use `rowsRequested` context field)

The batch authorizer (`batch-authorize.py`) implements row-level evaluation.
`main.py` Scenario 1 and 2 demonstrate dataset-level evaluation.

## Data warehouse integration patterns

The following warehouse connectors are on the roadmap. Until they are
available, use the `protectDataExport()` pattern above as the integration
template — add the AtlaSent `protect()` call as the first step in your
export pipeline before any warehouse API call.

| Warehouse | Connector status |
|---|---|
| Snowflake | Deferred — reference the connector slot pattern in `main.ts` |
| BigQuery | Deferred — reference the connector slot pattern in `main.ts` |
| Databricks | Deferred — reference the connector slot pattern in `main.ts` |

The connector slot pattern: call `protectDataExport()` first, then use the
returned `permit.permitId` as a correlation ID in the warehouse job metadata
(e.g., Snowflake job label, BigQuery job labels map, Databricks run tag).
This links every warehouse job to a verifiable AtlaSent permit.

## Protected actions

| Action | Enforcement rule |
|---|---|
| `customer.data.export` | PII → verified destination only; purpose required; row cap enforced |

## Related

- Clinical data export (regulated): [`atlasent-examples/regulated/clinical-data-export/`](../regulated/clinical-data-export/)
- Accounting close bundle: [`atlasent-examples/accounting-close/`](../accounting-close/)
- Policy reference: [`policies/data-export.yaml`](./policies/data-export.yaml)
