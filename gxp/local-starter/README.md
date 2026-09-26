# GxP Local Starter — Air-Gapped Authorization Demo

> **Phase 3 — Execution Assurance & Operational Sovereignty**  
> Uses [`atlasent-gxp-starter`](https://github.com/atlasent-systems-inc/atlasent-gxp-starter)
> v0.3.0 for **fully local**, air-gapped GxP authorization — no API key required.

Shows three Phase 3 capabilities in a single runnable script:

1. **Multi-pack composition** — stack 21 CFR Part 11 + EU Annex 11 policies with
   `mergePolicies`; most-restrictive-wins across frameworks.
2. **Local authorization** — `AuthorizationEngine` evaluates without any network
   call; deterministic, zero-latency, air-gapped.
3. **Offline audit bundle** — `exportAudit` exports a hash-chained, Merkle-rooted
   ZIP; `verifyAuditZip` verifies it with no internet access required.

## Run

```bash
npm install
npm start
```

No environment variables needed. All policies are loaded from the
`gxp-starter` package's `policies/` directory.

## What the script does

```
Step 1  Load policies (21 CFR Part 11 + EU Annex 11) from npm package
Step 2  Merge packs — most-restrictive-wins stacking model
Step 3  Authorize 5 canonical GxP scenarios
Step 4  Export hash-chained audit bundle to /tmp/
Step 5  Verify bundle offline (Merkle root, chain integrity, entry count)
```

## Scenarios

| Action | Description | Expected decision |
|--------|-------------|-------------------|
| `record.read` | Read batch manufacturing record | allow |
| `record.update` | Update in-process results | allow |
| `record.delete` | Delete a batch record | deny |
| `batch.release` | Release batch for distribution | escalate |
| `deviation.close` | Close a manufacturing deviation | escalate |

Decisions reflect the most-restrictive result across both loaded policy packs.

## Why local mode?

| Scenario | Recommendation |
|----------|---------------|
| Development / CI | Local mode — instant, no API key, no network |
| Air-gapped regulated environment | Local mode — offline-verifiable audit bundle |
| Production (managed policy, cloud audit) | Remote mode via `ATLASENT_API_KEY` + `ATLASENT_BASE_URL` |

Upgrade path: set `ATLASENT_API_KEY` + `ATLASENT_BASE_URL` and switch the
`AuthorizationEngine` call to `engine.authorize()` with remote delegation.
See `atlasent-gxp-starter/src/mcp-server.ts` for the remote-mode implementation.

## Regulatory context

| Requirement | Reference |
|-------------|-----------|
| System performs intended function consistently | 21 CFR Part 11 §11.10(a) |
| Audit trails — tamper-evident, date/time-stamped | 21 CFR Part 11 §11.10(e) |
| Controls for open systems — tamper detection | 21 CFR Part 11 §11.30 |
| Audit trails — changes documented | EU Annex 11 §9 |
| Security — Merkle root for tamper detection | EU Annex 11 §12 |

## Files

| File | Description |
|------|-------------|
| `main.ts` | Runnable demo: load → compose → authorize → export → verify |
| `package.json` | Dependencies: `gxp-starter` v0.3.0 |

## Related examples

- [`gxp/batch-record-release/`](../batch-record-release/) — managed API + dual sign-off
- [`gxp/quality-capa/`](../quality-capa/) — CAPA workflow
- [`flows/07-audit-verify/`](../../flows/07-audit-verify/) — managed API audit chain
