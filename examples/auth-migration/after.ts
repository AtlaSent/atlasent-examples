/**
 * Auth Migration — AFTER (correct)
 *
 * Raw HTTP requests to the AtlaSent API must now use the standard
 * `Authorization: Bearer <key>` header. The previous `X-AtlaSent-Key`
 * header is deprecated.
 *
 * If you use the SDK (@atlasent/sdk) you do not need to change anything —
 * the SDK has always sent the correct header. This migration only affects
 * code that builds raw fetch/urllib/axios requests directly.
 */

// ✅ Correct — use Authorization: Bearer
async function evaluateAction(apiKey: string): Promise<Response> {
  return fetch('https://api.atlasent.io/functions/v1/v1-evaluate', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${apiKey}`, // ← correct header
    },
    body: JSON.stringify({
      // Real /v1-evaluate wire request: { action_type, actor_id, context }.
      // There is no `agent`/`action` alias on the wire — that shim exists
      // only inside @atlasent/sdk's evaluate(), not the raw HTTP endpoint.
      action_type: 'data.export',
      actor_id: 'assistant',
      context: { format: 'csv' },
    }),
  });
}

// Quick migration checklist for raw HTTP callers:
//
//   Before:  'X-AtlaSent-Key': apiKey
//   After:   'Authorization': `Bearer ${apiKey}`
//
// The body/response shape is unchanged by this migration (auth header only).

evaluateAction(process.env.ATLASENT_API_KEY!).then(async (res) => {
  console.log('Status:', res.status);
  console.log('Body:', await res.json());
});
