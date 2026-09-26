// Demonstrates: SMS OTP secondary challenge for a break-glass operation.
//
// Flow:
//   1. Operator requests break-glass access to a production database.
//   2. POST /v1-evaluate -> decision: "hold", challenge_required: "sms_otp"
//   3. POST /v1-sms-otp/send  -> otp_id for the challenge session
//   4. User reads the 6-digit code from their phone and enters it.
//   5. POST /v1-sms-otp/verify -> { valid: true, challenge_token }
//   6. Re-evaluate with challenge_token in context -> decision: "allow"
//   7. POST /v1-verify-permit to close the audit loop before executing.
//
// Twilio is mocked here. In production, AtlaSent calls Twilio on your behalf
// when you supply TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM_NUMBER
// as org-level secrets in the AtlaSent console.
//
// Requires: ATLASENT_API_KEY, ATLASENT_BASE_URL, ATLASENT_ORG_ID env vars.
// ACTOR_PHONE_E164 defaults to "+15550100001" (demo value — override in prod).

const apiKey = process.env["ATLASENT_API_KEY"];
const baseUrl = process.env["ATLASENT_BASE_URL"] ?? "https://api.atlasent.io/functions/v1";
const orgId = process.env["ATLASENT_ORG_ID"];
const actorPhone = process.env["ACTOR_PHONE_E164"] ?? "+15550100001";

if (!apiKey || !orgId) {
  console.error("ATLASENT_API_KEY and ATLASENT_ORG_ID are required.");
  process.exit(1);
}

const headers = {
  Authorization: `Bearer ${apiKey}`,
  "Content-Type": "application/json",
};

// ── Types ─────────────────────────────────────────────────────────────────────

interface EvaluateResponse {
  decision: "allow" | "deny" | "hold" | "escalate";
  request_id: string;
  permit_token?: string;
  expires_at?: string;
  challenge?: {
    type: "sms_otp";
    message: string;
  };
  denial?: {
    code: string;
    reason: string;
  };
}

interface SmsSendResponse {
  otp_id: string;
  expires_at: string; // ISO-8601 — OTPs are valid for 10 minutes
  destination_hint: string; // masked number, e.g. "***-***-0001"
}

interface SmsVerifyResponse {
  valid: boolean;
  challenge_token?: string; // include in context.challenge_token on re-evaluate
  error?: string;
}

interface VerifyPermitResponse {
  valid: boolean;
  outcome: string;
  reason?: string;
}

// ── API helpers ───────────────────────────────────────────────────────────────

async function evaluate(
  actorId: string,
  actionType: string,
  context: Record<string, unknown> = {},
): Promise<EvaluateResponse> {
  const res = await fetch(`${baseUrl}/v1-evaluate`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      actor_id: actorId,
      action_type: actionType,
      context,
    }),
    signal: AbortSignal.timeout(10_000),
  });
  if (!res.ok) {
    throw new Error(`/v1-evaluate returned ${res.status}: ${await res.text()}`);
  }
  return res.json() as Promise<EvaluateResponse>;
}

async function smsSend(
  phoneE164: string,
  actionContext: string,
): Promise<SmsSendResponse> {
  // In dry-run / dev mode AtlaSent logs the OTP to the audit trail instead of
  // dispatching to Twilio. Set DRY_RUN=true in your org settings for local dev.
  const res = await fetch(`${baseUrl}/v1-sms-otp/send`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      org_id: orgId,
      phone_e164: phoneE164,
      action_context: actionContext,
    }),
    signal: AbortSignal.timeout(10_000),
  });
  if (!res.ok) {
    throw new Error(
      `/v1-sms-otp/send returned ${res.status}: ${await res.text()}`,
    );
  }
  return res.json() as Promise<SmsSendResponse>;
}

async function smsVerify(
  otpId: string,
  code: string,
): Promise<SmsVerifyResponse> {
  const res = await fetch(`${baseUrl}/v1-sms-otp/verify`, {
    method: "POST",
    headers,
    body: JSON.stringify({ otp_id: otpId, code }),
    signal: AbortSignal.timeout(10_000),
  });
  if (!res.ok) {
    throw new Error(
      `/v1-sms-otp/verify returned ${res.status}: ${await res.text()}`,
    );
  }
  return res.json() as Promise<SmsVerifyResponse>;
}

async function verifyPermit(
  permitToken: string,
  actorId: string,
  actionType: string,
): Promise<VerifyPermitResponse> {
  const res = await fetch(`${baseUrl}/v1-verify-permit`, {
    method: "POST",
    headers,
    body: JSON.stringify({ permit_token: permitToken, actor_id: actorId, action_type: actionType }),
    signal: AbortSignal.timeout(10_000),
  });
  if (!res.ok) {
    throw new Error(
      `/v1-verify-permit returned ${res.status}: ${await res.text()}`,
    );
  }
  return res.json() as Promise<VerifyPermitResponse>;
}

// ── Mock: simulate an operator reading the OTP from their phone ───────────────
//
// In a real app this is replaced by a form, CLI prompt, or callback webhook.
// We mock a deterministic 6-digit code here so the example runs without Twilio.
// AtlaSent's dry-run mode accepts the mock code "000000" for test actors.

