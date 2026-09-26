/**
 * src/evaluate.ts — AtlaSent agent tool call evaluator
 *
 * Reads TOOL_NAME, TOOL_ARGS, AGENT_ID, SESSION_ID from environment.
 * Calls atlasent.protect() with action string `agent_tool.<toolName>`.
 * Writes decision, permit_id, audit_hash, reason to $GITHUB_OUTPUT.
 *
 * Exit codes:
 *   0 — evaluation complete (any decision, including DENY — caller checks decision output)
 *   1 — AtlaSent unavailable (fail-closed: treat as DENY)
 *   2 — configuration error (missing env vars)
 */
import { appendFileSync } from "node:fs";
import atlasent, { AtlaSentDeniedError, AtlaSentError } from "@atlasent/sdk";

// The SDK's built-in default base URL is the bare host; the AtlaSent API is
// served under /functions/v1, so set it explicitly.
atlasent.configure({ baseUrl: process.env.ATLASENT_API_URL ?? "https://api.atlasent.io/functions/v1" });

const TOOL_NAME   = process.env.TOOL_NAME;
const TOOL_ARGS   = process.env.TOOL_ARGS ?? "{}";
const AGENT_ID    = process.env.AGENT_ID;
const SESSION_ID  = process.env.SESSION_ID;
const GITHUB_OUTPUT = process.env.GITHUB_OUTPUT ?? "";

if (!TOOL_NAME) {
  console.error("[evaluate] TOOL_NAME is required");
  process.exit(2);
}
if (!AGENT_ID) {
  console.error("[evaluate] AGENT_ID is required");
  process.exit(2);
}

/** Write a key=value pair to $GITHUB_OUTPUT. */
function setOutput(key: string, value: string): void {
  if (GITHUB_OUTPUT) {
    appendFileSync(GITHUB_OUTPUT, `${key}=${value}\n`, "utf8");
  } else {
    // Fallback for local testing
    console.log(`[output] ${key}=${value}`);
  }
}

async function main(): Promise<void> {
  let toolArgs: Record<string, unknown>;
  try {
    toolArgs = JSON.parse(TOOL_ARGS);
  } catch {
    console.error(`[evaluate] TOOL_ARGS is not valid JSON: ${TOOL_ARGS}`);
    process.exit(2);
  }

  console.log(`[evaluate] tool=${TOOL_NAME} agent=${AGENT_ID} session=${SESSION_ID}`);

  try {
    const permit = await atlasent.protect({
      agent: `github-actions:${AGENT_ID}`,
      action: `agent_tool.${TOOL_NAME}`,
      context: {
        toolName: TOOL_NAME,
        toolArgs,
        agentId: AGENT_ID,
        sessionId: SESSION_ID,
      },
    });

    console.log(`[evaluate] ALLOW permit=${permit.permitId} hash=${permit.auditHash ?? ""}`);
    setOutput("decision", "ALLOW");
    setOutput("permit_id", permit.permitId ?? "");
    setOutput("audit_hash", permit.auditHash ?? "");
    setOutput("reason", permit.reason ?? "");
    process.exit(0);

  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      const reason = err.reason ?? err.message;
      const evalId = err.evaluationId ?? "";
      console.log(`[evaluate] DENY reason=${reason} evaluation_id=${evalId}`);
      setOutput("decision", "DENY");
      setOutput("permit_id", "");
      setOutput("audit_hash", "");
      setOutput("reason", reason);
      // Exit 0 — the workflow step is not a failure; the decision gate is in the
      // "Execute tool (if permitted)" step which uses `if: outputs.decision == 'ALLOW'`.
      process.exit(0);
    }

    if (err instanceof AtlaSentError) {
      // Transport / server failure — fail-closed: treat as DENY
      console.error(`[evaluate] AtlaSent unavailable (code=${err.code}): ${err.message}`);
      setOutput("decision", "DENY");
      setOutput("permit_id", "");
      setOutput("audit_hash", "");
      setOutput("reason", `atlasent_unavailable: ${err.code}`);
      process.exit(1);
    }

    throw err;
  }
}

main().catch((err) => {
  console.error("[evaluate] unexpected error:", err);
  process.exit(1);
});
