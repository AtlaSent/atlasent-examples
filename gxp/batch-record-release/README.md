# GxP Batch Record Release — Authorization Quickstart

> **GxP pilot starter kit** — This example is part of the GxP pilot starter
> kit at [`atlasent-gxp-starter/`](https://github.com/atlasent-systems-inc/atlasent-gxp-starter).
> See that repo for the full org setup, policy validation tooling, and
> 21 CFR Part 11 / EU Annex 11 policy bundles.

AtlaSent enforces non-bypassable authorization for GxP manufacturing batch
record release using the `manufacturing.batch_record.release` action with
fail-closed, dual-approver, `machine_executable=false` enforcement.

## The 5-step flow

1. **QA review** — authorized QA manager reviews the completed batch record
   and initiates release via `certifiedBy` in the evaluation context.
2. **Evaluate** — call `atlasent.protect()` with full batch context. AtlaSent
   checks completeness, dual signatory presence, and authorized list membership.
3. **Dual sign-off** — a second authorized QA signatory (`qaSignoffBy`) must
   be distinct from the primary certifier; both must be on the authorized list.
4. **Issue permit** — on `allow`, a single-use cryptographic permit is issued
   (TTL: 15 minutes). Denied if batch record is incomplete or second approver
   is absent.
5. **Verify and execute** — permit is verified server-side before the batch
   status is set to `RELEASED` in the manufacturing system and a release
   certificate is generated.

> **`machine_executable=false`** — AI agents cannot auto-approve batch releases.
> A human QA decision is always required. If an AI agent attempts this action
> without a human in the loop, the request is denied at the policy layer.

## Run

```bash
pip install -r requirements.txt

# Full demo (3 scenarios, offline stub, no API key required)
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

## Scenarios

| # | Outcome | Reason |
|---|---------|--------|
| 1 | ALLOW | Complete batch record, both QA signatories present and authorized |
| 2 | DENY — `DENY_BATCH_RECORD_INCOMPLETE` | `batchRecordComplete=false` |
| 3 | DENY — `DENY_DUAL_APPROVER_MISSING` | `qaSignoffBy` absent (only one approver) |

## Context fields

| Field | Type | Description |
|-------|------|-------------|
| `batchId` | string | Unique batch identifier |
| `productCode` | string | Product / drug code |
| `lotNumber` | string | Manufacturing lot number |
| `certifiedBy` | string | Primary QA signatory (email) |
| `qaSignoffBy` | string | Second QA signatory (email) — distinct from `certifiedBy` |
| `batchRecordComplete` | boolean | All batch record sections reviewed |
| `deviationCount` | integer | Open deviations (informational) |
| `regulatoryRegion` | string | `US-FDA` \| `EU-EMA` \| `ICH` |

## Policy

Load `policies/batch-record-release.yaml` into your AtlaSent org:

> ⚠️ **WARNING**: This endpoint (`v1-policy-bundles`) is disabled in production and will return 404. See `atlasent-api/supabase/runtime-functions-disabled.json`.

```bash
curl -X POST https://api.atlasent.io/functions/v1/v1-policy-bundles \
  -H "Authorization: Bearer $ATLASENT_API_KEY" \
  -H "Content-Type: application/yaml" \
  --data-binary @policies/batch-record-release.yaml
```

## Prerequisites

- Python ≥ 3.11 or Node.js ≥ 20
- `atlasent` Python SDK or `@atlasent/sdk` npm package
- AtlaSent API key (optional — runs offline without one)

## Regulatory context

| Requirement | Reference |
|-------------|-----------|
| Batch record review before release | 21 CFR Part 211.192 |
| Electronic records integrity | 21 CFR Part 11 |
| Computerised systems validation | EU GMP Annex 11 |
| Dual authority for critical decisions | ICH Q10 §3.2.1 |
| Audit trail (10-year retention) | 21 CFR Part 211.68 |
