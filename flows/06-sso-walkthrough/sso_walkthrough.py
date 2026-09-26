# WARNING: This example uses a disabled endpoint that is not deployed in production.
# The `/v1/sso/connections` routes are served by the `v1-sso` edge function,
# which is listed in atlasent-api/supabase/runtime-functions-disabled.json.
# Calls to these routes will return 404 in production.

"""flows/06-sso-walkthrough/sso_walkthrough.py

End-to-end Okta SSO integration: connect -> JIT rule -> evaluate -> audit.

Run (live):
    export ATLASENT_API_URL=https://api.atlasent.io/functions/v1
    export ATLASENT_API_KEY=ask_live_xx
    export ATLASENT_ORG_ID=org_xx
    export OKTA_ISSUER=https://dev-XXXXXX.okta.com/oauth2/default
    export OKTA_CLIENT_ID=0oa...
    export OKTA_CLIENT_SECRET=...
    python sso_walkthrough.py

Run (dry-run):
    ATLASENT_DRY_RUN=true python sso_walkthrough.py
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

try:
    import httpx
except ImportError:
    print("httpx not installed — run: pip install httpx", file=sys.stderr)
    sys.exit(1)

DRY_RUN = os.environ.get("ATLASENT_DRY_RUN") == "true"

API_URL = "https://api.atlasent.io/functions/v1" if DRY_RUN else os.environ["ATLASENT_API_URL"]
API_KEY = "dry-run" if DRY_RUN else os.environ["ATLASENT_API_KEY"]
ORG_ID = "org_dry_run" if DRY_RUN else os.environ["ATLASENT_ORG_ID"]
OKTA_ISSUER = "https://dev-000000.okta.com/oauth2/default" if DRY_RUN else os.environ["OKTA_ISSUER"]
OKTA_CLIENT_ID = "0oaDryRun" if DRY_RUN else os.environ["OKTA_CLIENT_ID"]
OKTA_CLIENT_SECRET = "secret" if DRY_RUN else os.environ["OKTA_CLIENT_SECRET"]

_HEADERS = {
    "content-type": "application/json",
    "authorization": f"Bearer {API_KEY}",
}


def _stub(path: str, body: Any) -> Any:
    """Return plausible stub responses for dry-run mode."""
    print(f"  [dry-run] POST {path}", json.dumps(body, indent=2))
    if "/sso/connections" in path and "jit" not in path:
        return {"connection_id": "conn_dry_run_001"}
    if "jit-rules" in path:
        return {"rule_id": "rule_dry_run_001"}
    if "/v1-evaluate" in path:
        return {"decision": "allow", "permit_token": "permit_dry_run_001"}
    return {}


def post(path: str, body: Any) -> Any:
    if DRY_RUN:
        return _stub(path, body)
    r = httpx.post(
        f"{API_URL}{path}",
        headers=_HEADERS,
        json=body,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def get(path: str) -> Any:
    if DRY_RUN:
        print(f"  [dry-run] GET {path}")
        return {
            "events": [
                {
                    "event_id": "evt_dry_run_001",
                    "sso_subject": "alice@example.com",
                    "action": "production.deploy",
                    "decision": "allow",
                }
            ]
        }
    r = httpx.get(
        f"{API_URL}{path}",
        headers={"authorization": f"Bearer {API_KEY}"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def main() -> None:
    if DRY_RUN:
        print("[atlasent] dry-run mode — no live credentials needed\n")

    # Step 1 — Register SSO connection
    print("Step 1: Registering Okta SSO connection...")
    result = post(
        "/v1/sso/connections",
        {
            "org_id": ORG_ID,
            "provider": "okta",
            "issuer": OKTA_ISSUER,
            "client_id": OKTA_CLIENT_ID,
            "client_secret": OKTA_CLIENT_SECRET,
        },
    )
    connection_id = result["connection_id"]
    print(f"  connection_id: {connection_id}\n")

    # Step 2 — Define JIT rule
    print("Step 2: Creating JIT provisioning rule...")
    result = post(
        f"/v1/sso/connections/{connection_id}/jit-rules",
        {
            "claim": "groups",
            "claim_value": "engineering",
            "role": "developer",
        },
    )
    rule_id = result["rule_id"]
    print(f"  rule_id: {rule_id}\n")

    # Step 3 — Evaluate an action as the SSO-provisioned user
    print("Step 3: Evaluating action as SSO user sso:alice@example.com...")
    eval_result = post(
        "/v1-evaluate",
        {
            "actor_id": "sso:alice@example.com",
            "action_type": "production.deploy",
            "resource": "checkout-api",
        },
    )
    print(f"  decision: {eval_result['decision']}")
    if eval_result.get("permit_token"):
        print(f"  permit_token: {eval_result['permit_token']}")
    print()

    # Step 4 — Retrieve the audit event
    print("Step 4: Retrieving audit event for sso:alice@example.com...")
    audit_result = get("/v1/audit/events?subject=sso:alice@example.com&limit=1")
    events = audit_result.get("events", [])
    if not events:
        print("  No audit event found — check that the evaluate call was recorded.",
              file=sys.stderr)
        sys.exit(1)
    event = events[0]
    print(f"  event_id: {event.get('event_id')}")
    print(f"  sso_subject: {event.get('sso_subject')}")
    print(f"  decision: {event.get('decision')}")
    print()

    print("SSO walkthrough complete.")
    if DRY_RUN:
        print("[atlasent] dry-run smoke test passed")


if __name__ == "__main__":
    main()
