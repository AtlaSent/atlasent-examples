# GitHub Actions Deploy Gate V1 Quickstart

This is the primary AtlaSent Deploy Gate V1 quickstart. It gates one pilot action: **deploy `checkout-api` to production from GitHub Actions**.

The action name is always `production.deploy`. The API endpoints are `POST /v1-evaluate` and `POST /v1-verify-permit`.

## The 7-step flow

1. **Connect CI** — add AtlaSent secrets to GitHub Actions.
2. **Declare action** — describe this release as `production.deploy`.
3. **Evaluate** — ask AtlaSent whether this workflow may deploy this commit.
4. **Issue permit** — require an allow decision carrying a permit token.
5. **Verify permit** — verify and consume the permit immediately before deployment.
6. **Execute/block** — deploy only when `verified` is true; otherwise fail the job.
7. **Audit evidence** — write the decision, verification, evaluation id and proof hash to the job log.

The committed workflow is [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml).

## Prerequisites

Add these repository secrets in **Settings → Secrets and variables → Actions**:

| Secret | Purpose |
|---|---|
| `ATLASENT_API_KEY` | Runtime API key (`ask_…`) used by the workflow. |
| `ATLASENT_API_URL` | **Required.** AtlaSent API base URL, ending in `/functions/v1`: `https://api.atlasent.io/functions/v1`. (Self-hosted deployments use their own `https://<project-ref>.supabase.co/functions/v1`.) |
| `ATLASENT_ORG_ID` | Optional unless required by your AtlaSent tenant/SDK. The API key already resolves the org. |

> **`production.deploy` is evaluated as the workflow, not the person who pushed.** It is change-controlled: the runtime requires a verified workload identity and a change plan. The action exchanges the job's GitHub OIDC token for that identity (so the job needs `permissions: id-token: write`) and derives the plan from the commit. The identity is admitted only when this repository and workflow have an active GitHub Actions workload enrollment in AtlaSent, and the API key needs the `idp_broker:mint` scope in addition to `evaluate:write` and `verify:execute`.

## Recommended: the published action

For real pilots, prefer the maintained Marketplace action
[`Atlasent/atlasent-action`](https://github.com/Atlasent/atlasent-action).
It uses the same gate but also **auto-sends a `state_snapshot`** (so it works
against classes with `requires_state_snapshot=true`, where the raw calls below
would be denied `SNAPSHOT_REQUIRED`), **derives approvals from PR reviews**, and
builds a signed evidence bundle.

```yaml
# The job needs: permissions: { contents: read, pull-requests: read, id-token: write }
- name: AtlaSent gate
  id: gate
  uses: Atlasent/atlasent-action@v1
  env:
    ATLASENT_API_KEY: ${{ secrets.ATLASENT_API_KEY }}
    GITHUB_TOKEN: ${{ github.token }}
  with:
    action: production.deploy
    environment: production
    # Required: your runtime base ending in /functions/v1
    api-url: ${{ secrets.ATLASENT_API_URL }}
```

A non-`allow` decision (or any error) fails the step. Gate the deploy step on
`steps.gate.outputs.verified == 'true'`, never on `decision`. That's the
fail-closed guarantee.

## Why there is no raw `curl` version

Earlier versions of this quickstart called `/v1-evaluate` and
`/v1-verify-permit` directly with `curl`. That no longer works for
`production.deploy`: since 2026-08-25 the runtime refuses it without a signed
workload identity (`ACTOR_UNVERIFIED`) and a structured change plan
(`EXECUTION_PAYLOAD_HASH_REQUIRED`), and a shell script has no way to mint the
identity. The old block also sent `approvals` and `change_window` in its
context. Those were claims written into the workflow, not evidence: approvals
must come from real PR reviews and the change window is checked server-side.

The raw endpoints still serve action types that are not change-controlled; see
the API reference for their request shapes.

## Policy fixture

The included policy fixture uses `production.deploy` and blocks production deploys outside the change window or without two approvals. Use it as sample data for a pilot, not as a full policy-management workflow.
