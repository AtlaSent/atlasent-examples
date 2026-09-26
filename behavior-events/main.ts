/**
 * behavior-events: Behavior Event Sharing Authorization Demo (TypeScript)
 *
 * Mirrors main.py — same 4 scenarios, same enforcement outcomes.
 *
 * NOTE: Behavior events are Phase 3 and require a privacy review before
 * production use. See README.md for the privacy review checklist.
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
  console.log(`               permit_hash: ${p.permitHash ?? ""}`);
};

const execute = (msg: string) => console.log(`               → ${msg}`);

// ---------------------------------------------------------------------------
// Simulated behavior event dispatch
// Only reachable after protect() resolves.
// ---------------------------------------------------------------------------

const sysShareEvent = (
  eventCategory: string,
  subjectId: string,
  destination: string,
  purpose: string
) => {
  execute(
    `event '${eventCategory}' for subject ${subjectId} dispatched to ${destination}`
  );
  execute(`event logged in behavior audit trail (purpose=${purpose})`);
};

// ---------------------------------------------------------------------------
// Demo
// ---------------------------------------------------------------------------

async function run() {
  bar("behavior-events   Behavior Event Sharing Authorization Demo (TypeScript)");
  console.log(`  action: behavior.event.share`);
  console.log(`  note:   Phase 3 feature — requires privacy review before production use`);

  // 1 -- ALLOW: non-sensitive, consent verified, valid purpose and destination
  scenario(
    1,
    "behavior.event.share",
    "ALLOWED: non-sensitive category, consent verified, valid purpose and destination"
  );
  try {
    const p = await atlasent.protect({
      agent: "analytics-pipeline",
      action: "behavior.event.share",
      context: {
        subjectId: "usr-88412",
        eventCategory: "behavior.product.click",
        consentVerified: true,
        purpose: "product-analytics",
        destination: "analytics.internal.example",
      },
    });
    permitLine(p);
    sysShareEvent(
      "behavior.product.click",
      "usr-88412",
      "analytics.internal.example",
      "product-analytics"
    );
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) blocked(err.reason ?? err.message);
    else throw err;
  }

  // 2 -- DENY: sensitive category (health.mental), consentVerified=false -----
  scenario(
    2,
    "behavior.event.share",
    "BLOCKED: behavior.health.mental category, consentVerified=false"
  );
  try {
    await atlasent.protect({
      agent: "health-analytics-pipeline",
      action: "behavior.event.share",
      context: {
        subjectId: "usr-88413",
        eventCategory: "behavior.health.mental",
        consentVerified: false, // <-- no consent
        purpose: "mental-health-research",
        destination: "research.partner-a.example",
      },
    });
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      blocked(err.reason ?? err.message);
      console.log(`               evaluation_id: ${err.evaluationId}`);
      execute("event NOT shared — consent required for health category data");
    } else throw err;
  }

  // 3 -- DENY: behavior.minor category → HOLD_HUMAN_REVIEW_REQUIRED ----------
  scenario(
    3,
    "behavior.event.share",
    "BLOCKED: behavior.minor category → HOLD_HUMAN_REVIEW_REQUIRED"
  );
  console.log(
    "  Note: machine cannot auto-approve minor data — human privacy review required"
  );
  try {
    await atlasent.protect({
      agent: "analytics-pipeline",
      action: "behavior.event.share",
      context: {
        subjectId: "usr-child-001",
        eventCategory: "behavior.minor",
        consentVerified: true,
        purpose: "child-safety-research",
        destination: "research.partner-a.example",
      },
    });
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      blocked(err.reason ?? err.message);
      console.log(`               evaluation_id: ${err.evaluationId}`);
      execute("event NOT shared — human privacy reviewer must approve minor data sharing");
    } else throw err;
  }

  // 4 -- DENY: no purpose documented -----------------------------------------
  scenario(
    4,
    "behavior.event.share",
    "BLOCKED: purpose field empty → DENY_PURPOSE_MISSING"
  );
  try {
    await atlasent.protect({
      agent: "analytics-pipeline",
      action: "behavior.event.share",
      context: {
        subjectId: "usr-88414",
        eventCategory: "behavior.product.view",
        consentVerified: true,
        purpose: "", // <-- missing purpose
        destination: "analytics.internal.example",
      },
    });
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      blocked(err.reason ?? err.message);
      console.log(`               evaluation_id: ${err.evaluationId}`);
      execute("event NOT shared — purpose must be documented");
    } else throw err;
  }

  bar();
  console.log(`  Enforcement summary:`);
  console.log(`    BLOCKED  3 actions (consent missing / minor data / missing purpose)`);
  console.log(`    ALLOWED  1 action  (non-sensitive, consent verified, valid context)`);
  console.log();
}

run().catch((err) => {
  if (err instanceof AtlaSentError) {
    console.error(`AtlaSent unavailable (code=${err.code}): ${err.message}`);
    process.exit(2);
  }
  throw err;
});
