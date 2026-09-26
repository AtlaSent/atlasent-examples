/**
 * AtlaSent Rate Limit Handling — TypeScript (raw HTTP)
 *
 * The @atlasent/sdk handles 429 responses automatically with built-in
 * exponential back-off. This example shows how to implement the same
 * pattern for callers that use raw fetch rather than the SDK.
 *
 * Key points:
 *   • A 429 response body always includes `retry_after_ms`.
 *   • Respect that value rather than using a fixed delay.
 *   • Jitter (±10 %) avoids thundering-herd on shared rate-limit windows.
 *   • After `retries` exhausted, surface the original 429 to the caller.
 *
 * Run:
 *   ATLASENT_API_KEY=key_... npx tsx index.ts
 */

const API_URL = process.env.ATLASENT_API_URL ?? 'https://api.atlasent.io/functions/v1';
const API_KEY = process.env.ATLASENT_API_KEY!;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Add ±10 % jitter to avoid thundering herd on shared rate-limit windows. */
function jitter(ms: number): number {
  return ms * (0.9 + Math.random() * 0.2);
}

/**
 * Call /v1-evaluate with automatic 429 retry.
 *
 * The SDK (@atlasent/sdk) does this automatically — only implement
 * this pattern if you are making raw HTTP calls.
 */
async function evaluateWithBackoff(
  payload: object,
  retries = 4,
): Promise<Response> {
  const resp = await fetch(`${API_URL}/v1-evaluate`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${API_KEY}`,
    },
    body: JSON.stringify(payload),
  });

  if (resp.status === 429 && retries > 0) {
    // Clone before reading — body can only be consumed once.
    const body = await resp.clone().json() as { retry_after_ms?: number };
    const waitMs = jitter(body.retry_after_ms ?? 1000);
    console.warn(
      `Rate limited. Waiting ${Math.round(waitMs)}ms before retry ` +
        `(${retries} retries left)…`,
    );
    await sleep(waitMs);
    return evaluateWithBackoff(payload, retries - 1);
  }

  return resp;
}

async function main() {
  console.log('=== Rate Limit Handling Example ===\n');

  const payload = {
    agent: 'assistant',
    action: 'data.export',
    context: { format: 'csv' },
  };

  const resp = await evaluateWithBackoff(payload);

  if (!resp.ok) {
    console.error(`Request failed: ${resp.status}`);
    process.exit(1);
  }

  const result = await resp.json();
  console.log('Decision:', result.decision);
  if (result.reason) console.log('Reason:  ', result.reason);
}

main().catch((err) => {
  console.error('Unexpected error:', err);
  process.exit(1);
});
