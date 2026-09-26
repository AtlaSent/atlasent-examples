import { AtlaSentClient } from '@atlasent/sdk';

const client = new AtlaSentClient({
  baseUrl: process.env.ATLASENT_API_URL!,
  apiKey: process.env.ATLASENT_API_KEY!,
});

async function main() {
  console.log('=== Permit Issue → Verify Flow ===\n');

  // 1. Evaluate and receive a permit
  const evalResult = await client.evaluate({
    agent: 'svc-pipeline',
    action: 'data.process',
    context: { targetId: 'batch-job-789', environment: 'production' },
  });

  if (evalResult.decision !== 'allow' || !evalResult.permitId) {
    console.log(`❌ Not allowed: ${evalResult.decision}`);
    return;
  }

  console.log(`✅ Evaluation: ${evalResult.decision}`);
  console.log(`   Permit ID: ${evalResult.permitId}\n`);

  // 2. Verify the permit before using it. Permits are single-use — this
  // call both verifies AND consumes the permit; there is no separate
  // "consume" step in the API.
  const verified = await client.verifyPermit({ permitId: evalResult.permitId });
  console.log(`🔍 Permit verified: ${verified.outcome} (verified=${verified.verified})`);
  console.log(`   Expires: ${verified.expiresAt ? new Date(verified.expiresAt).toLocaleString() : 'n/a'}\n`);

  // ... do the actual work here ...
  console.log('⚙  Doing the work...\n');

  // 3. Confirm the permit is now consumed (single-use) via the lightweight
  // validity check.
  const status = await client.checkPermitValid(evalResult.permitId);
  console.log(`✓  Permit status: ${status.status} (valid=${status.valid})`);
}

main().catch(console.error);
