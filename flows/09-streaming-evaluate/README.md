# 09 · Streaming Evaluate (SSE Consumer)

This flow demonstrates how to consume the AtlaSent streaming evaluate endpoint
using Server-Sent Events (SSE). Streaming is useful when evaluation involves
long-context analysis or when you want real-time progress visibility.

## When to use streaming evaluation

- **Real-time content moderation** — surface an intermediate `progress` signal
  to update a UI before the final `decision` arrives.
- **Long-context evaluations** — avoid HTTP timeouts on evaluations that span
  large documents or multi-turn conversation histories.
- **Observability** — log per-rule scores as they are computed to aid debugging
  and policy tuning.

## Event types

| Type | Fields | Description |
|---|---|---|
| `progress` | `rule_id`, `score` | Intermediate signal from a single rule evaluation |
| `decision` | `decision`, `confidence` | Final authoritative decision (allow / deny / escalate) |
| `error` | `message` | Stream-level error; treat as deny/escalate |

## How `authorizeStream` works

`client.authorizeStream(request)` returns an async iterable. Each iteration
yields one parsed SSE event. The stream closes automatically after the
`decision` event is emitted.

```
client.authorizeStream(request)
  └─▶ async iterable
        ├── { type: 'progress', rule_id: 'pii-check',   score: 0.12 }
        ├── { type: 'progress', rule_id: 'rate-limit',  score: 0.05 }
        ├── { type: 'progress', rule_id: 'content-mod', score: 0.33 }
        └── { type: 'decision', decision: 'allow', confidence: 0.91 }
```

## Run it

```bash
export ATLASENT_API_KEY=ask_test_...
npm install
npm start
```

## Expected output

```
Starting streaming evaluation...

Stream connected. Receiving events:
────────────────────────────────────────────────────────────
[12:00:00.123] progress  rule=pii-check    score=0.120
[12:00:00.241] progress  rule=rate-limit   score=0.050
[12:00:00.389] progress  rule=content-mod  score=0.330
[12:00:00.512] DECISION  → allow (confidence: 0.91)
────────────────────────────────────────────────────────────
Stream complete. Final decision: allow
```

## Error handling

If the stream emits an `error` event, log it and treat the outcome as a
denial. Always wrap the `for await` loop in a try/catch to handle network
errors and premature stream termination.
