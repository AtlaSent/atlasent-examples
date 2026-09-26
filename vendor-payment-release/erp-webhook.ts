/**
 * erp-webhook.ts — NetSuite Invoice/Payment → AtlaSent integration pattern
 *
 * This file is a STUB demonstrating the ERP connector pattern.
 * The NetSuite API is not called — sample webhook payloads are hardcoded
 * to match the NetSuite webhook shape. Replace the stubs with real NetSuite
 * API calls in a production integration.
 *
 * Integration pattern:
 *   1. NetSuite fires Invoice.approve or Payment.release webhook
 *   2. This handler normalizes the event into AtlaSent's action vocabulary
 *   3. atlasent.protect() is called — fail-closed enforcement
 *   4. On ALLOW: permit issued → execute ERP mutation → consume permit
 *   5. On DENY/HOLD: payment blocked; hold queued for AP manager review
 *
 * Action vocabulary mapping:
 *   NetSuite Invoice.approve  → vendor.payment.release (pending AP cert step)
 *   NetSuite Payment.release  → vendor.payment.release (final payment run)
 *
 * Usage (stub mode — no live NetSuite or AtlaSent connection):
 *   npx tsx erp-webhook.ts
 */
import { createHmac, timingSafeEqual } from "node:crypto";
import { createServer, IncomingMessage, ServerResponse } from "node:http";
import atlasent, { AtlaSentDeniedError, AtlaSentError } from "@atlasent/sdk";

// The SDK's built-in default base URL is the bare host; the AtlaSent API is
// served under /functions/v1, so set it explicitly.
atlasent.configure({ baseUrl: process.env.ATLASENT_API_URL ?? "https://api.atlasent.io/functions/v1" });

// ---------------------------------------------------------------------------
// Webhook signature verification (same pattern as accounting-close/erp-webhook.ts)
// ---------------------------------------------------------------------------

const WEBHOOK_SECRET = process.env.ATLASENT_WEBHOOK_SECRET ?? "";
const NETSUITE_WEBHOOK_SECRET = process.env.NETSUITE_WEBHOOK_SECRET ?? "";
const SIGNATURE_TOLERANCE_SECONDS = 5 * 60;

function verifyAtlaSentSignature(req: IncomingMessage, rawBody: string): void {
  if (!WEBHOOK_SECRET) return; // skip in stub mode
  const sigHeader = req.headers["atlasent-signature"];
  if (!sigHeader || typeof sigHeader !== "string") {
    throw new Error("Missing AtlaSent-Signature header");
  }
  const parts: Record<string, string> = {};
  for (const part of sigHeader.split(",")) {
    const eq = part.indexOf("=");
    if (eq !== -1) parts[part.slice(0, eq).trim()] = part.slice(eq + 1).trim();
  }
  const { t: ts, v1: receivedSig } = parts;
  if (!ts || !receivedSig) throw new Error("Malformed AtlaSent-Signature header");
  const eventAge = Math.floor(Date.now() / 1000) - Number(ts);
  if (isNaN(eventAge) || eventAge > SIGNATURE_TOLERANCE_SECONDS) {
    throw new Error(`Webhook replay: event is ${eventAge}s old`);
  }
  const expected = createHmac("sha256", WEBHOOK_SECRET)
    .update(`${ts}.${rawBody}`)
    .digest("hex");
  const expectedBuf = Buffer.from(expected, "utf8");
  const receivedBuf = Buffer.from(receivedSig, "utf8");
  if (expectedBuf.length !== receivedBuf.length || !timingSafeEqual(expectedBuf, receivedBuf)) {
    throw new Error("AtlaSent-Signature HMAC mismatch");
  }
}

// ---------------------------------------------------------------------------
// NetSuite webhook payload shapes (hardcoded sample payloads)
// ---------------------------------------------------------------------------

/**
 * NetSuite Invoice.approve webhook payload shape.
 * Real NetSuite webhooks arrive at the Suitelet or REST Webhook configured
 * in Setup > Integration > Webhooks.
 */
