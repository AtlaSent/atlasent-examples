/**
 * src/execute.ts — Stub tool executor
 *
 * Only reached when evaluate.ts outputs decision=ALLOW.
 * Reads TOOL_NAME, TOOL_ARGS, PERMIT_ID from environment.
 *
 * Replace the stub dispatch below with actual tool execution.
 * The PERMIT_ID must be threaded through to the tool's execution context
 * for audit lineage — every privileged action should reference the permit
 * that authorized it.
 */

const TOOL_NAME  = process.env.TOOL_NAME;
const TOOL_ARGS  = process.env.TOOL_ARGS ?? "{}";
const PERMIT_ID  = process.env.PERMIT_ID ?? "";

if (!TOOL_NAME) {
  console.error("[execute] TOOL_NAME is required");
  process.exit(2);
}

let toolArgs: Record<string, unknown>;
try {
  toolArgs = JSON.parse(TOOL_ARGS);
} catch {
  console.error(`[execute] TOOL_ARGS is not valid JSON: ${TOOL_ARGS}`);
  process.exit(2);
}

console.log(`[execute] tool=${TOOL_NAME} permit=${PERMIT_ID}`);

// ---------------------------------------------------------------------------
// Tool dispatch — replace each case with actual tool execution
// ---------------------------------------------------------------------------

switch (TOOL_NAME) {
  case "bash": {
    // Replace with actual bash execution:
    // import { execSync } from "node:child_process";
    // const result = execSync(toolArgs.command as string, { encoding: "utf8" });
    console.log(`[execute] would run: bash ${JSON.stringify(toolArgs.command ?? toolArgs)}`);
    console.log(`[execute] (stub) bash execution simulated under permit ${PERMIT_ID}`);
    break;
  }

  case "read_file": {
    // Replace with actual file read:
    // import { readFileSync } from "node:fs";
    // const content = readFileSync(toolArgs.path as string, "utf8");
    console.log(`[execute] would read: ${toolArgs.path ?? JSON.stringify(toolArgs)}`);
    console.log(`[execute] (stub) read_file execution simulated under permit ${PERMIT_ID}`);
    break;
  }

  case "write_file": {
    // Replace with actual file write:
    // import { writeFileSync } from "node:fs";
    // writeFileSync(toolArgs.path as string, toolArgs.content as string, "utf8");
    console.log(`[execute] would write: ${toolArgs.path ?? JSON.stringify(toolArgs)}`);
    console.log(`[execute] (stub) write_file execution simulated under permit ${PERMIT_ID}`);
    break;
  }

  default: {
    // Replace with a plugin loader or error for unknown tools
    console.log(`[execute] would execute tool: ${TOOL_NAME} args=${JSON.stringify(toolArgs)}`);
    console.log(`[execute] (stub) ${TOOL_NAME} execution simulated under permit ${PERMIT_ID}`);
    break;
  }
}

console.log(`[execute] done — permit ${PERMIT_ID} will be consumed in consume.ts`);
