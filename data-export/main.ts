/**
 * data-export: Customer Data Export Authorization Quickstart (TypeScript)
 *
 * Mirrors main.py — 3 scenarios:
 *   1. Approved       — PII dataset to verified destination    → ALLOW
 *   2. Denied dest    — PII to unverified destination          → DENY_DESTINATION_UNVERIFIED
 *   3. Row-level mix  — mixed PII/non-PII batch, partial allow
 *
 * Uses protectDataExport() convenience wrapper and batch evaluation loop
 * with SHA-256 bundle sealing.
 *
 * Offline (mock server in another terminal):
 *   npx @atlasent/sdk mock
 *   ATLASENT_API_URL=http://127.0.0.1:4747 ATLASENT_API_KEY=mock npx tsx main.ts
 *
 * Live:
 *   ATLASENT_API_KEY=ask_live_... npx tsx main.ts
 */
import { createHash } from "node:crypto";
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

const scenario = (num: number | string, note: string) => {
  console.log(`\n▸ Scenario ${num} — customer.data.export`);
  console.log(`  ${note}`);
};

const blocked = (reason: string) => console.log(`  ✗ BLOCKED    ${reason}`);
const permitLine = (p: Permit) => {
  console.log(`  ✔ PERMITTED  ${p.reason ?? ""}`);
  console.log(`               permit_id: ${p.permitId}`);
};
const execute = (msg: string) => console.log(`               → ${msg}`);

// ---------------------------------------------------------------------------
// Export context type
// ---------------------------------------------------------------------------

interface ExportContext {
  datasetId: string;
  containsPii: boolean;
  destination: string;
  purpose: string;
  rowsRequested: number;
  requestedBy: string;
}

// ---------------------------------------------------------------------------
// SDK convenience wrapper — protectDataExport()
//
// Normalizes the export context and calls atlasent.protect() with the
// canonical customer.data.export action string.
// ---------------------------------------------------------------------------

async function protectDataExport(agent: string, ctx: ExportContext): Promise<Permit> {
  return atlasent.protect({
    agent,
    action: "customer.data.export",
    context: {
      datasetId: ctx.datasetId,
      containsPii: ctx.containsPii,
      destination: ctx.destination,
      purpose: ctx.purpose,
      rowsRequested: ctx.rowsRequested,
      requestedBy: ctx.requestedBy,
    },
  });
}

// ---------------------------------------------------------------------------
// Batch evaluation with SHA-256 bundle sealing
// ---------------------------------------------------------------------------

interface BatchRow extends ExportContext {
  rowId: string;
}

interface AllowedRow {
  rowId: string;
  permitId: string;
  auditHash?: string;
}

interface DeniedRow {
  rowId: string;
  decisionCode: string;
  evaluationId?: string;
}

/**
 * Evaluate a batch of rows, collecting allowed and denied rows.
 * Returns an export bundle sealed with SHA-256 over the allowed permits.
 */
async function batchAuthorize(
  rows: BatchRow[],
  agent: string,
): Promise<{
  allowed: AllowedRow[];
  denied: DeniedRow[];
  bundleHash: string;
}> {
  const allowed: AllowedRow[] = [];
  const denied: DeniedRow[] = [];

  // Evaluate rows sequentially (switch to Promise.all for production parallelism)
  for (const row of rows) {
    try {
      const p = await protectDataExport(agent, row);
      allowed.push({ rowId: row.rowId, permitId: p.permitId, auditHash: p.auditHash ?? undefined });
    } catch (err) {
      if (err instanceof AtlaSentDeniedError) {
        const reason = err.reason ?? "denied";
        const decisionCode = reason.includes(":") ? reason.split(":")[0].trim() : "DENY";
        denied.push({ rowId: row.rowId, decisionCode, evaluationId: err.evaluationId ?? undefined });
      } else throw err;
    }
  }

  // Seal the allowed-permits bundle with SHA-256
  const bundleBody = JSON.stringify(
    {
      createdAt: new Date().toISOString(),
      agent,
      allowedRows: allowed,
      permitCount: allowed.length,
    },
    null,
    2,
  );
  const bundleHash = createHash("sha256").update(bundleBody, "utf8").digest("hex");

  return { allowed, denied, bundleHash };
}

// ---------------------------------------------------------------------------
// Demo
// ---------------------------------------------------------------------------

