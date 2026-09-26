# Contract Execution and Amendment — Authorization Quickstart

AtlaSent enforces non-bypassable authorization for contract execution and
material amendment using the `contract.execute` and `contract.amend` action
types with fail-closed, SOX-aligned enforcement. Every contract decision is
recorded in an immutable SHA-256 hash-linked audit chain before the contract
management system is updated.

## The 5-step flow

1. **Legal review** — `legalApprovedBy` must be on the authorized legal
   approver list. All contracts require legal sign-off regardless of value.
2. **CFO threshold check** — contracts with `contractValue` above $250,000
   require additional `cfoSignOffBy` authorization. High-value contracts are
   blocked without it.
3. **Evaluate** — call `atlasent.protect()` with full contract context.
   AtlaSent checks approver lists, value threshold, and required fields.
4. **Issue permit** — on `allow`, a single-use cryptographic permit is issued
   (TTL: 15 minutes). Denied requests never reach the contract management system.
5. **Verify and execute** — permit is verified before the contract is marked
   EXECUTED and the revenue recognition schedule is initialized.

For `contract.amend`, material amendments additionally require an
`escalationNote` documenting the business rationale before the permit is issued.

> **`machine_executable=false`** — Automated procurement bots cannot
> self-authorize contract execution. Named legal counsel must appear on every
> execution request.

## Run

```bash
pip install -r requirements.txt

# Full demo (3 scenarios, offline stub, no API key required)
python main.py

# With live AtlaSent API
ATLASENT_API_KEY=ask_live_... python main.py
```

## Scenarios

| # | Action | Outcome | Reason |
|---|--------|---------|--------|
| 1 | `contract.execute` | ALLOW | $500k contract, legal + CFO sign-off present |
| 2 | `contract.execute` | DENY — `DENY_CFO_SIGNOFF_MISSING` | $750k contract, `cfoSignOffBy` absent |
| 3 | `contract.amend` | ALLOW | Material payment term amendment, legal sign-off + escalation note |

## Context fields — `contract.execute`

| Field | Type | Description |
|-------|------|-------------|
| `contractId` | string | Unique contract identifier |
| `counterparty` | string | Counterparty legal entity name |
| `contractValue` | float | Total contract value in USD |
| `contractType` | string | `master_services_agreement` \| `nda` \| `sow` \| `amendment` |
| `legalApprovedBy` | string | Legal counsel email (must be on authorized list) |
| `cfoSignOffBy` | string | CFO email — required when `contractValue > $250,000` |
| `effectiveDate` | string | ISO 8601 contract effective date |
| `termMonths` | integer | Contract duration in months |
| `revenueRecognitionMethod` | string | ASC 606 method (informational) |

## Context fields — `contract.amend`

| Field | Type | Description |
|-------|------|-------------|
| `contractId` | string | Contract being amended |
| `amendmentId` | string | Unique amendment identifier |
| `amendmentType` | string | `material` \| `administrative` |
| `amendedClause` | string | Clause or section being amended |
| `legalApprovedBy` | string | Legal counsel email (must be on authorized list) |
| `escalationNote` | string | Required for `material` amendments — business rationale |
| `priorTermValue` | string | Original term value (informational) |
| `newTermValue` | string | Amended term value (informational) |
| `revenueImpact` | string | `timing_only` \| `amount_change` \| `none` (informational) |

## Policy

Load `policies/contract-execution.yaml` into your AtlaSent org:

> ⚠️ **WARNING**: This endpoint (`v1-policy-bundles`) is disabled in production and will return 404.

```bash
curl -X POST https://api.atlasent.io/functions/v1/v1-policy-bundles \
  -H "Authorization: Bearer $ATLASENT_API_KEY" \
  -H "Content-Type: application/yaml" \
  --data-binary @policies/contract-execution.yaml
```

## Prerequisites

- Python ≥ 3.11
- `atlasent` Python SDK (`pip install atlasent>=0.9`)
- AtlaSent API key (optional — runs offline without one)

## Regulatory context

| Requirement | Reference |
|-------------|-----------|
| Financial commitment authorization | SOX Section 302 — CEO/CFO certification |
| Material contract controls | SOX Section 404 — internal controls |
| Revenue recognition | ASC 606 — contracts with customers |
| Delegation of authority | COSO framework — control environment |
| Audit trail | SOX Section 802 — records management |

### SOX / ASC 606 context

SOX Section 302 requires CEOs and CFOs to certify that material contracts are
properly authorized and disclosed. ASC 606 governs how contract terms affect
revenue recognition timing and amount. AtlaSent enforces these requirements by:

- **CFO threshold gate** — contracts above $250,000 require explicit CFO
  sign-off. The threshold is configurable per your delegation-of-authority
  policy. This prevents AP or legal teams from self-authorizing material
  financial commitments.
- **Legal review gate** — all contracts (regardless of value) require named
  legal counsel approval, satisfying the control-environment requirements
  of the COSO framework.
- **Material amendment escalation** — amendments that change payment terms,
  scope, or pricing require an `escalationNote` capturing the business
  rationale. This creates an auditable record of why the original contract
  terms were modified, supporting ASC 606 variable consideration analysis.
- **Immutable audit trail** — every execution and amendment decision is
  recorded in the hash-linked chain with contract ID, counterparty, value,
  approver identities, and effective date, giving auditors the complete
  authorization provenance for every contract in the estate.
