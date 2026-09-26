/**
 * gxp-batch-record-release: GxP Batch Record Release Authorization Demo (TypeScript)
 *
 * Mirrors main.py — same 3 scenarios, same enforcement outcomes.
 *
 * Offline (mock server in another terminal):
 *   npx @atlasent/sdk mock
 *   ATLASENT_API_URL=http://127.0.0.1:4747 ATLASENT_API_KEY=mock npx tsx main.ts
 *
 * Live:
 *   ATLASENT_API_KEY=ask_live_... npx tsx main.ts
 *
 * This example is part of the GxP pilot starter kit at atlasent-gxp-starter/.
 */
import atlasent, { AtlaSentDeniedError, AtlaSentError, type Permit } from "@atlasent/sdk";

// The SDK's built-in default base URL is the bare host; the AtlaSent API is
// served under /functions/v1, so set it explicitly.
atlasent.configure({ baseUrl: process.env.ATLASENT_API_URL ?? "https://api.atlasent.io/functions/v1" });

const WIDTH = 72;

// ---------------------------------------------------------------------------
// Display helpers
// ---------------------------------------------------------------------------

const bar = (title = "") => {
  if (title) {
    console.log(`\n${"━".repeat(WIDTH)}`);
    console.log(`  ${title}`);
    console.log(`${"━".repeat(WIDTH)}`);
  } else {
    console.log(`  ${"─".repeat(WIDTH - 4)}`);
  }
};

const scenario = (num: number | string, action: string, note: string) => {
  console.log(`\n▸ Scenario ${num} — ${action}`);
  console.log(`  ${note}`);
};

const blocked = (reason: string) =>
  console.log(`  ✗ BLOCKED    ${reason.replace(/\s*\[hold:[^\]]+\]/g, "")}`);

const permitLine = (p: Permit) => {
  console.log(`  ✔ PERMITTED  ${p.reason ?? ""}`);
  console.log(`               permit_id:   ${p.permitId}`);
  console.log(`               audit_hash:  ${p.auditHash ?? ""}`);
  console.log(`               permit_hash: ${p.permitHash ?? ""}`);
};

const execute = (msg: string) => console.log(`               → ${msg}`);

// ---------------------------------------------------------------------------
// Simulated manufacturing system mutations
// Only reachable after protect() resolves.
// ---------------------------------------------------------------------------

const sysReleaseBatch = (batchId: string, productCode: string, lotNumber: string) => {
  execute(`batch ${batchId} (${productCode} lot ${lotNumber}) status set to RELEASED`);
  execute("release certificate generated and posted to document management system");
};

// ---------------------------------------------------------------------------
// Demo
// ---------------------------------------------------------------------------

async function run() {
  bar("gxp-batch-record-release   Batch Record Release Authorization Demo (TypeScript)");
  console.log(`  action: manufacturing.batch_record.release`);
  console.log(`  policy: fail-closed, dual-approver, machine_executable=false`);

  // 1 -- ALLOW: complete record, both QA signatories present ----------------
  scenario(
    1,
    "manufacturing.batch_record.release",
    "ALLOWED: complete batch record, both QA signatories present"
  );
  try {
    const p = await atlasent.protect({
      agent: "qa.mgr@pharma.example",
      action: "manufacturing.batch_record.release",
      context: {
        batchId: "BATCH-2026-00147",
        productCode: "DRUG-XYZ-100MG",
        lotNumber: "L26-04417",
        certifiedBy: "qa.mgr@pharma.example",
        qaSignoffBy: "qa.lead@pharma.example",
        batchRecordComplete: true,
        deviationCount: 0,
        regulatoryRegion: "US-FDA",
      },
    });
    permitLine(p);
    sysReleaseBatch("BATCH-2026-00147", "DRUG-XYZ-100MG", "L26-04417");
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) blocked(err.reason ?? err.message);
    else throw err;
  }

  // 2 -- DENY: incomplete batch record (batchRecordComplete=false) -----------
  scenario(
    2,
    "manufacturing.batch_record.release",
    "BLOCKED: batchRecordComplete=false — record sections not yet reviewed"
  );
  try {
    await atlasent.protect({
      agent: "qa.mgr@pharma.example",
      action: "manufacturing.batch_record.release",
      context: {
        batchId: "BATCH-2026-00148",
        productCode: "DRUG-XYZ-100MG",
        lotNumber: "L26-04418",
        certifiedBy: "qa.mgr@pharma.example",
        qaSignoffBy: "qa.lead@pharma.example",
        batchRecordComplete: false, // <-- incomplete
        deviationCount: 2,
        regulatoryRegion: "EU-EMA",
      },
    });
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      blocked(err.reason ?? err.message);
      console.log(`               evaluation_id: ${err.evaluationId}`);
      execute("batch NOT released — record must be completed before release");
    } else throw err;
  }

  // 3 -- DENY: missing QA dual-signoff (only one approver) ------------------
  scenario(
    3,
    "manufacturing.batch_record.release",
    "BLOCKED: only one QA approver — dual sign-off requires second signatory"
  );
  try {
    await atlasent.protect({
      agent: "qa.mgr@pharma.example",
      action: "manufacturing.batch_record.release",
      context: {
        batchId: "BATCH-2026-00149",
        productCode: "VIAL-API-50MG",
        lotNumber: "L26-04419",
        certifiedBy: "qa.mgr@pharma.example",
        // qaSignoffBy intentionally omitted — only one approver
        batchRecordComplete: true,
        deviationCount: 0,
        regulatoryRegion: "US-FDA",
      },
    });
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      blocked(err.reason ?? err.message);
      console.log(`               evaluation_id: ${err.evaluationId}`);
      execute("batch NOT released — second QA signatory required");
    } else throw err;
  }

  bar();
  console.log(`  Enforcement summary:`);
  console.log(`    BLOCKED  2 actions (incomplete record / missing dual approver)`);
  console.log(`    ALLOWED  1 action  (permit-verified before batch release)`);
  console.log();
}

run().catch((err) => {
  if (err instanceof AtlaSentError) {
    console.error(`AtlaSent unavailable (code=${err.code}): ${err.message}`);
    process.exit(2);
  }
  throw err;
});
