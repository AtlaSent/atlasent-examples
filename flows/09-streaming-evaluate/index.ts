import { AtlaSentClient } from '@atlasent/sdk';

const client = new AtlaSentClient({
  apiKey: process.env.ATLASENT_API_KEY!,
  baseUrl: process.env.ATLASENT_API_URL ?? 'https://api.atlasent.io/functions/v1',
});

async function main() {
  console.log('Starting streaming evaluation...\n');

  const request = {
    agent: 'stream-demo-user',
    action: 'response.generate',
    context: {
      prompt: 'Write a detailed analysis of quarterly performance metrics',
    },
  };

  const stream = client.protectStream(request);

  console.log('Stream connected. Receiving events:');
  console.log('─'.repeat(60));

  let finalDecision: string | undefined;

  for await (const event of stream) {
    const ts = new Date().toISOString().substring(11, 23);

    if (event.type === 'progress') {
      console.log(`[${ts}] progress  stage=${event.stage}`);
    } else if (event.type === 'decision') {
      finalDecision = event.decision_canonical;
      console.log(`[${ts}] DECISION  → ${event.decision_canonical} (reason: ${event.reason || 'n/a'})`);
    }
  }

  console.log('─'.repeat(60));
  console.log(`Stream complete. Final decision: ${finalDecision ?? 'unknown'}`);
}

main().catch(console.error);
