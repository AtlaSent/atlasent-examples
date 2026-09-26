/**
 * financial-period-certify: Financial Period Close Certification Authorization Demo
 *
 * Demonstrates non-bypassable authorization for financial period close
 * certification using the AtlaSent SDK fail-closed enforcement model.
 *
 * Three scenarios:
 *   1. ALLOW  — Q1 close, authorized financial controller, all required fields present
 *   2. DENY   — policy denies (unauthorized actor attempting close certification)
 *   3. DENY   — missing financialController (TypeError before evaluate call)
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
  console.log(`  ✔ PERMITTED  period close certification authorized`);
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

  bar("financial-period-certify   Financial Period Close Authorization Demo");
  console.log("  mode:   live AtlaSent API");
  console.log("  action: period.close.certify");
  console.log("  policy: fail-closed, machine_executable=false, simple_majority, 48h window");

  // 1 ── ALLOW: Q1 close, authorized financial controller ----------------------
  scenario(
    1,
    "period.close.certify",
    "ALLOW: Q1 2026 close, authorized financial controller, all fields present",
  );
  try {
    const permit = await atlasent.protect({
      agent: "controller:jane",
      action: "period.close.certify",
      context: {
        periodId: "2026-Q1",
        certifiedBy: "controller:jane",
        financialController: "fc:bob",
        reconciliationComplete: true,
        varianceResolved: true,
        fail_closed: true,
      },
    });
    permitted(permit);
    console.log("               → period 2026-Q1 status set to CLOSED in ERP");
    console.log("               → SOX evidence bundle generated and archived");
    console.log("               → audit chain sealed for Q1 2026");
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      blocked(err.reason ?? "denied");
    } else if (err instanceof AtlaSentError) {
      console.error(`[transport] ${err.message}`);
    } else {
      throw err;
    }
  }

  // 2 ── DENY: unauthorized actor ----------------------------------------------
  scenario(
    2,
    "period.close.certify",
    "BLOCKED: accounts-payable clerk — financial-controller authority required",
  );
  try {
    const permit = await atlasent.protect({
      agent: "ap-clerk:dave",
      action: "period.close.certify",
      context: {
        periodId: "2026-Q1",
        certifiedBy: "ap-clerk:dave",
        financialController: "ap-clerk:dave",
        fail_closed: true,
      },
    });
    // Unreachable on deny
    console.log(`BYPASS DETECTED: permit=${permit.permitId}`);
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      blocked(err.reason ?? "denied");
      console.log(`               evaluation_id: ${err.evaluationId}`);
      console.log("               → period close NOT executed — financial controller required");
    } else if (err instanceof AtlaSentError) {
      console.error(`[transport] ${err.message}`);
    } else {
      throw err;
    }
  }

  // 3 ── DENY: missing financialController (TypeError) -------------------------
  scenario(
    3,
    "period.close.certify",
    "BLOCKED: missing financialController — TypeError thrown before HTTP call",
  );
  try {
    const context = {
      periodId: "2026-Q2",
      certifiedBy: "controller:jane",
      // financialController intentionally omitted
    } as { periodId: string; certifiedBy: string; financialController: string };
    if (!context.financialController) {
      throw new TypeError("financialController is required to certify a period close");
    }
    await atlasent.protect({ agent: "controller:jane", action: "period.close.certify", context });
  } catch (err) {
    if (err instanceof TypeError) {
      blocked(`TypeError: ${err.message}`);
      console.log("               evaluation_id: (none — blocked before HTTP call)");
      console.log("               → period close NOT executed");
    } else {
      throw err;
    }
  }

  bar();
  console.log("  Enforcement summary:");
  console.log("    BLOCKED  2 actions (policy deny / TypeError)");
  console.log("    ALLOWED  1 action  (permit-verified before period close execution)");
  console.log();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
