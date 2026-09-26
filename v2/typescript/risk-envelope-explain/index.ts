// v2/typescript/risk-envelope-explain
//
// Shows how to call POST /v1-evaluate with explain:true and read back the
// risk_envelope response. The risk_envelope is always present on v1-evaluate
// responses; the factors array is populated only when explain=true.
//
// Run (live):
//   ATLASENT_API_URL=https://api.atlasent.io/functions/v1 \
//   ATLASENT_API_KEY=ask_live_xx \
//   npm install && npm start
//
// Run (dry-run / smoke — no live API keys needed):
//   ATLASENT_DRY_RUN=true npm run smoke
//   # or: npm run smoke

// ---------------------------------------------------------------------------
// Types (mirrors the wire shapes in @atlasent/types)
// ---------------------------------------------------------------------------

type Decision = 'allow' | 'deny' | 'hold' | 'escalate';

interface FactorEval {
  factor: string;
  value: number;
  weight: number;
  reason: string;
}

interface RiskEnvelope {
  weighted_score: number;
  engine_decision: Decision;
  envelope_decision: Decision;
  /** true when the envelope overrode the rules-engine decision */
  promoted: boolean;
  /** Deny codes that force decision='deny' regardless of other signals. */
  hard_blocks: string[];
  /** Per-factor audit trace — only present when the request included explain:true */
  factors?: FactorEval[];
}

interface EvaluateResponse {
  decision: Decision;
  evaluation_id?: string;
  permit_token?: string;
  deny_reason?: string;
  hold_reason?: string;
  risk_score?: number;
  /** Structured risk envelope. Present on all v1-evaluate responses. */
  risk_envelope?: RiskEnvelope;
}

// ---------------------------------------------------------------------------
// Config — read from env; dry-run mode stubs the AtlaSent network call
// ---------------------------------------------------------------------------

const DRY_RUN = process.env.ATLASENT_DRY_RUN === 'true';
const API_URL = DRY_RUN
  ? 'https://api.atlasent.io/functions/v1' // not called in dry-run
  : (process.env.ATLASENT_API_URL ?? 'https://api.atlasent.io/functions/v1');
const API_KEY = DRY_RUN ? 'dry-run' : required('ATLASENT_API_KEY');

// ---------------------------------------------------------------------------
// Thin HTTP helper
// ---------------------------------------------------------------------------

async function callEvaluate(
  actionType: string,
  actorId: string,
  context: Record<string, unknown> = {},
): Promise<EvaluateResponse> {
  if (DRY_RUN) {
    // Dry-run stub: return a mock response with a realistic risk_envelope.
    return {
      decision: 'allow',
      evaluation_id: 'eval_dryrun_001',
      permit_token: 'pt_dryrun_xxx',
      risk_score: 62,
      risk_envelope: {
        weighted_score: 0.62,
        engine_decision: 'allow',
        envelope_decision: 'allow',
        promoted: false,
        hard_blocks: [],
        factors: [
          { factor: 'ACTION_SENSITIVITY', value: 0.8, weight: 0.3, reason: 'production.deploy is a high-sensitivity action class' },
          { factor: 'ACTOR_AUTHORITY',    value: 0.9, weight: 0.25, reason: 'actor has active authority grant for prod:deploy scope' },
          { factor: 'ENVIRONMENT',        value: 0.9, weight: 0.2,  reason: 'target environment is production' },
          { factor: 'CONTEXT_ANOMALY',    value: 0.1, weight: 0.15, reason: 'request matches known deployment window' },
          { factor: 'HISTORY',            value: 0.2, weight: 0.1,  reason: 'actor has 14 successful deploys in last 30 days' },
        ],
      },
    };
  }

  const res = await fetch(`${API_URL}/v1-evaluate`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${API_KEY}`,
    },
    body: JSON.stringify({
      action_type: actionType,
      actor_id: actorId,
      explain: true,
      context,
    }),
  });

  if (!res.ok) {
    throw new Error(`POST /v1-evaluate → HTTP ${res.status}: ${await res.text()}`);
  }
  return res.json() as Promise<EvaluateResponse>;
}

// ---------------------------------------------------------------------------
// Pretty-print helpers
// ---------------------------------------------------------------------------

function printRiskEnvelope(envelope: RiskEnvelope | undefined): void {
  if (!envelope) {
    console.log('  risk_envelope: (absent — older API version or not returned)');
    return;
  }

  console.log(`  weighted_score:    ${(envelope.weighted_score * 100).toFixed(1)}/100`);
  console.log(`  engine_decision:   ${envelope.engine_decision}`);
  console.log(`  envelope_decision: ${envelope.envelope_decision}`);

  // Check whether the envelope overrode the rules-engine decision.
  if (envelope.promoted) {
    console.log(`  promoted:          YES — envelope overrode engine`);
    console.log(`    (engine said ${envelope.engine_decision}, envelope resolved ${envelope.envelope_decision})`);
  } else {
    console.log(`  promoted:          no`);
  }

  // Absolute blocks — if present, any of these alone forces deny.
  if (envelope.hard_blocks.length > 0) {
    console.log(`  hard_blocks:       ${envelope.hard_blocks.join(', ')}`);
  } else {
    console.log(`  hard_blocks:       (none)`);
  }

  // Per-factor breakdown — only present when explain=true was sent.
  if (envelope.factors && envelope.factors.length > 0) {
    console.log('\n  Per-factor scores (explain=true):');
    for (const f of envelope.factors) {
      const contrib = (f.value * f.weight * 100).toFixed(1);
      console.log(`    ${f.factor.padEnd(24)} value=${f.value.toFixed(2)}  weight=${f.weight.toFixed(2)}  contrib=${contrib}pts`);
      console.log(`      reason: ${f.reason}`);
    }
  } else {
    console.log('  factors:           (absent — pass explain:true to receive per-factor trace)');
  }
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main(): Promise<void> {
  console.log('=== risk_envelope + explain Example ===\n');
  if (DRY_RUN) {
    console.log('[dry-run] AtlaSent network call is stubbed — no API key required\n');
  }

  const result = await callEvaluate(
    'production.deploy',
    'ci-runner:github-actions',
    { service: 'checkout-api', environment: 'production', ref: 'refs/heads/main' },
  );

  // Top-level decision
  console.log(`Decision:        ${result.decision}`);
  if (result.evaluation_id) console.log(`Evaluation ID:   ${result.evaluation_id}`);
  if (result.deny_reason)   console.log(`Deny reason:     ${result.deny_reason}`);
  if (result.hold_reason)   console.log(`Hold reason:     ${result.hold_reason}`);
  console.log('');

  // Risk envelope
  console.log('risk_envelope:');
  printRiskEnvelope(result.risk_envelope);
  console.log('');

  // Gate on the outcome
  if (result.decision !== 'allow') {
    console.log(`Blocked: ${result.deny_reason ?? result.hold_reason ?? result.decision}`);
    process.exitCode = 1;
    return;
  }

  if (DRY_RUN) {
    console.log('[dry-run] smoke test passed');
  } else {
    console.log('Permitted — proceed with deployment.');
  }
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
