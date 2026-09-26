# Behavior Events — Authorization Quickstart

> **Phase 3 feature** — Behavior events require a privacy review before
> production use. Complete the privacy review checklist below before deploying.

AtlaSent enforces non-bypassable authorization for behavioral event sharing
using the `behavior.event.share` action with data sensitivity classification
and consent enforcement.

## The 5-step flow

1. **Classify** — determine the `eventCategory` and whether it is in a
   sensitive category (`behavior.health.*`, `behavior.financial`,
   `behavior.minor`, `behavior.location.precise`).
2. **Gate minor data** — if `eventCategory=behavior.minor`, the request is
   denied immediately (`machine_executable=false`). A human privacy reviewer
   must approve all minor data sharing out-of-band.
3. **Evaluate** — call `atlasent.protect()`. For sensitive categories, AtlaSent
   checks `consentVerified=true`. For all categories, `purpose` must be
   documented and `destination` must be in the verified allowlist.
4. **Issue permit** — on `allow`, a single-use permit is issued (TTL: 5 min).
5. **Dispatch** — permit is verified server-side before the event is dispatched
   to the destination and logged in the behavior audit trail.

## Run

```bash
pip install -r requirements.txt

# Full demo (4 scenarios, offline stub, no API key required)
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

## Scenarios

| # | Outcome | Reason |
|---|---------|--------|
| 1 | ALLOW | Non-sensitive event, consent verified, valid purpose, verified destination |
| 2 | DENY — `DENY_CONSENT_NOT_VERIFIED` | `behavior.health.mental`, `consentVerified=false` |
| 3 | DENY — `HOLD_HUMAN_REVIEW_REQUIRED` | `behavior.minor` — machine cannot auto-approve |
| 4 | DENY — `DENY_PURPOSE_MISSING` | `purpose` field empty |

## Data sensitivity classification

| Category prefix | Sensitivity | Consent required | Machine auto-approve |
|-----------------|-------------|------------------|----------------------|
| `behavior.product.*` | Non-sensitive | Recommended | Yes |
| `behavior.location.city` | Low | Recommended | Yes |
| `behavior.health.*` | Sensitive | **Required** | Yes (with consent) |
| `behavior.financial` | Sensitive | **Required** | Yes (with consent) |
| `behavior.location.precise` | Sensitive | **Required** | Yes (with consent) |
| `behavior.minor` | Restricted | **Required** | **No — human review** |

## Privacy review checklist (required before production use)

Before deploying `behavior.event.share` in production, complete this checklist
with your privacy/legal team:

- [ ] All `eventCategory` values are defined and classified by sensitivity
- [ ] Consent collection mechanism verified for all sensitive categories
- [ ] Destination allowlist reviewed and approved by legal
- [ ] Data retention periods set per jurisdiction (GDPR / CCPA / COPPA)
- [ ] Minor data handling reviewed with legal (COPPA compliance)
- [ ] Purpose taxonomy documented and approved
- [ ] Privacy impact assessment (PIA) completed
- [ ] Data processing agreements (DPAs) in place for all destinations

## Context fields

| Field | Type | Description |
|-------|------|-------------|
| `subjectId` | string | Subject/user identifier |
| `eventCategory` | string | Behavior category (see classification table) |
| `consentVerified` | boolean | Explicit consent has been verified |
| `purpose` | string | Documented purpose (required, non-empty) |
| `destination` | string | Target system (must be in verified allowlist) |

## Policy

Load `policies/behavior-events.yaml` into your AtlaSent org:

> ⚠️ **WARNING**: This endpoint (`v1-policy-bundles`) is disabled in production and will return 404.

```bash
curl -X POST https://api.atlasent.io/functions/v1/v1-policy-bundles \
  -H "Authorization: Bearer $ATLASENT_API_KEY" \
  -H "Content-Type: application/yaml" \
  --data-binary @policies/behavior-events.yaml
```

## Regulatory context

| Requirement | Reference |
|-------------|-----------|
| Lawfulness of processing special categories | EU GDPR Art. 9 |
| Consent requirements | EU GDPR Art. 7; CCPA/CPRA |
| Children's data protection | COPPA (16 CFR Part 312) |
| Purpose limitation | EU GDPR Art. 5(1)(b) |
