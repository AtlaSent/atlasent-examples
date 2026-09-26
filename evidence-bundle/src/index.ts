// Demonstrates: generating a SOC 2 Type II evidence bundle for the last 90 days,
// printing the sha256 for auditor handoff, then listing all bundles.
//
// Flow: createEvidenceExport (soc2_type_ii) -> print sha256 -> listEvidenceExports
//
// Requires: ATLASENT_API_KEY, ATLASENT_BASE_URL, ATLASENT_ORG_ID env vars.
//
// The server defaults the evidence window to the 90 days preceding the request
// when no window is supplied.

import { AtlaSentClient, type CreateEvidenceExportInput } from "@atlasent/sdk";

const apiKey = process.env["ATLASENT_API_KEY"];
const baseUrl = process.env["ATLASENT_BASE_URL"];
const orgId = process.env["ATLASENT_ORG_ID"];

if (!apiKey || !baseUrl || !orgId) {
  console.error(
    "ATLASENT_API_KEY, ATLASENT_BASE_URL, and ATLASENT_ORG_ID are all required.",
  );
  process.exit(1);
}

const client = new AtlaSentClient({ apiKey, baseUrl });

async function main() {
  // ── Step 1: generate SOC 2 Type II evidence bundle ───────────────────────
  // Omitting `window` lets the server default to the last 90 days.
  const exportInput: CreateEvidenceExportInput = {
    regime: "soc2_type_ii",
  };

  console.log("Generating SOC 2 Type II evidence bundle (last 90 days)...");
  const result = await client.createEvidenceExport(orgId, exportInput);

  const record = result.export;
  const bundle = result.bundle;

  console.log("  export id:         ", record.id);
  console.log("  regime:            ", record.regime);
  console.log("  window from:       ", record.window_from);
  console.log("  window to:         ", record.window_to);
  console.log("  controls total:    ", record.controls_total);
  console.log("  controls evidenced:", record.controls_evidenced);
  console.log("  controls partial:  ", record.controls_partial);
  console.log("  controls missing:  ", record.controls_missing);
  console.log("  generated_at:      ", record.generated_at);

  // ── Step 2: print the sha256 for auditor handoff ─────────────────────────
  // The sha256 is the hex digest of the canonical bundle bytes. Hand this to
  // your auditor so they can verify the bundle has not been tampered with.
  console.log("\nBundle sha256 (provide to auditor for verification):");
  console.log(" ", result.sha256);
  console.log("  bundle_id:", bundle.bundle_id);

  // ── Step 3: list all evidence exports ────────────────────────────────────
  console.log("\nListing all evidence exports for this org...");
  const listResult = await client.listEvidenceExports(orgId);

  if (listResult.exports.length === 0) {
    console.log("  No exports found.");
  } else {
    for (const exp of listResult.exports) {
      console.log(
        `  ${exp.id}  regime=${exp.regime}  window=[${exp.window_from} -> ${exp.window_to}]  sha256=${exp.bundle_sha256}`,
      );
    }
  }
}

main().catch((err) => {
  console.error("Error:", err instanceof Error ? err.message : String(err));
  process.exit(1);
});
