/**
 * AtlaSent Protected Actions Example
 *
 * Demonstrates how to catch dangerous operations at the code level
 * using `requirePermit` and `classifyCommand`. Every dangerous call
 * lives inside requirePermit — it cannot be invoked directly.
 *
 * Run:
 *   ATLASENT_API_KEY=ask_test_... npx tsx index.ts
 */

import atlasent, {
  AtlaSentDeniedError,
  AtlaSentError,
  requirePermit,
  classifyCommand,
} from "@atlasent/sdk";

// The SDK's built-in default base URL is the bare host; the AtlaSent API is
// served under /functions/v1, so set it explicitly.
atlasent.configure({ baseUrl: process.env.ATLASENT_API_URL ?? "https://api.atlasent.io/functions/v1" });

// ── 1. Database delete ─────────────────────────────────────────────────────
//
// db.raw("DROP TABLE users") is never callable without a permit.
// If AtlaSent denies it, the SQL never runs.

async function dropUsersTable(
  db: { raw: (sql: string) => Promise<void> },
): Promise<void> {
  await requirePermit(
    {
      action_type: "database.table.drop",
      actor_id: "agent:code-agent",
      resource_id: "prod-db.users",
      environment: "production",
      context: {
        reversibility: "irreversible",
        blast_radius: "customer_data",
        human_requested: false,
        verified_backup: false,
      },
    },
    async () => {
      await db.raw("DROP TABLE users");
    },
  );
}

// ── 2. Command-level protection ─────────────────────────────────────────────
//
// classifyCommand returns the action_type for any destructive pattern.
// Safe commands pass straight through; dangerous ones require a permit.

async function runCommand(command: string, actorId: string): Promise<void> {
  const actionType = classifyCommand(command);
  if (actionType) {
    await requirePermit(
      {
        action_type: actionType,
        actor_id: actorId,
        resource_id: command,
        environment: "production",
        context: {
          command,
          reversibility: "potentially_irreversible",
          blast_radius: "unknown",
          human_requested: false,
        },
      },
      async () => {
        console.log(`  [exec] ${command}`);
      },
    );
    return;
  }
  console.log(`  [exec] ${command}`);
}

// ── 3. API-level protection ──────────────────────────────────────────────────
//
// Third-party API calls that are irreversible are wrapped the same way.
// railway.volumes.delete(volumeId) only runs inside the executor.

async function deleteRailwayVolume(
  volumeId: string,
  actorId: string,
): Promise<void> {
  await atlasent.requirePermit(
    {
      action_type: "database.volume.delete",
      actor_id: actorId,
      resource_id: volumeId,
      environment: "production",
      context: {
        contains_customer_data: true,
        reversibility: "irreversible",
        requires_human_approval: true,
      },
    },
    async () => {
      console.log(`  [mock] railway.volumes.delete("${volumeId}")`);
      // In production: await railway.volumes.delete(volumeId);
    },
  );
}

// ── Main ─────────────────────────────────────────────────────────────────────

async function main() {
  console.log("AtlaSent Protected Actions Demo\n");

  // Show classifyCommand output for a range of commands.
  const commands = [
    "rm -rf /tmp/build",
    "ls -la",
    "DROP TABLE sessions",
    "kubectl delete pod web-5d4f",
    "terraform destroy -auto-approve",
    "npm install",
    "DELETE FROM audit_logs WHERE created_at < '2020-01-01'",
  ];

  console.log("Command classification:");
  for (const cmd of commands) {
    const actionType = classifyCommand(cmd);
    const label = actionType ? `DANGEROUS → ${actionType}` : "safe";
    console.log(`  "${cmd.slice(0, 55)}"  →  ${label}`);
  }
  console.log();

  // Protected command: blocked because it matches a destructive pattern.
  console.log("Running destructive command through requirePermit:");
  try {
    await runCommand("rm -rf /var/customer-data", "agent:cleanup-bot");
    console.log("  Allowed and executed.\n");
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      console.log(`  Blocked: ${err.reason || err.message}\n`);
    } else if (err instanceof AtlaSentError) {
      console.log(`  AtlaSent error: ${err.message}\n`);
    } else {
      throw err;
    }
  }

  // Protected API call: only executes if policy allows it.
  console.log("Deleting Railway volume through requirePermit:");
  try {
    await deleteRailwayVolume("vol-prod-customer-db-01", "agent:infra-bot");
    console.log("  Allowed and executed.\n");
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      console.log(`  Blocked: ${err.reason || err.message}\n`);
    } else if (err instanceof AtlaSentError) {
      console.log(`  AtlaSent error: ${err.message}\n`);
    } else {
      throw err;
    }
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
