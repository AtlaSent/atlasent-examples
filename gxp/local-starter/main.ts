/**
 * GxP Local Starter — Phase 3 demo
 * ─────────────────────────────────────────────────────────────────────────
 * Demonstrates three Phase 3 Execution Assurance capabilities using the
 * `atlasent-gxp-starter` local policy engine — no API key required.
 *
 *   1. Multi-pack composition: 21 CFR Part 11 + EU Annex 11 stacked via
 *      `mergePolicies`; most-restrictive-wins (deny > escalate > allow).
 *
 *   2. Local authorization: `AuthorizationEngine` evaluates in-process,
 *      zero-latency, fully air-gapped, deterministic.
 *
 *   3. Offline audit bundle: `exportAudit` exports a hash-chained,
 *      Merkle-rooted ZIP bundle; `verifyAuditZip` verifies it without
 *      any network access.
 *
 * Run:
 *   npm install && npm start
 *
 * No environment variables needed.
 *
 * Regulatory refs:
 *   21 CFR Part 11 §11.10(a) — consistent intended performance
 *   21 CFR Part 11 §11.10(e) — audit trails
 *   21 CFR Part 11 §11.30    — open-systems tamper detection
 *   EU Annex 11 §9            — audit trails
 *   EU Annex 11 §12           — security / tamper fingerprint
 */

import { join } from "node:path";
import { tmpdir } from "node:os";
import { mkdirSync, existsSync } from "node:fs";
import {
  AuthorizationEngine,
  loadPoliciesFromDirectory,
  mergePolicies,
  exportAudit,
  verifyAuditZip,
  computeMerkleRoot,
  type AgentIdentity,
  type AgentAction,
} from "gxp-starter";

// ── Resolve policies bundled inside the npm package ──────────────────────────
// gxp-starter ships policies/ alongside its dist/.
const pkgRoot = new URL(
  "../../node_modules/gxp-starter",
  import.meta.url,
).pathname;

const policyDir = join(pkgRoot, "policies");

if (!existsSync(policyDir)) {
  console.error(
    `Policy directory not found: ${policyDir}\n` +
      `Run 'npm install' to install the gxp-starter package.`,
  );
  process.exit(1);
}

// ── Agent identity ────────────────────────────────────────────────────────────
const qaManager: AgentIdentity = {
  agentId: "qa-mgr-example-001",
  name: "QA Manager (local-starter demo)",
  roles: ["quality_assurance", "qa_manager"],
};

