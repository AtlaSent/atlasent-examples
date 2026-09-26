/**
 * gxp-vqp-re-derivation: Delta VQP Phase 3 — Re-derivation Audit Demo (TypeScript)
 *
 * Demonstrates VQP snapshot generation and re-derivation verification using
 * VQPClient from @atlasent/sdk. VQPClient is SERVER-SIDE ONLY — it requires
 * a Supabase service role key and must never be used in browser/client code.
 *
 * Offline: set ATLASENT_SUPABASE_URL=http://localhost:54321
 *          and ATLASENT_SUPABASE_SERVICE_ROLE_KEY=service_role_stub
 *
 * Live:
 *   ATLASENT_SUPABASE_URL=https://<project>.supabase.co \
 *   ATLASENT_SUPABASE_SERVICE_ROLE_KEY=<service_role_key> \
 *   ATLASENT_ORG_ID=org_replace_me \
 *   ATLASENT_BUNDLE_ID=bundle_replace_me \
 *   npx tsx main.ts
 */
import { VQPClient, AtlaSentError } from "@atlasent/sdk";

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

const snapshotLine = (snapshotId: string, promptHash: string, score: number, verdict: string) => {
  console.log(`  ✔ GENERATED  verdict: ${verdict}`);
  console.log(`               snapshot_id:  ${snapshotId}`);
  console.log(`               prompt_hash:  ${promptHash}`);
  console.log(`               score:        ${score}`);
};

const verifyLine = (result: {
  snapshotId: string;
  hashMatch: boolean;
  rerunScore?: number;
  scoreDelta?: number;
  verdictChanged?: boolean;
  auditLogId: string;
}) => {
  const matchIcon = result.hashMatch ? "✔" : "✗";
  console.log(`  ${matchIcon} VERIFIED    hash_match: ${result.hashMatch}`);
  console.log(`               snapshot_id:    ${result.snapshotId}`);
  console.log(`               audit_log_id:   ${result.auditLogId}`);
  if (result.rerunScore !== undefined) {
    console.log(`               rerun_score:    ${result.rerunScore}`);
  }
  if (result.scoreDelta !== undefined) {
    console.log(`               score_delta:    ${result.scoreDelta}`);
  }
  if (result.verdictChanged !== undefined) {
    console.log(`               verdict_changed: ${result.verdictChanged}`);
  }
};

const execute = (msg: string) => console.log(`               → ${msg}`);

// ---------------------------------------------------------------------------
// Demo
// ---------------------------------------------------------------------------

