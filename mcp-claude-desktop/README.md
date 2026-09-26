> **Later-phase reference.** This document is not part of the Deploy Gate V1 pilot. Keep first pilots focused on GitHub Actions + `production.deploy` + `/v1-evaluate` + `/v1-verify-permit`.

# MCP Server + Claude Desktop

Wires the AtlaSent MCP server to Claude Desktop so Claude can evaluate policies and check authorizations directly from the chat interface.

## Setup

1. Install the MCP server:
   ```bash
   npm install -g @atlasent/mcp-server
   ```

2. Copy `claude_desktop_config.json` into your Claude Desktop config:
   - **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

3. Set your API key in the config (replace `your_key_here`).

4. Restart Claude Desktop.

## What it enables

Once connected, Claude can:
- Call the `evaluate` tool to check whether an agent is authorized for an action
- Call `verify_permit` to verify a specific permit condition
- Read `atlasent://policies/{id}` to inspect policy bundles
- Call `deploy_service` to deploy service configurations
