/**
 * gxp-quality-capa: GxP Quality CAPA Lifecycle Authorization Demo (TypeScript)
 *
 * Mirrors main.py — same 3 flows, same enforcement outcomes.
 *
 * Offline (mock server in another terminal):
 *   npx @atlasent/sdk mock
 *   ATLASENT_API_URL=http://127.0.0.1:4747 ATLASENT_API_KEY=mock npx tsx main.ts
 *
 * Live:
 *   ATLASENT_API_KEY=ask_live_... npx tsx main.ts
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
};

const execute = (msg: string) => console.log(`               → ${msg}`);

// ---------------------------------------------------------------------------
// Simulated CAPA system mutations
// Only reachable after protect() resolves.
// ---------------------------------------------------------------------------

const sysInitiateCapa = (capaId: string, initiatedBy: string, severity: string) =>
  execute(`CAPA ${capaId} created in QMS, status=OPEN, severity=${severity}`);

const sysAssignCapa = (capaId: string, assignedTo: string, dueDate: string) =>
  execute(`CAPA ${capaId} assigned to ${assignedTo}, due=${dueDate}, status=ASSIGNED`);

const sysProgressCapa = (capaId: string, percent: number) =>
  execute(`CAPA ${capaId} progress updated: ${percent}% complete`);

const sysEffectivenessCheck = (capaId: string, score: number) =>
  execute(`CAPA ${capaId} effectiveness check recorded: score=${score}`);

const sysCloseCapa = (capaId: string) =>
  execute(`CAPA ${capaId} set to CLOSED — no further modifications permitted`);

// ---------------------------------------------------------------------------
// Demo
// ---------------------------------------------------------------------------

async function run() {
  bar("gxp-quality-capa   CAPA Lifecycle Authorization Demo (TypeScript)");
  console.log(`  policy: fail-closed, dual-approver for closure, qa_manager for initiation`);

  // =========================================================================
  // Flow 1: Full happy-path CAPA from initiation to closure
  // =========================================================================
  bar("Flow 1 — Full happy-path CAPA lifecycle");
  const capaId = "CAPA-2026-00042";

  // 1a — initiate
  scenario("1a", "quality.capa.initiate", "ALLOWED: QA manager initiates CAPA");
  try {
    const p = await atlasent.protect({
      agent: "qa.mgr@pharma.example",
      action: "quality.capa.initiate",
      context: {
        capaId,
        initiatedBy: "qa.mgr@pharma.example",
        source: "deviation-report-DR-2026-0081",
        severity: "major",
        description: "Out-of-specification pH result in final product testing",
      },
    });
    permitLine(p);
    sysInitiateCapa(capaId, "qa.mgr@pharma.example", "major");
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) blocked(err.reason ?? err.message);
    else throw err;
  }

  // 1b — assign
  scenario("1b", "quality.capa.assign", "ALLOWED: QA manager assigns CAPA owner");
  try {
    const p = await atlasent.protect({
      agent: "qa.mgr@pharma.example",
      action: "quality.capa.assign",
      context: {
        capaId,
        assignedBy: "qa.mgr@pharma.example",
        assignedTo: "process.eng@pharma.example",
        dueDate: "2026-08-15",
      },
    });
    permitLine(p);
    sysAssignCapa(capaId, "process.eng@pharma.example", "2026-08-15");
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) blocked(err.reason ?? err.message);
    else throw err;
  }

  // 1c — progress
  scenario("1c", "quality.capa.progress", "ALLOWED: owner updates progress");
  try {
    const p = await atlasent.protect({
      agent: "process.eng@pharma.example",
      action: "quality.capa.progress",
      context: {
        capaId,
        updatedBy: "process.eng@pharma.example",
        progressNote: "Root cause identified: calibration drift in pH meter probe",
        percentComplete: 50,
      },
    });
    permitLine(p);
    sysProgressCapa(capaId, 50);
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) blocked(err.reason ?? err.message);
    else throw err;
  }

  // 1d — effectiveness check
  scenario(
    "1d",
    "quality.capa.effectiveness_check",
    "ALLOWED: QA manager performs 90-day effectiveness check"
  );
  try {
    const p = await atlasent.protect({
      agent: "qa.mgr@pharma.example",
      action: "quality.capa.effectiveness_check",
      context: {
        capaId,
        checkedBy: "qa.mgr@pharma.example",
        effectivenessScore: 0.92,
        evidenceUri: "s3://qms-evidence/capa-2026-00042/effectiveness-check.pdf",
      },
    });
    permitLine(p);
    sysEffectivenessCheck(capaId, 0.92);
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) blocked(err.reason ?? err.message);
    else throw err;
  }

  // 1e — close
  scenario("1e", "quality.capa.close", "ALLOWED: dual QA approval for CAPA closure");
  try {
    const p = await atlasent.protect({
      agent: "qa.mgr@pharma.example",
      action: "quality.capa.close",
      context: {
        capaId,
        closedBy: "qa.mgr@pharma.example",
        secondClosedBy: "qa.director@pharma.example",
        closureRationale: "Root cause corrected; effectiveness score 0.92 above threshold",
      },
    });
    permitLine(p);
    sysCloseCapa(capaId);
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) blocked(err.reason ?? err.message);
    else throw err;
  }

  // =========================================================================
  // Flow 2: Closure blocked — missing dual approval
  // =========================================================================
  bar("Flow 2 — Closure blocked: missing secondClosedBy");
  scenario(
    2,
    "quality.capa.close",
    "BLOCKED: secondClosedBy absent — dual approval required for CAPA closure"
  );
  try {
    await atlasent.protect({
      agent: "qa.mgr@pharma.example",
      action: "quality.capa.close",
      context: {
        capaId: "CAPA-2026-00043",
        closedBy: "qa.mgr@pharma.example",
        // secondClosedBy intentionally omitted
        closureRationale: "Trying to self-close without second approver",
      },
    });
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      blocked(err.reason ?? err.message);
      console.log(`               evaluation_id: ${err.evaluationId}`);
      execute("CAPA NOT closed — second authorized QA signatory required");
    } else throw err;
  }

  // =========================================================================
  // Flow 3: Effectiveness check denied — unauthorized reviewer
  // =========================================================================
  bar("Flow 3 — Effectiveness check denied: unauthorized reviewer");
  scenario(
    3,
    "quality.capa.effectiveness_check",
    "BLOCKED: reviewer does not have qa_manager role"
  );
  try {
    await atlasent.protect({
      agent: "lab.tech@pharma.example",
      action: "quality.capa.effectiveness_check",
      context: {
        capaId: "CAPA-2026-00044",
        checkedBy: "lab.tech@pharma.example", // not in QA_MANAGERS
        effectivenessScore: 0.85,
        evidenceUri: "s3://qms-evidence/capa-2026-00044/check.pdf",
      },
    });
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      blocked(err.reason ?? err.message);
      console.log(`               evaluation_id: ${err.evaluationId}`);
      execute("effectiveness check NOT recorded — qa_manager role required");
    } else throw err;
  }

  bar();
  console.log(`  Enforcement summary:`);
  console.log(`    BLOCKED  2 actions (missing dual approval / unauthorized reviewer)`);
  console.log(`    ALLOWED  5 actions (full happy-path CAPA lifecycle permit-verified)`);
  console.log();
}

run().catch((err) => {
  if (err instanceof AtlaSentError) {
    console.error(`AtlaSent unavailable (code=${err.code}): ${err.message}`);
    process.exit(2);
  }
  throw err;
});
