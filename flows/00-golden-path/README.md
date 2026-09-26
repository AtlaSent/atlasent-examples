# 00 · Golden-path demo seed (offline narrative)

A fixed, narrated sequence of five AtlaSent decisions: normal allow,
risk-based deny, step-up recovery, regulated write, and
separation-of-duties deny.

This fixture is for sales walkthroughs. Every scene has a one-line narrative,
a declared expected decision, and enough context for a viewer to follow
without reading code.

## Rehearse it (<3 min)

```bash
npm install
npm run dry-run
```

Scheduled CI runs this same offline rehearsal with the pause set to zero.
`GOLDEN_PATH_PACE_MS` defaults to `1200` locally.

## Authority boundary

The five decisions printed in dry-run mode are fixture expectations, not
responses observed from a live AtlaSent runtime. They are not acceptance
evidence and do not prove that a Permit was issued or verified.

The scenarios intentionally mix a narrated human/service actor model with
legacy action identifiers. Current `production.deploy` requires a signed
`actor_identity.v1`; a GitHub workflow must obtain that identity through the
runtime broker from GitHub OIDC, not construct it from the scenario's
caller-supplied actor and not store an actor-signing private key.

For the current live staging contract, use the
`flow-01-deploy-gate-live` job in
[`.github/workflows/e2e-smoke.yml`](../../.github/workflows/e2e-smoke.yml).
That job uses the pinned AtlaSent Action to mint brokered workload identity,
evaluate, issue a Permit on ALLOW, and verify it fail-closed.

## What's in the seed

| # | Scene | Declared expectation |
|---|---|---|
| 1 | Normal production deploy | allow |
| 2 | After-hours deploy from unfamiliar actor | deny |
| 3 | Same deploy after MFA step-up + approver | allow |
| 4 | Regulated LIMS write (HbA1c) | allow |
| 5 | Bulk clinical export without override | deny |

Scenes 1–3 tell one deploy story with escalating context. Scenes 4–5 switch
to the GxP / clinical story. Fixtures live in
[`scenarios.json`](./scenarios.json), so the narrative can be edited without
changing the runner.

## Exit codes for the offline rehearsal

| Code | Meaning |
|---|---|
| `0` | The fixture loaded and all five scenes were rehearsed |
| `1` | The fixture or runner failed unexpectedly |

## Speaker notes

See [`demo-script.md`](./demo-script.md) for the per-scene talk track
(~4 minutes on a live call, ~2 minutes with `GOLDEN_PATH_PACE_MS=400`).
