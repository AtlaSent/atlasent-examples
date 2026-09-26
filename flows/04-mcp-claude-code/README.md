# 04 · MCP + Claude Code

Let Claude Code request AtlaSent permits on your behalf via the AtlaSent
MCP server (`@atlasent/mcp-server`). Drop the `.mcp.json` here into any
repo and Claude Code picks it up automatically on the next session.

## Run it (<3 min)

```bash
export ATLASENT_API_KEY=ask_test_REPLACE_ME
just run   # launches `claude` in this directory
```

Or from any shell:

```bash
cd flows/04-mcp-claude-code
claude
```

Then try the test prompt in [`prompts/deploy-request.md`](./prompts/deploy-request.md).

## Files

| File                         | Purpose                                                |
|------------------------------|--------------------------------------------------------|
| `.mcp.json`                  | Picked up by Claude Code; spawns the AtlaSent MCP srv  |
| `justfile`                   | `just run` → launch Claude Code here                   |
| `prompts/deploy-request.md`  | A prompt that exercises `atlasent.evaluate`            |

## What the MCP server exposes

Once wired in, Claude Code sees these tools (full list in
`atlasent-mcp-server`):

- `atlasent.evaluate` — ask for a decision + permit
- `atlasent.verifyPermit` / `atlasent.consumePermit`
- `atlasent.listPolicies` / `atlasent.getAuditTrail`

## What to look at next

- `flows/01-deploy-gate` — same gate, called programmatically.
- `v2/mcp-server/claude-desktop-config.json` — the Claude Desktop variant.
