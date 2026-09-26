> **Later-phase reference.** This document is not part of the Deploy Gate V1 pilot. Keep first pilots focused on GitHub Actions + `production.deploy` + `/v1-evaluate` + `/v1-verify-permit`.

> **Historical directory name.** Kept so existing links and tutorials
> keep working. The `v2/` directory name and `v2_*` tenant-flag
> identifiers below are historical labels. The substantive examples —
> batch evaluate, streaming evaluate, GraphQL read, MCP Streamable
> HTTP, OpenAI function-calling agent — ship as **Phase 2 additive
> capabilities** on the stable `/v1/*` wire surface. There is no
> "v2 product" and no "v2 surface"; the wire surface stays under
> `/v1/*`. Per Doctrine 5, `@atlasent/sdk@^2` is per-package SemVer
> and is independent of the platform version.

# Phase 2 additive-capability examples (`v2/` directory)

This directory hosts runnable
examples that exercise **Phase 2 additive capabilities** — batch
evaluate, streaming evaluate, GraphQL read, MCP Streamable HTTP —
on top of the stable `/v1/*` endpoints.

Everything in this directory is intended to be CI-tested by
`.github/workflows/v2-ci-matrix.yml` against a sandbox project.

## Layout

| Path | What it shows |
|---|---|
| `v2/python/authorize_many.py` | Batch evaluate via `client.authorize_many` |
| `v2/python/evaluate_basic.py` | Single-call `client.evaluate` (parity check vs base `/v1-evaluate`) |
| `v2/python/openai-functions-agent/` | OpenAI Chat Completions agent with tool-call gating |
| `v2/typescript/authorizeMany.ts` | Batch evaluate via `client.evaluateMany` |
| `v2/typescript/openai-functions-agent/` | TypeScript variant of the OpenAI agent |
| `v2/typescript/risk-envelope-explain/` | Call evaluate with `explain:true` and read `risk_envelope` — factor scores, `promoted`, `hard_blocks` |
| `v2/typescript/webhook-guard/` | Mount `webhookGuard` as Express middleware; standalone `guard.evaluate()` for non-Express servers |
| `v2/typescript/agent-guard/` | `agentGuard` factory: `guard.wrap(tool)`, `guard.wrapAll(tools)`, `AgentGuardError` handling |
| `v2/go/authorize_many.go` | Go SDK batch evaluate |
| `v2/github-action/` | Workflow demonstrating `evaluations:` list input |
| `v2/mcp-server/` | MCP Streamable HTTP transport demo |

## Tenant flags

These Phase 2 additive capabilities are **tenant-flag-gated** and
tenant-scoped. Examples honor the per-tenant flags
via env vars (flag names retained as code-level identifiers per
Doctrine 4):

- `ATLASENT_V2_BATCH=true` — use `/v1-evaluate/batch`
- `ATLASENT_V2_STREAMING=true` — use `/v1-evaluate/stream`
- `ATLASENT_V2_GRAPHQL=true` — use `/v1/graphql`

When unset, examples fall back to base `/v1-*` paths so they keep
running against the pilot-tier API today.

## Wire surface

All endpoints exercised here live under `/v1/*`. There is no `/v2/*`
URL namespace and no plan to introduce one (Doctrine 3). New Phase 2
endpoints land additively under `/v1/*`.

## Promotion vs base `/` (V1 flow examples)

V1 flow examples remain at the repo root (`basic-evaluate/`,
`langchain-guarded-agent/`, etc.) for now. Whether to move them
under a parallel directory is open question C.E4 in plan #21 —
not in scope here.

## See also

- Repo-level versioning callout: [`../README.md`](../README.md)
