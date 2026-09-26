# billing-entitlement

Demonstrates how to gate operations on AtlaSent billing entitlement using the
Python SDK.

## What It Shows

- Fetching `BillingEntitlement` via `BillingClient`
- Checking `has_action(AllowedAction.govern)` before running a privileged operation
- Detecting grace period state and surfacing days-remaining in error messages
- The `access_status` / `effective_status` / `grace_until` response fields

## Run

```bash
pip install -r requirements.txt
ATLASENT_API_KEY=ask_live_xxx python main.py
```

## Expected Output — active org

```
Fetching billing entitlement...
  org_id:        org_01abc
  access_status: active
  plan:          enterprise

✓ 'govern' is permitted — running governed operation...
  → Governed operation completed successfully.
```

## Expected Output — grace period

```
Fetching billing entitlement...
  org_id:        org_01abc
  access_status: grace
  plan:          enterprise
  ⚠  Your grace period expires in 5 days. Please renew your subscription.

✗ 'govern' is blocked (grace period).
  Grace period ends: 2026-05-14 (5 days remaining).
  Please renew your subscription to restore full access.
```

## Expected Output — restricted

```
Fetching billing entitlement...
  org_id:        org_01abc
  access_status: restricted
  plan:          enterprise

✗ 'govern' is blocked.
  Status:      restricted
  Deny reason: billing_restricted
```

## Related

- [Billing Grace Periods Guide](https://docs.atlasent.io/guides/billing-grace-periods)
- [Python SDK Reference](https://docs.atlasent.io/guides/python-sdk)
- [TypeScript SDK billing types](https://github.com/atlasent-systems-inc/atlasent-sdk/tree/main/typescript/packages/enforce/src/billing.ts)