interface NetSuiteInvoiceApprovePayload {
  eventType: "Invoice.approve";
  recordType: "invoice";
  recordId: string;
  changeType: "create" | "edit";
  fields: {
    entity: string;       // vendor internal ID
    tranid: string;       // transaction ID (PO reference)
    amount: number;
    currency: string;     // currency symbol: "USD", "EUR", etc.
    approvedby: string;   // employee email who triggered the approval
    memo?: string;
  };
  timestamp: string;      // ISO-8601
}

/**
 * NetSuite Payment.release webhook payload shape.
 * Fires when a payment batch is released for EFT/ACH processing.
 */
interface NetSuitePaymentReleasePayload {
  eventType: "Payment.release";
  recordType: "vendorpayment";
  recordId: string;
  changeType: "edit";
  fields: {
    entity: string;       // vendor internal ID
    tranid: string;       // payment transaction ID
    amount: number;
    currency: string;
    relatedPo: string;    // linked PO number
    account: string;      // ledger account
    approvedby: string;
    secondApprover?: string;
    memo?: string;
  };
  timestamp: string;
}

// ---------------------------------------------------------------------------
// Sample hardcoded NetSuite webhook payloads (stub — not live NetSuite events)
// ---------------------------------------------------------------------------

const SAMPLE_INVOICE_APPROVE: NetSuiteInvoiceApprovePayload = {
  eventType: "Invoice.approve",
  recordType: "invoice",
  recordId: "INV-2026-8821",
  changeType: "edit",
  fields: {
    entity: "VENDOR-0042",
    tranid: "PO-2026-1234",
    amount: 12500.00,
    currency: "USD",
    approvedby: "ap.alice@acme.com",
    memo: "Q1 software license renewal",
  },
  timestamp: new Date().toISOString(),
};

const SAMPLE_PAYMENT_RELEASE: NetSuitePaymentReleasePayload = {
  eventType: "Payment.release",
  recordType: "vendorpayment",
  recordId: "PMT-2026-0099",
  changeType: "edit",
  fields: {
    entity: "VENDOR-0099",
    tranid: "PMT-2026-0099",
    amount: 75000.00,
    currency: "USD",
    relatedPo: "PO-2026-5678",
    account: "AP-TRADE",
    approvedby: "ap.bob@acme.com",
    secondApprover: "ap.carol@acme.com",
    memo: "Annual services contract payment",
  },
  timestamp: new Date().toISOString(),
};

// ---------------------------------------------------------------------------
// Normalization: NetSuite event → AtlaSent action context
// ---------------------------------------------------------------------------

