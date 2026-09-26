/**
 * payment-operations: Payment Lifecycle Authorization Demo (TypeScript)
 *
 * Mirrors main.py — same 3 flows, same enforcement outcomes.
 * This example mirrors a production ledger implementation
 * where these actions are already in production use.
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
// Simulated payment system mutations
// Only reachable after protect() resolves.
// ---------------------------------------------------------------------------

const sysApprovePayment = (paymentId: string, amount: number, invoiceId: string) =>
  execute(`payment ${paymentId} ($${amount.toLocaleString()}) status → APPROVED (invoice=${invoiceId})`);

const sysDenyPayment = (paymentId: string, reason: string) =>
  execute(`payment ${paymentId} status → DENIED: ${reason.slice(0, 60)}`);

const sysExecutePayment = (paymentId: string, bankRef: string) => {
  execute(`payment ${paymentId} status → EXECUTED (bank_ref=${bankRef})`);
  execute("wire transfer initiated in banking system");
};

const sysHoldPayment = (paymentId: string, holdReason: string) => {
  execute(`payment ${paymentId} status → HELD: ${holdReason.slice(0, 60)}`);
  execute("compliance review ticket created, payment escalated");
};

const sysApproveQb = (transactionId: string, amount: number, account: string) =>
  execute(`QB transaction ${transactionId} ($${amount.toLocaleString()}) → APPROVED → ${account}`);

// ---------------------------------------------------------------------------
// Demo
// ---------------------------------------------------------------------------

async function run() {
  bar("payment-operations   Payment Lifecycle Authorization Demo (TypeScript)");
  console.log(
    "  Note: mirrors a production ledger implementation"
  );

  // =========================================================================
  // Flow 1: Full approved → executed flow
  // =========================================================================
  bar("Flow 1 — Full approved → executed payment flow");
  const paymentId1 = "PMT-2026-00881";

  scenario("1a", "payment.approval.approve", "ALLOWED: AP manager approves invoice payment");
  try {
    const p = await atlasent.protect({
      agent: "ap.mgr@acme.example",
      action: "payment.approval.approve",
      context: {
        paymentId: paymentId1,
        amount: 18750,
        approvedBy: "ap.mgr@acme.example",
        invoiceId: "INV-2026-4420",
        vendorId: "VND-00142",
      },
    });
    permitLine(p);
    sysApprovePayment(paymentId1, 18750, "INV-2026-4420");
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) blocked(err.reason ?? err.message);
    else throw err;
  }

  scenario("1b", "qb.transaction.approve", "ALLOWED: AP manager approves QB transaction");
  try {
    const p = await atlasent.protect({
      agent: "ap.mgr@acme.example",
      action: "qb.transaction.approve",
      context: {
        transactionId: "QB-2026-99104",
        amount: 18750,
        accountCode: "2000-ACCOUNTS-PAYABLE",
        approvedBy: "ap.mgr@acme.example",
      },
    });
    permitLine(p);
    sysApproveQb("QB-2026-99104", 18750, "2000-ACCOUNTS-PAYABLE");
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) blocked(err.reason ?? err.message);
    else throw err;
  }

  scenario("1c", "payment.execute.approved", "ALLOWED: treasury executes the approved payment");
  try {
    const p = await atlasent.protect({
      agent: "treasury.ops@acme.example",
      action: "payment.execute.approved",
      context: {
        paymentId: paymentId1,
        executedBy: "treasury.ops@acme.example",
        bankReference: "WIRE-20260529-00142",
      },
    });
    permitLine(p);
    sysExecutePayment(paymentId1, "WIRE-20260529-00142");
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) blocked(err.reason ?? err.message);
    else throw err;
  }

  // =========================================================================
  // Flow 2: Approved → held for fraud review
  // =========================================================================
  bar("Flow 2 — Approved → held for fraud review");
  const paymentId2 = "PMT-2026-00882";

  scenario(
    "2a",
    "payment.approval.approve",
    "ALLOWED: AP manager approves payment (later flagged by fraud system)"
  );
  try {
    const p = await atlasent.protect({
      agent: "ap.mgr@acme.example",
      action: "payment.approval.approve",
      context: {
        paymentId: paymentId2,
        amount: 47200,
        approvedBy: "ap.mgr@acme.example",
        invoiceId: "INV-2026-4421",
        vendorId: "VND-00889",
      },
    });
    permitLine(p);
    sysApprovePayment(paymentId2, 47200, "INV-2026-4421");
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) blocked(err.reason ?? err.message);
    else throw err;
  }

  scenario(
    "2b",
    "payment.execute.held",
    "ALLOWED: fraud system places payment on hold for compliance review"
  );
  try {
    const p = await atlasent.protect({
      agent: "fraud-compliance-system",
      action: "payment.execute.held",
      context: {
        paymentId: paymentId2,
        heldBy: "fraud-compliance-system",
        holdReason: "vendor VND-00889 added to watchlist 2026-05-28",
      },
    });
    permitLine(p);
    sysHoldPayment(paymentId2, "vendor VND-00889 added to watchlist 2026-05-28");
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) blocked(err.reason ?? err.message);
    else throw err;
  }

  // =========================================================================
  // Flow 3: policy_error on execution attempt
  // =========================================================================
  bar("Flow 3 — policy_error blocks execution attempt");

  scenario(
    3,
    "payment.execute.policy_error",
    "BLOCKED: execution blocked by policy violation (policy_error is terminal)"
  );
  try {
    await atlasent.protect({
      agent: "treasury.ops@acme.example",
      action: "payment.execute.policy_error",
      context: {
        paymentId: "PMT-2026-00883",
        policyRule: "DUPLICATE_PAYMENT_DETECTED",
        errorCode: "ERR-PAY-4001",
      },
    });
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      blocked(err.reason ?? err.message);
      console.log(`               evaluation_id: ${err.evaluationId}`);
      execute("payment NOT executed — policy_error is a terminal blocking state");
    } else throw err;
  }

  bar();
  console.log(`  Enforcement summary:`);
  console.log(`    BLOCKED  1 action  (policy_error terminal state)`);
  console.log(`    ALLOWED  5 actions (permit-verified before each state transition)`);
  console.log();
}

run().catch((err) => {
  if (err instanceof AtlaSentError) {
    console.error(`AtlaSent unavailable (code=${err.code}): ${err.message}`);
    process.exit(2);
  }
  throw err;
});
