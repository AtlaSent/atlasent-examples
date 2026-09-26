# Pricing Rule and Discount Governance — Authorization Quickstart

AtlaSent enforces non-bypassable authorization for pricing rule publication
and discount approval using the `pricing.rule.publish` and
`pricing.discount.approve` action types with fail-closed, tiered-authority
enforcement. Every pricing decision is recorded in an immutable SHA-256
hash-linked audit chain before the pricing engine or CRM is updated.

## The 5-step flow

1. **Discount tier classification** — the `discountPct` value determines which
   approval path applies automatically:
   - `<= 10%` — auto-approved by a pricing manager
   - `> 10%` — CFO escalation required (`cfoSignOffBy` must be present)
   - `> 40%` — hard deny, exceeds maximum delegated authority; no escalation path
2. **Authority check** — `approvedBy` must be on the authorized pricing manager
   list for all discount requests.
3. **Evaluate** — call `atlasent.protect()` with full discount context.
   AtlaSent applies the tier logic, checks approver lists, and issues the decision.
4. **Issue permit** — on `allow`, a single-use cryptographic permit is issued
   (TTL: 15 minutes). Denied requests never reach the CRM or pricing engine.
5. **Verify and execute** — permit is verified before the discount is marked
   APPROVED and the revenue recognition impact is logged.

> **`machine_executable=false`** — Sales bots cannot self-approve discounts.
> A named pricing manager must appear on every discount request.

## Run

```bash
pip install -r requirements.txt

# Full demo (3 scenarios, offline stub, no API key required)
python main.py

# With live AtlaSent API
ATLASENT_API_KEY=ask_live_... python main.py
```

## Scenarios

| # | Action | Outcome | Discount | Reason |
|---|--------|---------|----------|--------|
| 1 | `pricing.discount.approve` | ALLOW | 8% | Within auto-approval ceiling — pricing manager only |
| 2 | `pricing.discount.approve` | ALLOW | 25% | CFO escalation required and `cfoSignOffBy` present |
| 3 | `pricing.discount.approve` | DENY — `DENY_EXCEEDS_AUTHORITY` | 55% | Exceeds 40% maximum delegated authority ceiling |

## Discount authority tiers

| Discount range | Approval required | Notes |
|----------------|-------------------|-------|
| 0% – 10% | Pricing manager | Auto-approved within standard tier |
| > 10% – 40% | Pricing manager + CFO | `cfoSignOffBy` required |
| > 40% | No approval path | Hard deny — escalate to board committee |

## Context fields — `pricing.discount.approve`

| Field | Type | Description |
|-------|------|-------------|
| `discountId` | string | Unique discount request identifier |
| `customerId` | string | Customer or account identifier |
| `discountPct` | float | Requested discount percentage (0.0 – 100.0) |
| `dealValueUsd` | float | Total deal value in USD (informational, captured in audit) |
| `approvedBy` | string | Pricing manager email (must be on authorized list) |
| `cfoSignOffBy` | string | CFO email — required when `discountPct > 10%` |
| `businessJustification` | string | Business rationale for the discount |
| `dealStage` | string | `proposal` \| `negotiation` \| `final` |
| `productLine` | string | Product line or SKU group |
| `competitorName` | string | Competitor being displaced (informational) |

## Context fields — `pricing.rule.publish`

| Field | Type | Description |
|-------|------|-------------|
| `ruleId` | string | Unique pricing rule identifier |
| `ruleType` | string | `list_price` \| `volume_tier` \| `promotional` \| `regional` |
| `publishedBy` | string | Pricing manager email (must be on authorized list) |
| `effectiveDate` | string | ISO 8601 date the rule takes effect |
| `targetSegments` | list[string] | Customer segments the rule applies to |

## Policy

Load `policies/pricing-governance.yaml` into your AtlaSent org:

> ⚠️ **WARNING**: This endpoint (`v1-policy-bundles`) is disabled in production and will return 404. See `atlasent-api/supabase/runtime-functions-disabled.json`.

```bash
curl -X POST https://api.atlasent.io/functions/v1/v1-policy-bundles \
  -H "Authorization: Bearer $ATLASENT_API_KEY" \
  -H "Content-Type: application/yaml" \
  --data-binary @policies/pricing-governance.yaml
```

## Prerequisites

- Python ≥ 3.11
- `atlasent` Python SDK (`pip install atlasent>=0.9`)
- AtlaSent API key (optional — runs offline without one)

## Regulatory context

| Requirement | Reference |
|-------------|-----------|
| Revenue recognition — contract modification | ASC 606-10-25-10 through 25-13 |
| Delegation of authority | SOX Section 302 / COSO control environment |
| Price discrimination documentation | Robinson-Patman Act (US) |
| Transfer pricing controls | OECD Transfer Pricing Guidelines |
| Revenue controls | SOC 2 Type II CC4.1 — monitoring of controls |

### Revenue controls context

Ungoverned discounting creates material risks for revenue recognition and
financial reporting. AtlaSent addresses these risks by:

- **Tiered authority enforcement** — the discount tier logic mirrors common
  delegation-of-authority policies, making policy non-bypassable. A 35%
  discount cannot be approved without CFO sign-off, regardless of deal urgency.
- **Hard deny above ceiling** — discounts above 40% have no escalation path
  in the policy, preventing "escalation theater" where approvals are rubber-
  stamped under time pressure. The ceiling is configurable per your DOA policy.
- **CFO identity pinning** — `cfoSignOffBy` is validated against the authorized
  CFO list, preventing nominal "approval" by unauthorized delegates.
- **Immutable audit trail** — every discount decision (approve or deny) is
  recorded with the exact `discountPct`, `dealValueUsd`, approver identities,
  and business justification. This supports ASC 606 variable consideration
  analysis and SOX control evidence for revenue controls.
- **Pricing rule governance** — `pricing.rule.publish` gates prevent
  unauthorized list-price changes that could affect all customer invoices,
  requiring named pricing manager sign-off for every rule publication.
