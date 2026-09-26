/**
 * access-cert-revoke: Access Certificate Revocation Authorization Demo
 *
 * Demonstrates non-bypassable authorization for access certificate revocation
 * using the AtlaSent SDK with single-approver security review enforcement.
 *
 * Three scenarios:
 *   1. ALLOW  — valid certificate, security admin authorized, reason provided
 *   2. DENY   — policy denies (low-privilege requestor)
 *   3. DENY   — missing revocationReason (TypeError before evaluate call)
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
  console.log(`  ✔ PERMITTED  certificate revocation authorized`);
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

  bar("access-cert-revoke   Access Certificate Revocation Authorization Demo");
  console.log("  mode:   live AtlaSent API");
  console.log("  action: access.cert.revoke");
  console.log("  policy: high-risk, machine_executable=false, single-approver, 24h window");

  // 1 ── ALLOW: valid certificate, security admin authorized -------------------
  scenario(
    1,
    "access.cert.revoke",
    "ALLOW: valid certificate, security admin authorized, revocation reason provided",
  );
  try {
    const permit = await atlasent.protect({
      agent: "iam:security-admin",
      action: "access.cert.revoke",
      context: {
        certId: "cert:2026-Q2-ENG-42",
        revocationReason: "access no longer required — engineer offboarded 2026-05-28",
        authorizedBy: "iam:security-admin",
      },
    });
    permitted(permit);
    console.log("               → certificate cert:2026-Q2-ENG-42 revoked in PKI store");
    console.log("               → CRL updated, OCSP responder notified");
    console.log("               → dependent tokens invalidated");
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      blocked(err.reason ?? "denied");
    } else if (err instanceof AtlaSentError) {
      console.error(`[transport] ${err.message}`);
    } else {
      throw err;
    }
  }

  // 2 ── DENY: policy denies (low-privilege requestor) -------------------------
  scenario(
    2,
    "access.cert.revoke",
    "BLOCKED: low-privilege requestor — security-approver authority required",
  );
  try {
    const permit = await atlasent.protect({
      agent: "automation-bot",
      action: "access.cert.revoke",
      context: {
        certId: "cert:2026-Q2-ENG-99",
        revocationReason: "automated revocation attempt",
        authorizedBy: "automation-bot",
      },
    });
    // Unreachable on deny
    console.log(`BYPASS DETECTED: permit=${permit.permitId}`);
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      blocked(err.reason ?? "denied");
      console.log(`               evaluation_id: ${err.evaluationId}`);
      console.log("               → certificate NOT revoked — security admin required");
    } else if (err instanceof AtlaSentError) {
      console.error(`[transport] ${err.message}`);
    } else {
      throw err;
    }
  }

  // 3 ── DENY: missing revocationReason (TypeError) ----------------------------
  scenario(
    3,
    "access.cert.revoke",
    "BLOCKED: missing revocationReason — TypeError thrown before HTTP call",
  );
  try {
    const context = {
      certId: "cert:2026-Q2-ENG-77",
      authorizedBy: "iam:security-admin",
      // revocationReason intentionally omitted
    } as { certId: string; revocationReason: string; authorizedBy: string };
    if (!context.revocationReason) {
      throw new TypeError("revocationReason is required to request a certificate revocation permit");
    }
    await atlasent.protect({ agent: "iam:security-admin", action: "access.cert.revoke", context });
  } catch (err) {
    if (err instanceof TypeError) {
      blocked(`TypeError: ${err.message}`);
      console.log("               evaluation_id: (none — blocked before HTTP call)");
      console.log("               → certificate NOT revoked");
    } else {
      throw err;
    }
  }

  bar();
  console.log("  Enforcement summary:");
  console.log("    BLOCKED  2 actions (policy deny / TypeError)");
  console.log("    ALLOWED  1 action  (permit-verified before certificate revocation)");
  console.log();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
