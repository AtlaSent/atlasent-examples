// v2/typescript/evaluate-basic
//
// Basic single evaluation against POST /v1-evaluate via @atlasent/sdk.
//
// Run (live):
//   ATLASENT_API_URL=https://api.atlasent.io/functions/v1 \
//   ATLASENT_API_KEY=ask_live_xx \
//   npx tsx index.ts        # or: npm start
//
// Run (dry-run / smoke — no live API keys needed):
//   ATLASENT_DRY_RUN=true npx tsx index.ts
//   # or: npm run smoke

// ---------------------------------------------------------------------------
// Config — dry-run mode stubs the SDK + network call entirely.
// ---------------------------------------------------------------------------

const DRY_RUN = process.env.ATLASENT_DRY_RUN === 'true';

interface EvalSummary {
  decision: string;
  riskClass?: string;
  riskScore?: number;
  permitId?: string | null;
  requiresApproval?: boolean;
}

async function evaluateOnce(): Promise<EvalSummary> {
  if (DRY_RUN) {
    // Dry-run stub — no SDK client, no network. Mirror the live shape.
    return {
      decision: 'allow',
      riskClass: 'medium',
      riskScore: 62,
      permitId: 'permit_dryrun_001',
      requiresApproval: false,
    };
  }

  // Live path — construct the real SDK client only when not in dry-run, so
  // the dry-run smoke path never imports @atlasent/sdk or hits the network.
  const { AtlaSentClient } = await import('@atlasent/sdk');
  const client = new AtlaSentClient({
    apiKey: required('ATLASENT_API_KEY'),
    baseUrl: process.env.ATLASENT_API_URL ?? 'https://api.atlasent.io/functions/v1',
  });

  const result = await client.evaluate({
    agent: 'user-123',
    action: 'data.export',
    explain: true,
    environment: 'production',
    context: {
      email: 'alice@example.com',
      resource_id: 'dataset-456',
      sensitivity: 'confidential',
    },
  });

  return {
    decision: result.decision,
    riskClass: result.riskClass,
    riskScore: result.riskEnvelope?.weightedScore,
    permitId: result.permitToken,
    requiresApproval: result.decision === 'hold' || result.decision === 'escalate',
  };
}

async function main(): Promise<void> {
  console.log('=== Basic Evaluation Example ===\n');
  if (DRY_RUN) {
    console.log('[dry-run] AtlaSent SDK + network call stubbed — no API key required\n');
  }

  const result = await evaluateOnce();

  console.log(`Decision:    ${result.decision}`);
  if (result.riskClass !== undefined || result.riskScore !== undefined) {
    console.log(`Risk Level:  ${result.riskClass ?? 'n/a'} (score: ${result.riskScore ?? 'n/a'})`);
  }
  if (result.permitId) console.log(`Permit ID:   ${result.permitId}`);
  if (result.requiresApproval) console.log('⚠ Approval required before proceeding');

  if (DRY_RUN) console.log('\n[dry-run] smoke test passed');
}

function required(key: string): string {
  const v = process.env[key];
  if (!v) throw new Error(`Missing required env var: ${key}`);
  return v;
}

main().catch((err) => {
  console.error(err instanceof Error ? err.message : String(err));
  process.exitCode = 1;
});
