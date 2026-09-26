> **Later-phase reference.** This document is not part of the Deploy Gate V1 pilot. Keep first pilots focused on GitHub Actions + `production.deploy` + `/v1-evaluate` + `/v1-verify-permit`.

# 07 · Audit-chain verification

Download a signed audit export bundle from the AtlaSent API and verify
the Ed25519 chain **offline** — no network call is needed for the
verification step itself.

## What it demonstrates

| Step | What happens |
|------|--------------|
| 1 | `client.evaluate()` seeds at least one audit event |
| 2 | `client.createAuditExport()` calls `POST /v1-audit/exports` and returns a signed bundle |
| 3 | `verifyBundle(bundle)` checks chain integrity and the Ed25519 signature locally |

**Chain integrity** means:
- Each event's `previous_hash` equals the prior event's `hash`
- Each event's `hash` is recomputed from `SHA-256(prev_hash || canonicalJSON(payload))`
- `chain_head_hash` matches the last event's stored `hash`

**Signature verification** requires the org's SPKI-PEM public key (from
`GET /v1-signing-keys`). The chain check runs even without it — useful
for tamper detection when you don't have the key locally.

## Setup

```bash
export ATLASENT_API_KEY=ask_live_...
```

Optional — enables full signature verification:

```bash
export ATLASENT_PUBLIC_KEY_PEM="-----BEGIN PUBLIC KEY-----
...
-----END PUBLIC KEY-----"
```

## Run

```bash
npm install
npm start
```

## Expected output

```
=== 07 · Audit-chain verification ===

Step 1: evaluating demo-agent/read_record to seed audit log...
  decision: ALLOW
  permitId: <uuid>

Step 2: requesting signed audit export bundle...
  export_id:          <uuid>
  events:             42
  chain_head_hash:    a3f9c2e1...
  signature_status:   signed
  chain_integrity_ok: true

Step 3: verifying bundle offline...

  chain_integrity_ok: true
  head_hash_matches:  true
  tampered_events:    0
  signature_valid:    true
  matched_key_id:     <key-id>
  verified:           true

✅ Bundle verified: chain intact and signature valid.
```

## Key API shape (from `@atlasent/sdk`)

```ts
import { AtlaSentClient, verifyBundle } from "@atlasent/sdk";

const bundle = await client.createAuditExport({});
const result = await verifyBundle(bundle, { publicKeysPem: [pem] });
// result.chainIntegrityOk — adjacency + hash recomputation passed
// result.signatureValid   — Ed25519 signature matched a supplied key
// result.verified         — chainIntegrityOk && signatureValid
// result.tamperedEventIds — event IDs whose hash did not recompute
```

## What to look at next

- `verifyAuditBundle()` (lower-level, takes pre-imported `VerifyKey[]`) — exported from `@atlasent/sdk`
- `signedBytesFor()` — recreates the exact envelope the backend signed
- `atlasent-sdk/typescript/src/auditBundle.ts` — the full offline verifier source
- `atlasent-api/supabase/functions/v1-audit/verify.ts` — the reference verifier (source of truth)
