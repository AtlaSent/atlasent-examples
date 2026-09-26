# FDA MDSAP / ISO 13485 — Medical Device QMS Authorization Demo

Demonstrates fail-closed authorization for **medical device quality management system (QMS)**
operations under the **FDA Medical Device Single Audit Program (MDSAP)** and **ISO 13485:2016**
using the AtlaSent SDK.

## Scenarios

| # | Action | Actor | Outcome | Rule |
|---|--------|-------|---------|------|
| 1 | `complaint.handle` | `qm.ross` (quality_manager) | ✔ ALLOW | Authorized role; complaint file opened with MDR reportability assessment |
| 2 | `label.approve` | `ra.patel` (regulatory_affairs) | ✔ ALLOW | Authorized role; label version and DHF reference provided |
| 3 | `device.release` | `qp.chen` (qualified_person) | ⏸ ESCALATE | Dual QP approval required; second approver not confirmed |
| 4 | `design.change` | `op.jones` (production_operator) | ✗ DENY | Role not authorized for design changes |

## Regulatory coverage

| Requirement | Reference | AtlaSent control |
|-------------|-----------|-----------------|
| Design change impact assessment + dual approval | ISO 13485 §7.3.9 | `dual_approval` + `change_control` |
| Device release — final acceptance by QP | ISO 13485 §8.2.6 / 21 CFR 820.80 | `dual_approval` + `electronic_signature` |
| Labelling compliance — multi-market review | ISO 13485 §7.5.8 / 21 CFR 820.120 | `allowedRoles` + `data_integrity_check` |
| Complaint handling — MDR/vigilance reportability | ISO 13485 §8.2.2 / 21 CFR 820.198 | `audit_trail` + `supervisor_review` |
| CAPA initiation — systemic nonconformances | ISO 13485 §8.5.2 / §8.5.3 | `change_control` + `supervisor_review` |
| Process validation — special processes | ISO 13485 §7.5.6 | `dual_approval` + `validation_check` |
| Clinical data change — GCP audit trail | ICH E6 / 21 CFR 820 | `dual_approval` + `electronic_signature` |
| Distribution authorization — lot traceability | ISO 13485 §7.5.5 / 21 CFR 820.160 | `dual_approval` + `audit_trail` |
| MDSAP audit findings — objective evidence | MDSAP Audit Approach §9 | `audit_trail` + `supervisor_review` |

## Key enforcement properties

- **Deny-by-default** — any unregistered action or role is denied
- **Dual approval for critical actions** — `device.release`, `process.validate`, `distribution.authorize` all escalate without a confirmed second approver
- **DHR completeness check** — `device.release` requires `dhrComplete: true` context field
- **Fail-closed** — network error or stub failure → deny; no device release leaks through

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

This example exercises the `fda-mdsap` policy pack from
[`atlasent-gxp-starter/policies/fda-mdsap.yaml`](https://github.com/atlasent-systems-inc/atlasent-gxp-starter/blob/main/policies/fda-mdsap.yaml).

Key action vocabulary:
- `design.change` — design change authorization (high risk, escalate)
- `device.release` — finished device release (critical risk, escalate)
- `label.approve` — device labelling approval (high risk, allow)
- `complaint.handle` — post-market complaint handling (high risk, allow)
- `capa.initiate` — CAPA initiation (high risk, allow)
- `supplier.change` — approved supplier list change (high risk, allow)
- `process.validate` — special process validation (critical risk, escalate)
- `clinical_data.change` — clinical data modification (critical risk, escalate)
- `distribution.authorize` — distribution authorization (critical risk, escalate)
- `audit.finding` — MDSAP audit finding recording (medium risk, allow)

## Related

- [`atlasent-gxp-starter`](https://github.com/atlasent-systems-inc/atlasent-gxp-starter) — MDSAP + GxP policy packs, local authorization engine
- [`batch-record-release/`](../batch-record-release/) — 21 CFR Part 11 + 21 CFR Part 211 batch release
- [`hipaa-phi-access/`](../hipaa-phi-access/) — HIPAA Security Rule ePHI access controls
- [`iso-27001/`](../iso-27001/) — ISO/IEC 27001:2022 ISMS authorization
