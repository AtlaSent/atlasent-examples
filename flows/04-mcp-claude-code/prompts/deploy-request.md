# Deploy request — test prompt

Ask Claude Code something like:

> I want to deploy `checkout-api` to production. Please use the AtlaSent
> MCP server to request a deployment permit for me (actor: me, action:
> `production.deploy`, target: `checkout-api` in `production`), then summarise
> the decision, the risk factors, and the permit ID.

Claude Code should:

1. Call `atlasent.evaluate` via MCP.
2. Report the decision back to you.
3. Refuse to run any deploy command if the decision is not `allow`.
