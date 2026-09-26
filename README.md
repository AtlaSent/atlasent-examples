# atlasent-examples

Runnable example integrations — GitHub Actions, raw HTTP, and SDK quickstarts — showing how CI/CD pipelines and agents call AtlaSent's evaluate/verify-permit API to gate protected actions such as production deploys.

> **Versioning note (canonical).** AtlaSent has a single platform
> version — `v1`. There is no "v2 product" and no "v2 surface."
> The `v2/` directory below and the `@atlasent/sdk@^2` pin in some
> examples are **historical labels**, kept so existing links and
> tutorials keep working.
> The substantive work — batch evaluate, streaming evaluate,
> GraphQL read, MCP Streamable HTTP — ships as **Phase 2 additive
> capabilities** on the stable `/v1/*` wire surface and is
> tenant-flag-gated. The directory name is preserved for link
> stability.

Deploy Gate V1 examples for AtlaSent.

The primary walkthrough follows a single scenario: a team wants GitHub Actions to deploy `checkout-api` to production only when AtlaSent issues and verifies a permit for the `production.deploy` action. The other directories apply the same evaluate → permit → verify pattern to other protected actions and runtimes.


## Observe before you gate

The enforcement examples below are intentionally the later stage of the product journey. A connector can start in **Observe** mode: report bounded facts for an already-resolved Canon action, surface them in AtlaSent Action Inbox/History, and let the organization choose whether to protect that action.

Observe-mode integrations must not claim authorization, approval, verification, enforcement, or coverage. A raw provider event name is not automatically a Canon action: map it to a Canon action explicitly before reporting it. The examples in this repository are enforcement examples and stay fail-closed; they do not implement Observe mode.

## Deploy Gate V1 flow

Every Deploy Gate V1 example follows the same seven steps:

1. **Connect CI** — configure the CI runner with `ATLASENT_API_KEY`, `ATLASENT_API_URL`, and the actor identity.
2. **Declare action** — describe the requested action as `production.deploy` with target service, environment, ref, SHA, and change metadata.
3. **Evaluate** — call `POST /v1-evaluate` and fail closed on transport errors or deny decisions.
4. **Issue permit** — continue only if the allow decision includes a permit ID.
5. **Verify permit** — call `POST /v1-verify-permit` or the SDK equivalent immediately before running deployment steps.
6. **Execute/block** — execute the deployment only after verification; otherwise block and exit non-zero.
7. **Audit evidence** — print the permit ID, audit hash, and decision reason so the CI log can be attached to change evidence.

## Start here

| Directory | Status | What it shows |
|---|---|---|
| [`github-action-deploy/`](github-action-deploy/) | **Primary quickstart** | A clean GitHub Actions workflow for Deploy Gate V1 using `production.deploy`, `/v1-evaluate`, and `/v1-verify-permit`. |
| [`saas-production-safeguard/`](saas-production-safeguard/) | **Buyer-acceptance reference** | The full SaaS Production Safeguard Pack fixture: harmless app + build→gate→verify-at-boundary→deploy→evidence workflow + the 8-case buyer-acceptance suite (one job per case). Copy into an AtlaSent-controlled org. |
| [`salesforce-deploy-gate/`](salesforce-deploy-gate/) | **Business-system change gate** | Gate a Salesforce/NetSuite change (metadata deploy or live config edit) on `production.deploy` — illustrative stub data, offline-runnable, copy-me GitHub Actions gate. No new action class (BSCM: a business-system change *is* `production.deploy`). |
| [`node-deploy-gate/`](node-deploy-gate/) | Standalone runner | A Node.js deploy gate for teams that do not use GitHub Actions. |
| [`gitlab-ci-deploy/`](gitlab-ci-deploy/) | GitLab CI | A native `.gitlab-ci.yml` deploy gate (curl + jq, fail-closed) for teams on GitLab — same wire shape as the GitHub quickstart. |

## V1 flows

