# GitHub Actions Agent Tool Gate — AtlaSent Quickstart

AtlaSent-gated tool calls in a CI-driven agent pipeline. This quickstart
is the **agent tool call equivalent** of
[`atlasent-examples/github-action-deploy/`](../github-action-deploy/) —
same 7-step structure, same permit-verify-consume pattern, applied to
agent tool gating instead of deployment gating.

Every tool call (`bash`, `read_file`, `write_file`, or any custom tool)
is evaluated by AtlaSent before execution. High-risk tools require a
witness; low-risk tools are auto-approved; unknown tools are medium-risk
by default.

## The 7-step flow

1. **Connect CI** — add `ATLASENT_KEY` to GitHub Actions secrets.
2. **Declare tool action** — describe each tool call as `agent_tool.<toolName>`.
3. **Evaluate** — ask AtlaSent whether the agent may execute the tool.
4. **Issue permit** — require an allow decision with a permit ID.
5. **Execute tool** — run the tool only when the permit is issued.
6. **Consume permit** — close the audit record after execution (always runs).
7. **Audit evidence** — write the decision, permit ID, audit hash, tool name, and agent to the job log.

## Prerequisites

Add these repository secrets in **Settings → Secrets and variables → Actions**:

| Secret | Purpose |
|---|---|
| `ATLASENT_KEY` | API key used by the workflow. |
| `ATLASENT_API_URL` | Optional; defaults to `https://api.atlasent.io/functions/v1`. |

## Step 1: Connect CI

Add `ATLASENT_KEY` to your repository secrets. The workflow reads it as
`${{ secrets.ATLASENT_KEY }}`.

## Step 2: Seed the policy pack

> ⚠️ **WARNING**: This endpoint (`v1-policy-bundles`) is disabled in production and will return 404. See `atlasent-api/supabase/runtime-functions-disabled.json`.

```bash
curl -X POST https://api.atlasent.io/functions/v1/v1-policy-bundles \
  -H "Authorization: Bearer $ATLASENT_KEY" \
  -H "Content-Type: application/yaml" \
  --data-binary @policies/agent-tool.yaml
```

The policy pack enforces:
- `bash` → **high risk**, requires witness (`HOLD_WITNESS_REQUIRED`)
- `read_file` → **low risk**, auto-approved (`ALLOW`)
- all others → **medium risk** (evaluated per-session policy)

## Step 3: Install dependencies

```bash
npm install
```

## Step 4: Run the workflow

Trigger via the GitHub Actions UI (`workflow_dispatch`) or CLI:

```bash
gh workflow run agent-tool-gate.yml \
  -f tool_name=read_file \
  -f tool_args='{"path": "src/config.json"}'
```

```bash
gh workflow run agent-tool-gate.yml \
  -f tool_name=bash \
  -f tool_args='{"command": "ls -la"}'
```

## Step 5: Evaluate locally

```bash
cp .env.example .env
# Fill in ATLASENT_KEY

TOOL_NAME=read_file TOOL_ARGS='{"path":"README.md"}' AGENT_ID=dev SESSION_ID=local-1 \
  npx tsx src/evaluate.ts
```

## Step 6: Review the audit chain

Every tool call evaluation is recorded in the AtlaSent audit chain:

```bash
curl -H "Authorization: Bearer $ATLASENT_KEY" \
  "https://api.atlasent.io/v1/audit/exports?action=agent_tool.bash&from=2026-05-01" \
  -o agent-tool-audit.json
```

The chain captures: tool name, agent identity, session ID, decision,
permit ID, audit hash, and whether the permit was consumed (tool executed).

## Step 7: Offline bundle verification

Audit bundles follow the same SHA-256 hash-linked, Ed25519-signed format
as the accounting-close bundle. Verify with the shared verifier:

```bash
python ../accounting-close/verify-audit.py --bundle audit-bundle.json
```

## Workflow overview

```
workflow_dispatch
  → inputs: tool_name, tool_args
  → evaluate (src/evaluate.ts)
      → atlasent.protect({ action: "agent_tool.<toolName>", context: { toolName, toolArgs, agentId, sessionId } })
      → writes decision, permit_id, audit_hash to $GITHUB_OUTPUT
  → execute (src/execute.ts)   [only if decision == 'ALLOW']
      → stub tool dispatcher (replace with real tool execution)
  → consume (src/consume.ts)   [always]
      → atlasent.verifyAndConsume(permit_id)
  → audit evidence              [always]
      → logs tool_name, agent_id, session_id, decision, permit_id, audit_hash
```

## Action string convention

Tool call actions use the `agent_tool.<toolName>` convention:

| Tool | Action string | Risk level |
|---|---|---|
| `bash` | `agent_tool.bash` | high — requires witness |
| `read_file` | `agent_tool.read_file` | low — auto-approved |
| `write_file` | `agent_tool.write_file` | medium |
| `http_request` | `agent_tool.http_request` | medium |
| custom tool | `agent_tool.<custom>` | medium (default) |

## Fail-closed behavior

`src/evaluate.ts` is fail-closed:
- Any `AtlaSentDeniedError` → decision=DENY, exit 0 (not a CI failure)
- Any `AtlaSentError` (transport/server) → decision=DENY, exit 1 (CI failure surfaced)
- The execute step is skipped on any DENY

The consume step runs with `if: always()` so permits are consumed even if
the execute step fails — this closes the audit record accurately.

## Related

- Deploy gate quickstart: [`atlasent-examples/github-action-deploy/`](../github-action-deploy/)
- Accounting close authorization: [`atlasent-examples/accounting-close/`](../accounting-close/)
- Policy reference: [`policies/agent-tool.yaml`](./policies/agent-tool.yaml)
