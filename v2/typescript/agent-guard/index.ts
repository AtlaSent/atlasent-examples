// v2/typescript/agent-guard
//
// Authorize-before-execute for agent tool calls, built directly on the
// published @atlasent/sdk. Every tool call runs evaluate → verifyPermit
// (fail-closed) before the tool's real implementation executes.
//
// This inlines a small `agentGuard` factory so the example depends only on
// @atlasent/sdk. (The reusable @atlasent/action connector package is not yet
// published to npm; once it is, the same surface ships as a library.)
//
// Shows:
//   - agentGuard(client) factory with blockOnHold:true
//   - guard.wrap(tool, ctx) to wrap a single tool
//   - guard.wrapAll(tools, ctx) to guard an entire toolkit
//   - guard.call(tool, args, ctx) one-shot
//   - Catching AgentGuardError and reading .decision / .toolName
//   - Actor resolution: agentId → userId → defaultActorId
//
// Run (live):
//   ATLASENT_API_URL=https://api.atlasent.io/functions/v1 \
//   ATLASENT_API_KEY=ask_live_xx \
//   npx tsx index.ts        # or: npm start
//
// Run (dry-run / smoke — no live API keys needed):
//   ATLASENT_DRY_RUN=true npm run smoke
//   # or: npm run smoke

const DRY_RUN = process.env.ATLASENT_DRY_RUN === 'true';

function required(key: string): string {
  const v = process.env[key];
  if (!v) throw new Error(`Missing required env var: ${key}`);
  return v;
}

// ---------------------------------------------------------------------------
// Tool + context types (local — these would come from @atlasent/action once
// that connector package is published).
// ---------------------------------------------------------------------------

interface AgentTool<Args, Result> {
  name: string;
  description: string;
  call(args: Args): Promise<Result>;
}

interface AgentCallContext {
  agentId?: string;
  userId?: string;
  sessionId?: string;
}

type GuardDecision = 'deny' | 'hold' | 'escalate' | 'error';

// AgentGuardError carries structured fields for the agent loop to react to.
class AgentGuardError extends Error {
  readonly decision: GuardDecision;
  readonly toolName: string;
  readonly evaluationId?: string;
  constructor(opts: { decision: GuardDecision; toolName: string; evaluationId?: string; message: string }) {
    super(opts.message);
    this.name = 'AgentGuardError';
    this.decision = opts.decision;
    this.toolName = opts.toolName;
    this.evaluationId = opts.evaluationId;
  }
}

// ---------------------------------------------------------------------------
// Sample agent tools (LangChain-style).
// ---------------------------------------------------------------------------

const webSearchTool: AgentTool<{ query: string }, string> = {
  name: 'web_search',
  description: 'Search the web for a query and return a summary.',
  async call({ query }) {
    return `Search results for "${query}": [stub result]`;
  },
};

const codeExecuteTool: AgentTool<{ code: string; language: string }, string> = {
  name: 'code_execute',
  description: 'Execute a code snippet in a sandboxed environment.',
  async call({ code, language }) {
    return `[${language}] executed: ${code.slice(0, 40)}...`;
  },
};

const emailSendTool: AgentTool<{ to: string; subject: string; body: string }, string> = {
  name: 'email_send',
  description: 'Send an email to a recipient.',
  async call({ to, subject }) {
    return `Email queued to ${to} (subject: ${subject})`;
  },
};

// ---------------------------------------------------------------------------
// agentGuard factory — built on @atlasent/sdk.
//
// `client` is an AtlaSentClient. For each guarded tool call we:
//   1. evaluate({ agent, action, context })  → decision + permitToken
//   2. if allow + permit: verifyPermit({ permitId })  → fail-closed on !verified
//   3. only then run the tool's real implementation
// Anything else throws AgentGuardError (caught by the agent loop).
//
// Actor resolution order: ctx.agentId → ctx.userId → defaultActorId.
// ---------------------------------------------------------------------------

interface AgentGuardConfig {
  blockOnHold?: boolean;       // throw on hold (default true)
  defaultActorId?: string;     // fallback actor (default 'agent:unknown')
  environment?: string;        // forwarded to AtlaSent
}

