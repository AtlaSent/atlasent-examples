# GDPR Article 17 Right-to-Erasure — Authorization Quickstart

AtlaSent enforces non-bypassable authorization for GDPR customer data deletion
requests using the `customer.data.delete` action with fail-closed, DPO-signed
enforcement. Every deletion decision is recorded in an immutable SHA-256
hash-linked audit chain before any data is removed, giving the DPO a
verifiable compliance record for each erasure request.

## The 5-step flow

1. **Identity verification** — the data subject's identity must be verified
   (`identityVerified=true`) before the erasure request can be evaluated.
   Unverified requests are blocked at the policy layer.
2. **30-day window check** — GDPR Article 17 requires a response within 30
   days. Expired requests (`requestWindowExpired=true`) are denied and flagged
   as compliance breaches requiring DPO escalation.
3. **Legal hold check** — if an active legal basis for retention exists
   (`legalBasisForRetention` is set and non-empty), the deletion is blocked
   until the legal hold is resolved.
4. **DPO sign-off** — `dpoSignOffBy` must be on the authorized DPO list.
   Deletion cannot proceed without explicit DPO authorization.
5. **Issue permit + delete** — on `allow`, a single-use cryptographic permit
   is issued and the data deletion pipeline is triggered across all listed
   `dataCategories`.

> **`machine_executable=false`** — Automated scripts cannot self-authorize
> bulk data deletions. A named DPO must be present on every request.

## Run

```bash
pip install -r requirements.txt

# Full demo (3 scenarios, offline stub, no API key required)
python main.py

# With live AtlaSent API
ATLASENT_API_KEY=ask_live_... python main.py
```

## Scenarios

| # | Outcome | Reason |
|---|---------|--------|
| 1 | ALLOW | Verified erasure request, DPO sign-off, within 30-day window |
| 2 | DENY — `DENY_IDENTITY_NOT_VERIFIED` | `identityVerified=false` — identity verification not completed |
| 3 | DENY — `DENY_REQUEST_WINDOW_EXPIRED` | `requestWindowExpired=true` — request exceeds 30-day GDPR timeline |

## Context fields

| Field | Type | Description |
|-------|------|-------------|
| `requestId` | string | Unique Data Subject Request identifier |
| `customerId` | string | Customer identifier in the data platform |
| `identityVerified` | boolean | Must be `true` — blocked if false |
| `dpoSignOffBy` | string | DPO email (must be on authorized list) |
| `requestReceivedDate` | string | ISO 8601 date the request was received |
| `requestWindowExpired` | boolean | Must be `false` — 30-day GDPR window enforced |
| `legalBasisForRetention` | string | Active legal hold reason; `"none"` or empty to allow deletion |
| `dataCategories` | list[string] | Categories of data to be deleted (captured in audit chain) |
| `verificationMethod` | string | `email_otp` \| `id_document` \| `live_video` |
| `gdprArticle` | string | GDPR article invoked (informational) |
| `jurisdiction` | string | `EU` \| `UK` \| `EEA` |

## 30-day timeline enforcement

GDPR Article 17 requires controllers to act on erasure requests "without undue
delay and in any event within one month." AtlaSent enforces this by:

- Accepting a `requestWindowExpired` boolean that your DSR management system
  computes based on `requestReceivedDate`.
- Denying expired requests with a compliance-breach reason code that triggers
  DPO escalation in your ticketing system via the webhook.
- Recording the `requestReceivedDate` and decision timestamp in the immutable
  audit chain — giving auditors an unambiguous timeline for every erasure request.

## Policy

Load `policies/gdpr-erasure.yaml` into your AtlaSent org:

> ⚠️ **WARNING**: This endpoint (`v1-policy-bundles`) is disabled in production and will return 404. See `atlasent-api/supabase/runtime-functions-disabled.json`.

```bash
curl -X POST https://api.atlasent.io/functions/v1/v1-policy-bundles \
  -H "Authorization: Bearer $ATLASENT_API_KEY" \
  -H "Content-Type: application/yaml" \
  --data-binary @policies/gdpr-erasure.yaml
```

## Prerequisites

- Python ≥ 3.11
- `atlasent` Python SDK (`pip install atlasent>=0.9`)
- AtlaSent API key (optional — runs offline without one)

## Regulatory context

| Requirement | Reference |
|-------------|-----------|
| Right to erasure | GDPR Article 17 — "right to be forgotten" |
| Response timeline | GDPR Article 12(3) — one month (extendable to 3 months) |
| Identity verification before processing | GDPR Article 12(6) |
| Legal basis for retention | GDPR Article 17(3) — exceptions to erasure |
| DPO oversight | GDPR Article 37–39 — Data Protection Officer obligations |
| Audit trail | GDPR Article 5(2) — accountability principle |
| UK equivalents | UK GDPR Article 17 / DPA 2018 |

### GDPR Article 17 context

The right to erasure (Article 17) is one of the most operationally demanding
GDPR rights to fulfill safely. Key risks include:

- **Premature deletion** — deleting before identity is verified may erase the
  wrong customer's data or fulfill a fraudulent request.
- **Missed deadlines** — failure to respond within 30 days is a reportable
  breach under Article 33.
- **Legal hold violations** — deleting data subject to litigation holds or
  regulatory retention requirements can create legal liability.

AtlaSent addresses each risk with a distinct enforcement gate:

| Risk | AtlaSent enforcement |
|------|---------------------|
| Premature deletion | `identityVerified` gate — blocked until verification is confirmed |
| Missed deadline | `requestWindowExpired` gate — flags compliance breach, triggers DPO escalation |
| Legal hold violation | `legalBasisForRetention` gate — blocks deletion while active hold exists |
| Unauthorized deletion | `dpoSignOffBy` gate — only named DPO may authorize deletion |

Every decision (allow or deny) is recorded with the full erasure context in
the hash-linked audit chain, giving the DPO a per-request compliance record
that satisfies the accountability principle in Article 5(2).
