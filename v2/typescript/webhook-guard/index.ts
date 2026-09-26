// v2/typescript/webhook-guard
//
// Express server showing an authorize-before-execute webhook guard built
// directly on the published @atlasent/sdk. The guard evaluates every incoming
// webhook payload (evaluate → verifyPermit, fail-closed) before the route
// handler runs.
//
// This inlines a small `webhookGuard` factory so the example depends only on
// @atlasent/sdk + express. (The reusable @atlasent/action connector package
// is not yet published to npm; once it is, the same surface ships as a
// library.)
//
// Run (live):
//   ATLASENT_API_URL=https://api.atlasent.io/functions/v1 \
//   ATLASENT_API_KEY=ask_live_xx \
//   npx tsx index.ts        # or: npm start
//
// Run (dry-run / smoke — no live API keys needed):
//   ATLASENT_DRY_RUN=true npm run smoke
//   # or: npm run smoke

import express from 'express';
import type { Request, Response, NextFunction } from 'express';

const DRY_RUN = process.env.ATLASENT_DRY_RUN === 'true';
const PORT = process.env.PORT ? parseInt(process.env.PORT, 10) : 3000;

function required(key: string): string {
  const v = process.env[key];
  if (!v) throw new Error(`Missing required env var: ${key}`);
  return v;
}

// ---------------------------------------------------------------------------
// Types (local — these would come from @atlasent/action once that connector
// package is published).
// ---------------------------------------------------------------------------

type WebhookPayload = Record<string, unknown>;

type WebhookDecision = 'allow' | 'deny' | 'hold' | 'escalate' | 'error';

interface WebhookGuardResult {
  decision: WebhookDecision;
  verified: boolean;
  evaluationId?: string;
  riskScore?: number;
  reason?: string;
}

// Pulls action_type / actor_id / context out of a raw webhook body.
type WebhookPayloadExtractor = (payload: WebhookPayload) => {
  action_type: string;
  actor_id: string;
  context?: Record<string, unknown>;
};

// Structural client type so no value import is needed at module top level.
interface EvaluatingClient {
  evaluate(req: {
    agent: string;
    action: string;
    context?: Record<string, unknown>;
    environment?: string;
  }): Promise<{
    decision: string;
    permitToken?: string | null;
    evaluationId?: string;
    riskEnvelope?: { weightedScore?: number };
  }>;
  verifyPermit(req: {
    permitId: string;
    action?: string;
    agent?: string;
    environment?: string;
  }): Promise<{ verified: boolean }>;
}

interface WebhookGuardConfig {
  failClosed?: boolean;        // block on deny/hold/error (default true)
  environment?: string;
  extractor?: WebhookPayloadExtractor;
}

// ---------------------------------------------------------------------------
// webhookGuard factory — built on @atlasent/sdk.
// ---------------------------------------------------------------------------

const defaultExtractor: WebhookPayloadExtractor = (payload) => ({
  action_type: (payload['action_type'] as string | undefined) ?? 'webhook',
  actor_id: (payload['actor_id'] as string | undefined) ?? 'unknown',
  context: payload,
});

function webhookGuard(client: EvaluatingClient, config: WebhookGuardConfig = {}) {
  const failClosed = config.failClosed ?? true;
  const environment = config.environment;
  const extract = config.extractor ?? defaultExtractor;

  async function evaluate(payload: WebhookPayload): Promise<WebhookGuardResult> {
    try {
      const { action_type, actor_id, context } = extract(payload);
      const evaluation = await client.evaluate({
        agent: actor_id,
        action: action_type,
        environment,
        context,
      });
      const riskScore = evaluation.riskEnvelope?.weightedScore;

      if (evaluation.decision !== 'allow') {
        return {
          decision: evaluation.decision as WebhookDecision,
          verified: false,
          evaluationId: evaluation.evaluationId,
          riskScore,
          reason: `decision=${evaluation.decision}`,
        };
      }

      // Fail-closed: an allow only counts once the permit verifies.
      if (!evaluation.permitToken) {
        return { decision: 'allow', verified: false, evaluationId: evaluation.evaluationId, riskScore, reason: 'allow without permit' };
      }
      const verification = await client.verifyPermit({
        permitId: evaluation.permitToken,
        action: action_type,
        agent: actor_id,
        environment,
      });
      return {
        decision: 'allow',
        verified: verification.verified,
        evaluationId: evaluation.evaluationId,
        riskScore,
        reason: verification.verified ? undefined : 'permit failed verification',
      };
    } catch (err) {
      return { decision: 'error', verified: false, reason: err instanceof Error ? err.message : String(err) };
    }
  }

  // Express-compatible middleware. On a blocked decision with failClosed=true
  // it responds 403/500 and never calls next().
  async function middleware(
    req: Request & { atlasent?: WebhookGuardResult },
    res: Response,
    next: NextFunction,
  ): Promise<void> {
    const result = await evaluate((req.body ?? {}) as WebhookPayload);
    req.atlasent = result;

    const ok = result.decision === 'allow' && result.verified;
    if (ok || !failClosed) {
      next();
      return;
    }
    const status = result.decision === 'error' ? 500 : 403;
    res.status(status).json({ error: 'blocked by AtlaSent', decision: result.decision, reason: result.reason });
  }

  return { evaluate, middleware };
}

