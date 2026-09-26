/**
 * gxp-fda-mdsap: MDSAP / ISO 13485 Medical Device QMS Authorization Demo (TypeScript)
 *
 * Mirrors main.py — same 4 scenarios, same enforcement outcomes.
 *
 * Offline (no API key needed):
 *   npx tsx main.ts
 *
 * Live:
 *   ATLASENT_API_KEY=ask_live_... npx tsx main.ts
 *
 * Regulatory references:
 *   ISO 13485:2016 §7.3.9  — Design changes
 *   ISO 13485:2016 §7.5.8  — Labelling
 *   ISO 13485:2016 §8.2.2  — Complaints
 *   ISO 13485:2016 §8.2.6  — Device acceptance / release
 *   21 CFR Part 820.80     — Receiving, in-process, and finished device acceptance
 *   21 CFR Part 820.198    — Complaint files
 *   MDSAP Audit Approach Version 2021.3 (IMDRF/MDSAP WG/N47)
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

const escalated = (reason: string) =>
  console.log(`  ⏸ ESCALATED  ${reason.replace(/\s*\[hold:[^\]]+\]/g, "")}`);

const permitLine = (p: Permit) => {
  console.log(`  ✔ PERMITTED  ${p.reason ?? ""}`);
  console.log(`               permit_id:   ${p.permitId}`);
  console.log(`               audit_hash:  ${p.auditHash ?? ""}`);
  console.log(`               permit_hash: ${p.permitHash ?? ""}`);
};

const execute = (msg: string) => console.log(`               → ${msg}`);

// ---------------------------------------------------------------------------
// Simulated QMS state mutations
// Only reachable after protect() resolves.
// ---------------------------------------------------------------------------

const sysComplaintOpen = (complaintId: string, role: string) => {
  execute(`Complaint ${complaintId} opened in CAPA-linked complaint file`);
  execute("Complaint record appended to audit trail (ISO 13485 §8.2.2)");
  execute(`Assigned to: ${role}, MDR reportability assessment initiated`);
};

const sysLabelApprove = (deviceId: string, labelVersion: string, role: string) => {
  execute(`Label v${labelVersion} for device ${deviceId} approved in DHF`);
  execute("Label approval signed in Document Management System");
  execute(`Approver: ${role} — ISO 13485 §7.5.8 / 21 CFR 820.120`);
};

// ---------------------------------------------------------------------------
// Demo
// ---------------------------------------------------------------------------

async function run() {
  bar("gxp-fda-mdsap   MDSAP / ISO 13485 Medical Device QMS Authorization Demo");
  console.log(`  regulation:  ISO 13485:2016 / MDSAP / 21 CFR Part 820`);
  console.log(`  policy pack: fda-mdsap (atlasent-gxp-starter/policies/)`);

  // 1 -- ALLOW: quality manager handles a device complaint ──────────────────
  scenario(
    1,
    "complaint.handle",
    "ALLOWED: quality manager opens complaint file — ISO 13485 §8.2.2"
  );
  try {
    const p = await atlasent.protect({
      agent: "qm.ross@meddevice.example",
      action: "complaint.handle",
      context: {
        role: "quality_manager",
        complaintId: "CMP-2026-0441",
        deviceId: "MDV-PUMP-001",
        complaintSource: "field_report",
        reportabilityStatus: "under_assessment",
        regulatoryRef: "ISO 13485 §8.2.2 / 21 CFR 820.198",
      },
    });
    permitLine(p);
    sysComplaintOpen("CMP-2026-0441", "quality_manager");
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      blocked(err.reason ?? "denied");
    } else throw err;
  }

  // 2 -- ALLOW: regulatory affairs approves device labelling ─────────────────
  scenario(
    2,
    "label.approve",
    "ALLOWED: regulatory affairs approves device label — ISO 13485 §7.5.8"
  );
  try {
    const p = await atlasent.protect({
      agent: "ra.patel@meddevice.example",
      action: "label.approve",
      context: {
        role: "regulatory_affairs",
        deviceId: "MDV-PUMP-001",
        labelVersion: "3.2.1",
        markets: ["FDA", "CE", "TGA"],
        dhfReference: "DHF-MDV-PUMP-001-REV3",
        regulatoryRef: "ISO 13485 §7.5.8 / 21 CFR 820.120",
      },
    });
    permitLine(p);
    sysLabelApprove("MDV-PUMP-001", "3.2.1", "regulatory_affairs");
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      blocked(err.reason ?? "denied");
    } else throw err;
  }

  // 3 -- ESCALATE: qualified person requests device release ──────────────────
  scenario(
    3,
    "device.release",
    "ESCALATED: QP requests device release — dual approval + DHR required"
  );
  try {
    const p = await atlasent.protect({
      agent: "qp.chen@meddevice.example",
      action: "device.release",
      context: {
        role: "qualified_person",
        deviceId: "MDV-PUMP-001",
        lotNumber: "LOT-2026-0881",
        dhrComplete: true,
        // secondApproverRole absent — triggers escalate
        regulatoryRef: "ISO 13485 §8.2.6 / 21 CFR 820.80",
      },
    });
    permitLine(p);
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      const reason = err.reason ?? "denied";
      if (reason.includes("ESCALATE")) {
        escalated(reason);
      } else {
        blocked(reason);
      }
      console.log(`               evaluation_id: ${err.evaluationId}`);
      execute("Device release HELD — second QP approval and DHR review required");
    } else throw err;
  }

  // 4 -- DENY: unauthorized operator attempts design change ──────────────────
  scenario(
    4,
    "design.change",
    "BLOCKED: production operator not authorized for design changes"
  );
  try {
    await atlasent.protect({
      agent: "op.jones@meddevice.example",
      action: "design.change",
      context: {
        role: "production_operator", // not in DESIGN_CHANGE_ROLES
        dcrId: "DCR-2026-0112",
        changeDescription: "Update catheter tip material spec",
        regulatoryRef: "ISO 13485 §7.3.9",
      },
    });
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      blocked(err.reason ?? "denied");
      console.log(`               evaluation_id: ${err.evaluationId}`);
      execute("Design change NOT initiated — route to Quality Manager for authorization");
    } else throw err;
  }

  bar();
  console.log("  Enforcement summary:");
  console.log("    BLOCKED   1 action  (unauthorized role — production operator on design.change)");
  console.log("    ESCALATED 1 action  (dual QP approval required for device.release)");
  console.log("    ALLOWED   2 actions (complaint.handle + label.approve — permit-verified)");
  console.log();
}

run().catch((err) => {
  if (err instanceof AtlaSentError) {
    console.error(`AtlaSent error: ${err.message}`);
  } else {
    console.error(err);
  }
  process.exit(1);
});
