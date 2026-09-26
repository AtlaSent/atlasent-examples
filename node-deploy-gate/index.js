/**
 * AtlaSent Node.js Deploy Gate V1
 *
 * Flow: connect CI -> declare action -> evaluate -> issue permit ->
 * verify permit -> execute/block -> audit evidence.
 */

const apiKey = process.env.ATLASENT_API_KEY;
const apiUrl = (process.env.ATLASENT_API_URL ?? 'https://api.atlasent.io/functions/v1').replace(/\/$/, '');

if (!apiKey) {
  console.error('Error: ATLASENT_API_KEY is not set.');
  process.exit(1);
}

const service = process.env.SERVICE ?? 'checkout-api';
const targetEnv = process.env.TARGET_ENV ?? 'production';
const actor = process.env.ACTOR ?? 'ci-bot';
const ref = process.env.GITHUB_REF ?? 'refs/heads/main';
const sha = process.env.GITHUB_SHA ?? 'local-sha';
const action = 'production.deploy';

async function post(path, body) {
  const response = await fetch(`${apiUrl}${path}`, {
    method: 'POST',
    headers: {
      authorization: `Bearer ${apiKey}`,
      'content-type': 'application/json',
    },
    body: JSON.stringify(body),
  });
  const text = await response.text();
  if (!response.ok) throw new Error(`${path} failed: ${response.status} ${text}`);
  return text ? JSON.parse(text) : {};
}

function field(result, ...keys) {
  for (const key of keys) {
    const value = result[key];
    if (typeof value === 'string' && value.length > 0) return value;
  }
  return '';
}

async function main() {
  console.log('=== AtlaSent Deploy Gate V1 ===');
  console.log(`Service : ${service}`);
  console.log(`Target  : ${targetEnv}`);
  console.log(`Actor   : ${actor}`);
  console.log(`Action  : ${action}`);
  console.log('');

  console.log('Step 1/7 connect CI: env loaded.');
  console.log('Step 2/7 declare action: production.deploy.');

  // Real /v1-evaluate wire request: { action_type, actor_id, context }.
  // `environment` lives under `context`, not top-level.
  const context = { service, environment: targetEnv, ref, sha };

  console.log('Step 3/7 evaluate: POST /v1-evaluate.');
  const evaluation = await post('/v1-evaluate', { action_type: action, actor_id: actor, context });

  // Real response is flat: { decision, permit_token?, deny_reason?, ... }.
  const decision = field(evaluation, 'decision').toLowerCase();
  const reason = field(evaluation, 'deny_reason');
  const permitToken = field(evaluation, 'permit_token');
  const auditHash = field(evaluation, 'audit_entry_hash');

  console.log(`Decision : ${decision || 'unknown'}`);
  if (reason) console.log(`Reason   : ${reason}`);

  if (decision !== 'allow') {
    console.log('\nStep 6/7 block: gate rejected. Not deploying.');
    process.exit(2);
  }

  console.log('Step 4/7 issue permit: allow decision received.');
  if (!permitToken) {
    console.error('Error: decision is allow but no permit token was returned.');
    process.exit(3);
  }
  console.log(`Permit  : ${permitToken}`);

  console.log('Step 5/7 verify permit: POST /v1-verify-permit.');
  // Real verify request: { permit_token, action_type, actor_id, environment }.
  const verification = await post('/v1-verify-permit', {
    permit_token: permitToken,
    action_type: action,
    actor_id: actor,
    environment: targetEnv,
  });
  const valid = verification.valid === true;
  if (!valid) {
    console.log(`\nPermit verification failed (${verification.verify_error_code || 'unknown'}). Refusing to deploy.`);
    process.exit(3);
  }
  console.log(`Verified: ${verification.outcome || 'true'}`);

  console.log('\nStep 6/7 execute: deployment would run here.');
  console.log('Deploy command: ./deploy checkout-api production');

  console.log('\nStep 7/7 audit evidence:');
  console.log(`  action:      ${action}`);
  console.log(`  service:     ${service}`);
  console.log(`  environment: ${targetEnv}`);
  console.log(`  ref:         ${ref}`);
  console.log(`  sha:         ${sha}`);
  console.log(`  permit_token: ${permitToken}`);
  if (auditHash) console.log(`  audit_hash:  ${auditHash}`);
}

main().catch((err) => {
  console.error('Deploy gate failed closed:', err.message || err);
  process.exit(1);
});
