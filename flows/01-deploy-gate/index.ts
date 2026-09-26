const apiKey = process.env.ATLASENT_API_KEY;
if (!apiKey) {
  console.error('ATLASENT_API_KEY is required. Export it and re-run: export ATLASENT_API_KEY=...');
  process.exit(1);
}

const apiUrl = (process.env.ATLASENT_API_URL ?? 'https://api.atlasent.io/functions/v1').replace(/\/$/, '');
const service = process.env.SERVICE ?? 'checkout-api';
const targetEnv = process.env.TARGET_ENV ?? 'production';
const repository = process.env.GITHUB_REPOSITORY ?? 'local';
const actor = process.env.ACTOR ?? `ci-bot@${repository}`;
const ref = process.env.GITHUB_REF ?? 'refs/heads/main';
const sha = process.env.GITHUB_SHA ?? 'local-sha';
const action = 'production.deploy';

type Json = Record<string, unknown>;

async function post(path: string, body: Json): Promise<Json> {
  const response = await fetch(`${apiUrl}${path}`, {
    method: 'POST',
    headers: {
      authorization: `Bearer ${apiKey}`,
      'content-type': 'application/json',
    },
    body: JSON.stringify(body),
  });

  const text = await response.text();
  // Do not echo upstream bodies: a misconfigured proxy or debug handler could
  // reflect credentials or permit material into CI logs.
  if (!response.ok) throw new Error(`${path} failed with HTTP ${response.status}`);
  return text ? JSON.parse(text) : {};
}

function field(result: Json, ...keys: string[]): string {
  for (const key of keys) {
    const value = result[key];
    if (typeof value === 'string' && value.length > 0) return value;
  }
  return '';
}

async function main() {
  console.log('=== 01 · Deploy Gate V1 ===\n');
  console.log(`Service : ${service}`);
  console.log(`Target  : ${targetEnv}`);
  console.log(`Actor   : ${actor}`);
  console.log(`Action  : ${action}\n`);

  console.log('Step 1/7 connect CI: env loaded.');
  console.log('Step 2/7 declare action: production.deploy.');

  const context = {
    service,
    target_id: service,
    target: { id: service },
    environment: targetEnv,
    repo: repository,
    ref,
    commit_sha: sha,
  };
  const changePlan = {
    operation: 'deploy',
    revision: sha,
  };

  console.log('Step 3/7 evaluate: POST /v1-evaluate.');
  const evaluation = await post('/v1-evaluate', {
    action_type: action,
    actor_id: actor,
    resource_id: service,
    change_plan: changePlan,
    context,
  });

  const decision = field(evaluation, 'decision', 'outcome').toLowerCase();
  const reason = field(evaluation, 'deny_reason', 'reason');
  const permitToken = field(evaluation, 'permit_token', 'permit_id', 'permitId');
  const executionHash = field(evaluation, 'execution_hash_expected');
  const auditHash = field(evaluation, 'audit_entry_hash', 'audit_hash', 'auditHash');

  console.log(`Decision: ${decision || 'unknown'}`);
  if (reason) console.log(`Reason:   ${reason}`);

  if (['deny', 'hold', 'escalate'].includes(decision)) {
    console.log('\n❌ Step 6/7 block: gate rejected. Not deploying.');
    process.exit(2);
  }
  if (decision !== 'allow') {
    throw new Error('Evaluate returned an unknown or missing decision');
  }

  console.log('Step 4/7 issue permit: allow decision received.');
  if (!permitToken || !executionHash) {
    console.log('\n❌ Missing permit or execution binding. Refusing to deploy.');
    process.exit(3);
  }
  console.log('Permit:  issued (token withheld)');

  console.log('Step 5/7 verify permit: POST /v1-verify-permit.');
  const verification = await post('/v1-verify-permit', {
    permit_token: permitToken,
    action_type: action,
    actor_id: actor,
    environment: targetEnv,
    target_id: service,
    payload_hash: executionHash,
    context,
  });
  const status = field(verification, 'outcome', 'decision', 'status').toLowerCase();
  const valid = verification.valid === true && verification.consumed === true && status === 'allow';
  if (!valid) {
    console.log('\n❌ Permit verification failed. Refusing to deploy.');
    process.exit(3);
  }
  console.log(`Verified: ${status}`);

  console.log('\nStep 6/7 execute: running deploy steps (simulated)...');
  console.log('✅ Deploy complete.');

  console.log('\nStep 7/7 audit evidence:');
  console.log(`  action:      ${action}`);
  console.log(`  service:     ${service}`);
  console.log(`  environment: ${targetEnv}`);
  console.log(`  ref:         ${ref}`);
  console.log(`  sha:         ${sha}`);
  console.log('  permit:      issued and verified (token withheld)');
  if (auditHash) console.log(`  audit_hash:  ${auditHash}`);
}

main().catch((err) => {
  console.error('Flow failed:', err);
  process.exit(1);
});
