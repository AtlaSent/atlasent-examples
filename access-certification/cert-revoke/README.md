# Access Certificate Revocation — Authorization Quickstart

AtlaSent enforces non-bypassable authorization for access certificate revocation
using the `access.cert.revoke` action with high-risk, single-approver
security review enforcement. Every revocation decision (allow or deny) is
recorded in an immutable SHA-256 hash-linked audit chain before any certificate
is revoked.

## The 5-step flow

1. **Security admin authorization** — `authorizedBy` must be on the authorized
   security admins list. Unauthenticated or low-privilege requests are denied
   immediately.
2. **Required fields validation** — `certId` and `revocationReason` are both
   required. Missing fields throw `TypeError` before the evaluate call.
3. **Evaluate** — call `atlasent.protect()` with full certificate revocation
   context. AtlaSent checks authority, required fields, and approver availability.
4. **Issue permit** — on `allow`, a single-use cryptographic permit is issued
   (review window: 24 hours). Denied if authority is missing.
5. **Verify and execute** — permit is verified before the certificate revocation
   executes (CRL update, OCSP notification, dependent token invalidation).

> **`machine_executable=false`** — Automated agents cannot self-authorize
> certificate revocation. A security admin's identity must be present on
> every request.

## Run

```bash
pip install -r requirements.txt

# Full demo (3 scenarios, offline stub, no API key required)
python main.py

# With live AtlaSent API
ATLASENT_API_KEY=ask_live_... python main.py

# TypeScript demo
npm install
ATLASENT_API_KEY=ask_live_... npx tsx main.ts
```

## Scenarios

| # | Outcome | Reason |
|---|---------|--------|
| 1 | ALLOW | Valid certificate, authorized security admin, revocation reason provided |
| 2 | DENY — `DENY_AUTHORITY` | Automation bot not on authorized security admins list |
| 3 | DENY — `DENY_MISSING_FIELD` | `certId` absent |

## Context fields

| Field | Type | Description |
|-------|------|-------------|
| `certId` | string | Unique certificate identifier in the PKI/cert store |
| `revocationReason` | string | Reason for revocation (required, non-empty) |
| `authorizedBy` | string | Security admin email (must be on authorized list) |

## Escalation parameters

| Parameter | Value |
|-----------|-------|
| `assignedToRole` | `security-approver` |
| `quorumRequired` | `single_approver` |
| Review window | 24 hours (`86_400_000` ms) |

## Prerequisites

- Python ≥ 3.11 (for Python demo)
- Node.js ≥ 20 + `tsx` (for TypeScript demo)
- `atlasent` Python SDK (`pip install atlasent>=0.9`)
- `@atlasent/sdk` npm package
- AtlaSent API key (optional — runs offline without one)

## Regulatory context

| Requirement | Reference |
|-------------|-----------|
| Account management | NIST SP 800-53 AC-2 |
| Automated account management | NIST SP 800-53 AC-2(1) |
| Least privilege | NIST SP 800-53 AC-6 |
| Access provisioning and revocation | SOC 2 Type II CC6.2 |
| Access removal evidence | SOC 2 Type II CC6.3 |
| Removal or adjustment of access rights | ISO 27001 A.9.2.6 |
| Employee access controls | SOX Section 404 |
