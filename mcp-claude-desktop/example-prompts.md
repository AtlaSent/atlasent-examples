# Example Prompts for Claude Desktop

Once the AtlaSent MCP server is connected, try these prompts:

## Check authorization

```
Using the AtlaSent evaluate tool, check whether agent "assistant" is authorized
to perform "documents.read". Show me the full decision.
```

## Inspect a policy

```
Fetch the AtlaSent policy at atlasent://policies/default and summarize the rules.
```

## Verify a permit

```
Use verify_permit to check if role="admin" satisfies the production.deploy policy.
```

## Deploy a service

```
Deploy a service named "my-agent" using deploy_service with environment "production".
```
