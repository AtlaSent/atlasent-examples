/**
 * Minimal authorize-before-execute tool guard, built only on the published
 * `@atlasent/sdk` (`withPermit`). The framework guard packages
 * (@atlasent/langchain, @atlasent/llamaindex, @atlasent/cursor) are not on
 * npm yet, so this example carries the same pattern in ~50 lines.
 *
 * Contract: a tool's `execute` runs only after AtlaSent evaluated the call
 * AND the permit verified. Any denial, hold, or error means it does not run.
 */
import { AtlaSentDeniedError, withPermit } from "@atlasent/sdk";

/* eslint-disable @typescript-eslint/no-explicit-any -- tools take differently shaped inputs */
/** LangChain/Cursor style (`name`) or LlamaIndex style (`metadata.name`). */
export interface GuardableTool {
  name?: string;
  metadata?: { name: string };
  execute: (input: any) => Promise<any>;
}

export type GuardedTool<T> = Omit<T, "execute"> & { execute: (input: any) => Promise<any> };

function toolName(tool: GuardableTool): string {
  const name = tool.name ?? tool.metadata?.name;
  if (!name) throw new Error("tool has no name; refusing to guess an action type");
  return name;
}

export interface ToolGuardOptions {
  /** Who is acting, e.g. "service:langchain-demo". */
  agent: string;
  /**
   * Action type per tool. Defaults to the canonical "agent.tool.invoke"
   * (Canon ACT-0029), which requires context.tool and context.environment.
   * Action types must be dot-notation; a bare tool name is rejected.
   */
  action?: (toolName: string) => string;
  /** Extra context sent with every evaluation (e.g. environment). */
  extraContext?: Record<string, unknown>;
  /** "tool-result" returns a denial result instead of throwing. Default "throw". */
  onDeny?: "throw" | "tool-result";
  /** Shape of results: JSON strings (LangChain/Cursor style) or objects. Default "json-string". */
  resultFormat?: "json-string" | "object";
}

export function withToolGuard<T extends GuardableTool>(tools: T[], options: ToolGuardOptions): GuardedTool<T>[] {
  const asString = (options.resultFormat ?? "json-string") === "json-string";
  return tools.map((tool) => ({
    ...tool,
    execute: async (input: any): Promise<any> => {
      try {
        const name = toolName(tool);
        return await withPermit(
          {
            agent: options.agent,
            action: options.action ? options.action(name) : "agent.tool.invoke",
            context: { ...options.extraContext, tool: name, tool_input: input },
          },
          // Runs only after evaluate returned allow AND the permit verified.
          async (permit) => {
            const result = await tool.execute(input);
            if (typeof result === "string") {
              try {
                const parsed = JSON.parse(result) as unknown;
                if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
                  return JSON.stringify({ ...(parsed as object), _atlasent_permit_id: permit.permitId });
                }
              } catch {
                // non-JSON tool output is returned unchanged
              }
              return result;
            }
            if (result && typeof result === "object" && !Array.isArray(result)) {
              return { ...result, _atlasent_permit_id: permit.permitId };
            }
            return result;
          },
        );
      } catch (err) {
        if (err instanceof AtlaSentDeniedError && options.onDeny === "tool-result") {
          const denial = {
            denied: true as const,
            decision: err.decision,
            evaluationId: err.evaluationId,
            reason: err.reason ?? err.message,
          };
          return asString ? JSON.stringify(denial) : denial;
        }
        throw err;
      }
    },
  }));
}
