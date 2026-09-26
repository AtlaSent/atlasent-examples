> **Later-phase reference.** This document is not part of the Deploy Gate V1 pilot. Keep first pilots focused on GitHub Actions + `production.deploy` + `/v1-evaluate` + `/v1-verify-permit`.

# AtlaSent + Cursor Guarded Tool Example (v1.6.0)

Demonstrates AtlaSent authorization for Cursor/MCP-style tools using a small local guard, [`guard.ts`](guard.ts), built on the published `@atlasent/sdk`.

> `@atlasent/cursor` is not published to npm yet, so this example carries the same pattern itself. The action is the canonical `agent.tool.invoke`, with the tool name in `context.tool`.

The `withToolGuard` wrapper runs `evaluate → verifyPermit → execute` before each tool call. The returned tool array is a drop-in replacement for your MCP server's tool list — pass to `ListToolsResult` and call `execute` from your `CallToolResult` handler.

## Tools guarded

- `edit_file` — apply a unified diff patch to a file in the workspace
- `run_command` — execute a shell command in the project root

Both are configured with `onDeny: "tool-result"` so Cursor's agent receives a structured JSON denial string it can observe and adapt to.

## Setup

```bash
npm install
export ATLASENT_API_KEY=your-key
# Optional (this is the default): export ATLASENT_API_URL=https://api.atlasent.io/functions/v1
```

## Run (standalone demo)

```bash
npm run demo
```

## Use as an MCP server

For a production MCP server, integrate the guarded tools with `@modelcontextprotocol/sdk`:

```ts
server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: tools.map(({ name, description, parameters }) => ({
    name, description, inputSchema: parameters,
  })),
}));

server.setRequestHandler(CallToolRequestSchema, async (req) => {
  const tool = tools.find((t) => t.name === req.params.name)!;
  const result = await tool.execute(req.params.arguments ?? {});
  return { content: [{ type: "text", text: result }] };
});
```

See the [AtlaSent documentation](https://docs.atlasent.io) for the full integration guide.