async function run() {
  bar("data-export   Customer Data Export Authorization Quickstart (TypeScript)");

  // 1 -- Approved: PII to verified destination, valid purpose → ALLOW ------
  scenario(1, "ALLOW: PII dataset to verified destination with valid purpose");
  try {
    const p = await protectDataExport("analyst.alice@acme.com", {
      datasetId: "CRM-CUSTOMERS-Q1",
      containsPii: true,
      destination: "snowflake://acme/analytics",
      purpose: "Q1-churn-analysis",
      rowsRequested: 5_000,
      requestedBy: "analyst.alice@acme.com",
    });
    permitLine(p);
    execute("wrote 5,000 rows to snowflake://acme/analytics");
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) blocked(err.reason ?? err.message);
    else throw err;
  }

  // 2 -- Denied destination: PII to unverified destination -----------------
  scenario(2, "DENY_DESTINATION_UNVERIFIED: PII dataset to unverified destination");
  try {
    await atlasent.protect({
      agent: "analyst.bob@acme.com",
      action: "customer.data.export",
      context: {
        datasetId: "CRM-CUSTOMERS-Q1",
        containsPii: true,
        destination: "s3://personal-bucket-bob",
        purpose: "personal-analysis",
        rowsRequested: 500,
        requestedBy: "analyst.bob@acme.com",
      },
    });
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      blocked(err.reason ?? err.message);
      console.log(`               evaluation_id: ${err.evaluationId}`);
      execute("export NOT written");
    } else throw err;
  }

  // 3 -- Row-level batch: mixed PII/non-PII --------------------------------
  scenario(3, "Row-level partial: mixed PII/non-PII — non-PII approved, PII to unverified denied");

  const batchRows: BatchRow[] = [
    {
      rowId: "R001",
      datasetId: "EVENTS-ANON",
      containsPii: false,
      destination: "s3://personal-bucket-bob",   // unverified but non-PII → allowed
      purpose: "ad-hoc-analysis",
      rowsRequested: 1,
      requestedBy: "pipeline-bot@acme.com",
    },
    {
      rowId: "R002",
      datasetId: "EVENTS-ANON",
      containsPii: false,
      destination: "s3://personal-bucket-bob",
      purpose: "ad-hoc-analysis",
      rowsRequested: 1,
      requestedBy: "pipeline-bot@acme.com",
    },
    {
      rowId: "R003",
      datasetId: "CRM-SEGMENT-B",
      containsPii: true,
      destination: "s3://personal-bucket-bob",   // PII + unverified → denied
      purpose: "ad-hoc-analysis",
      rowsRequested: 1,
      requestedBy: "pipeline-bot@acme.com",
    },
    {
      rowId: "R004",
      datasetId: "CRM-SEGMENT-B",
      containsPii: true,
      destination: "s3://personal-bucket-bob",
      purpose: "ad-hoc-analysis",
      rowsRequested: 1,
      requestedBy: "pipeline-bot@acme.com",
    },
    {
      rowId: "R005",
      datasetId: "CRM-SEGMENT-C",
      containsPii: true,
      destination: "snowflake://acme/analytics", // PII + verified → allowed
      purpose: "monthly-retention-report",
      rowsRequested: 1,
      requestedBy: "pipeline-bot@acme.com",
    },
  ];

  const { allowed, denied, bundleHash } = await batchAuthorize(batchRows, "pipeline-bot@acme.com");

  for (const r of allowed) {
    console.log(`  ✔  ${r.rowId}  ALLOW   permit=${r.permitId}`);
  }
  for (const r of denied) {
    console.log(`  ✗  ${r.rowId}  DENY    ${r.decisionCode}`);
  }

  console.log();
  console.log(`  batch result: ${allowed.length} allowed / ${denied.length} denied`);
  console.log(`  bundle SHA-256: ${bundleHash.slice(0, 32)}...`);

  bar();
  console.log(`  Enforcement summary:`);
  console.log(`    ALLOWED  dataset export + 3 row-level exports`);
  console.log(`    BLOCKED  PII to unverified destination (2 rows + 1 dataset)`);
  console.log();
}

run().catch((err) => {
  if (err instanceof AtlaSentError) {
    console.error(`AtlaSent unavailable (code=${err.code}): ${err.message}`);
    process.exit(2);
  }
  throw err;
});
