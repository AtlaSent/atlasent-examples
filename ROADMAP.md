# atlasent-examples — roadmap

This repo's job is to give you runnable examples of the AtlaSent `v1`
contract, end to end. The canonical starting point is the deploy gate:
GitHub Actions asks permission to deploy, AtlaSent evaluates
`production.deploy`, a permit is issued and verified, and the deploy
either runs or blocks with audit evidence.

Everything below is **direction, not commitment**. Items in "Next" are
things we intend to add; nothing here is a dated promise, and an entry
moving is not a regression.

## Here now

Start with these — they run today.

- [`github-action-deploy/`](github-action-deploy/) — the primary
  quickstart: a clean GitHub Actions workflow exercising
  `production.deploy`, `/v1-evaluate` and `/v1-verify-permit`.
- [`flows/01-deploy-gate/`](flows/01-deploy-gate/) — the same seven-step
  gate as a runnable local TypeScript script.
- [`node-deploy-gate/`](node-deploy-gate/) — a standalone Node runner
  for teams not on GitHub Actions.
- [`flows/06-network-down-fail-closed/`](flows/06-network-down-fail-closed/)
  — the safety regression: proves the gate blocks when AtlaSent is
  unreachable. Worth reading even if you never run it, because
  fail-closed is the property the whole design rests on.
- [`typescript-sdk-quickstart/`](typescript-sdk-quickstart/) and
  [`python-sdk-quickstart/`](python-sdk-quickstart/) — the same flow
  through the published SDKs.

Supporting reading:

- [`docs/V1_PLAN.md`](docs/V1_PLAN.md) — the canonical seven-step flow,
  written out.
- [`docs/FIRST_HOUR_RUNBOOK.md`](docs/FIRST_HOUR_RUNBOOK.md) — a
  minute-by-minute walkthrough for an engineer who has never seen
  AtlaSent and has an hour.

## Next

Additive on the stable `/v1/*` surface. Some are tenant-gated — ask us
which are enabled for your tenant before building against one.

- CI gates beyond GitHub Actions — GitLab and Bitbucket.
- Audit export and offline verifier walkthroughs.
- SSO setup, SIEM ingest and webhook receivers.
- Policy bundle management and drift reporting.
- Broader agent-framework coverage — LangChain, LlamaIndex, OpenAI
  function calling, MCP.
- Batch, streaming and GraphQL examples, each showing both the
  flag-on path and the flag-off fallback so you can copy either.
- A CI matrix running every example on every push.

## Later

Longer-horizon, and deliberately vaguer because the shape is not settled:

- A proof-system lifecycle example — online verification, offline
  bundle verification with `atlasent-verify`, and payload binding.
- A deterministic replay harness for CI and auditor use.
- Multi-region continuity examples.

## A note on the `v2/` directory

There is one platform version: `v1`. The `v2/` directory name and the
`@atlasent/sdk@^2` pin in some examples are historical labels, kept so
existing links and tutorials keep working. They are not a claim about a
second platform version, and everything in that directory runs against
the same `/v1/*` endpoints.