// `client` is typed structurally so this file needs no value import at the top
// level — the real AtlaSentClient is imported dynamically in the live branch.
interface EvaluatingClient {
  evaluate(req: {
    agent: string;
    action: string;
    context?: Record<string, unknown>;
    environment?: string;
  }): Promise<{ decision: string; permitToken?: string | null; evaluationId?: string }>;
  verifyPermit(req: {
    permitId: string;
    action?: string;
    agent?: string;
    environment?: string;
  }): Promise<{ verified: boolean }>;
}

function agentGuard(client: EvaluatingClient, config: AgentGuardConfig = {}) {
  const blockOnHold = config.blockOnHold ?? true;
  const defaultActor = config.defaultActorId ?? 'agent:unknown';
  const environment = config.environment;

  function resolveActor(ctx?: AgentCallContext): string {
    if (ctx?.agentId) return `agent:${ctx.agentId}`;
    if (ctx?.userId) return `user:${ctx.userId}`;
    return defaultActor;
  }

  async function authorize<Args, Result>(
    tool: AgentTool<Args, Result>,
    args: Args,
    ctx?: AgentCallContext,
  ): Promise<Result> {
    const actor = resolveActor(ctx);
    const evaluation = await client.evaluate({
      agent: actor,
      action: `tool.${tool.name}`,
      environment,
      context: { ...(ctx ?? {}), tool: tool.name },
    });

    const blocked =
      evaluation.decision === 'deny' ||
      evaluation.decision === 'escalate' ||
      (evaluation.decision === 'hold' && blockOnHold);

    if (blocked) {
      throw new AgentGuardError({
        decision: evaluation.decision as GuardDecision,
        toolName: tool.name,
        evaluationId: evaluation.evaluationId,
        message: `tool ${tool.name} blocked: decision=${evaluation.decision}`,
      });
    }

    // Fail-closed: an allow is only honored once the permit verifies.
    if (evaluation.decision === 'allow') {
      if (!evaluation.permitToken) {
        throw new AgentGuardError({
          decision: 'error',
          toolName: tool.name,
          evaluationId: evaluation.evaluationId,
          message: `tool ${tool.name} allowed without a permit — blocking`,
        });
      }
      const verification = await client.verifyPermit({
        permitId: evaluation.permitToken,
        action: `tool.${tool.name}`,
        agent: actor,
        environment,
      });
      if (!verification.verified) {
        throw new AgentGuardError({
          decision: 'error',
          toolName: tool.name,
          evaluationId: evaluation.evaluationId,
          message: `tool ${tool.name} permit failed verification — blocking`,
        });
      }
    }

    return tool.call(args);
  }

  return {
    wrap<Args, Result>(tool: AgentTool<Args, Result>, ctx?: AgentCallContext) {
      return { call: (args: Args) => authorize(tool, args, ctx) };
    },
    wrapAll(tools: Array<AgentTool<never, unknown>>, ctx?: AgentCallContext) {
      return tools.map((tool) => ({ call: (args: never) => authorize(tool, args, ctx) }));
    },
    call: authorize,
  };
}

type AgentGuard = ReturnType<typeof agentGuard>;

// ---------------------------------------------------------------------------
// Examples
// ---------------------------------------------------------------------------

async function singleToolExample(guard: AgentGuard): Promise<void> {
  const ctx: AgentCallContext = {
    agentId: 'planner-v1',
    sessionId: 'session-abc123',
    userId: 'alice@example.com', // forwarded, but agentId wins for the actor
  };
  const guardedSearch = guard.wrap(webSearchTool, ctx);
  try {
    const result = await guardedSearch.call({ query: 'quarterly revenue forecast' });
    console.log(`[web_search] result: ${result}`);
  } catch (err) {
    if (err instanceof AgentGuardError) {
      console.warn(`[web_search] BLOCKED — decision=${err.decision} tool=${err.toolName}`);
      if (err.evaluationId) console.warn(`             evaluation_id=${err.evaluationId}`);
    } else {
      throw err;
    }
  }
}

