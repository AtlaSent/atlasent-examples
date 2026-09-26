/**
 * erp-webhook.ts
 *
 * ERP backend endpoint that closes the hold -> approval -> execution loop.
 *
 * Flow:
 *   1. controller-bot calls protect() -> AtlaSentDeniedError with [hold:key]
 *   2. ERP UI surfaces the hold; CFO approves in AtlaSent console
 *   3. AtlaSent console fires a webhook to this endpoint
 *   4. Handler retries protect() -> permit issued -> action executes
 *   5. Webhook responds 200; AtlaSent marks the hold fulfilled
 *
 * This is a conceptual sketch (plain Node.js http module, no framework
 * dependency). Drop the handler into Express / Fastify / Next.js API
 * routes as needed.
 *
 * Usage:
 *   ATLASENT_API_KEY=ask_live_... ATLASENT_WEBHOOK_SECRET=whsec_... npx tsx erp-webhook.ts
 */
import { createHmac, timingSafeEqual } from "node:crypto";
import { createServer, IncomingMessage, ServerResponse } from "node:http";
import atlasent, { AtlaSentDeniedError, AtlaSentError } from "@atlasent/sdk";

// The SDK's built-in default base URL is the bare host; the AtlaSent API is
// served under /functions/v1, so set it explicitly.
atlasent.configure({ baseUrl: process.env.ATLASENT_API_URL ?? "https://api.atlasent.io/functions/v1" });

// ---------------------------------------------------------------------------
// Webhook signature verification
// ---------------------------------------------------------------------------

const WEBHOOK_SECRET = process.env.ATLASENT_WEBHOOK_SECRET ?? "";
const SIGNATURE_TOLERANCE_SECONDS = 5 * 60; // 5 minutes

/**
 * Verifies the AtlaSent-Signature header before processing any webhook.
 *
 * Header format:  AtlaSent-Signature: t=<unix_ts>,v1=<hmac_hex>
 * HMAC input:     "<unix_ts>.<raw_body>"
 * Algorithm:      HMAC-SHA256 keyed with ATLASENT_WEBHOOK_SECRET
 *
 * Throws on any verification failure — caller must return 401.
 */
function verifySignature(req: IncomingMessage, rawBody: string): void {
  if (!WEBHOOK_SECRET) {
    throw new Error("ATLASENT_WEBHOOK_SECRET is not set — cannot verify webhook signatures");
  }
  const sigHeader = req.headers["atlasent-signature"];
  if (!sigHeader || typeof sigHeader !== "string") {
    throw new Error("Missing AtlaSent-Signature header");
  }

  // Parse t=<ts>,v1=<hex> pairs
  const parts: Record<string, string> = {};
  for (const part of sigHeader.split(",")) {
    const eq = part.indexOf("=");
    if (eq !== -1) parts[part.slice(0, eq).trim()] = part.slice(eq + 1).trim();
  }
  const { t: ts, v1: receivedSig } = parts;
  if (!ts || !receivedSig) {
    throw new Error("Malformed AtlaSent-Signature header");
  }

  // Replay protection: reject events older than 5 minutes
  const eventAge = Math.floor(Date.now() / 1000) - Number(ts);
  if (isNaN(eventAge) || eventAge > SIGNATURE_TOLERANCE_SECONDS) {
    throw new Error(
      `Webhook replay detected: event is ${eventAge}s old (max ${SIGNATURE_TOLERANCE_SECONDS}s)`,
    );
  }

  // Timing-safe HMAC comparison
  const expected = createHmac("sha256", WEBHOOK_SECRET)
    .update(`${ts}.${rawBody}`)
    .digest("hex");

  const expectedBuf = Buffer.from(expected, "utf8");
  const receivedBuf = Buffer.from(receivedSig, "utf8");
  if (
    expectedBuf.length !== receivedBuf.length ||
    !timingSafeEqual(expectedBuf, receivedBuf)
  ) {
    throw new Error("AtlaSent-Signature verification failed — HMAC mismatch");
  }
}

// ---------------------------------------------------------------------------
// Pending hold registry
//
// In production: replace with a DB table or Redis key-value store so
// pending holds survive process restarts.
// ---------------------------------------------------------------------------

interface PendingHold {
  agent: string;
  action: string;
  context: Record<string, unknown>;
  holdKey: string;
  requestedAt: string;
}

