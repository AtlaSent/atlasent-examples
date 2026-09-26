# Usage Metering

Pull governed-action usage data from AtlaSent: summary counters and a
paginated evaluation list. Use this to understand consumption relative to
your license limit, monitor deny rates, and build billing dashboards.

## What this shows

1. **Monthly summary** — total evaluations, billable allows, billable denies,
   holds, escalations, license limit, and % consumed.
2. **Detailed list** — the most recent evaluations with actor, action, and
   latency. Filterable by decision type. Cursor-paginated.
3. **Deny rate** — computed client-side from the two responses.

## Required environment variables

| Variable | Required | Description |
|---|---|---|
| `ATLASENT_API_KEY` | yes | API key with `usage:read` scope. |
| `ATLASENT_ORG_ID` | yes | Your AtlaSent org ID. |
| `ATLASENT_BASE_URL` | no | Defaults to `https://api.atlasent.io/functions/v1`. |

## Run

```bash
npm install
export ATLASENT_API_KEY=ask_live_...
export ATLASENT_ORG_ID=org_acme
npx tsx index.ts
```

## Expected output

```
Fetching monthly usage summary...

  Org:            org_acme
  Period:         6/1/2026 → 6/30/2026
  ─────────────────────────────────────────────
  Total evals:    4,821
  Billable allows:3,914
  Billable denies:612
  Holds:          213
  Escalations:    82
  ─────────────────────────────────────────────
  License limit:  10,000
  Usage:          [===========~               ] 39.2%

Fetching recent billable allow evaluations...

  Showing 10 of 3,914 allow evaluations

  evaluation_id                         actor_id                        action_type                           latency
  ────────────────────────────────────  ──────────────────────────────  ────────────────────────────────────  ───────
  eval_01HZ...                          ci-bot@acme.internal            production.deploy                     43ms
  eval_01HY...                          alice@acme.internal             data.export                           38ms
  ...

Fetching deny count...

  Total denies this month: 612 (12.7% of evaluations)
```

## Billable event definition

| Decision | Billable? | Notes |
|---|---|---|
| `allow` | Yes | A permit was issued and the action may execute. |
| `deny` | Plan-dependent | Billable on Growth and Enterprise; free on Starter. |
| `hold` | No | Pending approver action; billed once resolved as allow or deny. |
| `escalate` | No | Same as hold — billed on final resolution. |

## License limit behaviour

When `limit_pct_used` reaches 100 the org enters overage. AtlaSent continues
to authorize actions in overage (there is no hard cut-off), but the summary
sets `overage: true` and the console shows a banner. Overage is billed at the
per-evaluation rate on your plan.

When `limit` is `null` the org has an unlimited (enterprise custom) contract.
`limit_pct_used` is also `null` in this case.

## Cursor pagination

The list endpoint returns up to `limit` records per page (max 1000). When
`next_cursor` is present in the response, pass it as `?cursor=<value>` to
fetch the next page. Cursors are opaque strings tied to the query parameters —
do not change `decision` or `org_id` between pages.

## Next steps

- See the [AtlaSent documentation](https://docs.atlasent.io) for the full API
  reference and billing implications.
- See [`../billing-entitlement/`](../billing-entitlement/) for the complementary
  entitlement-check example that gates feature access based on plan.
