import { writeFileSync } from 'node:fs';
import type { AuditExport } from '@atlasent/sdk';

const API_URL = process.env.ATLASENT_API_URL!;
const API_KEY = process.env.ATLASENT_API_KEY!;

async function apiFetch<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: body ? 'POST' : 'GET',
    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${API_KEY}` },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.json() as Promise<T>;
}

async function main() {
  console.log('=== Signed Audit Export Example ===\n');

  const to = new Date().toISOString();
  const from = new Date(Date.now() - 7 * 86400_000).toISOString();

  console.log(`Exporting audit events from ${from.slice(0, 10)} to ${to.slice(0, 10)}…`);

  const bundle = await apiFetch<AuditExport>('/v1/audit/exports', { from, to });

  console.log(`Events:            ${bundle.events.length}`);
  console.log(`Chain integrity:   ${bundle.chain_integrity_ok}`);
  console.log(`Chain head hash:   ${bundle.chain_head_hash}`);
  console.log(`Signature status:  ${bundle.signature_status}`);
  console.log(`Signature:         ${bundle.signature.slice(0, 32)}…`);
  if (bundle.signing_key_id) console.log(`Signing key id:    ${bundle.signing_key_id}`);

  writeFileSync('audit-export.json', JSON.stringify(bundle, null, 2));
  console.log('\n✅ Saved to audit-export.json');
  console.log('   Verify offline with: atlasent audit verify --file audit-export.json');
}

main().catch(console.error);
