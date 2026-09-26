/**
 * gxp-hipaa-phi-access: HIPAA ePHI Access Authorization Demo (TypeScript)
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
 *   45 CFR 164.312(a) — Access controls
 *   45 CFR 164.312(b) — Audit controls
 *   45 CFR 164.312(c) — Integrity controls
 *   45 CFR 164.312(e) — Transmission security
 *   HITECH Act §13402  — Breach notification
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
// Simulated clinical system mutations
// Only reachable after protect() resolves.
// ---------------------------------------------------------------------------

const sysAccessPhi = (patientId: string, role: string, purpose: string) => {
  execute(`ePHI record for patient ${patientId} opened in audit-logged viewer`);
  execute("access event written to HIPAA audit log (45 CFR 164.312(b))");
  execute(`role: ${role}, purpose: ${purpose}`);
};

// ---------------------------------------------------------------------------
// Demo
// ---------------------------------------------------------------------------

async function run() {
  bar("gxp-hipaa-phi-access   HIPAA ePHI Access Authorization Demo (TypeScript)");
  console.log(`  regulation:  45 CFR Part 164 Subpart C — HIPAA Security Rule`);
  console.log(`  policy pack: hipaa-security (atlasent-gxp-starter/policies/)`);

  // 1 -- ALLOW: authorized clinician reads ePHI ─────────────────────────────
  scenario(
    1,
    "phi.access",
    "ALLOWED: authorized clinician with verified training, purpose documented"
  );
  try {
    const p = await atlasent.protect({
      agent: "dr.chen@hospital.example",
      action: "phi.access",
      context: {
        role: "clinician",
        patientId: "PT-20260011-882",
        accessPurpose: "clinical_treatment",
        hipaaTrainingCurrent: true,
        accessScope: "encounter_summary",
        regulatoryRef: "45 CFR 164.312(a)(1)",
      },
    });
    permitLine(p);
    sysAccessPhi("PT-20260011-882", "clinician", "clinical_treatment");
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      blocked(err.reason ?? "denied");
    } else throw err;
  }

  // 2 -- DENY: wrong role attempts ePHI export without dual-officer approval --
  scenario(
    2,
    "phi.export",
    "BLOCKED: 'data_analyst' role not authorized for ePHI export"
  );
  try {
    await atlasent.protect({
      agent: "analyst@hospital.example",
      action: "phi.export",
      context: {
        role: "data_analyst", // not in EXPORT_AUTHORIZED_ROLES
        patientId: "PT-20260011-882",
        exportFormat: "csv",
        encryptionVerified: true,
        regulatoryRef: "45 CFR 164.312(a)(2)(iv)",
      },
    });
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      blocked(err.reason ?? "denied");
      console.log(`               evaluation_id: ${err.evaluationId}`);
      execute("ePHI NOT exported — role authorization denied");
    } else throw err;
  }

  // 3 -- DENY: AI agent attempts phi.delete (machine_executable=false) ────────
  scenario(
    3,
    "phi.delete",
    "BLOCKED: AI agent cannot authorize ePHI deletion — machine_executable=false"
  );
  try {
    await atlasent.protect({
      agent: "ai-cleanup-agent@hospital.example",
      action: "phi.delete",
      context: {
        role: "privacy_officer",
        isAiAgent: true, // machine_executable=false blocks this
        patientId: "PT-20260011-882",
        deletionJustification: "retention_period_expired",
        regulatoryRef: "45 CFR 164.312(c)(1)",
      },
    });
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      blocked(err.reason ?? "denied");
      console.log(`               evaluation_id: ${err.evaluationId}`);
      execute("ePHI NOT deleted — human Privacy Officer authorization required");
    } else throw err;
  }

  // 4 -- ESCALATE: privacy officer requests ePHI export (dual approval) ───────
  scenario(
    4,
    "phi.export",
    "ESCALATED: Privacy Officer export request awaits dual officer sign-off"
  );
  try {
    const p = await atlasent.protect({
      agent: "privacy.officer@hospital.example",
      action: "phi.export",
      context: {
        role: "privacy_officer",
        patientId: "PT-20260011-882",
        exportFormat: "encrypted_pdf",
        exportRecipient: "state_health_dept",
        encryptionVerified: true,
        isAiAgent: false,
        // secondApproverRole absent — triggers escalate
        regulatoryRef: "45 CFR 164.312(a)(2)(iv) / 164.312(e)(1)",
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
      execute("ePHI export HELD — approval request queued for Security Officer review");
    } else throw err;
  }

  bar();
  console.log("  Enforcement summary:");
  console.log("    BLOCKED   2 actions (unauthorized role + AI agent machine_executable=false)");
  console.log("    ESCALATED 1 action  (dual officer approval required for ePHI export)");
  console.log("    ALLOWED   1 action  (permit-verified before ePHI access)");
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
