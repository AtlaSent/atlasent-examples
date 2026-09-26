# risk-envelope-explain (TypeScript)

Calls `POST /v1-evaluate` with `explain: true` and reads back the
`risk_envelope` response, demonstrating how to:

- Interpret `risk_envelope.promoted` to know when the envelope overrode the rules-engine decision
- Iterate `risk_envelope.factors` for per-factor scores (only present when `explain=true`)
- Check `risk_envelope.hard_blocks` for absolute deny codes
- Gracefully handle `risk_envelope` being absent (older API versions)

## Run (live)

```bash
export ATLASENT_API_URL=https://api.atlasent.io/functions/v1
export ATLASENT_API_KEY=ask_live_xx
bun run index.ts
```

## Run (dry-run / smoke — no API keys needed)

```bash
bun run smoke
# or: ATLASENT_DRY_RUN=true bun run index.ts
```

In dry-run mode the network call is stubbed and a realistic mock `risk_envelope`
is returned. This is the mode used by CI.

## Response shape

The `risk_envelope` object is always present on `POST /v1-evaluate` responses.
The `factors` array is gated behind `explain: true` to keep the default response
size small.

```jsonc
{
  "decision": "allow",
  "risk_envelope": {
    "weighted_score": 0.62,
    "engine_decision": "allow",
    "envelope_decision": "allow",
    "promoted": false,        // true when the envelope overrode the engine
    "hard_blocks": [],        // deny codes that force decision='deny'
    "factors": [              // only present when explain:true was sent
      {
        "factor": "ACTION_SENSITIVITY",
        "value": 0.8,
        "weight": 0.3,
        "reason": "production.deploy is a high-sensitivity action class"
      }
      // ...
    ]
  }
}
```

### `promoted`

When `promoted: true` the envelope's resolved decision (`envelope_decision`)
differs from the raw rules-engine decision (`engine_decision`). This happens
when `envelope_authoritative` is enabled for the org. Callers should always
gate on the top-level `decision` field — `promoted` is informational.

### `hard_blocks`

Any non-empty entry forces `decision='deny'` regardless of other signals.
Values are deny codes from the rule engine (e.g. `"deny_actors"`, `"change_window"`).

### `factors`

Present only when the request included `explain: true`. Each entry carries:
- `factor` — one of `ACTION_SENSITIVITY`, `ACTOR_AUTHORITY`,
  `ORG_POLICY_STRICTNESS`, `ENVIRONMENT`, `CONTEXT_ANOMALY`, `HISTORY`,
  `BEHAVIOR_BASELINE`
- `value` — normalized contribution in [0, 1]
- `weight` — configurable per-org weight in [0, 1]
- `reason` — human-readable string safe to log for audit / explainability
