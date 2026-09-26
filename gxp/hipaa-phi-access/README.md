# HIPAA ePHI Access — Authorization Demo

Demonstrates fail-closed authorization for **electronic protected health information (ePHI)**
access, export, and deletion under the **HIPAA Security Rule** (45 CFR Part 164 Subpart C)
using the AtlaSent SDK.

## Scenarios

| # | Action | Actor | Outcome | Rule |
|---|--------|-------|---------|------|
| 1 | `phi.access` | `dr.chen` (clinician) | ✔ ALLOW | Authorized role, training verified, purpose documented |
| 2 | `phi.export` | `analyst` (data_analyst) | ✗ DENY | Role not authorized for ePHI export |
| 3 | `phi.delete` | AI cleanup agent | ✗ DENY | `machine_executable=false` — AI cannot authorize ePHI deletion |
| 4 | `phi.export` | Privacy Officer | ⏸ ESCALATE | Dual officer approval required — held for Security Officer sign-off |

## Regulatory coverage

| Requirement | CFR Reference | AtlaSent control |
|-------------|--------------|-----------------|
| Access controls — unique user ID | 45 CFR 164.312(a)(1) | `allowedRoles` + `training_verification` |
| Automatic logoff / minimum necessary | 45 CFR 164.514(d) | `accessPurpose` context field |
| Audit controls — ePHI activity logging | 45 CFR 164.312(b) | `audit_trail` control |
| Encryption before export | 45 CFR 164.312(e)(2)(ii) | `encryptionVerified` context field |
| Integrity controls — deletion guard | 45 CFR 164.312(c)(1) | escalate + `supervisor_review` |
| Dual officer approval for exports | 45 CFR 164.312(a)(2)(iv) | `dual_approval` control |
| AI agent export blocked | 45 CFR 164.312(a)(2)(iv) | `machine_executable=false` |
| HITECH breach notification obligations | HITECH Act §13402 | `breach.assess` escalation path |

## Key enforcement properties

- **Deny-by-default** — any unregistered action or missing context field is denied
- **`machine_executable=false`** — `phi.delete` and `phi.export` block AI agent auto-approval
- **Dual approval** — ePHI export without a confirmed second officer escalates rather than denies (approval workflow triggered)
- **Fail-closed** — network error or stub failure → deny; no ePHI access leaks through

## Quick start

**Python (offline, no API key needed):**
```bash
pip install atlasent
python main.py
```

**TypeScript (offline, no API key needed):**
```bash
npm install
npm start
```

**Live AtlaSent API:**
```bash
ATLASENT_API_KEY=ask_live_... python main.py
# or
ATLASENT_API_KEY=ask_live_... npx tsx main.ts
```

## Policy pack

This example exercises the `hipaa-security` policy pack from
[`atlasent-gxp-starter/policies/hipaa-security.yaml`](https://github.com/atlasent-systems-inc/atlasent-gxp-starter/blob/main/policies/hipaa-security.yaml).

Key action vocabulary:
- `phi.access` — read ePHI (high risk)
- `phi.export` — export ePHI (critical risk, escalate)
- `phi.delete` — delete ePHI (critical risk, escalate)
- `phi.share` — share ePHI with business associates (critical risk, escalate)
- `breach.assess` — initiate HIPAA breach risk assessment (high risk)
- `business_associate.approve` — approve a Business Associate Agreement (high risk)

## Related

- [`atlasent-gxp-starter`](https://github.com/atlasent-systems-inc/atlasent-gxp-starter) — HIPAA + GxP policy packs, local authorization engine
- [`batch-record-release/`](../batch-record-release/) — 21 CFR Part 11 + 21 CFR Part 211 batch release
- [`clinical-data-access/`](../clinical-data-access/) — ICH E6(R3) GCP clinical trial data