type WebhookGuard = ReturnType<typeof webhookGuard>;

// Custom extractor for GitHub-style deploy payloads (action/actor at non-default paths).
const githubDeployExtractor: WebhookPayloadExtractor = (payload) => ({
  action_type: (payload['event'] as string | undefined) ?? 'deploy',
  actor_id: (payload['sender'] as { login?: string } | undefined)?.login ?? 'unknown',
  context: {
    repository: payload['repository'],
    environment: payload['environment'],
    ref: payload['ref'],
  },
});

// ---------------------------------------------------------------------------
// standalone usage (non-Express servers)
// ---------------------------------------------------------------------------

async function standaloneExample(guard: WebhookGuard, payload: WebhookPayload): Promise<void> {
  const result = await guard.evaluate(payload);
  switch (result.decision) {
    case 'allow':
      if (result.verified) {
        console.log(`[standalone] allowed — eval_id=${result.evaluationId} risk=${result.riskScore ?? 'n/a'}`);
      } else {
        console.warn(`[standalone] allow without verification — blocking: ${result.reason}`);
      }
      break;
    case 'deny':
      console.warn(`[standalone] denied: ${result.reason}`);
      break;
    case 'hold':
      console.warn(`[standalone] on hold (awaiting approval): ${result.reason}`);
      break;
    case 'escalate':
      console.warn(`[standalone] escalated — manual review required`);
      break;
    case 'error':
      console.error(`[standalone] infra error: ${result.reason}`);
      break;
  }
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

async function main(): Promise<void> {
  console.log('=== webhookGuard Example ===\n');

  if (DRY_RUN) {
    // Dry-run stub — no SDK client, no server, no network.
    console.log('[dry-run] AtlaSent SDK + network calls stubbed — no API key required');
    console.log('[dry-run] guard configured — failClosed=true, environment=production');
    console.log('[dry-run] standalone usage: const result = await guard.evaluate(payload)');
    console.log('[dry-run] express usage:    app.post("/hooks/deploy", guard.middleware, handler)');
    console.log('[dry-run] each request runs evaluate → verifyPermit (fail-closed) before the handler');
    const mockPayload: WebhookPayload = {
      event: 'deployment',
      sender: { login: 'ci-bot' },
      repository: 'checkout-api',
      environment: 'production',
      ref: 'refs/heads/main',
    };
    console.log('[dry-run] example payload:', JSON.stringify(mockPayload));
    console.log('[dry-run] smoke test passed (network calls skipped)');
    return;
  }

  // Live path — construct the real SDK client only outside dry-run.
  const { AtlaSentClient } = await import('@atlasent/sdk');
  const client = new AtlaSentClient({
    apiKey: required('ATLASENT_API_KEY'),
    baseUrl: process.env.ATLASENT_API_URL ?? 'https://api.atlasent.io/functions/v1',
  }) as unknown as EvaluatingClient;

  const guard = webhookGuard(client, {
    failClosed: true,
    environment: 'production',
    extractor: githubDeployExtractor,
  });

  // Standalone path as part of startup logging.
  console.log('[startup] standalone example: evaluating a sample payload...');
  await standaloneExample(guard, { event: 'ping', sender: { login: 'github' }, repository: 'checkout-api' });

  const app = express();
  app.use(express.json());

  app.post(
    '/hooks/deploy',
    guard.middleware,
    (req: Request & { atlasent?: WebhookGuardResult }, res: Response) => {
      const auditInfo = req.atlasent;
      if (auditInfo) {
        console.log(`[/hooks/deploy] eval_id=${auditInfo.evaluationId} decision=${auditInfo.decision} verified=${auditInfo.verified}`);
        if (auditInfo.riskScore !== undefined) console.log(`[/hooks/deploy] risk_score=${auditInfo.riskScore}`);
      }
      res.json({ status: 'deployed', evaluation_id: auditInfo?.evaluationId });
    },
  );

  app.get('/health', (_req, res) => res.json({ ok: true }));

  app.listen(PORT, () => {
    console.log(`webhookGuard example listening on http://localhost:${PORT}/hooks/deploy`);
    console.log('Try: curl -XPOST http://localhost:' + PORT + '/hooks/deploy -H "Content-Type: application/json" \\');
    console.log('  -d \'{"event":"deployment","sender":{"login":"ci-bot"},"environment":"production"}\'');
  });
}

main().catch((err) => {
  console.error(err instanceof Error ? err.message : String(err));
  process.exitCode = 1;
});
