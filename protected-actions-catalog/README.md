# Protected actions catalog — runnable example

This example wires the five canonical AtlaSent protected actions
end to end through `evaluate → permit → verify → execute → audit`,
in one TypeScript file. It is the runnable counterpart to
the protected-actions catalog in the [AtlaSent documentation](https://docs.atlasent.io).

The five actions are:

1. `production.deploy`
2. `vendor.payment.release`
3. `customer.data.export`
4. `reconciliation.certify`
5. `model.agent.execute_tool`

Each action is wrapped in `atlasent.protect(...)` so the protected
mutation is **unreachable** unless the policy returned `allow` *and*
the issued permit verified server-side. If either step fails, the
mutation never runs and `AtlaSentDeniedError` is raised with the
decision and reason.

## Run it

```bash
export ATLASENT_API_KEY=ask_test_...
npm install
npm start
```

You should see, for each action, an `evaluate` / `verify` round trip,
a single structured audit log line carrying the six canonical
operational visibility fields
(`atlasent.action`, `atlasent.actor_id`, `atlasent.resource_id`,
`atlasent.evaluation_id`, `atlasent.permit_id`,
`atlasent.policy_version`), and the protected mutation marker
`[executed]`. If the policy denies an action you will see `[blocked]`
with the deny reason and *no* `[executed]` line for that action.

## What this example is and is not

This example is the cleanest illustration of the AtlaSent contract:
non-bypassable execution binding across five canonical action types,
with the audit-visibility fields wired at the call site.

This example is **not** a deploy script, an AP integration, an export
job, a close runbook, or an agent harness. Those each live in their
own directory (`github-action-deploy/`, `accounting-close/`,
`langchain-guarded-agent/`, etc.) and use the same primitive.

## Mental model

AtlaSent is execution-time authorization, not a feature flag. A flag
controls whether a behavior is enabled; AtlaSent controls whether an
action is authorized to execute. The two are complementary; see
[Runtime control vs. feature flags](https://docs.atlasent.io).
