/**
 * reconciliation-certify: Reconciliation Certify Authorization Quickstart (TypeScript)
 *
 * Mirrors main.py — 3 scenarios:
 *   1. ALLOW           — authorized certifier, no dual-approval required
 *   2. HOLD_SECOND     — authorized certifier, balance diff > $10k threshold
 *   3. DENY_CERTIFIER  — certifier not in authorized-certifiers group
 *
 * Uses protectReconciliationCertify() from @atlasent/sdk (convenience wrapper
 * for the reconciliation.certify action).
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

const scenario = (num: number | string, note: string) => {
  console.log(`\n▸ Scenario ${num} — reconciliation.certify`);
  console.log(`  ${note}`);
};

const blocked = (reason: string) =>
  console.log(`  ✗ BLOCKED    ${reason.replace(/\s*\[hold:[^\]]+\]/g, "")}`);

const hold = (reason: string, holdKey: string) => {
  console.log(`  ⏸ HOLD       ${reason.replace(/\s*\[hold:[^\]]+\]/g, "")}`);
  console.log(`               hold_key: ${holdKey}`);
};

const permitLine = (p: Permit) => {
  console.log(`  ✔ PERMITTED  ${p.reason ?? ""}`);
  console.log(`               permit_id:   ${p.permitId}`);
  console.log(`               audit_hash:  ${p.auditHash ?? ""}`);
  console.log(`               permit_hash: ${p.permitHash ?? ""}`);
};

const execute = (msg: string) => console.log(`               → ${msg}`);

const parseHoldKey = (reason: string): string => {
  const m = reason.match(/\[hold:([^\]]+)\]/);
  return m ? m[1] : "";
};

// ---------------------------------------------------------------------------
// SDK convenience wrapper — protectReconciliationCertify()
//
// Wraps atlasent.protect() with the canonical reconciliation.certify
// action string and context shape.
// ---------------------------------------------------------------------------

interface ReconciliationContext {
  accountId: string;
  period: string;
  certifiedBy: string;
  balanceDifference: number;
  dualApprovalRequired: boolean;
  supportingEvidenceUri?: string;
  secondApprover?: string;
}

/**
 * SDK convenience method for reconciliation.certify.
 *
 * Equivalent to the protectCloseAction() call in accounting-close for
 * the reconciliation.certify action specifically.
 * Throws AtlaSentDeniedError on DENY or HOLD.
 */
async function protectReconciliationCertify(
  agent: string,
  ctx: ReconciliationContext,
): Promise<Permit> {
  return atlasent.protect({
    agent,
    action: "reconciliation.certify",
    context: {
      accountId: ctx.accountId,
      period: ctx.period,
      certifiedBy: ctx.certifiedBy,
      balanceDifference: ctx.balanceDifference,
      dualApprovalRequired: ctx.dualApprovalRequired,
      ...(ctx.supportingEvidenceUri ? { supportingEvidenceUri: ctx.supportingEvidenceUri } : {}),
      ...(ctx.secondApprover ? { secondApprover: ctx.secondApprover } : {}),
    },
  });
}

// ---------------------------------------------------------------------------
// Simulated close system mutations
// ---------------------------------------------------------------------------

const sysCertifyRecon = (accountId: string, by: string, period: string) =>
  execute(`reconciliation for ${accountId} (${period}) set to CERTIFIED by ${by}`);

// ---------------------------------------------------------------------------
// Demo
// ---------------------------------------------------------------------------

async function run() {
  bar("reconciliation-certify   Reconciliation Certify Authorization Quickstart (TypeScript)");

  // 1 -- ALLOW: authorized certifier, no dual-approval required ------------
  scenario(1, "ALLOW: authorized certifier, balance in tolerance, no dual-approval");
  try {
    const p = await protectReconciliationCertify("alice.chen@acme.com", {
      accountId: "CASH-1000",
      period: "Q1-2026",
      certifiedBy: "alice.chen@acme.com",
      balanceDifference: 0,
      dualApprovalRequired: false,
      supportingEvidenceUri: "s3://close-evidence/CASH-1000-Q1-2026.pdf",
    });
    permitLine(p);
    sysCertifyRecon("CASH-1000", "alice.chen@acme.com", "Q1-2026");
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) blocked(err.reason ?? err.message);
    else throw err;
  }

  // 2 -- HOLD_SECOND_APPROVER: balance diff > $10k threshold ---------------
  scenario(2, "HOLD_SECOND_APPROVER: balance difference $15,000 > $10,000 threshold");
  const reconCtx: ReconciliationContext = {
    accountId: "AR-3000",
    period: "Q1-2026",
    certifiedBy: "alice.chen@acme.com",
    balanceDifference: 15_000,
    dualApprovalRequired: true,
    supportingEvidenceUri: "s3://close-evidence/AR-3000-Q1-2026.pdf",
    // secondApprover intentionally omitted
  };
  let holdKey2 = "";
  try {
    const p = await protectReconciliationCertify("alice.chen@acme.com", reconCtx);
    permitLine(p);
    sysCertifyRecon("AR-3000", "alice.chen@acme.com", "Q1-2026");
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      holdKey2 = parseHoldKey(err.reason ?? "");
      holdKey2 ? hold(err.reason ?? "", holdKey2) : blocked(err.reason ?? err.message);
    } else throw err;
  }

  if (holdKey2) {
    console.log(`\n  [human] controller reviews in AtlaSent console and provides second approval`);
    console.log(`  [note]  retry protectReconciliationCertify() with secondApprover once approved`);
    console.log(`          see atlasent-examples/accounting-close/erp-webhook.ts for the pattern`);
  }

  // 3 -- DENY_CERTIFIER_NOT_AUTHORIZED: not in authorized-certifiers -------
  scenario(3, "DENY_CERTIFIER_NOT_AUTHORIZED: certifier not in authorized-certifiers group");
  try {
    await atlasent.protect({
      agent: "temp.worker@contractor.com",
      action: "reconciliation.certify",
      context: {
        accountId: "CASH-2000",
        period: "Q1-2026",
        certifiedBy: "temp.worker@contractor.com",
        balanceDifference: 0,
        dualApprovalRequired: false,
        supportingEvidenceUri: "s3://close-evidence/CASH-2000-Q1-2026.pdf",
      },
    });
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      blocked(err.reason ?? err.message);
      console.log(`               evaluation_id: ${err.evaluationId}`);
      execute("reconciliation NOT certified");
    } else throw err;
  }

  bar();
  console.log(`  Enforcement summary:`);
  console.log(`    ALLOWED  2 actions (direct allow + hold-then-approve)`);
  console.log(`    HOLD     1 action  (dual-approval required for $10k+ balance difference)`);
  console.log(`    BLOCKED  1 action  (certifier not in authorized-certifiers)`);
  console.log();
}

run().catch((err) => {
  if (err instanceof AtlaSentError) {
    console.error(`AtlaSent unavailable (code=${err.code}): ${err.message}`);
    process.exit(2);
  }
  throw err;
});