const pendingHolds = new Map<string, PendingHold>();

/** Call this before the first protect() attempt to register the hold context. */
export function registerHold(holdKey: string, hold: Omit<PendingHold, "holdKey" | "requestedAt">) {
  pendingHolds.set(holdKey, {
    ...hold,
    holdKey,
    requestedAt: new Date().toISOString(),
  });
}

// ---------------------------------------------------------------------------
// Approval webhook handler
// ---------------------------------------------------------------------------

/**
 * AtlaSent POSTs this payload when a held action is approved:
 *
 *   {
 *     event:    "hold.approved",
 *     hold_key: "je_cfo:JE-2026-4821",
 *     approved_by: "sarah.lee@acme.com",
 *     approved_at: "2026-04-29T18:42:00Z",
 *     permit_token: "pt_..."
 *   }
 */
interface HoldApprovedPayload {
  event: string;
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

  // Retry protect() now that the approval is on file in AtlaSent
  try {
    const permit = await atlasent.protect({
      agent: pending.agent,
      action: pending.action,
      context: { ...pending.context, approved_by, approved_at },
    });

    console.log(`[webhook] permit issued: id=${permit.permitId} hash=${permit.auditHash}`);
    pendingHolds.delete(hold_key);

    // Execute the accounting action
    await executeAccountingAction(pending.action, pending.context, permit.permitId);
    console.log(`[webhook] action executed under permit ${permit.permitId}`);
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      // Approval insufficient or permit already consumed — surface to ops
      console.error(`[webhook] still denied after approval: ${err.reason} (id=${err.evaluationId})`);
    } else if (err instanceof AtlaSentError) {
      // Transport / server failure — leave hold registered for retry
      console.error(`[webhook] AtlaSent unavailable (code=${err.code}): ${err.message}`);
      throw err; // return 500 so AtlaSent retries the webhook
    } else {
      throw err;
    }
  }
}

// ---------------------------------------------------------------------------
// Accounting action dispatcher
// Replace each stub with real DB writes / ERP API calls.
// ---------------------------------------------------------------------------

async function executeAccountingAction(
  action: string,
  context: Record<string, unknown>,
  permitId: string,
): Promise<void> {
  console.log(`[action] executing ${action} under permit ${permitId}`);
  switch (action) {
    case "journal_entry.approve":
      // await erpDb.journalEntries.approve(context.je_id as string, permitId);
      console.log(`[action] JE ${context.je_id} moved to APPROVED state`);
      break;
    case "period.close":
      // await erpDb.periods.close(context.period as string, permitId);
      console.log(`[action] period ${context.period} set to CLOSED`);
      break;
    case "reconciliation.certify":
      // await erpDb.reconciliations.certify(context.account_id as string, permitId);
      console.log(`[action] reconciliation for ${context.account_id} CERTIFIED`);
      break;
    default:
      console.warn(`[action] no handler registered for action=${action}`);
  }
}

// ---------------------------------------------------------------------------
// HTTP server
// ---------------------------------------------------------------------------

function readBody(req: IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    let body = "";
    req.on("data", (chunk) => (body += chunk));
    req.on("end", () => resolve(body));
    req.on("error", reject);
  });
}

const server = createServer(async (req: IncomingMessage, res: ServerResponse) => {
  if (req.method !== "POST" || req.url !== "/atlasent/webhook") {
    res.writeHead(404).end();
    return;
  }

  const rawBody = await readBody(req);

  // Verify AtlaSent-Signature before processing — never trust unauthenticated webhooks.
  try {
    verifySignature(req, rawBody);
  } catch (sigErr) {
    console.warn(`[webhook] signature rejected: ${(sigErr as Error).message}`);
    res.writeHead(401).end("unauthorized");
    return;
  }

  let payload: HoldApprovedPayload;
  try {
    payload = JSON.parse(rawBody);
  } catch {
    res.writeHead(400).end("bad json");
    return;
  }

  if (payload.event !== "hold.approved") {
    res.writeHead(200).end("ignored");
    return;
  }

  try {
    await handleHoldApproved(payload);
    res.writeHead(200).end("ok");
  } catch {
    res.writeHead(500).end("error");
  }
});

const PORT = Number(process.env.PORT ?? 3001);
server.listen(PORT, () => console.log(`[webhook] listening on :${PORT}/atlasent/webhook`));
