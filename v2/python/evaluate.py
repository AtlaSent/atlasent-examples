"""
v2 example: evaluate an action using the AtlaSent API.

Requires: ATLASENT_API_URL, ATLASENT_API_KEY environment variables.
pip install atlasent
"""

import os
import json
import urllib.request

API_URL = os.environ.get("ATLASENT_API_URL", "https://api.atlasent.io/functions/v1")
API_KEY = os.environ["ATLASENT_API_KEY"]


def call_api(path: str, body: dict | None = None) -> dict:
    url = f"{API_URL}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url,
        data=data,
        method="POST" if body else "GET",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


def main():
    # Real /v1-evaluate wire request: { action_type, actor_id, context }.
    # `environment` lives under `context`, not top-level; there is no
    # nested `actor`/`action` object shape on the wire.
    payload = {
        "action_type": "data.export",
        "actor_id": "user_123",
        "context": {"environment": "production", "org_id": "org_abc"},
    }

    decision = call_api("/v1-evaluate", payload)

    # Real /v1-evaluate response is flat: { decision, permit_token?,
    # request_id, deny_code?, deny_reason?, ... }. There is no `outcome`
    # field and no nested `risk`/`permit` object.
    print(f"Decision: {decision['decision']}")

    if decision["decision"] == "allow":
        permit_token = decision.get("permit_token")
        if permit_token:
            print(f"Permit: {permit_token} (expires {decision.get('permit_expires_at')})")
    elif decision["decision"] in ("deny", "hold", "escalate"):
        print(f"Not allowed. Reason: {decision.get('deny_reason')} (code: {decision.get('deny_code')})")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
