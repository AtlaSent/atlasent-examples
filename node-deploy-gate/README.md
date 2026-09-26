# Node Deploy Gate V1

Standalone Node.js CI deploy gate for teams that do not use GitHub Actions. It uses the same Deploy Gate V1 pilot story as the primary quickstart: `checkout-api` deploying to `production` under `production.deploy`.

## 7-step flow

1. **Connect CI** — load AtlaSent env vars.
2. **Declare action** — build a `production.deploy` request.
3. **Evaluate** — call `POST /v1-evaluate`.
4. **Issue permit** — require allow plus permit ID.
5. **Verify permit** — call `POST /v1-verify-permit`.
6. **Execute/block** — run deploy only after verification.
7. **Audit evidence** — print permit ID, audit hash, service, environment, ref, and SHA.

## Run

```bash
export ATLASENT_API_KEY=ask_test_...
export ATLASENT_API_URL=https://api.atlasent.io/functions/v1
npm install
npm start
```

Optional overrides: `SERVICE`, `TARGET_ENV`, `ACTOR`, `GITHUB_REF`, and `GITHUB_SHA`.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Allowed, permit issued and verified, deployment proceeded |
| `2` | Denied or not allowed |
| `3` | Allowed but no permit, or permit verification failed |
| `1` | Unexpected error |
