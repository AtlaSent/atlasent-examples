/**
 * gxp-clinical-data-access: GxP Clinical Data Access Authorization Demo (TypeScript)
 *
 * Mirrors main.py — same 3 scenarios, same enforcement outcomes.
 * Includes protectToolCall() example showing how to gate clinical data access
 * in an AI agent pipeline.
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
// Simulated clinical data access mutations
// Only reachable after protect() resolves.
// ---------------------------------------------------------------------------

const sysGrantAccess = (
  subjectId: string,
  dataCategory: string,
  accessedBy: string,
  trialId: string
) => {
  execute(
    `data access granted: ${accessedBy} → ${dataCategory} (subject=${subjectId}, trial=${trialId})`
  );
  execute("access session logged to clinical trial management system");
};

// ---------------------------------------------------------------------------
// AI agent pipeline example using protectToolCall()
//
// In a real AI agent pipeline, clinical data access should be gated using
// protectToolCall() with human_in_the_loop=true. This function shows the
// pattern for wrapping a clinical data tool call.
// ---------------------------------------------------------------------------

async function clinicalDataAccessTool(params: {
  subjectId: string;
  dataCategory: string;
  trialId: string;
  purpose: string;
  requestedBy: string;
}): Promise<void> {
  // Gate the tool call before executing it
  // protectToolCall() is the recommended API for AI agent pipelines;
  // it enforces machine_executable=false and requires human_in_the_loop=true
  // when the policy mandates it.
  const permit = await atlasent.protect({
    agent: params.requestedBy,
    action: "clinical.data.access",
    context: {
      subjectId: params.subjectId,
      dataCategory: params.dataCategory,
      accessedBy: params.requestedBy,
      purpose: params.purpose,
      aiAgent: true, // signals this is an AI agent call
      consentVerified: true,
      trialId: params.trialId,
    },
  });
  // Only reachable if policy allows
  permitLine(permit);
  sysGrantAccess(params.subjectId, params.dataCategory, params.requestedBy, params.trialId);
}

// ---------------------------------------------------------------------------
// Demo
// ---------------------------------------------------------------------------

async function run() {
  bar("gxp-clinical-data-access   Clinical Data Access Authorization Demo (TypeScript)");
  console.log(`  action: clinical.data.access`);
  console.log(`  policy: fail-closed, machine_executable=false, consent required, purpose required`);

  // 1 -- ALLOW: human researcher, aiAgent=false, valid purpose ---------------
  scenario(
    1,
    "clinical.data.access",
    "ALLOWED: human researcher, aiAgent=false, purpose=protocol-review, consent verified"
  );
  try {
    const p = await atlasent.protect({
      agent: "dr.smith@clinicalresearch.example",
      action: "clinical.data.access",
      context: {
        subjectId: "SUBJ-004",
        dataCategory: "efficacy-endpoints",
        accessedBy: "dr.smith@clinicalresearch.example",
        purpose: "protocol-review",
        aiAgent: false,
        consentVerified: true,
        trialId: "TRIAL-2026-PHASE3-001",
      },
    });
    permitLine(p);
    sysGrantAccess(
      "SUBJ-004",
      "efficacy-endpoints",
      "dr.smith@clinicalresearch.example",
      "TRIAL-2026-PHASE3-001"
    );
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) blocked(err.reason ?? err.message);
    else throw err;
  }

  // 2 -- DENY: AI agent access via protectToolCall() pattern ----------------
  // machine_executable=false enforces denial when no human-in-the-loop
  scenario(
    2,
    "clinical.data.access",
    "BLOCKED: aiAgent=true — machine_executable=false, no human-in-the-loop"
  );
  console.log(
    "  Note: use protectToolCall() with human_in_the_loop=true in AI agent pipelines"
  );
  try {
    // Demonstrating the tool-call pattern — this will be blocked by the policy
    await clinicalDataAccessTool({
      subjectId: "SUBJ-007",
      dataCategory: "safety-events",
      trialId: "TRIAL-2026-PHASE3-001",
      purpose: "automated-safety-review",
      requestedBy: "clinical-review-agent",
    });
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      blocked(err.reason ?? err.message);
      console.log(`               evaluation_id: ${err.evaluationId}`);
      execute("data access NOT granted — human review required before AI agent access");
    } else throw err;
  }

  // 3 -- DENY: missing purpose -----------------------------------------------
  scenario(
    3,
    "clinical.data.access",
    "BLOCKED: purpose field empty → DENY_PURPOSE_MISSING"
  );
  try {
    await atlasent.protect({
      agent: "dr.jones@clinicalresearch.example",
      action: "clinical.data.access",
      context: {
        subjectId: "SUBJ-012",
        dataCategory: "lab-results",
        accessedBy: "dr.jones@clinicalresearch.example",
        purpose: "", // <-- missing purpose
        aiAgent: false,
        consentVerified: true,
        trialId: "TRIAL-2026-PHASE3-001",
      },
    });
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      blocked(err.reason ?? err.message);
      console.log(`               evaluation_id: ${err.evaluationId}`);
      execute("data access NOT granted — purpose must be documented per ICH E6 GCP §8");
    } else throw err;
  }

  bar();
  console.log(`  Enforcement summary:`);
  console.log(`    BLOCKED  2 actions (AI agent blocked / missing purpose)`);
  console.log(`    ALLOWED  1 action  (human researcher, consent verified, purpose documented)`);
  console.log();
}

run().catch((err) => {
  if (err instanceof AtlaSentError) {
    console.error(`AtlaSent unavailable (code=${err.code}): ${err.message}`);
    process.exit(2);
  }
  throw err;
});
