/**
 * vendor-payment-release: Vendor Payment Release Authorization Quickstart (TypeScript)
 *
 * Mirrors main.py — 3 scenarios:
 *   1. Auto-approve  — $12,500, authorized AP certifier        → ALLOW
 *   2. Dual-approval — $75,000, no second approver             → HOLD_DUAL_APPROVAL
 *   3. Deny unauthorized — submitter not in ap-certifiers      → DENY_AUTHORITY
 *
 * Shows both the SDK convenience method `protectPaymentRelease()` and
 * the raw `atlasent.protect()` path.
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
  console.log(`\n▸ Scenario ${num} — vendor.payment.release`);
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
// SDK convenience wrapper — protectPaymentRelease()
//
// This thin wrapper normalises the vendor payment context and calls
// atlasent.protect() with the canonical action string.
// Use this in your AP automation code instead of calling protect() directly.
// ---------------------------------------------------------------------------

interface PaymentContext {
  amount: number;
  currency: string;
  vendorId: string;
  authorizedBy: string;
  purchaseOrder: string;
  threeWayMatch: boolean;
  ledgerAccount: string;
  secondApprover?: string;
}

/**
 * SDK convenience method for vendor.payment.release.
 *
 * Wraps atlasent.protect() with the canonical action string and context shape.
 * Throws AtlaSentDeniedError on DENY or HOLD (same as protect()).
 */
async function protectPaymentRelease(agent: string, ctx: PaymentContext): Promise<Permit> {
  return atlasent.protect({
    agent,
    action: "vendor.payment.release",
    context: {
      amount: ctx.amount,
      currency: ctx.currency,
      vendorId: ctx.vendorId,
      authorizedBy: ctx.authorizedBy,
      purchaseOrder: ctx.purchaseOrder,
      threeWayMatch: ctx.threeWayMatch,
      ledgerAccount: ctx.ledgerAccount,
      ...(ctx.secondApprover ? { secondApprover: ctx.secondApprover } : {}),
    },
  });
}

// ---------------------------------------------------------------------------
// Simulated ERP state mutations
// ---------------------------------------------------------------------------

const sysReleasePayment = (vendorId: string, amount: number, currency: string) =>
  execute(`payment of ${currency} ${amount.toLocaleString()} to ${vendorId} queued for release`);

// ---------------------------------------------------------------------------
// Demo
// ---------------------------------------------------------------------------

async function run() {
  bar("vendor-payment-release   Vendor Payment Release Authorization Quickstart (TypeScript)");

  // 1 -- Auto-approve: $12,500, authorized AP certifier → ALLOW -------------
  scenario(1, "ALLOW: $12,500 below dual-approval threshold, authorized AP certifier");

  // Using SDK convenience method protectPaymentRelease():
  try {
    const p = await protectPaymentRelease("ap.alice@acme.com", {
      amount: 12_500,
      currency: "USD",
      vendorId: "VENDOR-0042",
      authorizedBy: "ap.alice@acme.com",
      purchaseOrder: "PO-2026-1234",
      threeWayMatch: true,
      ledgerAccount: "AP-TRADE",
    });
    permitLine(p);
    sysReleasePayment("VENDOR-0042", 12_500, "USD");
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) blocked(err.reason ?? err.message);
    else throw err;
  }

  // 2 -- Dual-approval hold: $75,000, no second approver → HOLD_DUAL_APPROVAL
  scenario(2, "HOLD_DUAL_APPROVAL: $75,000 exceeds $50k threshold, no second approver");

  // Using raw atlasent.protect() path — identical to the convenience wrapper above:
  const paymentCtx = {
    amount: 75_000,
    currency: "USD",
    vendorId: "VENDOR-0099",
    authorizedBy: "ap.bob@acme.com",
    purchaseOrder: "PO-2026-5678",
    threeWayMatch: true,
    ledgerAccount: "AP-TRADE",
    // secondApprover intentionally omitted
  };
  let holdKey2 = "";
  try {
    const p = await atlasent.protect({
      agent: "ap.bob@acme.com",
      action: "vendor.payment.release",
      context: paymentCtx,
    });
    permitLine(p);
    sysReleasePayment("VENDOR-0099", 75_000, "USD");
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      holdKey2 = parseHoldKey(err.reason ?? "");
      holdKey2 ? hold(err.reason ?? "", holdKey2) : blocked(err.reason ?? err.message);
    } else throw err;
  }

  if (holdKey2) {
    console.log(`\n  [human] AP manager reviews in AtlaSent console and approves`);
    console.log(`  [note]  retry protectPaymentRelease() with secondApprover once approved`);
    console.log(`          see erp-webhook.ts for the approval → retry pattern`);
  }

  // 3 -- Deny unauthorized: submitter not in ap-certifiers → DENY_AUTHORITY --
  scenario(3, "DENY_AUTHORITY: submitter not in authorized ap-certifiers group");
  try {
    await atlasent.protect({
      agent: "contractor.x@external.com",
      action: "vendor.payment.release",
      context: {
        amount: 5_000,
        currency: "USD",
        vendorId: "VENDOR-0010",
        authorizedBy: "contractor.x@external.com",
        purchaseOrder: "PO-2026-0001",
        threeWayMatch: false,
        ledgerAccount: "AP-TRADE",
      },
    });
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      blocked(err.reason ?? err.message);
      console.log(`               evaluation_id: ${err.evaluationId}`);
      execute("payment NOT released");
    } else throw err;
  }

  bar();
  console.log(`  Enforcement summary:`);
  console.log(`    ALLOWED  1 action  (auto-approved below threshold)`);
  console.log(`    HOLD     1 action  (dual-approval required for $50k+)`);
  console.log(`    BLOCKED  1 action  (unauthorized submitter)`);
  console.log();
}

run().catch((err) => {
  if (err instanceof AtlaSentError) {
    console.error(`AtlaSent unavailable (code=${err.code}): ${err.message}`);
    process.exit(2);
  }
  throw err;
});
