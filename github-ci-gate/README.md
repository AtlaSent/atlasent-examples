# GitHub CI Gate — AtlaSent External Signal Ingestion

This example shows how to integrate AtlaSent's external assertion system into
a GitHub Actions CI/CD pipeline so that a `production.deploy` evaluation can
require proof that CI passed.

## What it does

1. **CI job** — runs your tests on every push.
2. **Post-assertion job** — after CI passes on `main`, posts a `github.ci_passed`
   assertion to AtlaSent (`POST /v1/assertions`) recording that tests passed for
   this exact SHA. The assertion is valid for 24 hours.
3. **Deploy job** — calls `POST /v1-evaluate` with `action_type: production.deploy`.
   Because the assertion exists and is unexpired, your AtlaSent policy can require
   `context.activeAssertions` to contain `github.ci_passed` before issuing a permit.
   The job fails if the decision is not `allow`.

The two phases are independent on purpose: CI and deployment can run at different
times (e.g. auto-deploy after merge review), and the assertion record bridges the
gap. The assertion is cryptographically hashed (`payload_hash`) so any tampering
is detectable.

## Prerequisites

Add these repository secrets in **Settings → Secrets and variables → Actions**:

| Secret | Purpose |
|---|---|
| `ATLASENT_API_KEY` | API key for your AtlaSent organization. |

Your API key must have at minimum these scopes:
- `assertions:write` — submit CI assertions
- `evaluate:write` — request authorization decisions
- `verify:execute` — verify issued permits (if you add a permit-verify step)

## Files

| File | Purpose |
|---|---|
| `.github/workflows/ci-with-gate.yml` | Complete GitHub Actions workflow |
| `atlasent-assertions.ts` | TypeScript helper using `@atlasent/sdk` for programmatic use |

## Policy configuration

For the deployment gate to enforce the CI requirement, your AtlaSent policy for
`production.deploy` should include a rule like:

```yaml
- effect: deny
  conditions:
    - field: "context.activeAssertions"
      operator: not_contains
      value: "github.ci_passed"
  reason: "CI must pass before production deploys"
```

When using the `github-production-deploy-gate` action pack, the CI requirement
rule is included in the `require-ci-gate` template.

## Two-phase flow diagram

```
push to main
    │
    ▼
┌─────────────────────────────┐
│  test job                   │
│  runs your test suite       │
│  outputs: sha               │
└──────────────┬──────────────┘
               │ needs: test
               ▼
┌─────────────────────────────┐
│  post-assertion job         │
│  POST /v1/assertions        │
│  assertion_type: github.ci_passed │
│  subject_ref: repo@sha      │
│  valid for 24 hours         │
└──────────────┬──────────────┘
               │ needs: post-assertion
               ▼
┌─────────────────────────────┐
│  deploy job                 │
│  POST /v1-evaluate          │
│  action_type: production.deploy │
│  policy checks activeAssertions │
│  → allow: deploy runs       │
│  → deny: job fails          │
└─────────────────────────────┘
```

## Using the TypeScript helper

If you call AtlaSent from Node.js instead of curl, use `atlasent-assertions.ts`:

```ts
import { assertCIPassed } from './atlasent-assertions.js';

await assertCIPassed({
  sha:    process.env.GITHUB_SHA!,
  repo:   process.env.GITHUB_REPOSITORY!,
  actor:  process.env.GITHUB_ACTOR!,
  runId:  process.env.GITHUB_RUN_ID!,
});
```

Install the SDK first: `npm install @atlasent/sdk`
