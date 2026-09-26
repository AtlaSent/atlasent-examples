> **Later-phase reference.** This example is not part of the Deploy Gate V1 pilot.

# flows/06-sso-walkthrough

End-to-end Okta SSO integration walkthrough: connect an Okta application to
AtlaSent, define a JIT (Just-In-Time) provisioning rule, and observe the first
audit event produced when an SSO-provisioned user triggers a gated action.

## What this shows

1. **Register an SSO connection** — POST your Okta issuer + client credentials
   to `/v1/sso/connections`.
2. **Define a JIT rule** — map incoming Okta group claims to AtlaSent roles
   so new users are provisioned on first login.
3. **Trigger a gated action** — the provisioned user evaluates an action;
   AtlaSent records the first audit event tied to the SSO identity.
4. **Verify the audit trail** — retrieve the audit event and confirm the
   `sso_subject` claim is present.

## Prerequisites

- An Okta developer org (free at [developer.okta.com](https://developer.okta.com))
- An AtlaSent project with SSO enabled (`atlasent_sso` feature flag on)
- `ATLASENT_API_URL`, `ATLASENT_API_KEY`, and `ATLASENT_ORG_ID` in your env

## Files

| File | Purpose |
|---|---|
| `sso_walkthrough.ts` | TypeScript end-to-end script (run with `npx tsx sso_walkthrough.ts`) |
| `sso_walkthrough.py` | Python sibling (run with `python sso_walkthrough.py`) |
| `package.json` | Node dependencies (`@atlasent/sdk@^2`, `node-fetch`) |
| `requirements.txt` | Python dependencies (`httpx`) |

## Run (TypeScript)

```bash
npm install
export ATLASENT_API_URL=https://api.atlasent.io/functions/v1
export ATLASENT_API_KEY=ask_live_xx
export ATLASENT_ORG_ID=org_xx
export OKTA_ISSUER=https://dev-XXXXXX.okta.com/oauth2/default
export OKTA_CLIENT_ID=0oa...
export OKTA_CLIENT_SECRET=...
npx tsx sso_walkthrough.ts
```

## Run (Python)

```bash
pip install -r requirements.txt
export ATLASENT_API_URL=https://api.atlasent.io/functions/v1
export ATLASENT_API_KEY=ask_live_xx
export ATLASENT_ORG_ID=org_xx
export OKTA_ISSUER=https://dev-XXXXXX.okta.com/oauth2/default
export OKTA_CLIENT_ID=0oa...
export OKTA_CLIENT_SECRET=...
python sso_walkthrough.py
```

## Dry-run mode

Set `ATLASENT_DRY_RUN=true` to run the script without live credentials.
All API calls are stubbed; the script logs each step and exits 0.

## Steps detail

### Step 1 — Register SSO connection

```http
POST /v1/sso/connections
Authorization: Bearer <ATLASENT_API_KEY>

{
  "org_id": "<ATLASENT_ORG_ID>",
  "provider": "okta",
  "issuer": "<OKTA_ISSUER>",
  "client_id": "<OKTA_CLIENT_ID>",
  "client_secret": "<OKTA_CLIENT_SECRET>"
}
```

Response includes a `connection_id` used in subsequent calls.

### Step 2 — Create JIT rule

```http
POST /v1/sso/connections/<connection_id>/jit-rules
Authorization: Bearer <ATLASENT_API_KEY>

{
  "claim": "groups",
  "claim_value": "engineering",
  "role": "developer"
}
```

Users whose Okta `groups` claim includes `engineering` are assigned the
`developer` role on first login.

### Step 3 — Evaluate an action as the SSO user

After the user logs in via Okta (OIDC redirect flow), AtlaSent returns a
session token bound to the SSO identity. Pass it as the `agent` field:

```http
POST /v1-evaluate
Authorization: Bearer <ATLASENT_API_KEY>

{
  "agent": "sso:alice@example.com",
  "action": "production.deploy",
  "resource": "checkout-api"
}
```

### Step 4 — Retrieve the audit event

```http
GET /v1/audit/events?subject=sso:alice@example.com&limit=1
Authorization: Bearer <ATLASENT_API_KEY>
```

The response contains an event with `sso_subject: "alice@example.com"` and
the Okta session ID — proving the full SSO → evaluate → audit chain.
