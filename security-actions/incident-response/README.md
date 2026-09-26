# Security Incident Response — Authorization Quickstart

AtlaSent enforces non-bypassable authorization for security incident escalation
and access quarantine using fail-closed, critical-risk enforcement. Every
security action decision (allow or deny) is recorded in an immutable
SHA-256 hash-linked audit chain before any incident escalation or access
change occurs.

## The 5-step flow

1. **SOC lead authorization** — `authorizedBy` must be on the authorized SOC
   leads list. Unauthenticated or low-privilege requests are denied immediately.
2. **Required fields validation** — `incidentId` + `severity` for escalation,
   `targetId` + `quarantineReason` for quarantine. Missing fields throw
   `TypeError` before the evaluate call.
3. **Evaluate** — call `atlasent.protect()` with full security context.
   AtlaSent checks authority, required fields, and quorum availability.
4. **Issue permit** — on `allow`, a single-use cryptographic permit is issued
   (escalation window: 1 hour). Denied if authority is missing or quorum
   not satisfied.
5. **Verify and execute** — permit is verified before the security action
   (incident escalation or access quarantine) executes.

> **`machine_executable=false`** — Automated agents cannot self-authorize
> security incident escalation or access quarantine. A SOC lead's identity
> must be present on every request.

## Run

```bash
pip install -r requirements.txt

# Full demo (4 scenarios, offline stub, no API key required)
python main.py

# With live AtlaSent API
ATLASENT_API_KEY=ask_live_... python main.py

# TypeScript demo
npm install
ATLASENT_API_KEY=ask_live_... npx tsx main.ts
```

## Scenarios

| # | Action | Outcome | Reason |
|---|--------|---------|--------|
| 1 | `security.incident.escalate` | ALLOW | Critical incident, authorized SOC lead, all fields present |
| 2 | `security.incident.escalate` | DENY — `DENY_AUTHORITY` | Intern SOC analyst not on authorized list |
| 3 | `security.access.quarantine` | ALLOW | Compromised principal, authorized SOC lead |
| 4 | `security.access.quarantine` | DENY — `DENY_MISSING_FIELD` | `quarantineReason` absent |

## Context fields

### `security.incident.escalate`

| Field | Type | Description |
|-------|------|-------------|
| `incidentId` | string | Unique incident identifier |
| `severity` | `"low"\|"medium"\|"high"\|"critical"` | Incident severity level |
| `authorizedBy` | string | SOC lead initiating the escalation |

### `security.access.quarantine`

| Field | Type | Description |
|-------|------|-------------|
| `targetId` | string | Principal identifier to quarantine |
| `quarantineReason` | string | Reason for quarantine (required) |
| `authorizedBy` | string | SOC lead initiating the quarantine |

## Escalation parameters

| Parameter | Value |
|-----------|-------|
| `assignedToRole` | `security-approver` |
| `quorumRequired` | `simple_majority` |
| Escalation window | 1 hour (`3_600_000` ms) |
| `fail_closed` | `true` |

## Prerequisites

- Python ≥ 3.11 (for Python demo)
- Node.js ≥ 20 + `tsx` (for TypeScript demo)
- `atlasent` Python SDK (`pip install atlasent>=0.9`)
- `@atlasent/sdk` npm package
- AtlaSent API key (optional — runs offline without one)

## Regulatory context

| Requirement | Reference |
|-------------|-----------|
| Incident handling | NIST SP 800-53 IR-4 |
| Incident monitoring | NIST SP 800-53 IR-5 |
| Account management (quarantine) | NIST SP 800-53 AC-2 |
| Logical access controls | SOC 2 Type II CC6.1 |
| Availability — incident response | SOC 2 Type II A1.2 |
| Removal of access rights | ISO 27001 A.9.2.6 |
| Incident detection and reporting | ISO 27035 Section 6.1 |
