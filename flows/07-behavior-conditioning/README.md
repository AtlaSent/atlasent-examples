# 07 · Behavior Conditioning

This flow demonstrates how AtlaSent's Behavior Verification System (BVS) state
influences `evaluate` decisions through behavior conditioning.

## What is behavior conditioning?

Behavior conditioning allows you to enrich an `evaluate` call with a user's
aggregated behavioral state. AtlaSent's `behavior-insights` service maintains
rolling aggregates of behavioral events — grouped by semantic category — without
exposing raw event data (trigger text, notes, or payload). The `@atlasent/behavior`
package (when available) provides typed helpers for fetching these aggregates and
attaching them as metadata to evaluate requests.

## Key concepts

| Concept | Description |
|---|---|
| **State summary** | Aggregated event counts and windows for a user across all categories |
| **Category aggregate** | Per-category count + confidence within a rolling time window |
| **Sensitive categories** | E.g. `behavior.health.mental` — low-confidence signal is flagged and handled gracefully |
| **Consent projection** | The SDK only surfaces aggregate statistics; no raw event content is readable via the API |
| **`attachToEvaluate`** | Helper that merges a state summary into evaluate `metadata` |

## How it works

1. **Fetch state summary** — `GET /api/patterns/summary/:userId` returns aggregate
   event counts and window boundaries. No raw event data is returned.
2. **Check sensitive categories** — `GET /api/patterns/category/:userId/:category`
   returns a count + `confidence_low` flag. If confidence is low (few events in window),
   the signal is treated as insufficient for conditioning.
3. **Run conditioned evaluate** — the state summary is attached to the `metadata`
   field of the evaluate request so the AtlaSent policy engine can factor in
   behavioral context when making a decision.

## Run it

```bash
export ATLASENT_API_KEY=ask_test_...
# Optional:
export ATLASENT_BEHAVIOR_URL=http://localhost:3001   # default
export DEMO_USER_ID=demo-user-001                    # default
npm install
npm start
```

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `ATLASENT_API_KEY` | — | Required. Your AtlaSent API key |
| `ATLASENT_BEHAVIOR_URL` | `http://localhost:3001` | Base URL for the behavior-insights service |
| `DEMO_USER_ID` | `demo-user-001` | User ID to condition on |

## Expected output

If the user has no prior behavior data:

```
AtlaSent Behavior Conditioning Demo
User: demo-user-001

1. Fetching behavior state summary (aggregates only)...
   (No behavior data yet for this user — run some evaluations first)

2. Checking mental health category aggregate...
   (No data for this category)

3. Running evaluate with behavior context...
   Decision: allow (confidence: 0.92)
```

With existing data the state summary and category aggregates are printed before
the conditioned evaluate result.

## Privacy note

The behavior-insights API never exposes raw event fields (`trigger_text`, `notes`,
`payload`). All data returned by the `/api/patterns/` endpoints is limited to
aggregated statistics derived from `pattern_entries` records.