async function toolkitExample(guard: AgentGuard): Promise<void> {
  const ctx: AgentCallContext = { agentId: 'executor-v2', sessionId: 'session-def456' };
  const [guardedSearch, guardedExecute, guardedEmail] = guard.wrapAll(
    [webSearchTool, codeExecuteTool, emailSendTool] as unknown as Array<AgentTool<never, unknown>>,
    ctx,
  );

  const toolCalls = [
    { tool: guardedSearch, name: 'web_search', args: { query: 'TypeScript best practices' } },
    { tool: guardedExecute, name: 'code_execute', args: { code: 'console.log("hello")', language: 'typescript' } },
    { tool: guardedEmail, name: 'email_send', args: { to: 'team@example.com', subject: 'Results', body: 'See attached.' } },
  ];

  for (const { tool, name, args } of toolCalls) {
    try {
      const result = await tool.call(args as never);
      console.log(`[${name}] OK: ${result}`);
    } catch (err) {
      if (err instanceof AgentGuardError) {
        console.warn(`[${name}] BLOCKED`);
        console.warn(`  decision:      ${err.decision}`);
        console.warn(`  toolName:      ${err.toolName}`);
        console.warn(`  message:       ${err.message}`);
        if (err.evaluationId) console.warn(`  evaluation_id: ${err.evaluationId}`);
      } else {
        throw err;
      }
    }
  }
}

async function directCallExample(guard: AgentGuard): Promise<void> {
  try {
    const result = await guard.call(
      webSearchTool,
      { query: 'open source LLM benchmarks' },
      { agentId: 'research-agent', sessionId: 'session-ghi789' },
    );
    console.log(`[direct call] result: ${result}`);
  } catch (err) {
    if (err instanceof AgentGuardError) {
      console.warn(`[direct call] BLOCKED — decision=${err.decision} tool=${err.toolName}`);
    } else {
      throw err;
    }
  }
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

async function main(): Promise<void> {
  console.log('=== agentGuard Example ===\n');

  if (DRY_RUN) {
    // Dry-run stub — no SDK client, no network. Print the API surface and exit.
    console.log('[dry-run] AtlaSent SDK + network calls stubbed — no API key required');
    console.log('[dry-run] agentGuard configured — blockOnHold=true, defaultActorId=agent:planner-v1');
    console.log('[dry-run]');
    console.log('[dry-run] API surface:');
    console.log('[dry-run]   const guard = agentGuard(client, { blockOnHold: true, defaultActorId })');
    console.log('[dry-run]   const wrapped = guard.wrap(tool, ctx)        // single tool');
    console.log('[dry-run]   const tools   = guard.wrapAll(tools, ctx)    // entire toolkit');
    console.log('[dry-run]   const result  = await guard.call(tool, args, ctx)  // one-shot');
    console.log('[dry-run]');
    console.log('[dry-run] Each call runs evaluate → verifyPermit (fail-closed) before the tool.');
    console.log('[dry-run] Actor resolution: ctx.agentId → ctx.userId → defaultActorId');
    console.log('[dry-run] AgentGuardError carries .decision / .toolName / .evaluationId');
    console.log('[dry-run] smoke test passed');
    return;
  }

  // Live path — construct the real SDK client only outside dry-run, so the
  // dry-run smoke path never imports @atlasent/sdk or hits the network.
  const { AtlaSentClient } = await import('@atlasent/sdk');
  const client = new AtlaSentClient({
    apiKey: required('ATLASENT_API_KEY'),
    baseUrl: process.env.ATLASENT_API_URL ?? 'https://api.atlasent.io/functions/v1',
  }) as unknown as EvaluatingClient;

  const guard = agentGuard(client, {
    blockOnHold: true,
    defaultActorId: 'agent:planner-v1',
    environment: 'production',
  });

  console.log('--- Example 1: guard.wrap(tool) ---');
  await singleToolExample(guard);

  console.log('\n--- Example 2: guard.wrapAll(tools) ---');
  await toolkitExample(guard);

  console.log('\n--- Example 3: guard.call(tool, args, ctx) ---');
  await directCallExample(guard);
}

main().catch((err) => {
  console.error(err instanceof Error ? err.message : String(err));
  process.exitCode = 1;
});
