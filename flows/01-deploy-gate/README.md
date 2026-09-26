# 01 · Deploy Gate V1

Gate `checkout-api` under the `production.deploy` action. This directory and
scheduled CI cover two different, explicitly named contracts.

## Local wire-contract runner

The TypeScript runner builds the canonical evaluate and verify request shapes,
fails closed on transport and non-ALLOW outcomes, and never prints API keys or
Permit tokens. Its offline contract tests run on every workflow execution:

```bash
npm install
npm run typecheck
npm test
```

A manual `npm start` can call a configured runtime, but the raw HTTP runner
does not mint `actor_identity.v1`. Because current `production.deploy`
requires a verified actor, an authenticated deny from that runner proves the
fail-closed boundary only. It does **not** prove ALLOW → Permit → verification.

## Live GitHub OIDC path

The `flow-01-deploy-gate-live` job in
[`.github/workflows/e2e-smoke.yml`](../../.github/workflows/e2e-smoke.yml)
uses the AtlaSent Action pinned to an immutable reviewed commit. The job has
`permissions: id-token: write` and GitHub Environment `staging`.

The Action requests a GitHub OIDC JWT for audience
`atlasent:actor_identity.v1`. The runtime broker verifies the JWT and an
exact tenant-owned workload enrollment, then signs the workload's
`actor_identity.v1`. No actor-signing private key is stored in this repository
or in GitHub Actions.

The runtime credential must be stored as repository secret
`ATLASENT_STAGING_API_KEY` and carry exactly the permissions needed by this
path:

- `evaluate:write`
- `verify:execute`
- `idp_broker:mint`

Set repository secret `ATLASENT_STAGING_API_URL` to the staging
`/functions/v1` base URL. The workflow maps it to the Action's
`ATLASENT_BASE_URL` variable.

The active enrollment must match every signed dimension exactly:

| Dimension | Value |
|---|---|
| Repository | `AtlaSent-Systems-Inc/atlasent-examples` |
| Immutable repository ID | `1213717770` |
| Workflow ref | `AtlaSent-Systems-Inc/atlasent-examples/.github/workflows/e2e-smoke.yml@refs/heads/main` |
| Ref | `refs/heads/main` |
| GitHub Environment | `staging` |
| AtlaSent environment | `staging` |
| Protected action | `production.deploy` |

Enrollment, a policy that admits the derived workload actor, and a GitHub App
installation owned by the same AtlaSent organization are operator
prerequisites. Merged workflow code is not evidence that any of them exist.

The live job succeeds only when the Action reports both
`decision=allow` and `verified=true`. It contains no deploy command; the
result is staging authorization evidence, not a production deployment.

## Local runner exit codes

| Code | Meaning |
|---|---|
| `0` | Allowed, Permit issued and verified, simulated deploy reached |
| `2` | Denied or otherwise not allowed |
| `3` | Permit or execution-binding verification failed |
| `1` | Unexpected error |