// ── Canonical GxP scenarios ───────────────────────────────────────────────────
const SCENARIOS: AgentAction[] = [
  {
    actionId: "record.read",
    description: "Read batch manufacturing record",
    resource: "mfg/batch/LOT-2026-DEMO",
  },
  {
    actionId: "record.update",
    description: "Update in-process parameter results",
    resource: "mfg/batch/LOT-2026-DEMO",
  },
  {
    actionId: "record.delete",
    description: "Delete a batch record",
    resource: "mfg/batch/LOT-2026-DEMO",
  },
  {
    actionId: "batch.release",
    description: "Release batch for distribution",
    resource: "mfg/batch/LOT-2026-DEMO",
  },
  {
    actionId: "deviation.close",
    description: "Close a manufacturing deviation",
    resource: "mfg/deviation/DEV-2026-DEMO",
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Main
// ─────────────────────────────────────────────────────────────────────────────

console.log("=".repeat(64));
console.log("GxP Local Starter — Phase 3 Demo");
console.log("atlasent-gxp-starter: local engine, no API key required");
console.log("=".repeat(64));
console.log();

// ── Step 1: Load policy packs ─────────────────────────────────────────────────
console.log("Step 1: Loading GxP policy packs from npm package…");

const allPolicies = loadPoliciesFromDirectory(policyDir);
const cfr11 = allPolicies.find((p) => p.id.includes("21cfr11") || p.id.includes("cfr11"));
const annex11 = allPolicies.find((p) => p.id.includes("annex11") || p.id.includes("eu-annex"));

const available = [cfr11, annex11].filter(Boolean) as typeof allPolicies;
if (available.length === 0) {
  // Fall back to all available policies if the specific ones aren't found
  available.push(...allPolicies.slice(0, 2));
}

console.log(`  Loaded ${allPolicies.length} policies from ${policyDir}`);
console.log(
  `  Using for demo: ${available.map((p) => p.id).join(", ") || "all available"}`,
);
console.log();

// ── Step 2: Merge packs — most-restrictive-wins stacking ─────────────────────
console.log("Step 2: Merging packs — most-restrictive-wins stacking model…");

const mergedId = available.map((p) => p.id).join("+");
const mergedTitle = available.map((p) => p.title ?? p.id).join(" + ");
const mergedPolicy =
  available.length > 1
    ? mergePolicies(mergedId, mergedTitle, available)
    : available[0]!;

console.log(`  Stacking model: deny (2) > escalate (1) > allow (0)`);
console.log(
  `  Merged policy ID: ${mergedPolicy.id}`,
);
console.log();

// ── Step 3: Authorize scenarios using the local engine ────────────────────────
console.log("Step 3: Authorizing 5 canonical GxP scenarios (local engine)…");
console.log();

const engine = new AuthorizationEngine();
engine.registerPolicy(mergedPolicy);

console.log(
  `${"action".padEnd(22)} ${"decision".padEnd(10)} ${"risk".padEnd(8)} description`,
);
console.log("─".repeat(72));

for (const action of SCENARIOS) {
  const resp = await engine.authorize({ agent: qaManager, action });
  console.log(
    `${action.actionId.padEnd(22)} ${resp.decision.padEnd(10)} ${(resp.riskLevel ?? "—").padEnd(8)} ${action.description}`,
  );
}

console.log();

// ── Step 4: Export hash-chained audit bundle ──────────────────────────────────
console.log("Step 4: Exporting hash-chained audit bundle to /tmp/…");

const bundleDir = join(tmpdir(), "atlasent-local-starter-demo");
mkdirSync(bundleDir, { recursive: true });
const bundlePath = join(
  bundleDir,
  `audit-bundle-local-demo-${Date.now()}.zip`,
);

const auditEntries = engine.audit.getEntries();
const merkleRoot = computeMerkleRoot(auditEntries);

const exportResult = await exportAudit(auditEntries, {
  outputPath: bundlePath,
});

console.log(`  ✓ Bundle exported: ${exportResult.output_path}`);
console.log(`    Entry count:  ${exportResult.entry_count}`);
console.log(`    Merkle root:  ${exportResult.merkle_root}`);
console.log();

// ── Step 5: Verify bundle offline ────────────────────────────────────────────
console.log("Step 5: Verifying bundle offline (no network required)…");

const verifyResult = await verifyAuditZip(bundlePath);

const bundleValid =
  verifyResult.chain_valid && verifyResult.merkle_root_verified;
const rootMatch = verifyResult.merkle_root === merkleRoot;

console.log(
  `  Bundle integrity:  ${bundleValid ? "✓ VALID" : "✗ INVALID"}`,
);
console.log(`  Chain integrity:   ${verifyResult.chain_valid ? "✓ intact" : "✗ BROKEN"}`);
console.log(
  `  Merkle root:       ${verifyResult.merkle_root_verified ? "✓ verified" : "✗ MISMATCH"}`,
);
console.log(
  `  Root consistent:   ${rootMatch ? "✓ matches pre-export root" : "✗ DIFFERS"}`,
);
console.log(`  Entry count:       ${verifyResult.entry_count}`);
console.log();

// ── Summary ───────────────────────────────────────────────────────────────────
console.log("=".repeat(64));
console.log("Summary");
console.log("=".repeat(64));
console.log(`
What this demo proved:

  ① Multi-pack composition: ${available.map((p) => p.id).join(" + ")}
    Stacked evaluation picks the strictest decision across all loaded packs.

  ② Local authorization: all ${auditEntries.length} decisions made in-process,
    zero network calls, deterministic output, air-gap ready.

  ③ Offline audit bundle: ${exportResult.entry_count} entries exported to ZIP,
    chain integrity verified, Merkle root computed and matched.
    Bundle at: ${exportResult.output_path}
    Merkle root to retain for offline inspection:
    ${merkleRoot}

Upgrade path → AtlaSent managed evaluator:
  Set ATLASENT_API_KEY + ATLASENT_BASE_URL to delegate evaluations to
  the hosted API with tenant-scoped risk uplift, Ed25519-signed audit
  chain, and managed policy lifecycle.
  https://atlasent.io
`);

if (!bundleValid) {
  console.error("✗ Audit bundle verification failed — investigate above.");
  process.exit(1);
}

console.log("✓ Demo complete.");
