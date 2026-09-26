/**
 * AtlaSent + Cursor — Guarded Tool Example (v1.6.0)
 *
 * Demonstrates AtlaSent authorization for Cursor/MCP-style tools
 * using a local guard (./guard.ts) on @atlasent/sdk.
 * (@atlasent/cursor is not published to npm yet.)
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
configure({ apiKey, baseUrl: process.env.ATLASENT_API_URL ?? "https://api.atlasent.io/functions/v1" });

const tools = withToolGuard(
  [
    {
      name: "edit_file",
      description: "Apply a unified diff patch to a file in the workspace",
      parameters: {
        type: "object" as const,
        properties: {
          path: { type: "string", description: "Relative path to the file" },
          patch: { type: "string", description: "Unified diff patch to apply" },
        },
        required: ["path", "patch"],
      },
      execute: async ({ path, patch }: { path: string; patch: string }): Promise<string> => {
        console.log(`  [mock] Patching ${path} (${patch.split("\n").length} lines)...`);
        return JSON.stringify({ success: true, path });
      },
    },
    {
      name: "run_command",
      description: "Execute a shell command in the project root directory",
      parameters: {
        type: "object" as const,
        properties: {
          command: { type: "string", description: "Shell command to run" },
        },
        required: ["command"],
      },
      execute: async ({ command }: { command: string }): Promise<string> => {
        console.log(`  [mock] Running: ${command}`);
        return JSON.stringify({ exitCode: 0, stdout: `[mock output for: ${command}]` });
      },
    },
  ],
  {
    agent: "cursor:demo-project",
    extraContext: { environment: "development" },
    onDeny: "tool-result",
  },
);

async function main() {
  console.log("AtlaSent + Cursor Guard Demo (v1.6.0)\n");

  const calls = [
    {
      name: "edit_file",
      input: {
        path: "src/index.ts",
        patch: "--- a/src/index.ts\n+++ b/src/index.ts\n@@ -1 +1 @@\n-old\n+new",
      },
    },
    {
      name: "run_command",
      input: { command: "npm test" },
    },
  ];

  for (const { name, input } of calls) {
    const tool = tools.find((t) => t.name === name)!;
    console.log(`Calling tool: ${name}`);

    try {
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
