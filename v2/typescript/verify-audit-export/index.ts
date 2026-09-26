/**
 * Generate and verify a signed audit export bundle.
 *
 * Uses the SDK's `verifyBundle` helper which mirrors the server's
 * canonicalization + Ed25519 verification byte-for-byte, so bundles
 * that verify here also verify server-side and vice versa.
 */

import { readFileSync } from 'node:fs';
import { verifyBundle, type AuditExport, type AuditBundle } from '@atlasent/sdk';

const API_URL = process.env.ATLASENT_API_URL ?? 'https://api.atlasent.io/functions/v1';
const API_KEY = process.env.ATLASENT_API_KEY!;

async function generateExport(from: string, to: string): Promise<AuditExport> {
  const res = await fetch(`${API_URL}/v1/audit/exports`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${API_KEY}` },
    body: JSON.stringify({ from, to }),
  });
  if (!res.ok) throw new Error(`Export failed: ${res.status}`);
  return (await res.json()) as AuditExport;
}

async function main() {
  const from = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString();
  const to = new Date().toISOString();

  console.log(`Generating audit export for ${from} → ${to}…`);
  const bundle = await generateExport(from, to);

  console.log(`Export ID:         ${bundle.export_id}`);
  console.log(`Events:            ${bundle.events.length}`);
  console.log(`Chain integrity:   ${bundle.chain_integrity_ok}`);
  console.log(`Signature status:  ${bundle.signature_status}`);

  // Verify offline using the operator's published SPKI-PEM trust set.
  // The SDK reproduces the server's canonicalization exactly — any
  // bundle that verifies here will also verify on any other consumer
  // using the same helper.
  const publicKeyPem = readFileSync('atlasent-audit-pub.pem', 'utf-8');
  // AuditExport carries the signed envelope fields byte-for-byte but isn't
  // nominally an AuditBundle because it lacks AuditBundle's catch-all index
  // signature — safe structural cast.
  const result = await verifyBundle(bundle as unknown as AuditBundle, { publicKeysPem: [publicKeyPem] });

  console.log(`\nChain verified:    ${result.chainIntegrityOk}`);
  console.log(`Signature valid:   ${result.signatureValid}`);
  console.log(`Head hash matches: ${result.headHashMatches}`);
  if (result.matchedKeyId) console.log(`Matched key id:    ${result.matchedKeyId}`);
  if (result.reason) console.log(`Reason:            ${result.reason}`);

  if (!result.verified) {
    console.error('\n❌ Export failed verification — treat as tampered.');
    process.exit(1);
  }
  console.log('\n✅ Export verified.');
}

main().catch(console.error);
