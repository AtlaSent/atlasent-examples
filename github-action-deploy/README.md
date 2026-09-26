# GitHub Actions Deploy Gate V1 Quickstart

This is the primary AtlaSent Deploy Gate V1 quickstart. It gates one pilot action: **deploy `checkout-api` to production from GitHub Actions**.

The action name is always `production.deploy`. The API endpoints are `POST /v1-evaluate` and `POST /v1-verify-permit`.

## The 7-step flow

1. **Connect CI** — add AtlaSent secrets to GitHub Actions.
2. **Declare action** — describe this release as `production.deploy`.
3. **Evaluate** — ask AtlaSent whether the actor may deploy.
4. **Issue permit** — require an allow decision carrying a `permit_token` (`pt.v2…`).
5. **Verify permit** — verify the permit immediately before deployment (with a top-level `environment`).
6. **Execute/block** — deploy only when verification succeeds; otherwise fail the job.
7. **Audit evidence** — write the decision, permit token, audit hash, ref, SHA, and service to the job log.

## Prerequisites

Add these repository secrets in **Settings → Secrets and variables → Actions**:

| Secret | Purpose |
|---|---|
| `ATLASENT_API_KEY` | Runtime API key (`ask_…`) used by the workflow. |
| `ATLASENT_API_URL` | **Required.** AtlaSent API base URL, ending in `/functions/v1`: `https://api.atlasent.io/functions/v1`. (Self-hosted deployments use their own `https://<project-ref>.supabase.co/functions/v1`.) |
| `ATLASENT_ORG_ID` | Optional unless required by your AtlaSent tenant/SDK. The API key already resolves the org. |

> **Actor must be on the allow-list.** The workflow evaluates as `github:${{ github.actor }}`. That value must appear in the policy's `allow_actors`, or the deploy is denied with `ACTOR_NOT_ALLOWED`. Adjust the prefix to match how your policy names GitHub callers.

## Recommended: the published action

For real pilots, prefer the maintained Marketplace action
[`AtlaSent-Systems-Inc/atlasent-action`](https://github.com/AtlaSent-Systems-Inc/atlasent-action).
It uses the same gate but also **auto-sends a `state_snapshot`** (so it works
against classes with `requires_state_snapshot=true`, where the raw calls below
would be denied `SNAPSHOT_REQUIRED`), **derives approvals from PR reviews**, and
builds a signed evidence bundle.

```yaml
- name: AtlaSent gate
  uses: AtlaSent-Systems-Inc/atlasent-action@v1
  env:
    ATLASENT_API_KEY: ${{ secrets.ATLASENT_API_KEY }}
  with:
    action: production.deploy
    environment: production
    # Required: your runtime base ending in /functions/v1
    api-url: ${{ secrets.ATLASENT_API_URL }}
    # actor defaults to github:${{ github.actor }} — must be on the policy allow_actors
```

A non-`allow` decision (or any error) fails the step, so a following `deploy`
job gated on `needs:` never runs. That's the fail-closed guarantee.

## Alternative: zero-dependency (raw API)

The block below calls the API directly with `curl` — no action dependency, useful
for understanding the exact wire shape or for non-GitHub runners. It does **not**
auto-send a `state_snapshot`, so use it only against classes with
`requires_state_snapshot=false` (or add a `state_snapshot` to the evaluate body).

Create `.github/workflows/deploy-gate.yml`:

```yaml
name: deploy-gate-v1

on:
  workflow_dispatch:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      deployments: write

    env:
      ATLASENT_API_KEY: ${{ secrets.ATLASENT_API_KEY }}
      # REQUIRED — set this secret to your runtime base ending in /functions/v1.
      ATLASENT_API_URL: ${{ secrets.ATLASENT_API_URL }}
      SERVICE: checkout-api
      TARGET_ENV: production
      ACTION_TYPE: production.deploy
      ACTOR: github:${{ github.actor }}   # must match the policy's allow_actors

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Evaluate production.deploy
        id: evaluate
        shell: bash
        run: |
          set -euo pipefail
          body=$(jq -n \
            --arg action_type "$ACTION_TYPE" \
            --arg actor_id "$ACTOR" \
            --arg service "$SERVICE" \
            --arg environment "$TARGET_ENV" \
            --arg ref "${{ github.ref }}" \
            --arg sha "${{ github.sha }}" \
            '{action_type:$action_type, actor_id:$actor_id,
              context:{environment:$environment, service:$service, ref:$ref, sha:$sha,
                       approvals:2, change_window:true}}')

          response=$(curl -fsS \
            -H "authorization: Bearer $ATLASENT_API_KEY" \
            -H "content-type: application/json" \
            -d "$body" \
            "$ATLASENT_API_URL/v1-evaluate")

          decision=$(jq -r '.decision' <<<"$response" | tr '[:upper:]' '[:lower:]')
          permit_token=$(jq -r '.permit_token // empty' <<<"$response")
          audit_hash=$(jq -r '.audit_entry_hash // empty' <<<"$response")
          deny_code=$(jq -r '.deny_code // empty' <<<"$response")

          echo "decision=$decision" >> "$GITHUB_OUTPUT"
          echo "permit_token=$permit_token" >> "$GITHUB_OUTPUT"
          echo "audit_hash=$audit_hash" >> "$GITHUB_OUTPUT"

          echo "AtlaSent decision: $decision  audit: $audit_hash"
          if [ "$decision" != "allow" ] || [ -z "$permit_token" ]; then
            echo "::error::AtlaSent blocked production.deploy (decision=$decision deny_code=$deny_code)."
            exit 1
          fi

      - name: Verify permit
        shell: bash
        run: |
          set -euo pipefail
          # NOTE: `environment` is a TOP-LEVEL field on verify — production permits
          # are denied with ENVIRONMENT_REQUIRED if it is omitted or only in context.
          body=$(jq -n \
            --arg permit_token "${{ steps.evaluate.outputs.permit_token }}" \
            --arg action_type "$ACTION_TYPE" \
            --arg actor_id "$ACTOR" \
            --arg environment "$TARGET_ENV" \
            '{permit_token:$permit_token, action_type:$action_type, actor_id:$actor_id, environment:$environment}')

          response=$(curl -fsS \
            -H "authorization: Bearer $ATLASENT_API_KEY" \
            -H "content-type: application/json" \
            -d "$body" \
            "$ATLASENT_API_URL/v1-verify-permit")

          valid=$(jq -r '.valid // false' <<<"$response")
          echo "AtlaSent permit verification: $valid"
          if [ "$valid" != "true" ]; then
            echo "::error::Permit verification failed: $(jq -rc '{outcome, verify_error_code, reason}' <<<"$response")"
            exit 1
          fi

      - name: Deploy checkout-api
        run: |
          echo "Deploying $SERVICE to $TARGET_ENV at ${{ github.sha }}"
          # Replace this line with your deployment command.

      - name: Audit evidence
        if: always()
        run: |
          echo "action=production.deploy"
          echo "service=$SERVICE"
          echo "environment=$TARGET_ENV"
          echo "ref=${{ github.ref }}"
          echo "sha=${{ github.sha }}"
          echo "decision=${{ steps.evaluate.outputs.decision }}"
          echo "permit_token=${{ steps.evaluate.outputs.permit_token }}"
          echo "audit_entry_hash=${{ steps.evaluate.outputs.audit_hash }}"
```

## Policy fixture

The included policy fixture uses `production.deploy` and blocks production deploys outside the change window or without two approvals. Use it as sample data for a pilot, not as a full policy-management workflow.
