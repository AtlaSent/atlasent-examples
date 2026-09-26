# ISO/IEC 27001:2022 — ISMS Authorization Demo

Demonstrates fail-closed authorization for **information security management system (ISMS)**
operations under **ISO/IEC 27001:2022** and **ISO/IEC 27002:2022** using the AtlaSent SDK.

## Scenarios

| # | Action | Actor | Outcome | Rule |
|---|--------|-------|---------|------|
| 1 | `access.grant` | `sm.rivera` (security_manager) | ✔ ALLOW | Authorized role; least-privilege review complete, data owner confirmed |
| 2 | `vulnerability.patch` | `admin.kim` (it_administrator) | ✔ ALLOW | CAB-approved, staging-tested; patch applied in maintenance window |
| 3 | `firewall.rule_change` | `net.okafor` (network_engineer) | ⏸ ESCALATE | Dual approval + CISO review required; second approver not confirmed |
| 4 | `privileged.access` | `dev.santos` (developer) | ✗ DENY | Role not authorized for privileged access |

## Regulatory coverage

| Requirement | Reference | AtlaSent control |
|-------------|-----------|-----------------|
| Access control — least privilege, need-to-know | ISO 27001 A.5.15 / A.5.18 | `dual_approval` + `audit_trail` |
| Access revocation on termination / role change | ISO 27001 A.5.18 / A.6.5 | `audit_trail` + `supervisor_review` |
| Information asset export — DLP compliance | ISO 27001 A.5.12 / A.8.12 | `dual_approval` + `data_integrity_check` |
| Cryptographic key rotation — lifecycle management | ISO 27001 A.8.24 / ISO 11770 | `change_control` + `validation_check` |
| Security incident declaration — escalation | ISO 27001 A.5.25 / A.5.26 | `supervisor_review` + `audit_trail` |
| Vulnerability patching — CAB + staging test | ISO 27001 A.8.8 | `change_control` + `validation_check` |
| Audit log access — restricted + meta-logged | ISO 27001 A.8.15 | `supervisor_review` + `data_integrity_check` |
| Backup restoration — production overwrite guard | ISO 27001 A.8.13 | `dual_approval` + `change_control` |
| Firewall changes — security impact assessment | ISO 27001 A.8.20 | `dual_approval` + `supervisor_review` |
| Privileged access — JIT, session monitoring | ISO 27001 A.8.2 / A.9.2.3 | `dual_approval` + `electronic_signature` |

## Key enforcement properties

- **Deny-by-default** — any unregistered action or unauthorized role is denied
- **Critical escalations** — `firewall.rule_change` and `privileged.access` always require dual approval + CISO review before execution
- **CAB gate on patches** — `vulnerability.patch` requires `cabApproved: true` and `stagingTested: true` context fields
- **Fail-closed** — network error or stub failure → deny; no privileged access leaks through

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

This example exercises the `iso-27001` policy pack from
[`atlasent-gxp-starter/policies/iso-27001.yaml`](https://github.com/atlasent-systems-inc/atlasent-gxp-starter/blob/main/policies/iso-27001.yaml).

Key action vocabulary:
- `access.grant` — access rights provisioning (high risk, allow)
- `access.revoke` — access rights revocation (medium risk, allow)
- `data.export` — classified data export (high risk, allow)
- `encryption.key_rotation` — cryptographic key rotation (high risk, allow)
- `incident.declare` — security incident declaration (high risk, allow)
- `vulnerability.patch` — vulnerability patch application (medium risk, allow)
- `audit.log_access` — audit log access (medium risk, allow)
- `backup.restore` — production backup restoration (high risk, allow)
- `firewall.rule_change` — firewall / network control change (critical risk, escalate)
- `privileged.access` — privileged / administrative access (critical risk, escalate)

## Related

- [`atlasent-gxp-starter`](https://github.com/atlasent-systems-inc/atlasent-gxp-starter) — ISO 27001 + GxP policy packs, local authorization engine
- [`hipaa-phi-access/`](../hipaa-phi-access/) — HIPAA Security Rule ePHI access controls
- [`fda-mdsap/`](../fda-mdsap/) — FDA MDSAP / ISO 13485 medical device QMS
- [`batch-record-release/`](../batch-record-release/) — 21 CFR Part 11 + 21 CFR Part 211 batch release
