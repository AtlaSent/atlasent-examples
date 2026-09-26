/**
 * infra-actions: Infrastructure Actions Authorization Demo (TypeScript)
 *
 * Mirrors main.py — same 5 scenarios, same enforcement outcomes.
 * Shows how classifyToolRisk() from @atlasent/sdk can be used to automatically
 * classify infra action risk level before calling protect().
 *
 * Note: These actions are also demonstrated in atlasent-examples/protected-actions/
 * (the original examples); this example consolidates them with full policy context.
 *
 * Offline (mock server in another terminal):
 *   npx @atlasent/sdk mock
 *   ATLASENT_API_URL=http://127.0.0.1:4747 ATLASENT_API_KEY=mock npx tsx main.ts
 *
 * Live:
 *   ATLASENT_API_KEY=ask_live_... npx tsx main.ts
 */
import atlasent, {
  AtlaSentDeniedError,
  AtlaSentError,
  type Permit,
  classifyToolRisk,   // built-in risk classifier from @atlasent/sdk
} from "@atlasent/sdk";

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

// Show classifyToolRisk result before the protect() call
const showRisk = (action: string) => {
  // classifyToolRisk() returns the risk level for an action string.
  // Use it to add context logging or to conditionally apply additional checks
  // before calling protect().
  try {
    const level = classifyToolRisk(action);
    console.log(`               risk_level:  ${level}  [classifyToolRisk]`);
  } catch {
    // classifyToolRisk may not be exported in all SDK versions; graceful fallback
    console.log(`               risk_level:  (classifyToolRisk not available)`);
  }
};

// ---------------------------------------------------------------------------
// Simulated infrastructure mutations
// Only reachable after protect() resolves.
// ---------------------------------------------------------------------------

const sysStopInstance = (instanceId: string, region: string) =>
  execute(`EC2 instance ${instanceId} (${region}) stop command issued via AWS SDK`);

const sysDeleteVolume = (objectName: string, database: string) => {
  execute(`volume '${objectName}' in database '${database}' scheduled for deletion`);
  execute("pre-deletion snapshot verified, deletion job queued");
};

// ---------------------------------------------------------------------------
// Demo
// ---------------------------------------------------------------------------

async function run() {
  bar("infra-actions   Infrastructure Actions Authorization Demo (TypeScript)");
  console.log(
    "  note:   see also atlasent-examples/protected-actions/ (original examples)"
  );

  // 1 -- aws.ec2.stop_instance: ALLOWED -------------------------------------
  scenario(1, "aws.ec2.stop_instance", "ALLOWED: on-call engineer, changeTicket present");
  showRisk("aws.ec2.stop_instance");
  try {
    const p = await atlasent.protect({
      agent: "oncall.sre@acme.example",
      action: "aws.ec2.stop_instance",
      context: {
        instanceId: "i-0a1b2c3d4e5f6a7b8",
        region: "us-east-1",
        authorizedBy: "oncall.sre@acme.example",
        changeTicket: "CHG-2026-04881",
        reason: "Memory leak detected — stopping for snapshot before replacement",
      },
    });
    permitLine(p);
    sysStopInstance("i-0a1b2c3d4e5f6a7b8", "us-east-1");
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) blocked(err.reason ?? err.message);
    else throw err;
  }

  // 2 -- aws.ec2.terminate_instance: DENIED (engineer, not IC) --------------
  scenario(
    2,
    "aws.ec2.terminate_instance",
    "BLOCKED: actor has on_call_engineer role only — incident_commander required"
  );
  showRisk("aws.ec2.terminate_instance");
  try {
    await atlasent.protect({
      agent: "oncall.sre@acme.example",
      action: "aws.ec2.terminate_instance",
      context: {
        instanceId: "i-0b2c3d4e5f6a7b8c9",
        region: "us-east-1",
        authorizedBy: "oncall.sre@acme.example", // not incident commander
        changeTicket: "CHG-2026-04882",
        reason: "Compromised instance — terminate immediately",
      },
    });
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      blocked(err.reason ?? err.message);
      console.log(`               evaluation_id: ${err.evaluationId}`);
      execute("instance NOT terminated — incident_commander role required");
    } else throw err;
  }

  // 3 -- github.repos.delete: DENIED (machine_executable=false) -------------
  scenario(
    3,
    "github.repos.delete",
    "BLOCKED: machine_executable=false — human review always required"
  );
  showRisk("github.repos.delete");
  try {
    await atlasent.protect({
      agent: "automation-bot",
      action: "github.repos.delete",
      context: {
        repoFullName: "acme-org/legacy-service",
        deletedBy: "automation-bot",
        changeTicket: "CHG-2026-04883",
        reason: "Repository archived and migrated to new org",
      },
    });
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      blocked(err.reason ?? err.message);
      console.log(`               evaluation_id: ${err.evaluationId}`);
      execute("repository NOT deleted — human review required in AtlaSent console");
    } else throw err;
  }

  // 4 -- database.table.drop: DENIED (backupVerified=false) -----------------
  scenario(
    4,
    "database.table.drop",
    "BLOCKED: backupVerified=false — backup must be verified before drop"
  );
  showRisk("database.table.drop");
  try {
    await atlasent.protect({
      agent: "ic.oncall@acme.example",
      action: "database.table.drop",
      context: {
        objectName: "staging_events_2024",
        database: "analytics-db-prod",
        authorizedBy: "ic.oncall@acme.example",
        backupVerified: false, // <-- no backup
        changeTicket: "CHG-2026-04884",
      },
    });
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      blocked(err.reason ?? err.message);
      console.log(`               evaluation_id: ${err.evaluationId}`);
      execute("table NOT dropped — run backup verification first");
    } else throw err;
  }

  // 5 -- database.volume.delete: ALLOWED (IC, backupVerified=true) ----------
  scenario(
    5,
    "database.volume.delete",
    "ALLOWED: incident commander, backupVerified=true, changeTicket present"
  );
  showRisk("database.volume.delete");
  try {
    const p = await atlasent.protect({
      agent: "ic.oncall@acme.example",
      action: "database.volume.delete",
      context: {
        objectName: "vol-analytics-archive-2023",
        database: "analytics-db-prod",
        authorizedBy: "ic.oncall@acme.example",
        backupVerified: true,
        changeTicket: "CHG-2026-04885",
      },
    });
    permitLine(p);
    sysDeleteVolume("vol-analytics-archive-2023", "analytics-db-prod");
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) blocked(err.reason ?? err.message);
    else throw err;
  }

  bar();
  console.log(`  Enforcement summary:`);
  console.log(`    BLOCKED  3 actions (insufficient role / machine_executable / no backup)`);
  console.log(`    ALLOWED  2 actions (permit-verified before infra mutation)`);
  console.log();
}

run().catch((err) => {
  if (err instanceof AtlaSentError) {
    console.error(`AtlaSent unavailable (code=${err.code}): ${err.message}`);
    process.exit(2);
  }
  throw err;
});
