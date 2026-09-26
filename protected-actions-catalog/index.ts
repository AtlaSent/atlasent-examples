/**
 * AtlaSent protected actions catalog — runnable example.
 *
 * Wires the five canonical protected actions end to end through
 *   evaluate -> permit -> verify -> execute -> audit
 *
 * The protected mutation for each action is only reachable when
 * atlasent.protect(...) returns a verified Permit. On any non-allow
 * decision or any failed verify, AtlaSentDeniedError is raised and
 * the mutation never runs.
 *
 * Run:
 *   ATLASENT_API_KEY=ask_test_... npx tsx index.ts
 */

import atlasent, {
  AtlaSentDeniedError,
  AtlaSentError,
  type Permit,
  type ProtectRequest,
} from "@atlasent/sdk";

// The SDK's built-in default base URL is the bare host; the AtlaSent API is
// served under /functions/v1, so set it explicitly.
atlasent.configure({ baseUrl: process.env.ATLASENT_API_URL ?? "https://api.atlasent.io/functions/v1" });

// ── Operational visibility ─────────────────────────────────────────
// A single structured log line per protected call site, carrying the
// six fields described in atlasent-docs/architecture/operational-visibility.md.

function emitAuditLine(args: {
  action: string;
  actorId: string;
  resourceId: string;
  decision: "allow" | "deny" | "hold" | "escalate";
  outcome: "verified" | "blocked";
  permit?: Permit;
  reason?: string;
}) {
  const line = {
    "atlasent.action": args.action,
    "atlasent.actor_id": args.actorId,
    "atlasent.resource_id": args.resourceId,
    "atlasent.decision": args.decision,
    "atlasent.outcome": args.outcome,
    "atlasent.evaluation_id": args.permit?.permitId,
    "atlasent.permit_id": args.permit?.permitId,
    "atlasent.audit_hash": args.permit?.auditHash,
    "atlasent.reason": args.reason,
  };
  console.log(JSON.stringify(line));
}

// ── The catalog binding ────────────────────────────────────────────
// One helper that captures the non-bypassable rule for every entry:
// the mutation is a function passed by reference; it only runs when
// protect() returns a verified permit. There is no branch in this
// helper that can execute the mutation on deny / hold / escalate /
// failed verify.

interface CatalogEntry {
  action: string;
  actorId: string;
  resourceId: string;
  context: ProtectRequest["context"];
  execute: (permit: Permit) => Promise<void> | void;
}

async function runProtected(entry: CatalogEntry): Promise<void> {
  try {
    const permit = await atlasent.protect({
      agent: entry.actorId,
      action: entry.action,
      context: { resource_id: entry.resourceId, ...entry.context },
    });

    await entry.execute(permit);

    emitAuditLine({
      action: entry.action,
      actorId: entry.actorId,
      resourceId: entry.resourceId,
      decision: "allow",
      outcome: "verified",
      permit,
    });
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      emitAuditLine({
        action: entry.action,
        actorId: entry.actorId,
        resourceId: entry.resourceId,
        decision: err.decision,
        outcome: "blocked",
        reason: err.reason,
      });
      return;
    }
    if (err instanceof AtlaSentError) {
      console.error(`[transport] ${entry.action}: ${err.message}`);
      return;
    }
    throw err;
  }
}

// ── 1. production.deploy ───────────────────────────────────────────

async function deployCheckoutApi(permit: Permit) {
  console.log(`[executed] production.deploy permit=${permit.permitId}`);
  // In production: await deployer.release({ service, ref, sha });
}

// ── 2. vendor.payment.release ──────────────────────────────────────

async function releaseVendorPayment(permit: Permit) {
  console.log(`[executed] vendor.payment.release permit=${permit.permitId}`);
  // In production: await ap.releasePayment("pmt_01HZ...");
}

// ── 3. customer.data.export ────────────────────────────────────────

async function exportCustomerData(permit: Permit) {
  console.log(`[executed] customer.data.export permit=${permit.permitId}`);
  // In production: await exporter.run({ dataset, destination, ... });
}

// ── 4. reconciliation.certify ──────────────────────────────────────

async function certifyReconciliation(permit: Permit) {
  console.log(`[executed] reconciliation.certify permit=${permit.permitId}`);
  // In production: await closeBook.certify({ period, account, permit });
}

// ── 5. model.agent.execute_tool ────────────────────────────────────

async function executeAgentTool(permit: Permit) {
  console.log(`[executed] model.agent.execute_tool permit=${permit.permitId}`);
  // In production: await toolRegistry.invoke(toolName, toolArgs, permit);
}

// ── Catalog ────────────────────────────────────────────────────────

const catalog: CatalogEntry[] = [
  {
    action: "production.deploy",
    actorId: "github-actions:alice",
    resourceId: "checkout-api@9f1a",
    context: {
      service: "checkout-api",
      environment: "production",
      ref: "refs/heads/main",
      sha: "9f1adeadbeef",
      change_ticket: "CHG-2026-0418",
    },
    execute: deployCheckoutApi,
  },
  {
    action: "vendor.payment.release",
    actorId: "user:ap_clerk_jane",
    resourceId: "pmt_01HZABCDEF",
    context: {
      vendor_id: "vnd_aero_supplies",
      amount_cents: 1_850_000,
      currency: "USD",
      ledger_account: "2100.accounts-payable",
      purchase_order: "PO-2026-7711",
      three_way_match: true,
      second_approver: "user:controller_kim",
    },
    execute: releaseVendorPayment,
  },
  {
    action: "customer.data.export",
    actorId: "user:analyst_dan",
    resourceId: "customers.v1@2026-05-19",
    context: {
      dataset: "customers.v1",
      rows_requested: 47213,
      destination: "s3://acme-exports/2026-05-19/",
      format: "ndjson",
      encryption: "aws-kms:alias/acme-exports",
      purpose: "quarterly-marketing-cohort",
      dpa_reference: "DPA-2025-EU-014",
      contains_pii: true,
      row_cap: 50000,
    },
    execute: exportCustomerData,
  },
  {
    action: "reconciliation.certify",
    actorId: "user:controller_kim",
    resourceId: "recon_2026-04_1000_usd",
    context: {
      period: "2026-04",
      account: "1000.cash.operating-usd",
      variance_cents: 0,
      dual_approval_required: true,
      second_approver: "user:cfo_lee",
      supporting_evidence_uri:
        "atlasent://evidence/2026-04/recon_1000_usd.json",
    },
    execute: certifyReconciliation,
  },
  {
    action: "model.agent.execute_tool",
    actorId: "agent:incident-responder-v3",
    resourceId: "github.repos.delete:acme/billing-archive",
    context: {
      tool_name: "github.repos.delete",
      tool_arguments: { owner: "acme", repo: "billing-archive" },
      tool_irreversible: true,
      tool_blast_radius: "shared_infrastructure",
      session_id: "sess_01HZSESSION",
      human_in_the_loop: true,
      model: "claude-opus-4-7",
      task_origin: "ops-runbook:cleanup-archives",
    },
    execute: executeAgentTool,
  },
];

async function main() {
  if (!process.env.ATLASENT_API_KEY) {
    console.error(
      "ATLASENT_API_KEY is not set. Export an ask_test_ or ask_live_ key first.",
    );
    process.exit(2);
  }

  console.log("AtlaSent — protected actions catalog\n");
  for (const entry of catalog) {
    await runProtected(entry);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
