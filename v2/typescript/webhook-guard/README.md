# webhook-guard (TypeScript)

Express server showing how to mount the AtlaSent `webhookGuard` middleware
from `@atlasent/action/connectors`. Every incoming webhook payload is
evaluated against AtlaSent before the route handler runs. Also shows
standalone `guard.evaluate(payload)` for non-Express servers.

## Run (live)

```bash
bun install
export ATLASENT_API_KEY=ask_live_xx
bun run index.ts
```

Then send a test request:

```bash
curl -XPOST http://localhost:3000/hooks/deploy \
  -H "Content-Type: application/json" \
  -d '{"event":"deployment","sender":{"login":"ci-bot"},"environment":"production","repository":"checkout-api"}'
```

## Run (dry-run / smoke — no API keys needed)

```bash
bun install
bun run smoke
# or: ATLASENT_DRY_RUN=true bun run index.ts
```

## Express middleware usage

```typescript
import { webhookGuard } from '@atlasent/action/connectors';

const guard = webhookGuard({
  apiKey:     process.env.ATLASENT_API_KEY!,
  failClosed: true,          // 403 on deny/hold, 500 on infra error (default)
  environment: 'production',
});

// Mount as route middleware — handler only runs on allow+verified decisions.
app.post('/hooks/deploy', guard.middleware, (req, res) => {
  // req.atlasent carries the full WebhookGuardResult for audit logging.
  const { evaluationId, riskScore } = req.atlasent!;
  res.json({ status: 'deployed', evaluation_id: evaluationId });
});
```

## Standalone usage (Hono, raw Node, serverless)

```typescript
const result = await guard.evaluate(payload);

if (result.decision !== 'allow' || !result.verified) {
  // block the action
}
// result.evaluationId and result.proofHash are set on allow+verified
```

## Config options

| Option | Default | Description |
|---|---|---|
| `apiKey` | — | AtlaSent API key (`ask_live_*` / `ask_test_*`). Required. |
| `failClosed` | `true` | When `true`, the middleware responds 403/500 on deny/hold/error. Set `false` to pass all decisions to the handler via `req.atlasent`. |
| `environment` | — | Optional environment string forwarded to AtlaSent for policy evaluation. |
| `extractor` | default | Function that pulls `action_type`, `actor_id`, and `context` from the raw body. The default reads `payload.action_type` / `payload.actor_id` with fallbacks to `payload.action` / `payload.actor`. Supply a custom extractor when your webhook payload uses different field names. |

## Custom extractor

```typescript
const guard = webhookGuard({
  apiKey: process.env.ATLASENT_API_KEY!,
  extractor: (payload) => ({
    action_type: payload['event'] as string,
    actor_id:    (payload['sender'] as { login: string }).login,
    context: { repository: payload['repository'] },
  }),
});
```

## `req.atlasent` shape

The middleware attaches a `WebhookGuardResult` to `req.atlasent`:

```typescript
interface WebhookGuardResult {
  decision:     'allow' | 'deny' | 'hold' | 'escalate' | 'error';
  verified:     boolean;        // true only when allow + verifyPermit passed
  evaluationId?: string;        // present on allow
  proofHash?:   string;         // present on allow
  riskScore?:   number;         // 0–100, present when returned by the API
  reason?:      string;         // deny/hold reason or error message
}
```

Gate on `verified`, not `decision` alone — `verified` is false when the
allow decision arrived but permit verification failed (fail-closed path).
