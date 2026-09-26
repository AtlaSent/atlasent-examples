# Payment Operations Lifecycle — Authorization Quickstart

> **Production reference** — This example mirrors the implementation in
> a production ledger system where these actions are already in
> production use.

AtlaSent enforces non-bypassable authorization for the full payment lifecycle
state machine. Each state transition requires a verified permit before the
mutation occurs.

## The 5-step flow

1. **Approve** — `payment.approval.approve`: AP manager approves an invoice
   payment; requires `ap_manager` role and amount within delegation limit.
2. **QB sync** — `qb.transaction.approve`: AP manager approves the corresponding
   QuickBooks transaction.
3. **Execute** — `payment.execute.approved`: Treasury executes the approved
   payment; requires `treasury` role and valid bank reference.
4. **Hold** — `payment.execute.held`: Fraud/compliance system can hold a payment
   at any point; triggers escalation to compliance team.
5. **Policy error** — `payment.execute.policy_error`: Terminal blocking state —
   execution is always denied when a policy violation is recorded.

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
npx @atlasent/sdk mock &
ATLASENT_API_URL=http://127.0.0.1:4747 ATLASENT_API_KEY=mock npx tsx main.ts
```

## Flows

| # | Flow | Outcome |
|---|------|---------|
| 1 | Approved → QB approved → executed | 3 × ALLOW |
| 2 | Approved → held for fraud review | 2 × ALLOW (approve + hold) |
| 3 | `policy_error` on execution attempt | DENY — `DENY_POLICY_VIOLATION` |

## Action types and context fields

### `payment.approval.approve`
| Field | Type | Description |
|-------|------|-------------|
| `paymentId` | string | Payment identifier |
| `amount` | number | Payment amount (USD) |
| `approvedBy` | string | AP manager email |
| `invoiceId` | string | Invoice reference |
| `vendorId` | string | Vendor identifier |

### `payment.approval.deny`
| Field | Type | Description |
|-------|------|-------------|
| `paymentId` | string | Payment identifier |
| `deniedBy` | string | AP manager email |
| `reason` | string | Documented denial reason |

### `payment.execute.approved`
| Field | Type | Description |
|-------|------|-------------|
| `paymentId` | string | Payment identifier |
| `executedBy` | string | Treasury staff email |
| `bankReference` | string | Bank wire reference |

### `payment.execute.held`
| Field | Type | Description |
|-------|------|-------------|
| `paymentId` | string | Payment identifier |
| `heldBy` | string | System or person placing the hold |
| `holdReason` | string | Reason for hold |

### `payment.execute.policy_error`
| Field | Type | Description |
|-------|------|-------------|
| `paymentId` | string | Payment identifier |
| `policyRule` | string | Policy rule that was violated |
| `errorCode` | string | Error code for audit |

### `qb.transaction.approve`
| Field | Type | Description |
|-------|------|-------------|
| `transactionId` | string | QuickBooks transaction ID |
| `amount` | number | Transaction amount |
| `accountCode` | string | GL account code |
| `approvedBy` | string | AP manager email |

## Policy

Load `policies/payment-operations.yaml` into your AtlaSent org:

> ⚠️ **WARNING**: This endpoint (`v1-policy-bundles`) is disabled in production and will return 404. See `atlasent-api/supabase/runtime-functions-disabled.json`.

```bash
curl -X POST https://api.atlasent.io/functions/v1/v1-policy-bundles \
  -H "Authorization: Bearer $ATLASENT_API_KEY" \
  -H "Content-Type: application/yaml" \
  --data-binary @policies/payment-operations.yaml
```
