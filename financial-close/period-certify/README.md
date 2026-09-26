# Financial Period Close Certification — Authorization Quickstart

AtlaSent enforces non-bypassable authorization for financial period close
certification using the `period.close.certify` action with fail-closed,
critical-risk, financial controller quorum enforcement. Every close certification
decision (allow or deny) is recorded in an immutable SHA-256 hash-linked audit
chain before any period status is updated in the ERP.

## The 5-step flow

1. **Financial controller authorization** — `financialController` must be on the
   authorized controllers list. Unauthenticated or low-privilege requests are
   denied immediately.
2. **Required fields validation** — `periodId`, `certifiedBy`, and
   `financialController` are all required. Missing fields throw `TypeError`
   before the evaluate call.
3. **Evaluate** — call `atlasent.protect()` with full period close context.
   AtlaSent checks authority, required fields, and quorum availability.
4. **Issue permit** — on `allow`, a single-use cryptographic permit is issued
   (close window: 48 hours). Denied if authority is missing or quorum not
   satisfied.
5. **Verify and execute** — permit is verified before the period close executes
   in the ERP (status update, SOX evidence generation, audit chain sealing).

> **`machine_executable=false`** — Automated agents cannot self-authorize
> period close certification. A financial controller's identity must be present
> on every request.

## Run

```bash
pip install -r requirements.txt

# Full demo (3 scenarios, offline stub, no API key required)
python main.py

# With live AtlaSent API
ATLASENT_API_KEY=ask_live_... python main.py

# TypeScript demo
npm install
ATLASENT_API_KEY=ask_live_... npx tsx main.ts
```

## Scenarios

| # | Outcome | Reason |
|---|---------|--------|
| 1 | ALLOW | Q1 2026 close, authorized financial controller, all fields present |
| 2 | DENY — `DENY_AUTHORITY` | AP clerk not on authorized financial controllers list |
| 3 | DENY — `DENY_MISSING_FIELD` | `financialController` absent |

## Context fields

| Field | Type | Description |
|-------|------|-------------|
| `periodId` | string | Financial period identifier (e.g. `2026-Q1`, `2026-04`) |
| `certifiedBy` | string | Primary certifier (controller or accountant initiating the close) |
| `financialController` | string | Financial controller authorizing the period close |

## Escalation parameters

| Parameter | Value |
|-----------|-------|
| `assignedToRole` | `financial-controller` |
| `quorumRequired` | `simple_majority` |
| Close window | 48 hours (`172_800_000` ms) |
| `fail_closed` | `true` |

## Prerequisites

- Python ≥ 3.11 (for Python demo)
- Node.js ≥ 20 + `tsx` (for TypeScript demo)
- `atlasent` Python SDK (`pip install atlasent>=0.9`)
- `@atlasent/sdk` npm package
- AtlaSent API key (optional — runs offline without one)

## Regulatory context

| Requirement | Reference |
|-------------|-----------|
| CEO/CFO certification | SOX Section 302 |
| Internal controls over financial reporting | SOX Section 404 |
| Risk assessment | SOC 2 Type II CC3.2 |
| Monitoring of controls | SOC 2 Type II CC4.1 |
| Control environment — segregation of duties | COSO Framework |
