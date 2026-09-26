#!/usr/bin/env node
// Verified-actor demo — mint a server-compatible `actor_identity.v1` assertion.
//
// Zero dependencies. Node >= 20 (Ed25519 WebCrypto). Run:
//
//   node mint-actor-identity.mjs
//
// What it shows, end to end:
//   1. Generate an Ed25519 issuer keypair (the L2-capable algorithm).
//   2. Print the ACTOR_TRUSTED_ISSUERS entry to configure on the runtime.
//   3. Mint an actor_identity.v1 assertion bound to a specific request and
//      sign it (byte-identical canonicalization to the runtime verifier).
//   4. Self-verify the signature, then print the two evaluate requests —
//      the SPOOFED one (no assertion -> deny ACTOR_UNVERIFIED) and the
//      VERIFIED one (assertion attached -> allow + signed evidence).
//
// The canonicalize() below is copied verbatim from the runtime's
// _shared/canonical.ts so the signature this script produces verifies on the
// server. See guides/verified-actor-enablement.md for the operator steps.

const { subtle } = globalThis.crypto;

// ── byte-identical to atlasent-api _shared/canonical.ts ──────────────
function canonicalize(value) {
  if (value === undefined) return "null";
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) {
    return "[" + value.map((v) => (v === undefined ? "null" : canonicalize(v))).join(",") + "]";
  }
  const entries = [];
  for (const k of Object.keys(value).sort()) {
    const v = value[k];
    if (v === undefined) continue;
    entries.push(JSON.stringify(k) + ":" + canonicalize(v));
  }
  return "{" + entries.join(",") + "}";
}

const hex = (buf) => Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, "0")).join("");

// The runtime strips `signature` and canonicalizes the rest (see
// canonicalActorIdentityPayload in _shared/actor_identity.ts).
const signingPayload = (a) => {
  const { signature: _omit, ...rest } = a;
  return canonicalize(rest);
};

// ── the request we are authorizing (edit these for your case) ────────
const REQUEST = {
  action_type: "agent.tool_call",
  actor_id: "spiffe://acme/ci/deploy-bot",
  tenant_id: "00000000-0000-0000-0000-000000000001", // your AtlaSent org id
  environment: "production",
};
const ISSUER_ID = "workload-idp.acme";
const KID = "kid-demo-1";

async function main() {
  // 1 — issuer keypair (Ed25519: the verification key is public → L2-capable).
  const kp = await subtle.generateKey({ name: "Ed25519" }, true, ["sign", "verify"]);
  const pubHex = hex(await subtle.exportKey("raw", kp.publicKey)); // 32-byte raw → hex

  // 2 — the ACTOR_TRUSTED_ISSUERS entry to set on the runtime project.
  const issuersEntry = { [ISSUER_ID]: { [KID]: { alg: "Ed25519", key: pubHex, allowed_environments: [REQUEST.environment] } } };

  // 3 — mint + sign the assertion, bound to THIS request.
  const now = Date.now();
  const assertion = {
    version: "actor_identity.v1",
    subject: { principal_id: REQUEST.actor_id, principal_kind: "workload" },
    binding: { action_type: REQUEST.action_type, tenant_id: REQUEST.tenant_id, environment: REQUEST.environment },
    issuer: { type: "oidc", issuer_id: ISSUER_ID, kid: KID },
    issued_at: new Date(now - 60_000).toISOString(),
    expires_at: new Date(now + 60 * 60_000).toISOString(),
    signature: "",
  };
  const payload = signingPayload(assertion);
  assertion.signature = hex(await subtle.sign({ name: "Ed25519" }, kp.privateKey, new TextEncoder().encode(payload)));

  // 4 — self-verify (sanity: the crypto is sound before you send it).
  const ok = await subtle.verify(
    { name: "Ed25519" },
    kp.publicKey,
    Uint8Array.from(assertion.signature.match(/../g).map((h) => parseInt(h, 16))),
    new TextEncoder().encode(payload),
  );

  const spoofRequest = { action_type: REQUEST.action_type, actor_id: REQUEST.actor_id, context: { environment: REQUEST.environment } };
  const verifiedRequest = { ...spoofRequest, actor_identity: assertion };

  console.log(`
=== 1. Configure the trusted issuer (runtime project) ==========================
supabase secrets set ACTOR_TRUSTED_ISSUERS='${JSON.stringify(issuersEntry)}' \\
  --project-ref <runtime-project-ref>

=== 2. Enable the gate on the action class ====================================
UPDATE public.action_classes SET requires_verified_actor = TRUE
 WHERE slug = '${REQUEST.action_type}';

=== 3a. SPOOFED request (no actor_identity) → DENY =============================
POST /v1-evaluate
${JSON.stringify(spoofRequest, null, 2)}
  expect → { "decision": "deny", "deny_code": "ACTOR_UNVERIFIED" }   (no permit)

=== 3b. VERIFIED request (assertion attached) → ALLOW ==========================
POST /v1-evaluate
${JSON.stringify(verifiedRequest, null, 2)}
  expect → decision proceeds normally; on allow the signed
           evaluation.completed audit event carries:
           verified_actor_identity: { issuer_id: "${ISSUER_ID}", kid: "${KID}", principal_kind: "workload" }

=== signature self-check ======================================================
local Ed25519 verify over the canonical payload: ${ok ? "✓ PASS" : "✗ FAIL"}
(canonicalization is byte-identical to the runtime, so this signature also
 verifies server-side; the runtime additionally checks the four bindings:
 subject==actor_id, action_type, tenant_id, environment.)
`);
  if (!ok) process.exit(1);
}

main().catch((e) => { console.error(e); process.exit(1); });
