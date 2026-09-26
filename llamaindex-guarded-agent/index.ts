/**
 * AtlaSent + LlamaIndex — Guarded Agent Example (TypeScript, v1.6.0)
 *
 * Wraps LlamaIndex-style tools with AtlaSent authorize-first semantics
 * using a local guard (./guard.ts) on @atlasent/sdk.
 * (@atlasent/llamaindex is not published to npm yet.)
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
      metadata: {
        name: "vector_search",
        description: "Semantic search over the knowledge base",
        parameters: {
          type: "object",
          properties: {
            query: { type: "string" },
            topK: { type: "number" },
          },
          required: ["query"],
        },
      },
      execute: async ({ query, topK = 5 }: { query: string; topK?: number }) => {
        console.log(`  [mock] Searching for "${query}" (top ${topK})...`);
        return {
          results: [
            { id: "doc_001", score: 0.92, text: "AtlaSent governance overview..." },
            { id: "doc_002", score: 0.87, text: "Policy evaluation deep dive..." },
          ],
          total: 2,
        };
      },
    },
    {
      metadata: {
        name: "upsert_document",
        description: "Add or update a document in the knowledge base",
        parameters: {
          type: "object",
          properties: {
            id: { type: "string" },
            text: { type: "string" },
          },
          required: ["id", "text"],
        },
      },
      execute: async ({ id, text }: { id: string; text: string }) => {
        console.log(`  [mock] Upserting document ${id}...`);
        return { upserted: true, id, length: text.length };
      },
    },
  ],
  {
    agent: "service:llamaindex-demo",
    extraContext: { environment: "production" },
    onDeny: "tool-result",
    resultFormat: "object",
  },
);

async function main() {
  console.log("AtlaSent + LlamaIndex Guard Demo (v1.6.0)\n");

  for (const tool of tools) {
    const name = tool.metadata.name;
    console.log(`Running tool: ${name}`);

    try {
      const input =
        name === "vector_search"
          ? { query: "governance policy evaluation", topK: 3 }
          : { id: "doc_003", text: "New compliance documentation entry." };

      const result = await tool.execute(input as Record<string, unknown>);
      const r = result as Record<string, unknown>;

      if (r.denied) {
        console.log(`  Denied:     ${r.reason}`);
        console.log(`  Evaluation: ${r.evaluationId}`);
      } else {
        console.log(`  Result: ${JSON.stringify(result)}`);
        if (r._atlasent_permit_id) {
          console.log(`  Permit: ${String(r._atlasent_permit_id).slice(0, 16)}...`);
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
