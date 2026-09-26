/**
 * security-incident-response: Security Incident Escalation & Access Quarantine Demo
 *
 * Demonstrates non-bypassable authorization for critical security operations
 * using the AtlaSent SDK fail-closed enforcement model.
 *
 * Four scenarios:
 *   1. ALLOW  — critical incident, authorized SOC lead, all required fields present
 *   2. DENY   — missing incidentId field (TypeError before evaluate call)
 *   3. ALLOW  — access quarantine, authorized SOC lead, target identified
 *   4. DENY   — policy denies quarantine (missing quarantineReason field)
 *
 * Run:
 *   ATLASENT_API_KEY=ask_test_... npx tsx main.ts
 */

import atlasent, {
  AtlaSentDeniedError,
  AtlaSentError,
  type Permit,
} from "@atlasent/sdk";

// The SDK's built-in default base URL is the bare host; the AtlaSent API is
// served under /functions/v1, so set it explicitly.
atlasent.configure({ baseUrl: process.env.ATLASENT_API_URL ?? "https://api.atlasent.io/functions/v1" });

const WIDTH = 72;

function bar(title?: string): void {
  if (title) {
    console.log(`\n${"━".repeat(WIDTH)}`);
    console.log(`  ${title}`);
    console.log("━".repeat(WIDTH));
  } else {
    console.log(`  ${"─".repeat(WIDTH - 4)}`);
  }
}

function scenario(num: number | string, action: string, note: string): void {
  console.log(`\n▸ Scenario ${num} — ${action}`);
  console.log(`  ${note}`);
}

function permitted(permit: Permit): void {
  console.log(`  ✔ PERMITTED  escalation/quarantine authorized`);
  console.log(`               permit_id:   ${permit.permitId}`);
  console.log(`               audit_hash:  ${permit.auditHash}`);
  console.log(`               permit_hash: ${permit.permitHash}`);
}

function blocked(reason: string): void {
  console.log(`  ✗ BLOCKED    ${reason}`);
}

async function main(): Promise<void> {
  if (!process.env.ATLASENT_API_KEY) {
    console.error(
      "ATLASENT_API_KEY is not set. Export an ask_test_ or ask_live_ key first.",
    );
    process.exit(2);
  }

  bar("security-incident-response   Security Operations Authorization Demo");
  console.log("  mode:   live AtlaSent API");
  console.log("  actions: security.incident.escalate, security.access.quarantine");
  console.log("  policy:  fail-closed, machine_executable=false, 1h quorum window");

  // 1 ── ALLOW: critical incident escalation -----------------------------------
  scenario(
    1,
    "security.incident.escalate",
    "ALLOW: critical incident, authorized SOC lead",
  );
  try {
    const permit = await atlasent.protect({
      agent: "soc:lead-alice",
      action: "security.incident.escalate",
      context: {
        environment: "production",
        incidentId: "INC-2026-CRIT-001",
        severity: "critical",
        authorizedBy: "soc:lead-alice",
        affectedSystems: ["prod-api", "auth-service"],
        detectedAt: "2026-05-29T07:00:00Z",
        fail_closed: true,
      },
    });
    permitted(permit);
    console.log("               → incident escalation workflow triggered");
    console.log("               → SOC team notified via PagerDuty");
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      blocked(err.reason ?? "denied");
    } else if (err instanceof AtlaSentError) {
      console.error(`[transport] ${err.message}`);
    } else {
      throw err;
    }
  }

  // 2 ── DENY: missing incidentId (TypeError before evaluate) ------------------
  scenario(
    2,
    "security.incident.escalate",
    "BLOCKED: missing incidentId — TypeError thrown before evaluate call",
  );
  try {
    // @ts-expect-error intentionally omitting incidentId to demonstrate TypeError
    await atlasent.securityGate({
      severity: "high",
      authorizedBy: "soc:analyst-bob",
    });
  } catch (err) {
    if (err instanceof TypeError) {
      blocked(`TypeError: ${err.message}`);
      console.log("               evaluation_id: (none — blocked before HTTP call)");
      console.log("               → security action NOT executed");
    } else {
      throw err;
    }
  }

  // 3 ── ALLOW: access quarantine ---------------------------------------------
  scenario(
    3,
    "security.access.quarantine",
    "ALLOW: compromised principal, authorized SOC lead, quarantine reason provided",
  );
  try {
    const permit = await atlasent.protect({
      agent: "soc:lead-alice",
      action: "security.access.quarantine",
      context: {
        environment: "production",
        targetId: "user:compromised-carol",
        quarantineReason: "suspected credential compromise via spear phishing",
        authorizedBy: "soc:lead-alice",
        incidentReference: "INC-2026-CRIT-001",
        fail_closed: true,
      },
    });
    permitted(permit);
    console.log("               → all access for user:compromised-carol revoked");
    console.log("               → access revocation cascade initiated across IAM systems");
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      blocked(err.reason ?? "denied");
    } else if (err instanceof AtlaSentError) {
      console.error(`[transport] ${err.message}`);
    } else {
      throw err;
    }
  }

  // 4 ── DENY: policy denies (no quorum) --------------------------------------
  scenario(
    4,
    "security.access.quarantine",
    "BLOCKED: policy denies — security-approver quorum not satisfied",
  );
  try {
    const permit = await atlasent.protect({
      agent: "low-privilege-agent",
      action: "security.access.quarantine",
      context: {
        environment: "production",
        targetId: "user:some-target",
        quarantineReason: "low-privilege agent attempting quarantine",
        authorizedBy: "low-privilege-agent",
        fail_closed: true,
      },
    });
    // Unreachable on deny
    console.log(`BYPASS DETECTED: permit=${permit.permitId}`);
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      blocked(err.reason ?? "denied");
      console.log(`               evaluation_id: ${err.evaluationId}`);
      console.log("               → quarantine NOT executed — security authority required");
    } else if (err instanceof AtlaSentError) {
      console.error(`[transport] ${err.message}`);
    } else {
      throw err;
    }
  }

  bar();
  console.log("  Enforcement summary:");
  console.log("    BLOCKED  2 actions (TypeError / policy deny)");
  console.log("    ALLOWED  2 actions (permit-verified before security action execution)");
  console.log();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