| Directory | What it shows |
|---|---|
| [`flows/00-golden-path/`](flows/00-golden-path/) | Offline narrated five-scene fixture; it does not claim current-runtime live acceptance. |
| [`flows/01-deploy-gate/`](flows/01-deploy-gate/) | The seven-step gate as a TypeScript script for local CI runner testing. |
| [`flows/04-mcp-claude-code/`](flows/04-mcp-claude-code/) | AtlaSent as an MCP server driving Claude Code. |
| [`flows/06-network-down-fail-closed/`](flows/06-network-down-fail-closed/) | Proves the gate blocks when AtlaSent is unreachable. |
| [`flows/06-sso-walkthrough/`](flows/06-sso-walkthrough/) | End-to-end Okta SSO integration: SSO connection → JIT rule → first audit event. |
| [`flows/07-audit-verify/`](flows/07-audit-verify/) | Offline bundle verification for auditors. |
| [`flows/clinical-unblind-gate/`](flows/clinical-unblind-gate/) | Clinical unblinding execution-system simulator: refuses to release a treatment assignment without a verified, context-bound permit (standard + emergency). |

`flows/00-golden-path` is a presentation fixture with caller-supplied narrative identities and mixed legacy actions. CI rehearses it offline only. The live `production.deploy` check is `flow-01-deploy-gate-live` in `.github/workflows/e2e-smoke.yml`; it uses GitHub OIDC and a runtime-minted `actor_identity.v1` through the pinned AtlaSent Action.

## Phase 2 additive-capability examples (`v2/` directory)

The [`v2/`](v2/) directory hosts CI-tested examples that exercise
**Phase 2 additive capabilities on the `/v1/*` wire surface** —
batch evaluate, streaming evaluate, GraphQL read, and MCP Streamable
HTTP. The directory name is a historical label preserved per
Doctrine 4; the wire surface stays under `/v1/*`. See
**[`v2/README.md`](v2/README.md)** for the full layout and tenant-flag
contract.

> **V1 pilot scoping.** These Phase 2 capabilities are
> tenant-flag-gated. Ask us which are enabled for your tenant before
> building against one.

Quick links:

| Directory | What it shows |
|---|---|
| [`v2/typescript/openai-functions-agent/`](v2/typescript/openai-functions-agent/) | OpenAI Chat Completions agent — tool calls gated by AtlaSent `evaluate` via `@atlasent/sdk@^2` (SDK SemVer per Doctrine 5; targets the `/v1/*` surface). |
| [`v2/python/openai-functions-agent/`](v2/python/openai-functions-agent/) | Python sibling using `httpx`. |
| [`v2/typescript/authorize-many/`](v2/typescript/authorize-many/) | Batch evaluate via `evaluateMany` (tenant-flag `v2_batch`). |
| [`v2/go/`](v2/go/) | Go SDK batch evaluate. |
| [`v2/typescript/risk-envelope-explain/`](v2/typescript/risk-envelope-explain/) | Call `POST /v1-evaluate` with `explain:true` and read back `risk_envelope` — factor scores, `promoted` flag, and `hard_blocks`. |
| [`v2/typescript/webhook-guard/`](v2/typescript/webhook-guard/) | Mount `webhookGuard` from `@atlasent/action/connectors` as Express middleware on `/hooks/deploy`; includes standalone `guard.evaluate()` for non-Express servers. |
| [`v2/typescript/agent-guard/`](v2/typescript/agent-guard/) | `agentGuard` factory with `blockOnHold:true` — `guard.wrap(tool)`, `guard.wrapAll(tools)`, catching `AgentGuardError`, and actor resolution from agent/user context. |

All examples under `v2/` are exercised by [`.github/workflows/v2-examples.yml`](.github/workflows/v2-examples.yml) on every push (Node 20 / Python 3.11 matrix, dry-run mode when no live API key is present).

## Pilot defaults

