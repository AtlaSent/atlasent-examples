/**
 * AtlaSent Webhook Verification — TypeScript / Express
 *
 * Demonstrates verifying an incoming AtlaSent webhook using
 * `assertWebhook` from `@atlasent/sdk`. The raw request body
 * must be passed to the verifier before any JSON parsing.
 *
 * Run:
 *   ATLASENT_WEBHOOK_SECRET=whsec_... npx tsx index.ts
 */

import express from 'express';
import { assertWebhook, verifyWebhook, WebhookVerificationError } from '@atlasent/sdk';

const app = express();
const PORT = Number(process.env.PORT ?? 3000);

// Mount the raw body parser on this route only — JSON.parse must
// happen AFTER verification so the signature covers the exact bytes
// received on the wire.
app.post(
  '/webhooks/atlasent',
  express.raw({ type: 'application/json' }),
  async (req, res) => {
    const signature = req.headers['x-atlasent-signature'] as string;
    const rawBody = (req.body as Buffer).toString('utf-8');

    // assertWebhook throws WebhookVerificationError if the signature is
    // missing, expired, or invalid. verifyWebhook is the non-throwing
    // boolean-returning variant. Both are async — the signing secret
    // comparison is constant-time and awaits internally.
    try {
      await assertWebhook(rawBody, signature, process.env.ATLASENT_WEBHOOK_SECRET!);
    } catch (err) {
      if (err instanceof WebhookVerificationError) {
        return res.status(400).json({ error: 'invalid_signature' });
      }
      throw err;
    }

    // Safe to parse now — bytes are confirmed authentic.
    const event = JSON.parse(rawBody) as { type: string };
    console.log('Verified event:', event.type);

    // Acknowledge immediately; process asynchronously if needed.
    res.json({ received: true });
  },
);

// Health check
app.get('/health', (_req, res) => res.json({ ok: true }));

app.listen(PORT, () => {
  console.log(`Webhook receiver listening on http://localhost:${PORT}`);
  console.log('POST /webhooks/atlasent  — AtlaSent event endpoint');
});

// Export verifyWebhook for use in serverless/edge handlers that
// don't use Express (e.g. Next.js, Cloudflare Workers).
export { verifyWebhook, assertWebhook };