interface AtlaSentPaymentContext {
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
 * Normalize a NetSuite Invoice.approve event to AtlaSent's vendor.payment.release context.
 */
function normalizeInvoiceApprove(payload: NetSuiteInvoiceApprovePayload): {
  agent: string;
  context: AtlaSentPaymentContext;
} {
  return {
    agent: payload.fields.approvedby,
    context: {
      amount: payload.fields.amount,
      currency: payload.fields.currency,
      vendorId: payload.fields.entity,
      authorizedBy: payload.fields.approvedby,
      purchaseOrder: payload.fields.tranid,
      threeWayMatch: true, // NetSuite invoice approval implies 3-way match completed
      ledgerAccount: "AP-TRADE",
    },
  };
}

/**
 * Normalize a NetSuite Payment.release event to AtlaSent's vendor.payment.release context.
 */
function normalizePaymentRelease(payload: NetSuitePaymentReleasePayload): {
  agent: string;
  context: AtlaSentPaymentContext;
} {
  return {
    agent: payload.fields.approvedby,
    context: {
      amount: payload.fields.amount,
      currency: payload.fields.currency,
      vendorId: payload.fields.entity,
      authorizedBy: payload.fields.approvedby,
      purchaseOrder: payload.fields.relatedPo,
      threeWayMatch: true,
      ledgerAccount: payload.fields.account,
      ...(payload.fields.secondApprover ? { secondApprover: payload.fields.secondApprover } : {}),
    },
  };
}

// ---------------------------------------------------------------------------
// Pending hold registry (same pattern as accounting-close/erp-webhook.ts)
// ---------------------------------------------------------------------------

interface PendingHold {
  agent: string;
  action: string;
  context: AtlaSentPaymentContext;
  holdKey: string;
  requestedAt: string;
}

const pendingHolds = new Map<string, PendingHold>();

export function registerHold(holdKey: string, hold: Omit<PendingHold, "holdKey" | "requestedAt">) {
  pendingHolds.set(holdKey, { ...hold, holdKey, requestedAt: new Date().toISOString() });
}

// ---------------------------------------------------------------------------
// AtlaSent hold.approved webhook handler
// ---------------------------------------------------------------------------

interface HoldApprovedPayload {
  event: "hold.approved";
  hold_key: string;
  approved_by: string;
  approved_at: string;
  permit_token?: string;
}

async function handleHoldApproved(payload: HoldApprovedPayload): Promise<void> {
  const { hold_key, approved_by, approved_at } = payload;
  console.log(`[webhook] hold approved: key=${hold_key} by=${approved_by} at=${approved_at}`);

  const pending = pendingHolds.get(hold_key);
  if (!pending) {
    console.warn(`[webhook] unknown hold_key=${hold_key} — ignoring`);
    return;
  }

  try {
    const permit = await atlasent.protect({
      agent: pending.agent,
      action: pending.action,
      context: { environment: "production", ...pending.context, approved_by, approved_at },
    });
    console.log(`[webhook] permit issued: id=${permit.permitId} hash=${permit.auditHash}`);
    pendingHolds.delete(hold_key);
    await executeErpAction(pending.action, pending.context, permit.permitId);
    console.log(`[webhook] ERP action executed under permit ${permit.permitId}`);
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      console.error(`[webhook] still denied after approval: ${err.reason} (id=${err.evaluationId})`);
    } else if (err instanceof AtlaSentError) {
      console.error(`[webhook] AtlaSent unavailable (code=${err.code}): ${err.message}`);
      throw err; // return 500 so AtlaSent retries
    } else {
      throw err;
    }
  }
}

// ---------------------------------------------------------------------------
// ERP action dispatcher (stub — replace with real NetSuite API calls)
// ---------------------------------------------------------------------------

async function executeErpAction(
  action: string,
  context: AtlaSentPaymentContext,
  permitId: string,
): Promise<void> {
  console.log(`[action] executing ${action} under permit ${permitId}`);
  // In production: call NetSuite payment API
  // e.g. await netSuiteClient.vendorPayments.release(context.purchaseOrder, permitId);
  console.log(`[action] payment of ${context.currency} ${context.amount.toLocaleString()} to ${context.vendorId} released`);
}

// ---------------------------------------------------------------------------
// NetSuite webhook handler — receives Invoice.approve and Payment.release events
// ---------------------------------------------------------------------------

async function handleNetSuiteWebhook(
  payload: NetSuiteInvoiceApprovePayload | NetSuitePaymentReleasePayload,
): Promise<void> {
  console.log(`[netsuite] received ${payload.eventType} for record ${payload.recordId}`);

  let normalized: { agent: string; context: AtlaSentPaymentContext };

  if (payload.eventType === "Invoice.approve") {
    normalized = normalizeInvoiceApprove(payload as NetSuiteInvoiceApprovePayload);
  } else if (payload.eventType === "Payment.release") {
    normalized = normalizePaymentRelease(payload as NetSuitePaymentReleasePayload);
  } else {
    console.warn(`[netsuite] unhandled event type: ${(payload as { eventType: string }).eventType}`);
    return;
  }

  try {
    const permit = await atlasent.protect({
      agent: normalized.agent,
      action: "vendor.payment.release",
      context: { environment: "production", ...normalized.context },
    });
    console.log(`[atlasent] ALLOW permit=${permit.permitId}`);
    await executeErpAction("vendor.payment.release", normalized.context, permit.permitId);
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      const holdMatch = (err.reason ?? "").match(/\[hold:([^\]]+)\]/);
      if (holdMatch) {
        const holdKey = holdMatch[1];
        registerHold(holdKey, {
          agent: normalized.agent,
          action: "vendor.payment.release",
          context: normalized.context,
        });
        console.log(`[atlasent] HOLD key=${holdKey} — queued for AP manager review`);
      } else {
        console.error(`[atlasent] DENY reason=${err.reason} evaluation_id=${err.evaluationId}`);
        // In production: surface denial to AP queue / NetSuite SuiteFlow
      }
    } else if (err instanceof AtlaSentError) {
      console.error(`[atlasent] unavailable (code=${err.code}): ${err.message}`);
      throw err;
    } else {
      throw err;
    }
  }
}

