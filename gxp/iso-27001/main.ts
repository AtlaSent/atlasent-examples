/**
 * gxp-iso-27001: ISO/IEC 27001:2022 ISMS Authorization Demo (TypeScript)
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
 *   ISO 27001:2022 A.5.15 — Access control
 *   ISO 27001:2022 A.5.18 — Access rights
 *   ISO 27001:2022 A.8.2  — Privileged access rights
 *   ISO 27001:2022 A.8.8  — Management of technical vulnerabilities
 *   ISO 27001:2022 A.8.15 — Logging
 *   ISO 27001:2022 A.8.20 — Networks security
 *   ISO/IEC 27002:2022    — Implementation guidance
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
// Simulated ISMS state mutations
// Only reachable after protect() resolves.
// ---------------------------------------------------------------------------

const sysGrantAccess = (resource: string, subject: string, role: string) => {
  execute(`Access provisioned: ${subject} → ${resource}`);
  execute("Access grant logged to ISMS audit trail (ISO 27001 A.8.15)");
  execute(`Authorizing role: ${role}, least-privilege review complete`);
};

const sysApplyPatch = (cveId: string, system: string, role: string) => {
  execute(`Patch for ${cveId} applied to ${system}`);
  execute("Patch record written to change log (ISO 27001 A.8.8)");
  execute(`Applied by: ${role}, CAB approval and staging test on record`);
};

// ---------------------------------------------------------------------------
// Demo
// ---------------------------------------------------------------------------

async function run() {
  bar("gxp-iso-27001   ISO/IEC 27001:2022 ISMS Authorization Demo");
  console.log(`  regulation:  ISO/IEC 27001:2022 + ISO/IEC 27002:2022`);
  console.log(`  policy pack: iso-27001 (atlasent-gxp-starter/policies/)`);

  // 1 -- ALLOW: security manager grants access ───────────────────────────────
  scenario(
    1,
    "access.grant",
    "ALLOWED: security manager provisions access — ISO 27001 A.5.15"
  );
  try {
    const p = await atlasent.protect({
      agent: "sm.rivera@corp.example",
      action: "access.grant",
      context: {
        role: "security_manager",
        subjectId: "emp-20260441",
        targetResource: "data-warehouse/finance-reports",
        accessLevel: "read_only",
        businessJustification: "quarterly_close_review",
        reviewedByDataOwner: true,
        regulatoryRef: "ISO 27001:2022 A.5.15 / A.5.18",
      },
    });
    permitLine(p);
    sysGrantAccess("data-warehouse/finance-reports", "emp-20260441", "security_manager");
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      blocked(err.reason ?? "denied");
    } else throw err;
  }

  // 2 -- ALLOW: IT administrator patches a vulnerability ─────────────────────
  scenario(
    2,
    "vulnerability.patch",
    "ALLOWED: IT administrator applies CAB-approved CVE patch — ISO 27001 A.8.8"
  );
  try {
    const p = await atlasent.protect({
      agent: "admin.kim@corp.example",
      action: "vulnerability.patch",
      context: {
        role: "it_administrator",
        cveId: "CVE-2026-12801",
        targetSystem: "prod-api-cluster-03",
        severity: "high",
        cabApproved: true,
        stagingTested: true,
        maintenanceWindow: "2026-06-13T02:00Z",
        regulatoryRef: "ISO 27001:2022 A.8.8",
      },
    });
    permitLine(p);
    sysApplyPatch("CVE-2026-12801", "prod-api-cluster-03", "it_administrator");
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      blocked(err.reason ?? "denied");
    } else throw err;
  }

  // 3 -- ESCALATE: network engineer changes firewall rule ────────────────────
  scenario(
    3,
    "firewall.rule_change",
    "ESCALATED: firewall change requires dual approval + CISO review — ISO 27001 A.8.20"
  );
  try {
    const p = await atlasent.protect({
      agent: "net.okafor@corp.example",
      action: "firewall.rule_change",
      context: {
        role: "network_engineer",
        firewallId: "fw-dmz-prod-01",
        ruleDescription: "Allow inbound 443 from partner CIDR 203.0.113.0/24",
        securityImpactAssessment: true,
        // secondApproverRole absent — triggers escalate
        cabTicket: "CAB-2026-0881",
        regulatoryRef: "ISO 27001:2022 A.8.20",
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
      execute("Firewall rule change HELD — CAB dual-approval and CISO sign-off required");
    } else throw err;
  }

  // 4 -- DENY: unauthorized developer attempts privileged access ─────────────
  scenario(
    4,
    "privileged.access",
    "BLOCKED: developer role not authorized for privileged access — ISO 27001 A.8.2"
  );
  try {
    await atlasent.protect({
      agent: "dev.santos@corp.example",
      action: "privileged.access",
      context: {
        role: "developer", // not in PRIVILEGED_ROLES
        targetSystem: "prod-db-primary",
        accessReason: "urgent_debugging",
        regulatoryRef: "ISO 27001:2022 A.8.2",
      },
    });
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      blocked(err.reason ?? "denied");
      console.log(`               evaluation_id: ${err.evaluationId}`);
      execute("Privileged access NOT granted — route to CISO for break-glass authorization");
    } else throw err;
  }

  bar();
  console.log("  Enforcement summary:");
  console.log("    BLOCKED   1 action  (unauthorized role — developer on privileged.access)");
  console.log("    ESCALATED 1 action  (dual approval + CISO review for firewall.rule_change)");
  console.log("    ALLOWED   2 actions (access.grant + vulnerability.patch — permit-verified)");
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
