# Vendor Payment Release — AtlaSent Quickstart

AtlaSent enforces non-bypassable authorization for AP payment release workflows
and produces an immutable, offline-verifiable audit trail for every permitted
payment action.

## The 7-step flow

1. **Install SDK** — add AtlaSent to your AP automation service.
2. **Configure environment** — add your API key and org ID.
3. **Seed the policy pack** — upload `policies/vendor-payment-release.yaml` to your AtlaSent tenant.
4. **Run the Python quickstart** — see 3 enforcement scenarios run end-to-end.
5. **Run the TypeScript quickstart** — same scenarios via the SDK convenience method and raw `protect()`.
6. **Review the audit chain** — every permitted payment is captured in a hash-linked chain.
7. **Offline bundle verification** — verify the audit evidence with no AtlaSent dependency.

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.11+ | For `main.py` |
| Node.js 20+ | For `main.ts` and `erp-webhook.ts` |
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

Or export directly:
```bash
export ATLASENT_API_KEY=ask_live_...
export ATLASENT_ORG_ID=org_...
```

Without an API key the scripts run in offline stub mode — no network required,
deterministic policy enforcement, full audit trail in memory.

## Step 3: Seed the policy pack

> ⚠️ **WARNING**: This endpoint (`v1-policy-bundles`) is disabled in production and will return 404.

```bash
curl -X POST https://api.atlasent.io/functions/v1/v1-policy-bundles \
  -H "Authorization: Bearer $ATLASENT_API_KEY" \
  -H "Content-Type: application/yaml" \
  --data-binary @policies/vendor-payment-release.yaml
```

The policy pack enforces:
- Payments above **$50,000** require dual approval (`HOLD_DUAL_APPROVAL`)
- Payments above **$250,000** require CFO-role approval (`HOLD_CFO_APPROVAL`)
- Submitter must be in the `ap-certifiers` group (`DENY_AUTHORITY` on fail)

## Step 4: Run the Python quickstart (3 scenarios)

```bash
python main.py
```

| Scenario | Amount | Submitter | Expected outcome |
|---|---|---|---|
| 1 | $12,500 | `ap.alice@acme.com` (ap-certifiers) | **ALLOW** — below threshold |
| 2 | $75,000 | `ap.bob@acme.com` (ap-certifiers), no second approver | **HOLD_DUAL_APPROVAL** — above $50k |
| 3 | $5,000 | `contractor.x@external.com` (not in ap-certifiers) | **DENY_AUTHORITY** — unauthorized |

**Scenario 1** shows the happy path: the payment is below the $50,000
dual-approval threshold and the submitter is in the `ap-certifiers` group.
AtlaSent issues a cryptographic permit; the stub ERP queues the payment.

**Scenario 2** shows the hold path: $75,000 exceeds the $50,000 threshold but
no `secondApprover` is provided. The script shows the hold key and then
simulates an AP manager approving the hold in the console — the retry with
`secondApprover` resolves and a permit is issued.

**Scenario 3** shows the deny path: the submitter is not in the `ap-certifiers`
group. AtlaSent returns `DENY_AUTHORITY` and the payment is blocked before
reaching the ERP.

## Step 5: Run the TypeScript quickstart

```bash
npx tsx main.ts
```

The TypeScript quickstart demonstrates two calling patterns:

- **`protectPaymentRelease()`** — the SDK convenience wrapper that normalizes
  the vendor payment context and calls `atlasent.protect()` with the canonical
  `vendor.payment.release` action string. Use this in production AP automation.

- **`atlasent.protect()`** — the raw SDK path. Identical enforcement, slightly
  more verbose. Useful when you need full control over the request shape.

Both patterns throw `AtlaSentDeniedError` on DENY or HOLD — the caller decides
how to surface the hold to the AP manager (see `erp-webhook.ts`).

## Step 6: Review the audit chain

Every permitted action is appended to a SHA-256 hash-linked audit chain.
The offline stub prints the chain at the end of each run:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Audit Trail   2 permitted action(s)   immutable hash-linked chain
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  [1] 2026-05-29T...
      action:    vendor.payment.release
      actor:     ap.alice@acme.com
      permit_id: pt_...
      hash:      <32 hex chars>
      prev:      (genesis)
```

With a live API key, export the chain from the AtlaSent audit API:
```bash
curl -H "Authorization: Bearer $ATLASENT_API_KEY" \
  "https://api.atlasent.io/v1/audit/exports?from=2026-05-01&to=2026-05-31" \
  -o audit-export.json
```

## Step 7: Offline bundle verification

The audit bundle is self-contained. Verify it with no AtlaSent SDK dependency:

```bash
# Export the bundle (offline stub mode)
python main.py --export bundle.json 2>/dev/null || true

# Verify with the accounting-close verifier (same bundle format)
python ../accounting-close/verify-audit.py --bundle bundle.json
```

The verifier exits non-zero if any event field is tampered with, any event is
inserted/deleted/reordered, or the Ed25519 signature does not verify.

## ERP connector patterns

`erp-webhook.ts` is the reference integration pattern for ERP systems. It
demonstrates:

- **NetSuite `Invoice.approve`** → normalized to `vendor.payment.release`
- **NetSuite `Payment.release`** → normalized to `vendor.payment.release`

The stub hardcodes sample NetSuite webhook payloads (no live NetSuite connection
required). To run in stub mode:

```bash
npx tsx erp-webhook.ts
```

To run as a live webhook server (requires `ATLASENT_API_KEY`):

```bash
ATLASENT_API_KEY=ask_live_... ATLASENT_WEBHOOK_SECRET=whsec_... npx tsx erp-webhook.ts
# POST /netsuite/webhook — receive NetSuite events
# POST /atlasent/webhook — receive AtlaSent hold.approved callbacks
```

The `hold.approved` callback pattern is the same as in
`atlasent-examples/accounting-close/erp-webhook.ts` — register the hold
context before the first `protect()` attempt, then retry with the approval
metadata once the hold is released.

### Connector slots (deferred)

The following ERP connectors are in the roadmap but not yet available:
- **NetSuite SuiteApp** — native SuiteFlow integration with AtlaSent
- **SAP S/4HANA** — BRF+ workflow connector
- **Coupa** — Spend Management webhook receiver

Until official connectors are available, use the normalization pattern in
`erp-webhook.ts` as the integration template.

## Protected actions

| Action | Enforcement rule |
|---|---|
| `vendor.payment.release` | Submitter must be in `ap-certifiers`; dual approval for $50k+; CFO for $250k+ |

## Related

- Full accounting close bundle: [`atlasent-examples/accounting-close/`](../accounting-close/)
- Reconciliation certify quickstart: [`atlasent-examples/reconciliation-certify/`](../reconciliation-certify/)
- Policy reference: [`policies/vendor-payment-release.yaml`](./policies/vendor-payment-release.yaml)
