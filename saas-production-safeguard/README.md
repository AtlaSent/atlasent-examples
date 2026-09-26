# SaaS Production Safeguard Pack — reference environment

The runnable reference fixture for the **SaaS Production Safeguard Pack** (canonical
spec: `atlasent` `contract/safeguard-pack/products/saas-production-safeguard/`). Copy
this directory into an **AtlaSent-controlled** GitHub repo, set two secrets, and you
have the full build → gate → verify-at-execution-boundary → deploy → evidence path
plus the eight-case buyer-acceptance suite — all running against the live AtlaSent API
before any customer grants access.

## What's here

```
app/build.sh        harmless static "build" (emits out/index.html + a digest)
app/deploy.sh       harmless "deploy" (no-op static publish)
.github/workflows/
  deploy-gate.yml    action-based gate: build → authorize → verify @ boundary → deploy → evidence
  acceptance.yml     the 8 acceptance cases, one job each (buyer-clickable)
scripts/
  run-acceptance-case.sh   the per-case driver (real API responses, no fabrication)
```

## Setup (in the AtlaSent-controlled org)

1. Copy this directory to the repo root of the reference repo.
2. Provision the org's `production.deploy` via `seed_saas_production_safeguard(<org_id>)`
   (enforced + `allow_actors`). AtlaSent performs this step for the
   reference org; see the pack runbook.
3. Set repo secrets:
   - `ATLASENT_API_KEY` — `ask_*` scoped `evaluate:write` + `verify:execute` (+ `audit:read`, `audit:export`)
   - `ATLASENT_BASE_URL` — `https://api.atlasent.io/functions/v1` (**must** end in `/functions/v1`; self-hosted: your deployment's `https://<ref>.supabase.co/functions/v1`)

## Run

- **Happy path:** Actions → `deploy-gate` → Run. The workflow pins
  `atlasent-action` to the reviewed commit, issues an unconsumed permit, and
  independently verifies and consumes it immediately before the harmless deploy.
- **HR-1 human-resume companion:** Run `deploy-gate` with `wait_for_approval=true`
  only after the reference policy is configured to return `hold` or `escalate`.
  An authorized human resolves that exact request in the console; the workflow
  resumes only on a fresh, correctly bound terminal permit and then verifies it at
  the deploy boundary. The evidence must show the same evaluation ID, a
  `waited-for-approval=true` output, and a successful boundary verification.
- **Acceptance suite:** Actions → `acceptance-suite` → Run (case = `all`). Each of
  AC-1..AC-8 runs as its own job and asserts the expected runtime code and that no
  deploy would run.

| Case | Asserts |
|---|---|
| AC-1 compliant | allow + permit; verify `verified`; deploy runs |
| AC-2 caller outside authority | evaluate deny `ACTOR_NOT_ALLOWED` |
| AC-3 missing approval | evaluate deny `INSUFFICIENT_APPROVALS` |
| AC-4 missing permit | verify `MISSING_PERMIT` (invalid) |
| AC-5 altered artifact | verify `PAYLOAD_MISMATCH` (mismatch) |
| AC-6 wrong environment | verify `ENVIRONMENT_MISMATCH` (mismatch) |
| AC-7 expired permit | verify `PERMIT_EXPIRED` (expired) — see note |
| AC-8 replayed permit | 2nd verify `PERMIT_ALREADY_USED` (replay_blocked) |

**AC-7 note (honest):** the default permit TTL is 1h, impractical to wait for in CI.
To run AC-7 automatically, set the reference org's `production.deploy`
`permit_ttl_seconds` ≤ 60 and the repo variable `PERMIT_TTL_SECONDS` to match; the
driver then waits and verifies expiry. Otherwise AC-7 reports **SKIPPED** with
guidance — it is never faked green.

## Prerequisites (from the pack readiness ledger)

- **B1** — the org's `production.deploy` is `enforced` (else no permit is minted and
  AC-1 fails at the gate).
- **B2** — the bundle carries `allow_actors` (provided by `seed_saas_production_safeguard`;
  else AC-2 does not produce `ACTOR_NOT_ALLOWED`).
- **B3/B4** — verification happens in the `deploy` job with `environment` + artifact
  digest, so AC-5/AC-6 fail at the execution boundary (not only at evaluate).
- **HR-1** — configure a test-only reference policy to return `hold` or `escalate`
  and assign an authorized human resolver. This is deliberately separate from the
  eight acceptance cases and must never be enabled against a customer or production
  environment.

## Why this matters

The app does nothing consequential — the deploy is a static no-op. The product being
demonstrated is the **authorization chain**: request → authority → decision → permit →
execution → verification → evidence, and that the gate genuinely fails for a missing,
expired, replayed, wrong-artifact, wrong-environment, or unauthorized permit.
