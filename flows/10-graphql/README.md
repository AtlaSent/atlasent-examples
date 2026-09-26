# 10 · GraphQL Audit Queries

This flow demonstrates how to query the AtlaSent GraphQL API for audit log
data — a key capability for compliance reporting and post-incident review.

## Why GraphQL for audit?

The AtlaSent GraphQL API provides a flexible, self-documenting interface for
querying evaluation history. Unlike the REST audit endpoint, GraphQL lets you:

- Request exactly the fields you need (no over-fetching).
- Compose multiple queries in a single network round-trip.
- Use typed variables for safe parameter injection.
- Paginate and filter server-side before results arrive.

## Use cases

| Use case | Query pattern |
|---|---|
| Compliance evidence export | `auditLog(limit: N)` with `createdAt`, `decision`, `ruleId` |
| Incident investigation | `auditLog(userId: $id, since: $ts)` |
| Denial trend analysis | `auditLog(decision: "deny", since: $yesterday)` grouped by `ruleId` |
| SLA reporting | `auditLog` aggregated by hour/day client-side |

## Queries in this example

### `RecentAuditLog`

Fetches the most recent N audit log entries for any user:

```graphql
query RecentAuditLog($limit: Int!, $userId: String) {
  auditLog(limit: $limit, userId: $userId) {
    id
    decision
    userId
    ruleId
    confidence
    createdAt
    metadata
  }
}
```

### `DeniedEvaluations`

Fetches all `deny` decisions since a given timestamp — useful for generating
daily denial reports:

```graphql
query DeniedEvaluations($since: String!) {
  auditLog(decision: "deny", since: $since, limit: 100) {
    id
    userId
    ruleId
    confidence
    createdAt
  }
}
```

## Run it

```bash
export ATLASENT_API_KEY=ask_test_...
npm install
npm start
```

## Expected output

```
AtlaSent GraphQL API Demo

1. Fetching recent audit log (last 5 entries)...
   Found 5 entries:
   - [2025-11-01T12:00:00Z] user=alice decision=allow
   - [2025-11-01T11:58:22Z] user=bob   decision=deny
   ...

2. Fetching denied evaluations since 2025-10-31...
   Found 3 denied evaluation(s)
   By rule: { 'rate-limit': 2, 'content-policy': 1 }
```

## Extending the example

- Export results as CSV using a streaming JSON-to-CSV library.
- Schedule this script as a nightly cron job and upload the output to S3 or GCS.
- Add pagination using GraphQL `cursor`-based arguments when `limit: 100` is
  insufficient.
