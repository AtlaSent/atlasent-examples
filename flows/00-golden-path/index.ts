import { AtlaSentClient } from '@atlasent/sdk';
import type { EvaluateResponse } from '@atlasent/sdk';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

type Scenario = {
  id: string;
  title: string;
  narrative: string;
  expect: 'allow' | 'deny';
  request: {
    actor: Record<string, unknown> & { id?: string };
    action: Record<string, unknown> & { type: string; description: string };
    target: Record<string, unknown>;
    context?: Record<string, unknown>;
  };
};

const here = dirname(fileURLToPath(import.meta.url));
const seed = JSON.parse(readFileSync(join(here, 'scenarios.json'), 'utf8')) as {
  scenarios: Scenario[];
};

const paceMs = Number(process.env.GOLDEN_PATH_PACE_MS ?? '1200');
const dryRun = process.env.GOLDEN_PATH_DRY_RUN === '1';

const apiKey = process.env.ATLASENT_API_KEY;
if (!apiKey && !dryRun) {
  console.error(
    'ATLASENT_API_KEY is required. Export it and re-run, or use GOLDEN_PATH_DRY_RUN=1 to rehearse.',
  );
  process.exit(1);
}

const client = apiKey
  ? new AtlaSentClient({
      baseUrl: process.env.ATLASENT_API_URL ?? 'https://api.atlasent.io/functions/v1',
      apiKey,
    })
  : null;

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function badge(decision: string) {
  const lower = decision.toLowerCase();
  if (lower === 'allow') return '✅ allow';
  if (lower === 'deny') return '⛔ deny';
  return `· ${lower}`;
}

async function runScenario(s: Scenario, index: number, total: number) {
  console.log(`\n── Scene ${index + 1}/${total} · ${s.id} ──`);
  console.log(s.title);
  console.log(`\n  ${s.narrative}\n`);

  if (dryRun || !client) {
    console.log(`  (dry-run) expect: ${badge(s.expect)}`);
    return { ok: true, decision: s.expect };
  }

  // Project the legacy actor/action/target scenario shape into the
  // v1 evaluate contract: { agent, action, context }. The actor and
  // target sub-shapes fold into context so the policy engine can
  // still branch on any of those fields.
  const actorId = String(s.request.actor.id ?? 'unknown');
  const actionType = String(s.request.action.type);
  const context: Record<string, unknown> = {
    ...(s.request.target as Record<string, unknown>),
    ...(s.request.context ?? {}),
    actor: s.request.actor,
    description: s.request.action.description,
  };

  // V1 EvaluateResponse fields:
  //   decision      – canonical lowercase: "allow" | "deny" | "hold" | "escalate"
  //   evaluationId  – stable ID present on both CP and SaaS runtimes
  //   permitToken   – returned when decision is "allow"; send to verify-permit
  //   reasons       – array of reason strings (replaces old singular "reason")
  const result: EvaluateResponse = await client.evaluate({
    agent: actorId,
    action: actionType,
    context,
  });

  const decision = result.decision.toLowerCase();
  console.log(`  decision:      ${badge(result.decision)}`);
  console.log(`  evaluationId:  ${result.evaluationId}`);

  // reasons is an array in V1
  const reasons = result.reasons ?? [];
  for (const r of reasons) {
    console.log(`  reason:        ${r}`);
  }

  if (decision === 'allow' && result.permitToken) {
    console.log(`  permitToken:   ${result.permitToken}`);
  }

  const ok = decision === s.expect;
  if (!ok) {
    console.log(`  ⚠ expected ${s.expect}, got ${decision}`);
  }
  return { ok, decision };
}

async function main() {
  const total = seed.scenarios.length;
  console.log('=== Golden-path demo seed ===');
  console.log(
    `${total} canonical scenarios. Pace ${paceMs}ms${dryRun ? ' · DRY-RUN' : ''}.`,
  );

  let mismatches = 0;
  for (let i = 0; i < total; i++) {
    const { ok } = await runScenario(seed.scenarios[i], i, total);
    if (!ok) mismatches++;
    if (i < total - 1) await sleep(paceMs);
  }

  console.log('\n── Done ──');
  if (mismatches > 0) {
    console.log(`⚠ ${mismatches} scenario(s) did not match expectation.`);
    process.exit(2);
  }
  console.log('All scenarios matched expected decisions.');
}

main().catch((err) => {
  console.error('Seed run failed:', err);
  process.exit(1);
});
