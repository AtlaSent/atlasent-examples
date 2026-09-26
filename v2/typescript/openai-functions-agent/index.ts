// v2/typescript/openai-functions-agent
//
// Minimal OpenAI Chat Completions agent with function-calling tool defs
// gated by AtlaSent evaluate. Each tool call is authorized via
// @atlasent/sdk before execution.
//
// Run (live):
//   ATLASENT_API_URL=https://api.atlasent.io/functions/v1 \
//   ATLASENT_API_KEY=ask_live_xx \
//   OPENAI_API_KEY=sk-... \
//   npx tsx index.ts        # or: npm start
//
// Run (dry-run / smoke — no live API keys needed):
//   ATLASENT_DRY_RUN=true npx tsx index.ts
//   # or: npm run smoke

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface AtlasentDecision {
  decision: "allow" | "deny" | "hold" | "escalate";
  reason?: string;
  permitToken?: string | null;
}

interface ToolCall {
  name: string;
  args: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Config — dry-run mode stubs the AtlaSent + OpenAI network calls entirely.
// Neither @atlasent/sdk nor openai is imported on the dry-run path.
// ---------------------------------------------------------------------------

const DRY_RUN = process.env.ATLASENT_DRY_RUN === "true";
const V2_BATCH = process.env.ATLASENT_V2_BATCH === "true";

// Tool definitions handed to the model. Each tool's `name` becomes the
// AtlaSent action id (`tool.<name>`).
const TOOL_DEFS = [
  {
    type: "function" as const,
    function: {
      name: "get_weather",
      description: "Get the current weather for a city",
      parameters: {
        type: "object",
        properties: { city: { type: "string" } },
        required: ["city"],
      },
    },
  },
  {
    type: "function" as const,
    function: {
      name: "send_email",
      description: "Send an email to the user",
      parameters: {
        type: "object",
        properties: {
          to: { type: "string" },
          subject: { type: "string" },
          body: { type: "string" },
        },
        required: ["to", "subject", "body"],
      },
    },
  },
];

// Local tool implementations — stand-ins for real integrations.
const impl: Record<string, (args: Record<string, unknown>) => string> = {
  get_weather: ({ city }) => `${city}: 72°F, sunny`,
  send_email: ({ to, subject }) => `email queued to ${to} (${subject})`,
};

// ---------------------------------------------------------------------------
// Authorization — per-call fan-out over the SDK's evaluate(), or evaluateBatch
// when ATLASENT_V2_BATCH=true. The SDK is imported lazily so the dry-run path
// never resolves the package.
// ---------------------------------------------------------------------------

async function authorizeBatch(
  toolCalls: ToolCall[],
  agent: string,
): Promise<AtlasentDecision[]> {
  if (DRY_RUN) {
    // Dry-run stub — always allow, no network / no SDK import.
    return toolCalls.map(() => ({ decision: "allow", reason: "dry-run stub" }));
  }

  const { AtlaSentClient } = await import("@atlasent/sdk");
  const client = new AtlaSentClient({
    apiKey: required("ATLASENT_API_KEY"),
    baseUrl: process.env.ATLASENT_API_URL ?? "https://api.atlasent.io/functions/v1",
  });

  const requests = toolCalls.map((tc) => ({
    agent,
    action: `tool.${tc.name}`,
    context: { resource: "agent-session", ...tc.args },
  }));

  if (V2_BATCH) {
    // Single round-trip; requires the org's `v2_batch` feature flag.
    const batch = await client.evaluateBatch(requests);
    return batch.items.map((item) => ({
      decision: item.decision ?? "deny",
      reason: item.reason ?? (item.error ? `error:${item.error}` : undefined),
      permitToken: item.permitToken ?? null,
    }));
  }

  // Per-call fan-out over the canonical evaluate() method.
  const out: AtlasentDecision[] = [];
  for (const req of requests) {
    const r = await client.evaluate(req);
    out.push({
      decision: r.decision,
      reason: r.reason,
      permitToken: r.permitToken,
    });
  }
  return out;
}

// ---------------------------------------------------------------------------
// Model — returns the tool calls the model wants to make. Dry-run simulates a
// fixed plan; live asks OpenAI (imported lazily).
// ---------------------------------------------------------------------------

async function modelToolCalls(prompt: string): Promise<ToolCall[]> {
  if (DRY_RUN) {
    console.log("[dry-run] skipping OpenAI call; simulating two tool calls");
    return [
      { name: "get_weather", args: { city: "Paris" } },
      {
        name: "send_email",
        args: {
          to: "alice@example.com",
          subject: "Weather summary",
          body: "72°F, sunny",
        },
      },
    ];
  }

  const { default: OpenAI } = await import("openai");
  const openai = new OpenAI();
  const completion = await openai.chat.completions.create({
    model: "gpt-4o-mini",
    messages: [{ role: "user", content: prompt }],
    tools: TOOL_DEFS,
  });
  const calls = completion.choices[0]?.message.tool_calls ?? [];
  return calls.map((c) => ({
    name: c.function.name,
    args: JSON.parse(c.function.arguments) as Record<string, unknown>,
  }));
}

async function runOnce(prompt: string, agent = "demo-agent"): Promise<string> {
  const parsed = await modelToolCalls(prompt);
  if (parsed.length === 0) return "";

  const decisions = await authorizeBatch(parsed, agent);

  return parsed
    .map((c, i) => {
      const d = decisions[i];
      if (!d || d.decision !== "allow") {
        return `denied ${c.name}: ${d?.reason ?? "no reason"}`;
      }
      return impl[c.name](c.args);
    })
    .join("\n");
}

function required(key: string): string {
  const v = process.env[key];
  if (!v) throw new Error(`Missing env var: ${key}`);
  return v;
}

// ---------------------------------------------------------------------------
// Entry point — runs under tsx / node / bun. (Avoid `import.meta.main`, which
// is undefined under Node + tsx.)
// ---------------------------------------------------------------------------

async function main(): Promise<void> {
  if (DRY_RUN) {
    console.log("[atlasent] dry-run mode — no live API keys needed");
  }
  const out = await runOnce(
    "What's the weather in Paris and email a summary to alice@example.com?",
  );
  console.log(out);
  if (DRY_RUN) console.log("[atlasent] dry-run smoke test passed");
}

main().catch((err) => {
  console.error(err instanceof Error ? err.message : String(err));
  process.exitCode = 1;
});