async function run() {
  // VQPClient is SERVER-SIDE ONLY. It uses the Supabase service role key,
  // which has elevated privileges and must never be exposed to clients.
  const client = new VQPClient({
    serviceRoleKey: process.env.ATLASENT_SUPABASE_SERVICE_ROLE_KEY ?? "",
    supabaseUrl: process.env.ATLASENT_SUPABASE_URL ?? "",
  });

  const orgId = process.env.ATLASENT_ORG_ID ?? "org_replace_me";
  const bundleId = process.env.ATLASENT_BUNDLE_ID ?? "bundle_replace_me";

  bar("gxp-vqp-re-derivation   Delta VQP Phase 3 Re-derivation Audit Demo (TypeScript)");
  console.log(`  org:    ${orgId}`);
  console.log(`  bundle: ${bundleId}`);
  console.log(`  ⚠  VQPClient is server-side only (serviceRoleKey required)`);

  // ---------------------------------------------------------------------------
  // Scenario 1 — Generate + Verify (hash match)
  // Generates a VQP snapshot with all 6 criteria met, then verifies it.
  // Expects: hashMatch=true, verdictChanged=false
  // ---------------------------------------------------------------------------
  scenario(
    1,
    "generate + verify (hash match)",
    "All 6 VQP criteria met → expect verdict=qualified, hashMatch=true"
  );

  const vqpContext = {
    // CC6.1 — Access Control
    access_control: {
      mfa_enforced: true,
      least_privilege: true,
      role_review_completed: true,
    },
    // CC7.2 — Audit Coverage
    audit_coverage: {
      all_events_logged: true,
      retention_policy_met: true,
      tamper_evident: true,
    },
    // CC7.4 — Escalation Paths
    escalation_paths: {
      defined: true,
      tested_last_cycle: true,
      owner_assigned: true,
    },
    // CC8.1 — Deny Specificity
    deny_specificity: {
      no_wildcard_denies: true,
      scope_documented: true,
    },
    // CC6.3 — Hold Conditions
    hold_conditions: {
      hold_logic_tested: true,
      release_criteria_documented: true,
    },
    // CC5.2 — Override Governance
    override_governance: {
      override_requires_dual_approval: true,
      override_audit_logged: true,
      break_glass_policy_current: true,
    },
  };

  let generatedSnapshotId = "snap_placeholder_replace_me";

  try {
    const gen = await client.generate({ bundleId, orgId, vqpContext });
    generatedSnapshotId = gen.snapshotId;
    snapshotLine(gen.snapshotId, gen.promptHash, gen.score, gen.verdict);
    execute(`snapshot stored — use snapshotId for future verify calls`);
  } catch (err) {
    if (err instanceof AtlaSentError) {
      console.log(`  ✗ UNAVAILABLE  code=${err.code}: ${err.message}`);
      execute(`using placeholder snapshotId for downstream scenarios`);
    } else throw err;
  }

  bar();

  // Verify the snapshot we just generated — expect hashMatch=true
  try {
    const verify1 = await client.verify({ snapshotId: generatedSnapshotId });
    verifyLine(verify1);
    if (verify1.hashMatch) {
      execute("prompt hash verified — snapshot is unmodified since generation");
    } else {
      execute("ALERT: hash mismatch — snapshot may have been tampered with");
    }
    if (verify1.verdictChanged === false) {
      execute("verdict unchanged — qualification status is stable");
    }
  } catch (err) {
    if (err instanceof AtlaSentError) {
      console.log(`  ✗ UNAVAILABLE  code=${err.code}: ${err.message}`);
    } else throw err;
  }

  // ---------------------------------------------------------------------------
  // Scenario 2 — Verify only (snapshot already exists)
  // Verifies a pre-existing snapshot ID without regenerating.
  // Expects: hashMatch=true (snapshot was not modified)
  // ---------------------------------------------------------------------------
  scenario(
    2,
    "verify only (snapshot already exists)",
    "Verify a pre-existing snapshot by ID — expect hashMatch=true"
  );

  // Replace with a real snapshot ID from a previous generate call.
  const existingSnapshotId = "snap_existing_replace_me";

  try {
    const verify2 = await client.verify({ snapshotId: existingSnapshotId });
    verifyLine(verify2);
    if (verify2.hashMatch) {
      execute("snapshot integrity confirmed — no re-derivation needed");
    } else {
      execute("ALERT: hash mismatch — initiate re-derivation workflow");
    }
  } catch (err) {
    if (err instanceof AtlaSentError) {
      console.log(`  ✗ UNAVAILABLE  code=${err.code}: ${err.message}`);
    } else throw err;
  }

  // ---------------------------------------------------------------------------
  // Scenario 3 — Verify with rerun (score drift detected)
  // Passes rerun=true to re-evaluate criteria against current state.
  // Shows how to detect scoreDelta > 0 and verdictChanged.
  // ---------------------------------------------------------------------------
  scenario(
    3,
    "verify with rerun (score drift detection)",
    "rerun=true re-evaluates criteria — detect scoreDelta and verdictChanged"
  );

  try {
    const verify3 = await client.verify({
      snapshotId: generatedSnapshotId,
      rerun: true,
    });
    verifyLine(verify3);

    // Detect score drift
    if (verify3.scoreDelta !== undefined && verify3.scoreDelta > 0) {
      execute(
        `score drift detected: delta=${verify3.scoreDelta} — review criteria changes`
      );
    } else {
      execute("no score drift detected — criteria scores are stable");
    }

    // Detect verdict change — triggers mandatory re-derivation audit
    if (verify3.verdictChanged) {
      execute(
        "ALERT: verdict changed — mandatory re-derivation audit required per CC7.2"
      );
      execute("open a re-derivation ticket and notify compliance team");
    } else {
      execute("verdict unchanged — no re-derivation audit required");
    }

    // Audit log reference
    execute(`audit event recorded: auditLogId=${verify3.auditLogId}`);
  } catch (err) {
    if (err instanceof AtlaSentError) {
      console.log(`  ✗ UNAVAILABLE  code=${err.code}: ${err.message}`);
    } else throw err;
  }

  bar();
  console.log(`  VQP criteria evaluated (6 total):`);
  console.log(`    access_control      (CC6.1)`);
  console.log(`    audit_coverage      (CC7.2)`);
  console.log(`    escalation_paths    (CC7.4)`);
  console.log(`    deny_specificity    (CC8.1)`);
  console.log(`    hold_conditions     (CC6.3)`);
  console.log(`    override_governance (CC5.2)`);
  console.log();
  console.log(`  Verdicts: qualified (score≥85, no fails)`);
  console.log(`            conditionally_qualified (score≥60, no fails)`);
  console.log(`            not_qualified`);
  console.log();
}

run().catch((err) => {
  if (err instanceof AtlaSentError) {
    console.error(`AtlaSent unavailable (code=${err.code}): ${err.message}`);
    process.exit(2);
  }
  throw err;
});
