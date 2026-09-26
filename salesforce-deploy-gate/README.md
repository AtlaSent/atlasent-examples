# Salesforce / NetSuite / ServiceNow / Jira / AWS change gate — `production.deploy`

Gate a **change to a business system of record** (Salesforce metadata deploy,
NetSuite SDF deploy, ServiceNow change request, Jira change/incident issue,
an AWS infrastructure change via Terraform, or a live config edit) on an AtlaSent permit, using the **`production.deploy`** action. This is a
**vendor-neutral "authorized change or deployment plan" execution** flow
(atlasent#438): AtlaSent authorizes the exact change plan and preserves the
evidence, and the plan converges on `production.deploy` regardless of vendor.
**No new action class:** per the canonical Business Systems Change Management
pack (`CAP-BSCM-001`, atlasent#440), a business-system release is
`production.deploy`, and a live config edit is its **state-snapshot execution
profile** — not a new Canon identity.

> **This is a demonstration, not a customer integration.**
> - **Salesforce, NetSuite, ServiceNow, Jira, and AWS are reference scenarios,
>   not customer claims.** By default the payloads here are **hardcoded,
>   synthetic stubs** matching the real change-plan shape. No Salesforce,
>   NetSuite, ServiceNow, Jira, or Terraform/AWS CLI is called.
> - **Optional real-CLI mode** (`connectors.ts`, opt-in via `USE_REAL_CLI=true`):
>   shells out to your real `sf` / `suitecloud` CLI and parses its real
>   dry-run/validate JSON output into the same shape, in place of the sample
>   payload. This is real shellout + real JSON parsing, not a stub — but it has
>   **not been run against a live Salesforce/NetSuite org or CLI** in this repo
>   (no such credentials exist here); the default field mapping matches each
>   CLI's *documented* dry-run JSON shape and is unit-tested against fixture
>   JSON, but confirm it against your actual CLI version's output before pilot
>   use (`ComponentMapping` is overridable via env if it differs). CAB approval
>   count / change window / requester still come from your change-management
>   system, never inferred from the CLI. See the module header in
>   `connectors.ts` for the full boundary statement.
> - **Optional real ServiceNow mode** (`connectors.ts`, opt-in via
>   `USE_REAL_SERVICENOW_API=true`): makes a real, read-only Table API GET
>   against `change_request` (Basic Auth, an `itil`-scoped integration user —
>   the pattern AtlaSent has already proven live against a real PDI, per its
>   internal ServiceNow OAuth setup guide) and parses the
>   real JSON response into the same shape. ServiceNow has no equivalent
>   official deploy CLI, so this reads the change_request record directly
>   instead of shelling out. **Not been run against a live instance from this
>   repo** — confirm `DEFAULT_SERVICENOW_CHANGE_MAPPING` against your
>   instance's actual field set (custom fields, renamed fields) before pilot
>   use. This connector is **read-only** — like the CLI connectors' `validate`/
>   `--dryrun` calls, it never writes to the change_request record; it exists
>   to build a real plan digest, not to execute the change.
> - **Optional real Jira mode** (`connectors.ts`, opt-in via
>   `USE_REAL_JIRA_API=true`): makes a real, read-only REST API GET against
>   `/rest/api/3/issue/{key}` (Basic Auth, `email:api_token` — Atlassian
>   Cloud's documented API-token scheme, no OAuth app required) and parses the
>   real JSON response into the same shape. Jira has no equivalent official
>   deploy CLI either, so this reads the issue directly. **Not been run
>   against a live site from this repo** — confirm `DEFAULT_JIRA_ISSUE_MAPPING`
>   against your project's actual field/issue-type configuration (custom
>   fields, renamed statuses) before pilot use. Also **read-only** — it never
>   transitions or comments on the issue.
> - **Optional real Terraform mode** (`connectors.ts`, opt-in via
>   `USE_REAL_CLI=true` — the same flag as the sf/suitecloud connectors, since
>   this is genuinely a CLI shellout): shells out to `terraform show -json
>   <planfile>` and parses the real plan JSON into the same shape. AWS has no
>   single official "deploy CLI"; Terraform is the reference IaC tool here.
>   **This does NOT run `terraform plan` itself** — your pipeline must already
>   have produced the plan file (`terraform plan -out=<file>`, the step that
>   needs real AWS credentials) before this connector reads it; `terraform
>   show -json` is a pure, read-only re-serialization needing no AWS
>   credentials of its own. `target_system: "aws"` / `plan_format:
>   "terraform-plan"` are both already-documented example values in
>   atlasent's `CHANGE_PLAN_EXECUTION_CONVENTIONS.md`. **Not been run against
>   a live plan file from this repo** — confirm `DEFAULT_TERRAFORM_MAPPING`
>   (`resource_changes[].{type,address}`) against your Terraform/provider
>   version's actual `show -json` output before pilot use.
> - All identifiers (`acme-prod`, `acme-release-bot`, `acmecorp`,
>   `123456789012`, org/account/instance/site ids, digests) are **synthetic
>   placeholders** (`123456789012` is AWS's own well-known documentation
>   example account id). No real credentials, tenant IDs, URLs, permits, or
>   signatures are included — set `ATLASENT_API_KEY` / `ATLASENT_API_URL`
>   yourself for the live path.
> - It reuses `production.deploy`; it introduces **no new canonical action and no
>   wire-contract change**.
> - It does **not yet constitute a live connector-backed close-platform (or any
>   other) integration** — that is a controlled acceptance-run step, not something this
>   demo claims.

## Action vocabulary mapping

| Business-system change | AtlaSent action | Profile |
|---|---|---|
| Salesforce metadata deploy (`sf project deploy`, sandbox → prod) | `production.deploy` | artifact-bound (deploy-plan digest) |
| NetSuite SuiteCloud / SDF project deploy | `production.deploy` | artifact-bound (SDF package digest) |
| ServiceNow change request (`change_request` record, CAB-approved) | `production.deploy` | artifact-bound (change-record digest — the record IS the plan) |
| Jira issue (Change/Incident issue type, CAB-approved) | `production.deploy` | artifact-bound (issue-field digest — the issue IS the plan) |
| AWS infrastructure change (Terraform plan) | `production.deploy` | artifact-bound (Terraform resource-change digest) |
| Live Salesforce config edit (Flow / approval process / validation rule) | `production.deploy` | **state-snapshot profile** (before/after config digest) |

## The flow (fail-closed)

```
Salesforce/NetSuite/ServiceNow/Jira/AWS change  →  build & digest the change plan (or config snapshot)
        →  AtlaSent evaluate  (bind: actor, target org/account/instance/site, environment, payload digest, state snapshot)
        →  require decision=allow AND a permit_token   (else BLOCK)
        →  AtlaSent verify-permit AT THE DEPLOY BOUNDARY  (re-bind the same digest; single-use)
        →  require valid=true   (else BLOCK — mismatch/replay/expired)
        →  run the real deploy  (sf project deploy / SDF deploy / ServiceNow or Jira change implementation / terraform apply)
        →  emit offline-verifiable evidence
```

The permit is **issued at the gate but verified + consumed at the deploy step**.
A swapped metadata package, a wrong target org/environment, or a replayed token
between gate and deploy fails at `/v1-verify-permit` with `PAYLOAD_MISMATCH` /
`ENVIRONMENT_MISMATCH` / `PERMIT_ALREADY_USED`. That is the whole product: the
change that runs is the exact change that was authorized.

## What binds the permit

| Bound field | Source |
|---|---|
| `actor_id` | `github:<username>` (must match the policy `allow_actors`) |
| `target_id` | the Salesforce org / NetSuite account / ServiceNow instance / Jira site / AWS account (e.g. `salesforce:acme-prod`, `servicenow:acmecorp`, `jira:acmecorp`, `aws:123456789012`) |
| `environment` | `production` |
| `execution_payload_hash` | `sha256` of the built change plan (metadata package / SDF project / change_request record fields / Jira issue fields / Terraform resource changes) |
| `context.state_snapshot` | before/after config digest — the state-snapshot profile for live config edits |
| `context.approvals` | CAB approval count (change-management gate) |

## Run it

```bash
npm install

# Offline stub — no API key, no network. Prints the exact evaluate/verify request
# bodies for six illustrative changes: a Salesforce metadata deploy, a NetSuite
# SuiteCloud/SDF deploy, a ServiceNow change request, a Jira issue, an AWS
# Terraform plan, and a live Salesforce config edit (state-snapshot profile).
npm run demo

# Live path — set both secrets, then the stub POSTs to your tenant and fails
# closed unless decision=allow + permit verified.
export ATLASENT_API_KEY=ask_live_...          # scoped evaluate:write + verify:execute
export ATLASENT_API_URL=https://api.atlasent.io/functions/v1   # MUST end in /functions/v1
npm run demo

# Type-check
npx tsc --noEmit

# Unit tests (pure connector-parsing logic — no real sf/suitecloud invoked)
npm test

# Real-CLI mode — replaces the two artifact-bound sample payloads (metadata
# deploy, SDF deploy) with a live `sf` / `suitecloud` dry-run parsed into the
# same shape. Falls back to the sample stub per-change if the CLI is absent or
# its output doesn't match the configured mapping. See the README callout
# above and the connectors.ts header before relying on this for a pilot.
export USE_REAL_CLI=true
export SF_PROJECT_DIR=/path/to/your/sfdx/project     # cwd for the sf CLI
export SF_ORG=your-org-alias
export SUITECLOUD_PROJECT_DIR=/path/to/your/sdf/project
export NETSUITE_ACCOUNT=1234567
export CHANGE_REQUEST_ID=CHG-2026-1234                # from your CAB ticket
export CHANGE_APPROVALS=2
npm run demo

# Real ServiceNow mode — replaces the sample change_request payload with a
# live Table API GET (read-only) parsed into the same shape. Falls back to the
# sample stub if credentials are absent, the request fails, or the response
# doesn't match the configured mapping.
export USE_REAL_SERVICENOW_API=true
export SERVICENOW_INSTANCE=your-instance-name         # https://<instance>.service-now.com
export SERVICENOW_USER=your-itil-scoped-integration-user
export SERVICENOW_PASSWORD=...
export CHANGE_REQUEST_ID=CHG0000123                    # the change number, not the sys_id
export CHANGE_APPROVALS=2
npm run demo

# Real Jira mode — replaces the sample issue payload with a live REST API GET
# (read-only) parsed into the same shape. Falls back to the sample stub if
# credentials are absent, the request fails, or the response doesn't match
# the configured mapping.
export USE_REAL_JIRA_API=true
export JIRA_SITE=your-site-name                        # https://<site>.atlassian.net
export JIRA_EMAIL=your-atlassian-account-email
export JIRA_API_TOKEN=...
export CHANGE_REQUEST_ID=CHG-1234                       # the issue key
export CHANGE_APPROVALS=2
npm run demo

# Real Terraform mode (AWS) — replaces the sample resource-changes payload
# with a real `terraform show -json <planfile>` parsed into the same shape.
# Requires an ALREADY-PRODUCED plan file — this does NOT run `terraform plan`
# itself (see the README callout above and connectors.ts's module header).
export USE_REAL_CLI=true                                # same flag as sf/suitecloud
export TERRAFORM_PLAN_FILE=/path/to/your/tfplan          # from `terraform plan -out=tfplan`
export TERRAFORM_PROJECT_DIR=/path/to/your/terraform/project
export AWS_ACCOUNT_ID=123456789012
export TERRAFORM_WORKSPACE=prod-us-east-1
export CHANGE_REQUEST_ID=CHG-2026-5678
export CHANGE_APPROVALS=2
npm run demo
```

`build.sh` packages the illustrative Salesforce metadata into `out/` and prints
the `sha256` digest the permit binds to — the same digest the reference workflow
computes.

## Use it in CI (copy-me reference gate)

`.github/workflows/deploy-gate.yml` is the reference GitHub Actions gate to copy
into the repo that deploys your Salesforce/NetSuite change. It builds the deploy
plan, evaluates `production.deploy` bound to the plan digest, **verifies the permit
in the deploy job** (the real execution boundary), and only then runs the deploy.
Gate on `verified`, never on `decision`.

Required secrets:

| Secret | Value |
|---|---|
| `ATLASENT_API_KEY` | `ask_*` key scoped `evaluate:write` + `verify:execute` (+ `audit:read`, `audit:export` for evidence) |
| `ATLASENT_API_URL` | `https://api.atlasent.io/functions/v1` (must end in `/functions/v1`) |

## Buyer-acceptance suite

[`.github/workflows/salesforce-acceptance-suite.yml`](../.github/workflows/salesforce-acceptance-suite.yml)
(repo root — GitHub only discovers workflows there, not under a package
subdirectory) runs one job per case (a button in the Actions tab), each a
**real** AtlaSent API response — nothing fabricated. Driver:
`scripts/run-acceptance-case.sh SF-N`. Prerequisite: the org's `production.deploy`
is provisioned enforced with `allow_actors` (see below).

| Case | Scenario | Expected result |
|---|---|---|
| SF-1 | Compliant Salesforce metadata deploy (2 approvals, in window, approved deployer) | `allow` → permit → **verified** → deploy would run |
| SF-2 | Caller outside `allow_actors` | deny `ACTOR_NOT_ALLOWED` — no deploy |
| SF-3 | Only 1 CAB approval (need 2) | deny `INSUFFICIENT_APPROVALS` — no deploy |
| SF-4 | Outside the change window | deny `OUTSIDE_CHANGE_WINDOW` — no deploy |
| SF-5 | Verify with no permit | `MISSING_PERMIT` — no deploy |
| SF-6 | Swapped metadata package after allow | `PAYLOAD_MISMATCH` — no deploy |
| SF-7 | Production permit presented for sandbox | `ENVIRONMENT_MISMATCH` — no deploy |
| SF-8 | Replayed (reused) permit | `PERMIT_ALREADY_USED` (replay_blocked) — no second deploy |
| SF-9 | Live config edit (state-snapshot profile), compliant | `allow` → permit bound to before/after state → **verified** |
| SF-10 | Expired permit (needs short-TTL class) | `PERMIT_EXPIRED` — no deploy (skips unless TTL ≤ 60s) |

```bash
export ATLASENT_API_KEY=ask_live_...
export ATLASENT_BASE_URL=https://api.atlasent.io/functions/v1
export ATLASENT_ACTOR='github:github-actions[bot]'   # MUST match the seeded allow_actors
bash scripts/run-acceptance-case.sh SF-1             # one case (Salesforce, the default)

TARGET_SYSTEM=netsuite   bash scripts/run-acceptance-case.sh SF-1   # the same case against NetSuite
TARGET_SYSTEM=servicenow bash scripts/run-acceptance-case.sh SF-1   # the same case against ServiceNow
TARGET_SYSTEM=jira       bash scripts/run-acceptance-case.sh SF-1   # the same case against Jira
TARGET_SYSTEM=aws        bash scripts/run-acceptance-case.sh SF-1   # the same case against AWS
# or run every case × every system from the Actions tab
# (workflow_dispatch: case=all, target_system=all)
```

### Salesforce, NetSuite, ServiceNow, Jira, and AWS are one contract, run five times

The suite is parameterized by `TARGET_SYSTEM` (`salesforce` | `netsuite` |
`servicenow` | `jira` | `aws`, default `salesforce`). All five drive the
**same** `production.deploy` action and the same vendor-neutral change-plan
conventions — only `target_id` and `plan_format` differ (`salesforce-change-set`
vs `netsuite-sdf-project` vs `servicenow-change-request` vs `jira-issue` vs
`terraform-plan`). An unrecognized system fails closed rather than quietly
running Salesforce.

**A Salesforce run does not evidence NetSuite, ServiceNow, Jira, or AWS** (and
vice versa). To claim more than one, run each and record each pass
separately. One case is deliberately Salesforce-only: **SF-9** (live config
edit) has no NetSuite, ServiceNow, Jira, or AWS `plan_format` in the
change-plan vocabulary, so under any other `TARGET_SYSTEM` it reports
**SKIPPED with that reason** rather than inventing `netsuite-config-edit` /
`servicenow-config-edit` / `jira-config-edit` / `aws-config-edit`. NetSuite,
ServiceNow, Jira, and AWS change plans are covered by SF-1..SF-8.

Every evaluate carries the change-plan conventions (`target_system`, `plan_format`,
`authority_path`, `canonical_plan_digest`, `evidence_set_digest`) in the open context,
so they appear in the exported evidence where the acceptance lane asserts them.
`canonical_plan_digest` is always the `execution_payload_hash` the permit binds, and
`evidence_set_digest` is a real digest over the approval evidence the case presents —
it changes when the evidence changes.

## Provision the tenant side (for the live path / pilot)

The `production.deploy` class must be **enforced with an active bundle**, else
evaluate returns `allow` with **no permit** (shadow class) and the gate correctly
fails closed. Seed it with the SaaS Production Safeguard function (reused as-is —
no new action class):

```sql
select public.seed_saas_production_safeguard('<org-uuid>');
-- 1-arg is the only deployed signature, and it BAKES IN
--   allow_actors = ['github:github-actions[bot]']
-- Run the suite as that caller (ATLASENT_ACTOR), or republish the bundle's
-- allow_actors to your approved deployer FIRST and set ATLASENT_ACTOR to match.
-- Mismatch here is the #1 acceptance-run failure: SF-1/SF-9 deny ACTOR_NOT_ALLOWED.
```

The `policies/production-deploy.json` bundle in this directory is the illustrative
policy (CAB approval `require_approvals: 2` + change-window + `allow_actors`);
`policies/production-deploy.tests.json` holds the allow/deny fixtures.

## Evidence & offline verification

Every gated change produces tamper-evident, offline-verifiable evidence — the
authorization is provable after the fact without trusting AtlaSent at verify time:

- **Per run:** the gate workflow's `Audit evidence` step emits the `permit_token`
  and `audit_entry_hash` for the change that ran. `/v1-evaluate` writes the
  immutable, hash-linked, Ed25519-signed audit entry **before** the deploy runs.
- **Export the chain:** pull the audit bundle for a window/actor via the SDK
  (`@atlasent/sdk` or the `atlasent` Python SDK) — see
  [`../accounting-close/verify-audit.py`](../accounting-close/verify-audit.py)
  for the export + verify pattern (`audit:read` + `audit:export` scopes).
- **Verify offline:** validate the exported bundle with the standalone
  `atlasent-audit-verify` CLI (repo `atlasent-verify`) — hash-chain continuity +
  Ed25519 signatures, no network, no AtlaSent dependency. Use
  `--require-signatures` so a green run positively proves every entry was
  signature-checked.

This demo does not ship a pre-baked bundle: evidence is real runtime state, so
generate it from a live run against your provisioned org rather than inspecting a
fabricated file.

## Becoming a pilot

This demo is deliberately the **runnable, clonable** shape. To graduate it to a
buyer-acceptance pilot, mirror `saas-production-safeguard/` (the build → gate →
verify-at-boundary → deploy → evidence workflow + the per-case acceptance matrix),
pointing its `target_id` at the pilot's Salesforce org / NetSuite account /
ServiceNow instance / Jira site / AWS account. The authorization contract does
not change — it is `production.deploy` throughout.
