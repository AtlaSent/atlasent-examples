/**
 * Auth Migration — BEFORE (deprecated)
 *
 * This file shows the OLD way of authenticating raw HTTP requests to
 * the AtlaSent API. The `X-AtlaSent-Key` header is deprecated and will
 * be removed in a future release.
 *
 * See after.ts for the correct pattern.
 *
 * NOTE: The SDK (@atlasent/sdk) always uses the correct Authorization
 * header internally — this migration only affects callers that construct
 * raw HTTP requests themselves.
 */

// ❌ Deprecated — do not use X-AtlaSent-Key
fetch('https://api.atlasent.io/functions/v1/v1-evaluate', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-AtlaSent-Key': process.env.ATLASENT_API_KEY!, // ← deprecated header
  },
  body: JSON.stringify({
    // Real /v1-evaluate wire request: { action_type, actor_id, context }.
    action_type: 'data.export',
    actor_id: 'assistant',
    context: { format: 'csv' },
  }),
});

// The SDK always did the right thing — no migration needed if you use it:
// import { AtlaSentClient } from '@atlasent/sdk';
// const client = new AtlaSentClient({ apiKey: 'key_...' }); // SDK handles auth correctly
