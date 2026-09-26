/**
 * Example: Agent Tool Execution Gate — LLM agent HITL
 *
 * Shows how to gate every tool call made by an autonomous agent.
 * - Low-risk tools (read_file, search) pass through with protect()
 * - High-risk tools (write_file, bash) route to HITL
 * - Critical tools (exec, deploy) require explicit human approval
 * - observe mode for unknown tools
 */
import {
  protectToolCall,
  classifyToolRisk,
  type AgentToolMode,
  configure,
} from "@atlasent/sdk";
import { EscalationDeniedError } from "@atlasent/sdk";

// The SDK's built-in default base URL is the bare host; the AtlaSent API is
// served under /functions/v1, so set it explicitly.
configure({ baseUrl: process.env.ATLASENT_API_URL ?? "https://api.atlasent.io/functions/v1" });

const agentId = "agent_gpt4o_session_7f3a";
const sessionId = "sess_abc123";

const toolCalls: Array<{ tool: string; args: Record<string, unknown>; mode?: AgentToolMode }> = [
  { tool: "read_file",   args: { path: "/etc/config.yaml" } },
  { tool: "write_file",  args: { path: "/tmp/output.txt", content: "hello" } },
  { tool: "bash",        args: { command: "rm -rf /tmp/scratch" } },
  { tool: "send_email",  args: { to: "cfo@acme.com", subject: "Report ready" } },
  { tool: "custom_tool", args: { value: 42 }, mode: "observe" },
];

for (const call of toolCalls) {
  const risk = classifyToolRisk(call.tool);
  console.log(`\nTool: ${call.tool} (risk=${risk})`);
  try {
    const result = await protectToolCall({
      toolName: call.tool,
      toolArgs: call.args,
      agentId,
      sessionId,
      mode: call.mode,
      assignedToRole: "agent-supervisor",
      waitMs: 10 * 60 * 1000,
      onEscalationCreated: (h) =>
        console.log(`  Escalated to supervisor: ${h.escalationId}`),
    });

    if ("would_have_blocked" in result) {
      // ShadowOutcome from observe mode
      console.log(`  Shadow: would_have_blocked=${result.would_have_blocked}, decision=${result.decision}`);
    } else if ("approvalBasis" in result) {
      // ApprovalPermit
      console.log(`  Approved: ${result.approvalBasis} (by ${result.resolvedBy ?? "policy"})`);
    } else {
      // Permit
      console.log(`  Permitted: ${result.permitId}`);
    }
  } catch (err) {
    if (err instanceof EscalationDeniedError) {
      console.error(`  BLOCKED by supervisor: ${err.outcome.resolutionNote ?? "denied"}`);
    } else {
      throw err;
    }
  }
}
