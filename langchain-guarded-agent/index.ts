/**
 * AtlaSent + LangChain — Guarded Agent Example (v1.6.0)
 *
 * Wraps LangChain-style tools with AtlaSent authorize-first semantics
 * using a local guard (./guard.ts) on @atlasent/sdk.
 * (@atlasent/langchain is not published to npm yet.)
 * Run: npx tsx index.ts
 */

import { AtlaSentDeniedError, configure } from "@atlasent/sdk";
import { withToolGuard } from "./guard.js";

const apiKey = process.env.ATLASENT_API_KEY;
if (!apiKey) {
  console.error("ATLASENT_API_KEY is required.");
  process.exit(1);
}

// The SDK's built-in default is the bare host; the AtlaSent API is served
// under /functions/v1, so always pass an explicit base URL.
configure({ apiKey, baseUrl: process.env.ATLASENT_URL ?? "https://api.atlasent.io/functions/v1" });

const tools = withToolGuard(
  [
    {
      name: "delete_user",
      description: "Permanently delete a user account. High-impact.",
      execute: async ({ userId }: { userId: string }): Promise<string> => {
        console.log(`  [mock] Deleting user ${userId}...`);
        return JSON.stringify({ deleted: true, user_id: userId });
      },
    },
    {
      name: "export_audit_log",
      description: "Export the full audit log for a date range.",
      execute: async ({ from, to }: { from: string; to: string }): Promise<string> => {
        console.log(`  [mock] Exporting audit log ${from} → ${to}...`);
        return JSON.stringify({ exported: true, from, to, rows: 142 });
      },
    },
  ],
  {
    agent: "service:langchain-demo",
    extraContext: { environment: "production" },
    onDeny: "tool-result",
  },
);

async function main() {
  console.log("AtlaSent + LangChain Guard Demo (v1.6.0)\n");

  for (const tool of tools) {
    console.log(`Running tool: ${tool.name}`);
    try {
      const input =
        tool.name === "delete_user"
          ? { userId: "usr_demo_123" }
          : { from: "2026-01-01", to: "2026-05-01" };

      const result = await tool.execute(input);
      const parsed = JSON.parse(result) as Record<string, unknown>;

      if (parsed.denied) {
        console.log(`  Denied:     ${parsed.reason}`);
        console.log(`  Evaluation: ${parsed.evaluationId}`);
      } else {
        console.log(`  Result: ${result}`);
        if (parsed._atlasent_permit_id) {
          console.log(`  Permit: ${String(parsed._atlasent_permit_id).slice(0, 16)}...`);
        }
      }
    } catch (err) {
      if (err instanceof AtlaSentDeniedError) {
        console.log(`  Denied (thrown): ${err.message}`);
      } else {
        console.error("  Unexpected error:", err);
      }
    }
    console.log();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
