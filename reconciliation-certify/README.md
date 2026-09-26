# Reconciliation Certify — AtlaSent Quickstart

Targeted quickstart for the `reconciliation.certify` protected action.
Extracted from the full accounting close bundle — self-contained, runnable
in under 30 seconds.

For the full 7-scenario accounting close workflow (including journal entry
approval, period close, adjustment submit, and emergency override), see
[`atlasent-examples/accounting-close/`](../accounting-close/).

## The 5-step flow

1. **Install SDK** — add AtlaSent to your close-management service.
2. **Configure environment** — add your API key and org ID.
3. **Seed the policy pack** — upload `policies/reconciliation-certify.yaml`.
4. **Run the quickstart** — 3 scenarios covering allow, hold, and deny.
5. **Offline bundle verification** — verify the audit evidence with no AtlaSent dependency.

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.11+ | For `main.py` |
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

> ⚠️ **WARNING**: This endpoint (`v1-policy-bundles`) is disabled in production and will return 404.

```bash
curl -X POST https://api.atlasent.io/functions/v1/v1-policy-bundles \
  -H "Authorization: Bearer $ATLASENT_API_KEY" \
  -H "Content-Type: application/yaml" \
  --data-binary @policies/reconciliation-certify.yaml
```

The policy pack enforces:
- Certifier must be in the `authorized-certifiers` group (`DENY_CERTIFIER_NOT_AUTHORIZED` on fail)
- Balance difference above **$10,000** requires dual approval (`HOLD_SECOND_APPROVER`)
- Certifier must be assigned to the period being certified (`DENY_PERIOD_MISMATCH` on fail)

## Step 4: Run the quickstart

**Python:**
```bash
python main.py
```

**TypeScript:**
```bash
npx tsx main.ts
```

| Scenario | Certifier | Balance Diff | Expected outcome |
|---|---|---|---|
| 1 | `alice.chen@acme.com` (authorized) | $0.00 | **ALLOW** |
| 2 | `alice.chen@acme.com` (authorized) | $15,000 | **HOLD_SECOND_APPROVER** → approve → **ALLOW** |
| 3 | `temp.worker@contractor.com` (unauthorized) | $0.00 | **DENY_CERTIFIER_NOT_AUTHORIZED** |

**Scenario 1** shows the happy path: authorized certifier, balance within
tolerance, no dual-approval required. AtlaSent issues a cryptographic permit
and the reconciliation is certified.

**Scenario 2** shows the hold path: the balance difference ($15,000) exceeds
the $10,000 dual-approval threshold. The script shows the hold key and then
simulates a controller providing the second approval — the retry resolves and
a permit is issued.

**Scenario 3** shows the deny path: the certifier is not in the
`authorized-certifiers` group. AtlaSent returns
`DENY_CERTIFIER_NOT_AUTHORIZED` immediately, before the reconciliation
system is touched.

### TypeScript convenience wrapper

`main.ts` uses `protectReconciliationCertify()` — a thin wrapper over
`atlasent.protect()` that normalizes the context shape and uses the
canonical `reconciliation.certify` action string. Use this in your
close-automation code instead of calling `protect()` directly.

## Step 5: Offline bundle verification

The audit trail produced by the offline stub is hash-linked and
Ed25519-signed (same format as the accounting-close bundle). Verify with
the shared verifier:

```bash
# Re-use the accounting-close verifier — same bundle format
python ../accounting-close/verify-audit.py --bundle bundle.json
```

With a live API key, export from the AtlaSent audit API:
```bash
curl -H "Authorization: Bearer $ATLASENT_API_KEY" \
  "https://api.atlasent.io/v1/audit/exports?action=reconciliation.certify" \
  -o recon-audit.json
```

## Close-management platform integration

A normalizer maps your close tool's `close_task.completed` events (where task
type = `reconciliation`) to the `reconciliation.certify` action:

```
close_task.completed
  → task.type == "reconciliation"
  → normalize to reconciliation.certify context
  → atlasent.protect({ action: "reconciliation.certify", context: { ... } })
```

The integration uses the same webhook pattern as
`atlasent-examples/accounting-close/erp-webhook.ts`:

1. The close platform fires `close_task.completed` with task type = `reconciliation`
2. The normalizer maps task fields to `reconciliation.certify` context
3. `atlasent.protect()` evaluates the action fail-closed
4. On ALLOW: permit issued → task moves to `certified` state
5. On HOLD: hold queued for second approver; task shows `pending_approval`
6. On DENY: task moves to `certification_blocked`

No vendor-specific normalizer ships in this repo. Use the normalization pattern
from `atlasent-examples/accounting-close/erp-webhook.ts` as the template — its
`executeAccountingAction()` dispatcher shows where to map `reconciliation.certify`
onto your platform's close-task API.

## Protected actions

| Action | Enforcement rule |
|---|---|
| `reconciliation.certify` | Certifier in `authorized-certifiers`; dual approval for $10k+ balance diff; period assignment enforced |

## Related

- Full accounting close bundle (7 scenarios): [`atlasent-examples/accounting-close/`](../accounting-close/)
- Vendor payment release quickstart: [`atlasent-examples/vendor-payment-release/`](../vendor-payment-release/)
- Policy reference: [`policies/reconciliation-certify.yaml`](./policies/reconciliation-certify.yaml)