// ---------------------------------------------------------------------------
// Stub demo: process the hardcoded sample payloads
// ---------------------------------------------------------------------------

async function runStubDemo(): Promise<void> {
  console.log("=== erp-webhook.ts stub demo ===");
  console.log("Processing hardcoded NetSuite sample payloads (no live API calls)\n");

  console.log("--- Sample 1: Invoice.approve ($12,500) ---");
  await handleNetSuiteWebhook(SAMPLE_INVOICE_APPROVE);

  console.log("\n--- Sample 2: Payment.release ($75,000 with dual approval) ---");
  await handleNetSuiteWebhook(SAMPLE_PAYMENT_RELEASE);

  console.log("\nStub demo complete.");
  console.log("To run as a live webhook server: set ATLASENT_API_KEY and start the HTTP server.");
}

// ---------------------------------------------------------------------------
// HTTP server (only starts when ATLASENT_API_KEY is set)
// ---------------------------------------------------------------------------

function readBody(req: IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    let body = "";
    req.on("data", (chunk) => (body += chunk));
    req.on("end", () => resolve(body));
    req.on("error", reject);
  });
}

async function startServer(): Promise<void> {
  const server = createServer(async (req: IncomingMessage, res: ServerResponse) => {
    if (req.method !== "POST") { res.writeHead(405).end(); return; }

    const rawBody = await readBody(req);

    if (req.url === "/netsuite/webhook") {
      // NetSuite webhook — NETSUITE_WEBHOOK_SECRET verification would go here
      let payload: NetSuiteInvoiceApprovePayload | NetSuitePaymentReleasePayload;
      try { payload = JSON.parse(rawBody); } catch { res.writeHead(400).end("bad json"); return; }
      try {
        await handleNetSuiteWebhook(payload);
        res.writeHead(200).end("ok");
      } catch { res.writeHead(500).end("error"); }
      return;
    }

    if (req.url === "/atlasent/webhook") {
      // AtlaSent hold.approved callback
      try { verifyAtlaSentSignature(req, rawBody); } catch (e) {
        res.writeHead(401).end("unauthorized"); return;
      }
      let payload: HoldApprovedPayload;
      try { payload = JSON.parse(rawBody); } catch { res.writeHead(400).end("bad json"); return; }
      if (payload.event !== "hold.approved") { res.writeHead(200).end("ignored"); return; }
      try { await handleHoldApproved(payload); res.writeHead(200).end("ok"); }
      catch { res.writeHead(500).end("error"); }
      return;
    }

    res.writeHead(404).end();
  });

  const PORT = Number(process.env.PORT ?? 3002);
  server.listen(PORT, () => {
    console.log(`[webhook] listening on :${PORT}`);
    console.log(`  POST /netsuite/webhook  — receive NetSuite Invoice.approve / Payment.release`);
    console.log(`  POST /atlasent/webhook  — receive AtlaSent hold.approved callbacks`);
  });
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

if (process.env.ATLASENT_API_KEY) {
  startServer().catch(console.error);
} else {
  runStubDemo().catch(console.error);
}