| Variable | Default / expected value |
|---|---|
| `ATLASENT_API_KEY` | GitHub secret or local env var. |
| `ATLASENT_API_URL` | `https://api.atlasent.io/functions/v1` — the canonical AtlaSent API base URL. Paths such as `/v1-evaluate` are appended to it. Some examples read `ATLASENT_BASE_URL` instead; same value. |
| `ATLASENT_ORG_ID` | Required by SDKs that scope requests by organisation. |
| `SERVICE` | `checkout-api` |
| `TARGET_ENV` | `production` |
| Action | `production.deploy` |
| Evaluate endpoint | `POST /v1-evaluate` |
| Verify endpoint | `POST /v1-verify-permit` |

## Canonical SDK surface examples

When integrating via the AtlaSent SDK (rather than raw HTTP), there are two forms of the canonical execution-boundary contract — both fail-closed, both produce the same audit-chain entry, both keep the Permit visible as a first-class artifact. Pick the form that fits the call site.

| Directory | Surface | When to use |
|---|---|---|
| [`python-sdk-quickstart/`](python-sdk-quickstart/) | `protect()` — primitive that returns the verified `Permit` | You need the Permit as a value to pass across a boundary, persist alongside your record, or interleave with non-trivial control flow. |
| [`typescript-sdk-quickstart/`](typescript-sdk-quickstart/) | `atlasent.protect(...)` | TS twin of the above. |
| [`with-permit-py/`](with-permit-py/) | `with_permit()` — lexically-scoped form with callback | The action body is a single lexical scope; "no permit, no execution" is the only thing the call site needs to express. |
| [`with-permit-ts/`](with-permit-ts/) | `atlasent.withPermit(...)` | TS twin of the above. Requires `@atlasent/sdk@2.10.0`. |
| [`basic-evaluate/`](basic-evaluate/) | Raw HTTP `/v1-evaluate` + `/v1-verify-permit` | You can't (or don't want to) use the SDK and need to see the wire shape. The SDK examples above do both calls for you. |
| [`protected-actions/`](protected-actions/) | `requirePermit()` — descriptor form for dangerous operations | The action is described by a richer `ProtectedAction` (`resource_id` + `environment`) — e.g., `database.table.drop`. |

The canonical surface and the boundary contract are documented in [Runtime flow](https://docs.atlasent.io/concepts/runtime-flow) and the [quickstart](https://docs.atlasent.io/quickstart/first-evaluation).

## Regulated environments

PHI, GxP, and clinical examples live under [`regulated/`](regulated/). These are valid, production-quality examples but are **not part of the Deploy Gate V1 pilot** — if you are a finance or DevOps buyer, you do not need them.

| Directory | What it shows |
|---|---|
| [`regulated/gxp-21cfr-scenario/`](regulated/gxp-21cfr-scenario/) | 21 CFR Part 11 electronic records and audit trail for a pharma AI agent. |
| [`regulated/lims-write/`](regulated/lims-write/) | Gate a write into a Laboratory Information Management System (GxP boundary). |
| [`regulated/clinical-data-export/`](regulated/clinical-data-export/) | Batch-authorize a PHI export; every row is individually evaluated. |
| [`regulated/langchain-clinical-agent/`](regulated/langchain-clinical-agent/) | LangChain agent with per-tool clinical authorization via `@atlasent_guard`. |

## Later-phase examples

The rest of the repository is retained for reference only and is **not part of the Deploy Gate V1 pilot**. SSO, SIEM/webhooks, GitLab, Bitbucket, audit export, drift reporting, policy bundles, agent frameworks, browser examples, and broad SDK integrations are later-phase material. Keep a first pilot on the GitHub Actions deploy gate above.

## Documentation

- **Primary quickstart:** [`github-action-deploy/README.md`](github-action-deploy/README.md)
- **V1 plan:** [`docs/V1_PLAN.md`](docs/V1_PLAN.md)
- **Phase 2 additive examples (`v2/` directory):** [`v2/README.md`](v2/README.md)
- **Later-phase roadmap:** [`ROADMAP.md`](ROADMAP.md)
