"""Basic AtlaSent authorization check over raw HTTP.

The canonical flow is two calls — `/v1-evaluate` mints a Permit, then
`/v1-verify-permit` confirms the Permit is current and binds it
into the audit chain. **Both calls are required** before executing a
state-changing action: an `allow` decision alone is not authorization,
and skipping the verify step is fail-open.

If you are using the AtlaSent SDK, use `protect()` / `with_permit()`
instead — those issue both calls for you and fail closed by
construction. See ../python-sdk-quickstart/ and ../with-permit-py/.
This example exists to show the raw wire shape for callers that do
not (or cannot) use the SDK.
"""

import os

import httpx

API_KEY = os.environ["ATLASENT_API_KEY"]
BASE_URL = os.environ.get("ATLASENT_BASE_URL", "https://api.atlasent.io/functions/v1")


def evaluate(actor_id: str, action_type: str, context: dict | None = None) -> dict:
    response = httpx.post(
        f"{BASE_URL}/v1-evaluate",
        headers={"Authorization": f"Bearer {API_KEY}"},
        json={"actor_id": actor_id, "action_type": action_type, "context": context or {}},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def verify_permit(permit_token: str, action_type: str, actor_id: str, environment: str) -> dict:
    # permit_token is the only strictly required field, but action_type /
    # actor_id / environment bind the verification to the same request that
    # was evaluated — omitting them means a stolen/misrouted token would
    # still verify. Always send the full binding.
    response = httpx.post(
        f"{BASE_URL}/v1-verify-permit",
        headers={"Authorization": f"Bearer {API_KEY}"},
        json={
            "permit_token": permit_token,
            "action_type": action_type,
            "actor_id": actor_id,
            "environment": environment,
        },
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


if __name__ == "__main__":
    # ── Step 1: evaluate ──────────────────────────────────────────────
    actor_id = "assistant"
    action_type = "documents.read"
    environment = "production"
    evaluation = evaluate(
        actor_id=actor_id,
        action_type=action_type,
        context={"classification": "internal", "environment": environment},
    )
    decision = str(evaluation.get("decision", "unknown")).lower()
    request_id = evaluation.get("request_id", "")
    permit_token = evaluation.get("permit_token", "")
    deny_code = evaluation.get("deny_code")

    print(f"Decision      : {decision}")
    print(f"Request ID    : {request_id}")
    if deny_code:
        print(f"Deny code     : {deny_code}")

    # Fail closed on anything other than ALLOW. `hold` and `escalate` are
    # NOT permits — they indicate the request is queued for an external
    # signal and must be re-evaluated after that signal arrives.
    if decision != "allow":
        raise SystemExit(f"Access denied: {evaluation}")

    if not permit_token:
        raise SystemExit("ALLOW with no permit token — refusing to proceed.")

    # ── Step 2: verify the permit ─────────────────────────────────────
    # Closes the window between issue and execute: catches policy revocations,
    # TTL elapsed, and tampering. Skipping this step is fail-open. The SDK's
    # `protect()` does this for you; the raw flow has to do it explicitly.
    verification = verify_permit(permit_token, action_type, actor_id, environment)
    if not verification.get("valid"):
        raise SystemExit(
            f"Permit failed verification ({verification.get('verify_error_code')}): refusing to proceed."
        )

    # ── Step 3: execute ───────────────────────────────────────────────
    print(f"Permit token  : {permit_token}")
    print(f"Outcome       : {verification.get('outcome', 'ok')}")
    print("\nAccess granted, permit verified — proceeding.")
