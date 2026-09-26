# HR Employee Offboarding — Authorization Quickstart

AtlaSent enforces non-bypassable authorization for HR employee offboarding
using the `hr.employee.offboard` action with fail-closed, SOX-aligned
access-control enforcement. Every offboarding decision (allow or deny) is
recorded in an immutable SHA-256 hash-linked audit chain before any system
access is revoked.

## The 5-step flow

1. **Termination prerequisite** — `employeeStatus` must be `terminated` before
   an offboarding permit can be issued. Active employees are blocked at the
   policy layer.
2. **HR authorization** — `authorizedBy` must be on the authorized HR manager
   list and a valid `hrAuthToken` must be present. Unauthenticated requests are
   denied immediately.
3. **Evaluate** — call `atlasent.protect()` with full offboarding context.
   AtlaSent checks status, authority, and token presence.
4. **Issue permit** — on `allow`, a single-use cryptographic permit is issued
   (TTL: 15 minutes). Denied if the employee is still active or auth is missing.
5. **Verify and execute** — permit is verified before the access revocation
   cascade runs across all listed systems (Okta, GitHub Enterprise, Slack, etc.).

> **`machine_executable=false`** — Automated agents cannot self-authorize
> offboarding. An HR manager's identity and token must be present on every
> request.

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
| 1 | ALLOW | Terminated employee, authorized HR manager, valid auth token, access revocation cascade |
| 2 | DENY — `DENY_INVALID_STATUS` | `employeeStatus=active` — termination workflow must precede offboarding |
| 3 | DENY — `DENY_MISSING_AUTH` | `hrAuthToken` absent — unauthenticated request |

## Context fields

| Field | Type | Description |
|-------|------|-------------|
| `employeeId` | string | Unique employee identifier |
| `employeeStatus` | string | Must be `terminated` — blocked if `active` or `on_leave` |
| `authorizedBy` | string | HR manager email (must be on authorized list) |
| `hrAuthToken` | string | HR system authorization token — required, non-empty |
| `effectiveDate` | string | ISO 8601 offboarding effective date |
| `terminationReason` | string | `voluntary_resignation` \| `involuntary` \| `retirement` |
| `revocationSystems` | list[string] | Systems to revoke access from (recorded in audit chain) |
| `equipmentReturnRequired` | boolean | Whether equipment return checklist is required |
| `finalPayrollRun` | string | ISO 8601 date of final payroll run |

## Access revocation cascade

The `revocationSystems` context field records which downstream systems are
included in the offboarding cascade. This field is captured in the audit chain
at permit-issuance time, giving auditors a point-in-time snapshot of which
systems were in scope for access revocation.

Supported systems (informational — policy does not gate on system list):

| System | Access type |
|--------|-------------|
| `okta-idp` | SSO / identity provider |
| `github-enterprise` | Source code repositories |
| `slack` | Internal communications |
| `salesforce` | CRM data access |
| `jira` | Project management |
| `workday` | HRIS self-service |

## Policy

Load `policies/hr-offboarding.yaml` into your AtlaSent org:

> ⚠️ **WARNING**: This endpoint (`v1-policy-bundles`) is disabled in production and will return 404. See `atlasent-api/supabase/runtime-functions-disabled.json`.

```bash
curl -X POST https://api.atlasent.io/functions/v1/v1-policy-bundles \
  -H "Authorization: Bearer $ATLASENT_API_KEY" \
  -H "Content-Type: application/yaml" \
  --data-binary @policies/hr-offboarding.yaml
```

## Prerequisites

- Python ≥ 3.11
- `atlasent` Python SDK (`pip install atlasent>=0.9`)
- AtlaSent API key (optional — runs offline without one)

## Regulatory context

| Requirement | Reference |
|-------------|-----------|
| Access provisioning / de-provisioning controls | SOX Section 404 — IT general controls |
| Segregation of duties | SOX Section 302 / COSO framework |
| Privileged access termination | NIST SP 800-53 AC-2(j) |
| HR data access logging | SOC 2 Type II CC6.2 |
| Employee data retention | GDPR Article 5(1)(e) — storage limitation |

### SOX access controls context

SOX Section 404 requires that access to financial systems is revoked promptly
upon termination. AtlaSent enforces this by:

- Blocking offboarding of non-terminated employees (prevents premature access
  revocation that could disrupt active payroll or benefits processing).
- Requiring an HR manager's authorization token on every request (prevents
  unauthorized or automated revocation without HR oversight).
- Recording the full revocation cascade scope in the immutable audit chain,
  giving auditors evidence that all required system access was addressed.
- Issuing single-use permits — each offboarding action is a discrete,
  permit-gated event that cannot be replayed.
