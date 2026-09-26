# GxP Examples

Authorization examples for AI agents in GxP-regulated life sciences environments.
All examples use AtlaSent for non-bypassable, fail-closed execution-time authorization.

## Examples

| Directory | Mode | Languages | Key capability |
|-----------|------|-----------|----------------|
| [`batch-record-release/`](./batch-record-release/) | Managed API | Python · TypeScript | Dual sign-off batch release; `machine_executable=false` |
| [`clinical-data-access/`](./clinical-data-access/) | Managed API | Python · TypeScript | Clinical trial data access; ICH E6(R3) GCP |
| [`quality-capa/`](./quality-capa/) | Managed API | Python · TypeScript | CAPA state machine; deviation lifecycle |
| [`vqp-re-derivation/`](./vqp-re-derivation/) | Managed API | Python · TypeScript | Verifiable Qualification Package re-derivation |
| [`local-starter/`](./local-starter/) | Local / air-gapped | TypeScript | Phase 3: multi-pack composition, offline audit bundle |
| [`hipaa-phi-access/`](./hipaa-phi-access/) | Local / air-gapped | Python · TypeScript | HIPAA Security Rule ePHI access; `machine_executable=false` on export/delete |
| [`fda-mdsap/`](./fda-mdsap/) | Local / air-gapped | Python · TypeScript | MDSAP / ISO 13485 medical device QMS; dual QP approval for device release |
| [`iso-27001/`](./iso-27001/) | Local / air-gapped | Python · TypeScript | ISO/IEC 27001:2022 ISMS; firewall + privileged access escalation |

## Managed API vs local mode

| Mode | When to use | Requires |
|------|-------------|----------|
| **Managed API** | Production, SaaS, managed policy lifecycle | `ATLASENT_API_KEY` + `ATLASENT_BASE_URL` |
| **Local / air-gapped** | Development, CI, regulated env without outbound network | Nothing — no API key |

## Quick start

**Managed API examples:**

```bash
cd batch-record-release     # or clinical-data-access / quality-capa / vqp-re-derivation
pip install -r requirements.txt
ATLASENT_API_KEY=ask_live_... python main.py
# TypeScript variant:
npm install && ATLASENT_API_KEY=ask_live_... npx tsx main.ts
```

**Local / air-gapped (Phase 3):**

```bash
cd local-starter
npm install && npm start
# No environment variables needed.
```

## Regulatory coverage

| Standard | Covered by |
|----------|-----------|
| 21 CFR Part 11 — Electronic records / e-signatures | `batch-record-release`, `local-starter` |
| 21 CFR Part 211 — cGMP batch records | `batch-record-release` |
| EU GMP Annex 11 — Computerised systems | `batch-record-release`, `local-starter` |
| ICH E6(R3) GCP — Clinical data audit trail | `clinical-data-access`, `local-starter` |
| ICH Q10 — Pharmaceutical quality system | `quality-capa` |
| HIPAA Security Rule — 45 CFR Part 164 Subpart C (ePHI) | `hipaa-phi-access` |
| ISO 13485:2016 / MDSAP — Medical device QMS (design, release, distribution) | `fda-mdsap` |
| ISO/IEC 27001:2022 — ISMS (access, firewall, privileged access) | `iso-27001` |

## Phase 3 — Execution Assurance (local-starter)

The [`local-starter/`](./local-starter/) example demonstrates three Phase 3 capabilities
from [`atlasent-gxp-starter`](https://github.com/atlasent-systems-inc/atlasent-gxp-starter) v0.3.0:

1. **Multi-pack composition** — 21 CFR Part 11 + EU Annex 11 stacked with most-restrictive-wins (`deny > escalate > allow`)
2. **Local authorization** — `AuthorizationEngine` evaluates in-process, zero-latency, air-gapped
3. **Offline audit bundle** — `exportAudit` + `verifyAuditZip` with Merkle-root tamper detection

## Related

- [atlasent-gxp-starter](https://github.com/atlasent-systems-inc/atlasent-gxp-starter) — GxP policy engine, 21 CFR Part 11 + EU Annex 11 + HIPAA packs
- [flows/07-audit-verify/](../flows/07-audit-verify/) — managed API audit chain verification
