# GxP Clinical Data Access — Authorization Quickstart

AtlaSent enforces non-bypassable authorization for clinical trial data access
using the `clinical.data.access` action with fail-closed, `machine_executable=false`
enforcement. All access decisions are recorded in a tamper-evident audit trail
for 21 CFR Part 11 compliance.

> **21 CFR Part 11 context** — This policy enforces electronic records access
> controls required under 21 CFR Part 11. Every access decision (allow and deny)
> is recorded in a SHA-256 hash-linked audit chain. Denied access attempts are
> also logged, providing a complete access history for regulatory inspections.
> Consent verification is enforced at the policy layer, not as an application
> check, ensuring it cannot be bypassed.

## The 5-step flow

1. **Initiate access** — researcher calls `atlasent.protect()` with full
   subject access context including `purpose`, `consentVerified`, and `aiAgent`.
2. **Evaluate** — AtlaSent checks: AI agent flag, purpose presence, consent
   status, and authorized researcher list membership.
3. **Machine_executable gate** — if `aiAgent=true`, the request is denied
   regardless of other context. Human oversight is always required.
4. **Issue permit** — on `allow`, a single-use permit is issued (TTL: 5 min).
5. **Verify and access** — permit is verified server-side before access is
   granted and logged in the CTMS audit trail.

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
| 1 | ALLOW | Human researcher, `aiAgent=false`, `purpose=protocol-review`, `consentVerified=true` |
| 2 | DENY — `DENY_AI_AGENT_NOT_PERMITTED` | `aiAgent=true` — `machine_executable=false` blocks AI agents without human-in-the-loop |
| 3 | DENY — `DENY_PURPOSE_MISSING` | `purpose` field empty |

## AI agent pipeline pattern

The TypeScript `main.ts` shows how to use `protectToolCall()` to gate clinical
data access in an AI agent pipeline. The `clinicalDataAccessTool()` function
wraps `atlasent.protect()` and is called from the agent pipeline. When
`aiAgent=true`, the policy denies the request because `machine_executable=false`.

To allow an AI agent to access clinical data with human oversight:

```typescript
// In your agent pipeline, use human_in_the_loop=true
const permit = await atlasent.protect({
  agent: "clinical-review-agent",
  action: "clinical.data.access",
  context: {
    aiAgent: true,
    human_in_the_loop: true,   // human has reviewed and approved this access
    humanReviewedBy: "dr.smith@clinicalresearch.example",
    // ... rest of context
  },
});
```

## Context fields

| Field | Type | Description |
|-------|------|-------------|
| `subjectId` | string | Clinical trial subject identifier |
| `dataCategory` | string | Type of data being accessed (e.g. `efficacy-endpoints`, `lab-results`) |
| `accessedBy` | string | Researcher email — must be on authorized list |
| `purpose` | string | Documented purpose (required, non-empty) |
| `aiAgent` | boolean | `true` if request is from an AI agent — always denied |
| `consentVerified` | boolean | Subject consent has been verified |
| `trialId` | string | Clinical trial identifier |

## Policy

Load `policies/clinical-data-access.yaml` into your AtlaSent org:

> ⚠️ **WARNING**: This endpoint (`v1-policy-bundles`) is disabled in production and will return 404. See `atlasent-api/supabase/runtime-functions-disabled.json`.

```bash
curl -X POST https://api.atlasent.io/functions/v1/v1-policy-bundles \
  -H "Authorization: Bearer $ATLASENT_API_KEY" \
  -H "Content-Type: application/yaml" \
  --data-binary @policies/clinical-data-access.yaml
```

## Regulatory context

| Requirement | Reference |
|-------------|-----------|
| Electronic records access controls | 21 CFR Part 11 §11.10(d) |
| Informed consent | 21 CFR Part 50/56 |
| Access documentation with purpose | ICH E6 (R2) GCP §8 |
| Special category personal data | EU GDPR Art. 9 |
| PHI access controls | HIPAA 45 CFR §164.312 |
| Audit trail (10-year retention) | 21 CFR Part 11 §11.10(e) |
