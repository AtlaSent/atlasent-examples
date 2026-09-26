/**
 * atlasent-close-pilot: Accounting Close Authorization Demo (TypeScript)
 *
 * Mirrors main.py — same 9 scenarios, same enforcement outcomes.
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

const PERIOD = "Q1-2026";
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
// Simulated accounting system mutations
// Only reachable after protect() resolves.
// ---------------------------------------------------------------------------

const sysCompleteTask = (taskId: string, by: string) =>
  execute(`task ${taskId} marked COMPLETE (by ${by})`);

const sysCertifyRecon = (accountId: string, by: string) =>
  execute(`reconciliation for ${accountId} set to CERTIFIED by ${by}`);

const sysApproveJe = (jeId: string, amount: number) =>
  execute(`JE ${jeId} ($${amount.toLocaleString()}) moved to APPROVED state`);

const sysSubmitAdj = (adjId: string, by: string) =>
  execute(`adjustment ${adjId} submitted by ${by}`);

const sysClosePeriod = (period: string) =>
  execute(`period ${period} set to CLOSED -- no further postings accepted`);

// ---------------------------------------------------------------------------
// Demo
// ---------------------------------------------------------------------------

async function run() {
  bar("atlasent-close-pilot   Accounting Close Authorization Demo (TypeScript)");
  console.log(`  period: ${PERIOD}`);

  // 1 -- close_task.complete: BLOCKED (missing context) -------------------
  scenario(1, "close_task.complete", "BLOCKED: missing context fields");
  try {
    await atlasent.protect({
      agent: "close-automation",
      action: "close_task.complete",
      context: { source: "automated-close-bot" }, // task_id / completed_by / period absent
    });
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      blocked(err.reason ?? err.message);
      console.log(`               evaluation_id: ${err.evaluationId}`);
      execute("task NOT marked complete");
    } else throw err;
  }

  // 2 -- reconciliation.certify: ALLOWED ----------------------------------
  scenario(2, "reconciliation.certify", "ALLOWED: full context -> verified permit -> audit");
  try {
    const p = await atlasent.protect({
      agent: "alice.chen@acme.com",
      action: "reconciliation.certify",
      context: {
        account_id: "CASH-1000",
        certified_by: "alice.chen@acme.com",
        period: PERIOD,
        balance_difference: 0,
        dual_approval_required: false,
      },
    });
    permitLine(p);
    sysCertifyRecon("CASH-1000", "alice.chen@acme.com");
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) blocked(err.reason ?? err.message);
    else throw err;
  }

  // 3 -- journal_entry.approve: HOLD -> CFO approval -> ALLOWED -----------
  scenario(3, "journal_entry.approve", "HOLD: $250k > $100k limit -> CFO approval -> permit");
  const jeId = "JE-2026-4821";
  const amount = 250_000;
  const jeCtx = { je_id: jeId, amount, period: PERIOD };
  let holdKey3 = "";
  try {
    const p = await atlasent.protect({ agent: "controller-bot", action: "journal_entry.approve", context: jeCtx });
    permitLine(p);
    sysApproveJe(jeId, amount);
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      holdKey3 = parseHoldKey(err.reason ?? "");
      holdKey3 ? hold(err.reason ?? "", holdKey3) : blocked(err.reason ?? err.message);
    } else throw err;
  }

  if (holdKey3) {
    // In production: poll AtlaSent console or handle approval webhook (see erp-webhook.ts)
    console.log(`\n  [human] CFO reviews in AtlaSent console and approves`);
    console.log(`  [note]  retry protect() once hold_key='${holdKey3}' is approved`);
    console.log(`          see erp-webhook.ts for the approval -> retry pattern`);
  }

  // 4 -- adjustment.submit: BLOCKED (unauthorized submitter) --------------
  scenario(4, "adjustment.submit", "BLOCKED: dave.ops not on authorized submitter list");
  try {
    await atlasent.protect({
      agent: "dave.ops@acme.com",
      action: "adjustment.submit",
      context: { adjustment_id: "ADJ-2026-009", submitted_by: "dave.ops@acme.com", period: PERIOD, amount: 1500 },
    });
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      blocked(err.reason ?? err.message);
      execute("adjustment NOT submitted");
    } else throw err;
  }

  // 4b -- adjustment.submit: ALLOWED (authorized submitter) ---------------
  scenario("4b", "adjustment.submit", "ALLOWED: carol.jones is on authorized submitter list");
  try {
    const p = await atlasent.protect({
      agent: "carol.jones@acme.com",
      action: "adjustment.submit",
      context: { adjustment_id: "ADJ-2026-009", submitted_by: "carol.jones@acme.com", period: PERIOD, amount: 1500 },
    });
    permitLine(p);
    sysSubmitAdj("ADJ-2026-009", "carol.jones@acme.com");
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) blocked(err.reason ?? err.message);
    else throw err;
  }

  // 5 -- period.close: BLOCKED (outstanding tasks) ------------------------
  scenario(5, "period.close", "BLOCKED: 3 outstanding close tasks remain");
  try {
    await atlasent.protect({
      agent: "cfo-bot",
      action: "period.close",
      context: { period: PERIOD, all_tasks_complete: false, incomplete_task_count: 3 },
    });
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      blocked(err.reason ?? err.message);
      execute("period NOT closed");
    } else throw err;
  }

  // 5b -- period.close: HOLD -> CFO sign-off -> ALLOWED -------------------
  scenario("5b", "period.close", "HOLD: tasks done, missing CFO sign-off -> approval -> permit");
  const periodCtx = { period: PERIOD, all_tasks_complete: true };
  try {
    const p = await atlasent.protect({ agent: "cfo-bot", action: "period.close", context: periodCtx });
    permitLine(p);
    sysClosePeriod(PERIOD);
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      const hk = parseHoldKey(err.reason ?? "");
      hk ? hold(err.reason ?? "", hk) : blocked(err.reason ?? err.message);
      if (hk) {
        console.log(`\n  [human] CFO signs off in AtlaSent console`);
        console.log(`  [note]  retry protect() once hold_key='${hk}' is approved`);
      }
    } else throw err;
  }

  // 6 -- reconciliation.certify: BLOCKED (dual approval, missing second_approver) --
  scenario(6, "reconciliation.certify",
    "BLOCKED: dual_approval_required=true but second_approver not provided");
  try {
    await atlasent.protect({
      agent: "alice.chen@acme.com",
      action: "reconciliation.certify",
      context: {
        account_id: "AR-3000",
        certified_by: "alice.chen@acme.com",
        period: PERIOD,
        balance_difference: 0,
        dual_approval_required: true,
        // second_approver intentionally omitted
      },
    });
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      blocked(err.reason ?? err.message);
      execute("reconciliation NOT certified");
    } else throw err;
  }

  // 6b -- reconciliation.certify: ALLOWED (dual approval satisfied) -------
  scenario("6b", "reconciliation.certify",
    "ALLOWED: dual_approval_required=true with second_approver provided");
  try {
    const p = await atlasent.protect({
      agent: "alice.chen@acme.com",
      action: "reconciliation.certify",
      context: {
        account_id: "AR-3000",
        certified_by: "alice.chen@acme.com",
        period: PERIOD,
        balance_difference: 0,
        dual_approval_required: true,
        second_approver: "bob.smith@acme.com",
      },
    });
    permitLine(p);
    sysCertifyRecon("AR-3000", "alice.chen@acme.com");
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) blocked(err.reason ?? err.message);
    else throw err;
  }

  bar();
  console.log(`  Enforcement summary:`);
  console.log(`    BLOCKED  3 actions (missing context / unauthorized actor / missing dual approver)`);
  console.log(`    HOLD     2 actions (CFO approval required -- see erp-webhook.ts)`);
  console.log(`    ALLOWED  4 actions (permit-verified before execution)`);
  console.log();
}

run().catch((err) => {
  if (err instanceof AtlaSentError) {
    console.error(`AtlaSent unavailable (code=${err.code}): ${err.message}`);
    process.exit(2);
  }
  throw err;
});