function mockReadOtpFromPhone(destinationHint: string): string {
  console.log(
    `  [mock] OTP sent to ${destinationHint} — simulating user input.`,
  );
  const mockCode = "000000"; // accepted by AtlaSent in dry-run mode
  console.log(`  [mock] User entered: ${mockCode}`);
  return mockCode;
}

// ── Main flow ─────────────────────────────────────────────────────────────────

async function main() {
  const actorId = "ops-lead@acme.internal";
  const actionType = "database.production.break_glass";

  // ── Step 1: initial evaluate ──────────────────────────────────────────────
  console.log("Step 1: requesting break-glass access...");
  console.log(`  actor_id:    ${actorId}`);
  console.log(`  action_type: ${actionType}`);

  const initial = await evaluate(actorId, actionType, {
    resource_id: "prod-postgres-primary",
    environment: "production",
    reason: "P0 incident — prod API returning 500s",
  });

  console.log(`  decision:    ${initial.decision}`);
  console.log(`  request_id:  ${initial.request_id}`);

  if (initial.decision === "deny") {
    console.error(
      `  Denied (${initial.denial?.code ?? "DENY"}): ${initial.denial?.reason ?? "policy denied"}`,
    );
    process.exit(1);
  }

  if (initial.decision !== "hold") {
    // Unexpected decision — fail closed.
    console.error(
      `  Unexpected decision "${initial.decision}" — expected hold with challenge_required.`,
    );
    process.exit(1);
  }

  if (initial.challenge?.type !== "sms_otp") {
    console.error(
      `  Hold without sms_otp challenge — check org policy configuration.`,
    );
    process.exit(1);
  }

  console.log(`  Challenge:   ${initial.challenge.message}`);

  // ── Step 2: send OTP to the actor's enrolled phone ────────────────────────
  console.log("\nStep 2: sending SMS OTP...");
  console.log(`  phone_e164:      ${actorPhone}`);
  console.log(`  action_context:  break_glass`);

  const sendResult = await smsSend(actorPhone, "break_glass");
  console.log(`  otp_id:          ${sendResult.otp_id}`);
  console.log(`  destination:     ${sendResult.destination_hint}`);
  console.log(`  expires_at:      ${sendResult.expires_at}`);

  // ── Step 3: collect the 6-digit code ─────────────────────────────────────
  console.log("\nStep 3: collecting OTP from user...");
  const userCode = mockReadOtpFromPhone(sendResult.destination_hint);

  // ── Step 4: verify the OTP ────────────────────────────────────────────────
  console.log("\nStep 4: verifying OTP...");
  const verification = await smsVerify(sendResult.otp_id, userCode);

  if (!verification.valid) {
    console.error(
      `  OTP verification failed: ${verification.error ?? "invalid or expired code"}`,
    );
    process.exit(1);
  }

  console.log(`  OTP valid — challenge_token received.`);
  const challengeToken = verification.challenge_token!;

  // ── Step 5: re-evaluate with the challenge_token ──────────────────────────
  console.log("\nStep 5: re-evaluating with challenge_token...");

  const reeval = await evaluate(actorId, actionType, {
    resource_id: "prod-postgres-primary",
    environment: "production",
    reason: "P0 incident — prod API returning 500s",
    challenge_token: challengeToken, // proves OTP was satisfied
  });

  console.log(`  decision:    ${reeval.decision}`);

  if (reeval.decision !== "allow") {
    console.error(`  Re-evaluation did not allow: ${reeval.decision}`);
    if (reeval.denial) {
      console.error(
        `  Denial code: ${reeval.denial.code} — ${reeval.denial.reason}`,
      );
    }
    process.exit(1);
  }

  if (!reeval.permit_token) {
    console.error("  ALLOW with no permit_token — refusing to proceed.");
    process.exit(1);
  }

  console.log(`  permit_token: ${reeval.permit_token}`);
  console.log(`  expires_at:   ${reeval.expires_at}`);

  // ── Step 6: verify the permit before executing ────────────────────────────
  //
  // This step is mandatory. Skipping it is fail-open: an allow decision is not
  // authorization until the permit is verified. The SDK's protect() does both
  // steps for you; the raw flow must do it explicitly.
  console.log("\nStep 6: verifying permit before executing...");

  const permitVerification = await verifyPermit(
    reeval.permit_token,
    actorId,
    actionType,
  );

  if (!permitVerification.valid) {
    console.error(
      `  Permit verification failed (${permitVerification.outcome}): ${permitVerification.reason}`,
    );
    process.exit(1);
  }

  console.log(`  Permit verified — outcome: ${permitVerification.outcome}`);

  // ── Step 7: execute the break-glass action ────────────────────────────────
  //
  // The action only runs here, after both evaluate and verify-permit succeed.
  // The permit token is stored alongside the action record for audit traceability.
  console.log("\nStep 7: executing break-glass action...");
  console.log(`  [action] Granting temporary read access to prod-postgres-primary`);
  console.log(`  [action] Permit: ${reeval.permit_token}`);
  console.log(`  [action] Break-glass session opened. Expires in 1 hour.`);

  console.log("\nDone. Full audit trail recorded in AtlaSent.");
  console.log(
    `  Review at: https://console.atlasent.io/decisions/${initial.request_id}`,
  );
}

main().catch((err) => {
  console.error("Error:", err instanceof Error ? err.message : String(err));
  process.exit(1);
});
