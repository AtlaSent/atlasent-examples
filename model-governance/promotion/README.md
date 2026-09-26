# ML Model Promotion Governance — Authorization Quickstart

AtlaSent enforces non-bypassable authorization for ML model promotion to
production using the `ml.model.promote` action with fail-closed, safety-gated
enforcement. Every promotion decision is recorded in an immutable SHA-256
hash-linked audit chain before the model registry is updated or deployment
pipelines are triggered.

## The 5-step flow

1. **Safety evaluation** — all automated safety checks (`safetyChecksPassed`)
   must pass before a promotion request can be submitted. Failing models are
   blocked at the policy layer.
2. **AI safety sign-off** — an authorized AI safety reviewer (`safetySignOffBy`)
   must explicitly sign off on the model before promotion.
3. **Staging validation gate** — production promotions require
   `stagingValidationComplete=true`. Models cannot skip the staging environment.
4. **Evaluate** — call `atlasent.protect()` with full model context. AtlaSent
   checks safety, staging gate, and approver authority.
5. **Issue permit + promote** — on `allow`, a single-use cryptographic permit
   is issued and the model registry is updated with the promotion record.

> **`machine_executable=false`** — Automated CI/CD pipelines cannot
> self-authorize production promotions. An ML lead or director with AI safety
> sign-off must be present on every production promotion request.

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
| 1 | ALLOW | Validated model, safety sign-off present, staging validation complete |
| 2 | DENY — `DENY_SAFETY_CHECKS_FAILED` | `safetyChecksPassed=false` — bias audit and adversarial robustness failures |
| 3 | DENY — `DENY_STAGING_VALIDATION_MISSING` | `stagingValidationComplete=false` for production target |

## Context fields

| Field | Type | Description |
|-------|------|-------------|
| `modelId` | string | Unique model identifier |
| `modelVersion` | string | Semantic version of the model artifact |
| `targetEnvironment` | string | `staging` \| `production` |
| `approvedBy` | string | ML lead / director email (must be on authorized list) |
| `safetySignOffBy` | string | AI safety reviewer email (must be on safety list) |
| `safetyChecksPassed` | boolean | All automated safety evaluations passed |
| `stagingValidationComplete` | boolean | Required `true` for production targets |
| `riskTier` | string | `low` \| `medium` \| `high` — informational, captured in audit |
| `evalReportUri` | string | URI to evaluation report document |
| `biasAuditComplete` | boolean | Bias audit completed (informational) |
| `fairnessScore` | float | Fairness metric 0.0–1.0 (informational) |
| `failedSafetyChecks` | list[string] | Names of failing checks (informational on deny) |

## Policy

Load `policies/model-promotion.yaml` into your AtlaSent org:

> ⚠️ **WARNING**: This endpoint (`v1-policy-bundles`) is disabled in production and will return 404. See `atlasent-api/supabase/runtime-functions-disabled.json`.

```bash
curl -X POST https://api.atlasent.io/functions/v1/v1-policy-bundles \
  -H "Authorization: Bearer $ATLASENT_API_KEY" \
  -H "Content-Type: application/yaml" \
  --data-binary @policies/model-promotion.yaml
```

## Prerequisites

- Python ≥ 3.11
- `atlasent` Python SDK (`pip install atlasent>=0.9`)
- AtlaSent API key (optional — runs offline without one)

## Regulatory context

| Requirement | Reference |
|-------------|-----------|
| AI system risk classification | EU AI Act Article 9 — risk management system |
| High-risk AI documentation | EU AI Act Article 11 — technical documentation |
| Human oversight for high-risk AI | EU AI Act Article 14 |
| AI management system | ISO/IEC 42001:2023 — AI management system requirements |
| Logging and traceability | EU AI Act Article 12 |
| Bias and fairness testing | EU AI Act Annex IV §2(e) |

### EU AI Act / ISO 42001 context

The EU AI Act classifies certain AI systems as high-risk and requires
documented human oversight, safety evaluation, and audit trails before
deployment. AtlaSent enforces these requirements by:

- **Blocking promotion of models with failing safety checks** — the
  `safetyChecksPassed` gate ensures automated bias, robustness, and
  fairness evaluations must pass before any human reviewer is asked to
  sign off, preventing sign-off fatigue on known-failing models.
- **Requiring explicit AI safety reviewer sign-off** — the `safetySignOffBy`
  field pins accountability to a named individual from the AI safety team,
  satisfying the human oversight requirement in Article 14.
- **Enforcing the staging gate for production** — the
  `stagingValidationComplete` gate ensures models are validated in a
  controlled environment before reaching end users, supporting the risk
  management obligations in Article 9.
- **Immutable audit trail** — every allow and deny decision is captured in
  the hash-linked chain with the full evaluation context (model ID, version,
  risk tier, approver, safety reviewer, eval report URI), satisfying the
  logging and traceability requirements in Article 12 and ISO 42001 §10.2.
