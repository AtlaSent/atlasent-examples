import express from 'express';
import { verifyWebhookSignature } from '@atlasent/sdk';
import type { WebhookPayload } from '@atlasent/sdk';

const app = express();
const PORT = process.env['PORT'] ?? 3000;
const WEBHOOK_SECRET = process.env['ATLASENT_WEBHOOK_SECRET'];

if (!WEBHOOK_SECRET) {
  console.error('ATLASENT_WEBHOOK_SECRET environment variable is required');
  process.exit(1);
}

// Use raw body parser — HMAC is computed over the exact bytes before parsing.
app.post(
  '/webhooks/atlasent',
  express.raw({ type: 'application/json' }),
  async (req, res) => {
    const signature = req.headers['x-atlasent-signature'] as string | undefined;
    const eventType = req.headers['x-atlasent-event'] as string | undefined;

    if (!signature) {
      console.warn('[webhook] Missing X-AtlaSent-Signature header');
      return res.status(401).send('Missing signature');
    }

    // Verify HMAC-SHA256 signature using constant-time comparison
    const isValid = await verifyWebhookSignature(
      req.body as Buffer,
      signature,
      WEBHOOK_SECRET!,
    );

    if (!isValid) {
      console.warn('[webhook] Signature verification FAILED — rejecting');
      return res.status(401).send('Invalid signature');
    }

    let event: WebhookPayload<Record<string, unknown>>;
    try {
      event = JSON.parse((req.body as Buffer).toString('utf-8'));
    } catch {
      return res.status(400).send('Invalid JSON body');
    }

    // Respond 200 immediately so AtlaSent does not retry
    res.sendStatus(200);

    // Process asynchronously after responding
    handleEvent(event).catch((err) =>
      console.error('[webhook] Handler error:', err),
    );
  },
);

async function handleEvent(
  event: WebhookPayload<Record<string, unknown>>,
): Promise<void> {
  console.log(`[webhook] Received: ${event.event_type} (id=${event.id})`);

  switch (event.event_type) {
    case 'enforcement.blocked': {
      const { action, actor, deny_reason, environment } = event.data as {
        action: string;
        actor: string;
        deny_reason: string;
        environment: string;
      };
      console.log(
        `[enforcement.blocked] ${actor} attempted "${action}" in ${environment}` +
          ` — DENIED: ${deny_reason}`,
      );
      // TODO: post to Slack, PagerDuty, SIEM, etc.
      break;
    }

    case 'enforcement.pending_approval': {
      const { action, actor, evaluation_id } = event.data as {
        action: string;
        actor: string;
        evaluation_id: string;
      };
      console.log(
        `[enforcement.pending_approval] ${actor} → "${action}" is on hold` +
          ` (eval_id=${evaluation_id})`,
      );
      // TODO: notify approver
      break;
    }

    case 'enforcement.approved':
    case 'enforcement.rejected': {
      const { evaluation_id, reviewer_id } = event.data as {
        evaluation_id: string;
        reviewer_id: string;
      };
      console.log(
        `[${event.event_type}] eval_id=${evaluation_id} by reviewer=${reviewer_id}`,
      );
      break;
    }

    case 'policy.violation': {
      const { policy_id, severity, description } = event.data as {
        policy_id: string;
        severity: string;
        description: string;
      };
      console.log(
        `[policy.violation] [${severity.toUpperCase()}] ${policy_id}: ${description}`,
      );
      break;
    }

    default:
      console.log(`[webhook] Unhandled event type: ${event.event_type}`);
  }
}

app.listen(PORT, () => {
  console.log(`Webhook receiver listening on http://localhost:${PORT}/webhooks/atlasent`);
});
