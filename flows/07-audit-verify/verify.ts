// 07 · Audit-chain verification
// ==============================
// Downloads a signed audit export bundle from the AtlaSent API and
// verifies the Ed25519 chain offline — no API call needed for the
// verification step itself.
//
// What this demonstrates:
//   1. Use AtlaSentClient to run an evaluation, creating at least one
//      audit event.
//   2. Call client.createAuditExport() to get a signed bundle from
//      POST /v1-audit/exports.
//   3. Pass the bundle to verifyBundle() for pure offline verification:
//      - adjacency check (each event's previous_hash == prior event's hash)
//      - per-event SHA-256 recomputation from the canonical payload
//      - chain_head_hash matches the last event's stored hash
//      - Ed25519 signature verified against the org's public key(s)
//
// Run:
//   export ATLASENT_API_KEY=ask_live_...
//   npm install && npm start
//
// Optional:
//   ATLASENT_API_URL=https://api.atlasent.io/functions/v1   # override base URL
//   ATLASENT_PUBLIC_KEY_PEM="-----BEGIN PUBLIC KEY-----\n..."  # supply public key for sig check

import { AtlaSentClient, verifyBundle, type AuditBundle } from "@atlasent/sdk";

const apiKey = process.env.ATLASENT_API_KEY;
if (!apiKey) {
  console.error("ATLASENT_API_KEY is required.");
  process.exit(1);
}

const client = new AtlaSentClient({
  apiKey,
  baseUrl: process.env.ATLASENT_API_URL ?? "https://api.atlasent.io/functions/v1",
});

async function main(): Promise<void> {
  console.log("=== 07 · Audit-chain verification ===\n");

  // ── Step 1: generate an evaluation so there is at least one audit event ──
  console.log("Step 1: evaluating demo-agent/read_record to seed audit log...");
  const decision = await client.evaluate({
    agent: "demo-agent",
    action: "record.read",
    context: { flow: "07-audit-verify" },
  });
  console.log(`  decision: ${decision.decision}`);
  console.log(`  permitId: ${decision.permitId}`);

  // ── Step 2: export the audit chain as a signed bundle ────────────────────
  console.log("\nStep 2: requesting signed audit export bundle...");
  const bundle = await client.createAuditExport({});
  console.log(`  export_id:          ${bundle.export_id}`);
  console.log(`  events:             ${bundle.events.length}`);
  console.log(`  chain_head_hash:    ${bundle.chain_head_hash.slice(0, 16)}...`);
  console.log(`  signature_status:   ${bundle.signature_status}`);
  console.log(`  chain_integrity_ok: ${bundle.chain_integrity_ok}`);

  // ── Step 3: verify offline ───────────────────────────────────────────────
  //
  // verifyBundle() needs no API key — it works purely from the bundle
  // fields. Supply ATLASENT_PUBLIC_KEY_PEM to verify the Ed25519
  // signature; without it, chain integrity still runs but
  // signatureValid will be false with an explanatory reason.
  console.log("\nStep 3: verifying bundle offline...");
  const publicKeyPem = process.env.ATLASENT_PUBLIC_KEY_PEM;
  // createAuditExport()'s AuditExportResult carries the signed envelope
  // fields byte-for-byte (see @atlasent/sdk's own doc comment on
  // AuditExportResult) but isn't nominally an AuditBundle because it lacks
  // AuditBundle's catch-all index signature — safe structural cast.
  const result = await verifyBundle(bundle as unknown as AuditBundle, {
    publicKeysPem: publicKeyPem ? [publicKeyPem] : [],
  });

  console.log(`\n  chain_integrity_ok: ${result.chainIntegrityOk}`);
  console.log(`  head_hash_matches:  ${result.headHashMatches}`);
  console.log(`  tampered_events:    ${result.tamperedEventIds.length}`);
  console.log(`  signature_valid:    ${result.signatureValid}`);
  if (result.matchedKeyId) {
    console.log(`  matched_key_id:     ${result.matchedKeyId}`);
  }
  if (result.reason) {
    console.log(`  reason:             ${result.reason}`);
  }
  console.log(`  verified:           ${result.verified}`);

  if (!result.chainIntegrityOk) {
    console.error("\n❌ Chain integrity check failed.");
    if (result.tamperedEventIds.length > 0) {
      console.error(`   Tampered event IDs: ${result.tamperedEventIds.join(", ")}`);
    }
    process.exit(1);
  }

  if (!result.signatureValid) {
    // Chain is intact but we could not verify the signature — either
    // no public key was supplied or the key does not match.
    console.warn(
      "\n⚠  Chain integrity OK, but signature could not be verified."
    );
    console.warn(
      "   Set ATLASENT_PUBLIC_KEY_PEM to the SPKI-PEM public key from"
    );
    console.warn("   GET /v1-signing-keys to complete offline verification.");
    // Exit 0 — chain is intact; signature check is optional without the key.
    return;
  }

  console.log("\n✅ Bundle verified: chain intact and signature valid.");
}

main().catch((err: unknown) => {
  console.error("Flow failed:", err instanceof Error ? err.message : err);
  process.exit(1);
});
