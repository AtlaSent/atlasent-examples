// v2/typescript/authorize-many
//
// Batch authorization over @atlasent/sdk. The SDK has no `authorizeMany`
// convenience; this example fans out over the real `evaluate()` method (one
// call per action), or uses the `evaluateBatch()` round-trip when
// ATLASENT_V2_BATCH=true and the `v2_batch` tenant flag is enabled.
//
// Run (live):
//   ATLASENT_API_URL=https://api.atlasent.io/functions/v1 \
//   ATLASENT_API_KEY=ask_live_xx \
//   npx tsx index.ts        # or: npm start
//
// Run (dry-run / smoke — no live API keys needed):
//   ATLASENT_DRY_RUN=true npx tsx index.ts
//   # or: npm run smoke

const DRY_RUN = process.env.ATLASENT_DRY_RUN === 'true';
const V2_BATCH = process.env.ATLASENT_V2_BATCH === 'true';

const ACTIONS = [
  'tool.web_search',
  'tool.code_execute',
  'data.read',
  'data.write',
  'model.invoke',
] as const;

interface Row {
  action: string;
  decision: string;
  riskLevel?: string;
}

async function authorizeMany(): Promise<Row[]> {
  if (DRY_RUN) {
    // Dry-run stub — no SDK client, no network. Representative decisions.
    const stub: Record<string, [string, string]> = {
      'tool.web_search': ['allow', 'low'],
      'tool.code_execute': ['deny', 'high'],
      'data.read': ['allow', 'medium'],
      'data.write': ['hold', 'high'],
      'model.invoke': ['allow', 'low'],
    };
    return ACTIONS.map((action) => ({
      action,
      decision: stub[action][0],
      riskLevel: stub[action][1],
    }));
  }

  // Live path — construct the real SDK client only outside dry-run.
  const { AtlaSentClient } = await import('@atlasent/sdk');
  const client = new AtlaSentClient({
    apiKey: required('ATLASENT_API_KEY'),
    baseUrl: process.env.ATLASENT_API_URL ?? 'https://api.atlasent.io/functions/v1',
  });

  const agent = 'agent-001';
  const requests = ACTIONS.map((action) => ({
    agent,
    action,
    context: { environment: 'production' },
  }));

  if (V2_BATCH) {
    // Single round-trip; requires the org's `v2_batch` feature flag.
    // evaluateBatch returns { items } in input order; per-item `decision`
    // may be absent on an item-level error (surfaced via item.error).
    const batch = await client.evaluateBatch(requests);
    return batch.items.map((item, i) => ({
      action: ACTIONS[i],
      decision: item.decision ?? (item.error ? `error:${item.error}` : 'unknown'),
      riskLevel: undefined,
    }));
  }

  // Per-action fan-out over the canonical evaluate() method.
  const rows = await Promise.all(
    requests.map(async (req, i) => {
      const r = await client.evaluate(req);
      return { action: ACTIONS[i], decision: r.decision, riskLevel: r.riskClass };
    }),
  );
  return rows;
}

async function main(): Promise<void> {
  console.log('=== Batch Authorization Example ===\n');
  if (DRY_RUN) {
    console.log('[dry-run] AtlaSent SDK + network calls stubbed — no API key required\n');
  }

  const rows = await authorizeMany();

  console.log('Action'.padEnd(25) + 'Decision'.padEnd(12) + 'Risk');
  console.log('─'.repeat(50));
  for (const row of rows) {
    console.log(row.action.padEnd(25) + row.decision.padEnd(12) + (row.riskLevel ?? 'n/a'));
  }

  const allowed = rows.filter((r) => r.decision === 'allow').length;
  console.log(`\n${allowed}/${rows.length} actions allowed`);

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
