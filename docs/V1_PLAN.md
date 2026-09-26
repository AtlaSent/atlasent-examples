# Deploy Gate V1 Plan

Deploy Gate V1 is one pilot story: **GitHub Actions requests permission to deploy `checkout-api` to production, AtlaSent evaluates `production.deploy`, a permit is issued and verified, and the deployment either executes or blocks with audit evidence.**

## Canonical 7-step flow

1. **Connect CI** — add `ATLASENT_API_KEY`, `ATLASENT_API_URL`, and optional `ATLASENT_ORG_ID` to the CI environment.
2. **Declare action** — model the action as `production.deploy` with service, environment, ref, SHA, change window, and approval metadata.
3. **Evaluate** — call `POST /v1-evaluate` or the SDK `evaluate` wrapper.
4. **Issue permit** — require an allow decision with a permit ID before continuing.
5. **Verify permit** — call `POST /v1-verify-permit` or the SDK verify wrapper immediately before deployment.
6. **Execute/block** — execute deployment commands only after permit verification; deny, hold, missing permit, invalid permit, and network errors block.
7. **Audit evidence** — print decision, reason, permit ID, audit hash, service, environment, ref, and SHA into the CI log.

## In scope for V1

- One clean GitHub Actions quickstart in `github-action-deploy/`.
- Local Deploy Gate runner in `flows/01-deploy-gate/`.
- Standalone Node runner in `node-deploy-gate/`.
- Network-down fail-closed regression in `flows/06-network-down-fail-closed/`.
- Use `production.deploy` everywhere for deploy policy examples.
- Use `/v1-evaluate` and `/v1-verify-permit` everywhere endpoints are shown directly.

## Out of scope until later phases

- SSO setup walkthroughs.
- SIEM ingest and webhook receivers.
- GitLab, Bitbucket, and broad CI integrations beyond GitHub Actions.
- Audit export/offline verifier examples.
- Drift reporting.
- Policy bundle management examples.
- Agent-framework, browser, regulated workflow, and broad SDK integration demos.
