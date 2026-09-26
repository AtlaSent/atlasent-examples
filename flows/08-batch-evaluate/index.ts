import { AtlaSentClient } from '@atlasent/sdk';

const client = new AtlaSentClient({
  apiKey: process.env.ATLASENT_API_KEY!,
  baseUrl: process.env.ATLASENT_API_URL ?? 'https://api.atlasent.io/functions/v1',
});

// BatchEvalItem shape: { agent, action, context? } — see @atlasent/sdk.
const items = [
  { userId: 'user-001', agent: 'user-001', action: 'message.send', context: { content: 'Hello!' } },
  { userId: 'user-002', agent: 'user-002', action: 'funds.transfer', context: { amount: 500 } },
  { userId: 'user-003', agent: 'user-003', action: 'report.read', context: { report_id: 'Q4-2025' } },
  { userId: 'user-004', agent: 'user-004', action: 'profile.update', context: { field: 'email' } },
  { userId: 'user-005', agent: 'user-005', action: 'message.send', context: { content: 'Need help' } },
];

async function main() {
  console.log(`Submitting batch of ${items.length} items...`);

  // evaluateBatch() returns { batchId, items, partial, rateLimit } with
  // per-item results in input order — index back into `items` for userId.
  const batch = await client.evaluateBatch(
    items.map(({ agent, action, context }) => ({ agent, action, context })),
  );

  console.log('\nBatch results:');
  console.log('─'.repeat(60));

  for (const result of batch.items) {
    const userId = items[result.index]?.userId ?? `item-${result.index}`;
    const decision = result.decision ?? (result.error ? `error:${result.error}` : 'unknown');
    const icon = decision === 'allow' ? '✓' : decision === 'deny' ? '✗' : '⚠';
    console.log(`${icon} ${userId.padEnd(12)} → ${decision.padEnd(10)} (decisionId: ${result.decisionId ?? 'n/a'})`);
  }

  const summary = {
    allow: batch.items.filter(r => r.decision === 'allow').length,
    deny: batch.items.filter(r => r.decision === 'deny').length,
    escalate: batch.items.filter(r => r.decision === 'escalate').length,
  };

  console.log('─'.repeat(60));
  console.log(`Summary: ${summary.allow} allowed, ${summary.deny} denied, ${summary.escalate} escalated`);
}

main().catch(console.error);
