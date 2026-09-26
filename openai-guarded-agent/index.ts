#!/usr/bin/env npx tsx
/**
 * AtlaSent + OpenAI — Guarded Agent Demo
 *
 * Shows how to wrap OpenAI function-calling tools with AtlaSent
 * execution authorization, using a local guard (./guard.ts) on the
 * published @atlasent/sdk. (@atlasent/agent is not published to npm yet.)
 * Every tool call goes through:
 *
 *   evaluate → permit → verify → execute
 *
 * A tool body runs only after evaluate returned allow AND the permit
 * verified. Deny, hold, or any error means it does not run.
 *
 * Usage:
 *   export ATLASENT_API_KEY="ask_live_..."
 *   export ATLASENT_API_URL="https://api.atlasent.io/functions/v1"   # optional (default)
 *   npx tsx index.ts
 */

import { AtlaSentDeniedError, configure } from "@atlasent/sdk";
import { withToolGuard } from "./guard.js";

const apiKey = process.env.ATLASENT_API_KEY;
if (!apiKey) {
  console.error("✗ Missing env: ATLASENT_API_KEY");
  process.exit(1);
}

// The SDK's built-in default is the bare host; the AtlaSent API is served
// under /functions/v1, so always pass an explicit base URL.
configure({ apiKey, baseUrl: process.env.ATLASENT_API_URL ?? "https://api.atlasent.io/functions/v1" });

// ─── OpenAI function-calling tool definitions ─────────────────
// These are the `tools` you pass to chat.completions.create(). The guard
// sits between OpenAI choosing a tool and your code executing it.

const deleteUserDefinition = {
  type: "function" as const,
  function: {
    name: "delete_user",
    description: "Permanently delete a user account and all associated data",
    parameters: {
      type: "object",
      properties: {
        user_id: { type: "string", description: "The user ID to delete" },
        reason: { type: "string", description: "Reason for deletion" },
      },
      required: ["user_id", "reason"],
    },
  },
};

const exportDataDefinition = {
  type: "function" as const,
  function: {
    name: "export_data",
    description: "Export customer data in the requested format",
    parameters: {
      type: "object",
      properties: {
        customer_id: { type: "string" },
        format: { type: "string", enum: ["csv", "json"] },
      },
      required: ["customer_id", "format"],
    },
  },
};

// Action type per tool. Action types must be dot-notation.
const ACTIONS: Record<string, string> = {
  delete_user: "user.delete",
  export_data: "data.export",
};

const [deleteUser, exportData] = withToolGuard(
  [
    {
      name: deleteUserDefinition.function.name,
      definition: deleteUserDefinition,
      execute: async (args: { user_id: string; reason: string }) => {
        // This only runs if AtlaSent authorized AND the permit verified.
        console.log(`  [tool] Deleting user ${args.user_id}...`);
        return { deleted: true, user_id: args.user_id };
      },
    },
    {
      name: exportDataDefinition.function.name,
      definition: exportDataDefinition,
      execute: async (args: { customer_id: string; format: string }) => {
        console.log(`  [tool] Exporting ${args.format} data for ${args.customer_id}...`);
        return { export_id: `exp_${Date.now()}`, records: 1247, format: args.format };
      },
    },
  ],
  {
    agent: "agent:support-bot",
    action: (name) => {
      const action = ACTIONS[name];
      if (!action) throw new Error(`no action type mapped for tool ${name}; refusing to run it`);
      return action;
    },
    extraContext: { environment: "staging", session_id: "demo-session-001" },
    resultFormat: "object",
  },
);

// ─── Demo Execution ───────────────────────────────────────────
// In a real agent, the tool name and arguments come from OpenAI's
// `tool_calls`; here they are fixed so the demo runs without an OpenAI key.

async function run(label: string, fn: () => Promise<Record<string, unknown>>) {
  console.log(`${label}\n`);
  try {
    const result = await fn();
    console.log("  ✓ Tool executed");
    console.log(`    Result: ${JSON.stringify(result)}`);
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      console.log("  ✗ Tool blocked by AtlaSent");
      console.log(`    Decision:   ${err.decision}`);
      console.log(`    Reason:     ${err.reason ?? err.message}`);
      console.log(`    Evaluation: ${err.evaluationId ?? "—"}`);
    } else {
      // Fail-closed: transport or verification errors also block the tool.
      console.log(`  ✗ Tool not run (fail-closed): ${(err as Error).message}`);
    }
  }
  console.log("\n" + "─".repeat(50) + "\n");
}

async function runDemo() {
  console.log("─── AtlaSent Guarded Agent Demo ───\n");
  await run("1️⃣  Attempting: delete_user (high-impact tool)", () =>
    deleteUser.execute({ user_id: "usr_123", reason: "Account closure requested" }),
  );
  await run("2️⃣  Attempting: export_data (medium-risk tool)", () =>
    exportData.execute({ customer_id: "cust_456", format: "csv" }),
  );
  console.log("─── Demo complete ───");
}

runDemo().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});
