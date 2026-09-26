# GxP VQP Re-derivation — Delta VQP Phase 3 Quickstart

This example demonstrates **Delta VQP Phase 3 re-derivation auditing** using
AtlaSent's `VQPClient` (TypeScript) and direct Supabase edge function calls
(Python). It covers snapshot generation, integrity verification, and score
drift detection across all 6 SOC 2 VQP criteria.

> **Server-side only.** `VQPClient` requires a Supabase **service role key**
> (`ATLASENT_SUPABASE_SERVICE_ROLE_KEY`). It must never run in a browser or
> be exposed to client-side code. The Python script has the same constraint.

## VQP Criteria

| Criterion | SOC 2 Ref | Description |
|-----------|-----------|-------------|
| `access_control` | CC6.1 | MFA, least-privilege, role review |
| `audit_coverage` | CC7.2 | Event logging, retention, tamper-evidence |
| `escalation_paths` | CC7.4 | Defined, tested, owner-assigned |
| `deny_specificity` | CC8.1 | No wildcard denies, scope documented |
| `hold_conditions` | CC6.3 | Hold logic tested, release criteria documented |
| `override_governance` | CC5.2 | Dual approval, audit log, break-glass policy |

## Verdicts

| Verdict | Condition |
|---------|-----------|
| `qualified` | score ≥ 85, no criterion failures |
| `conditionally_qualified` | score ≥ 60, no criterion failures |
| `not_qualified` | score < 60 or one or more criterion failures |

## Scenarios

| # | Scenario | Expected outcome |
|---|----------|------------------|
| 1 | Generate + Verify | `verdict=qualified`, `hashMatch=true`, `verdictChanged=false` |
| 2 | Verify only (existing snapshot) | `hashMatch=true` |
| 3 | Verify with rerun (score drift) | `scoreDelta` and `verdictChanged` surfaced |

## Run

### TypeScript

```bash
npm install

# Copy and fill in env vars
cp .env.example .env
# Edit .env: set ATLASENT_SUPABASE_URL, ATLASENT_SUPABASE_SERVICE_ROLE_KEY,
#            ATLASENT_ORG_ID, ATLASENT_BUNDLE_ID

npm run demo
```

Offline (no Supabase project required):

```bash
ATLASENT_SUPABASE_URL=http://localhost:54321 \
ATLASENT_SUPABASE_SERVICE_ROLE_KEY=service_role_stub \
ATLASENT_ORG_ID=org_stub \
ATLASENT_BUNDLE_ID=bundle_stub \
npm run demo
```

### Python

```bash
pip install -r requirements.txt

# Offline stub mode (ATLASENT_SUPABASE_URL not set — prints stub outputs)
python main.py

# Live
ATLASENT_SUPABASE_URL=https://your-project.supabase.co \
ATLASENT_SUPABASE_SERVICE_ROLE_KEY=<service_role_key> \
ATLASENT_ORG_ID=org_replace_me \
ATLASENT_BUNDLE_ID=bundle_replace_me \
python main.py
```

## API

### `VQPClient.generate({ bundleId, orgId, vqpContext })`

Calls the `v1-generate-vqp` Supabase edge function. Returns:

```ts
{ snapshotId, promptHash, score, verdict, criteria }
```

### `VQPClient.verify({ snapshotId, rerun? })`

Calls the `v1-verify-vqp` Supabase edge function. Returns:

```ts
{ snapshotId, hashMatch, rerunScore, scoreDelta, verdictChanged, auditLogId }
```

Pass `rerun: true` to re-evaluate all criteria against current state and
detect score drift.

## Prerequisites

- Node.js ≥ 20 (TypeScript) or Python ≥ 3.11
- `@atlasent/sdk` ≥ 2.5.0 (TypeScript) / `httpx` ≥ 0.27.0 (Python)
- Supabase project with `v1-generate-vqp` and `v1-verify-vqp` edge functions
  deployed, and a service role key
