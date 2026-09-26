# go-http-middleware

Demonstrates the AtlaSent Go SDK `Middleware()` wrapping a standard `net/http` mux.

## Run

```bash
cp .env.example .env && source .env
go run main.go
```

Then test:

```bash
# Allowed (set X-AtlaSent-Action and X-AtlaSent-Subject headers)
curl -H "X-AtlaSent-Action: production.deploy" \
     -H "X-AtlaSent-Subject: agent-001" \
     http://localhost:8080/api/deploy

# Denied — missing action header → 403
curl http://localhost:8080/api/deploy
```
