#!/usr/bin/env python3
"""Basic evaluation example using the AtlaSent Python SDK.

Run (live):
    export ATLASENT_API_URL=https://api.atlasent.io/functions/v1
    export ATLASENT_API_KEY=ask_live_xx   # or ask_test_xx
    python evaluate_basic.py

Run (dry-run / smoke — no live API keys needed):
    ATLASENT_DRY_RUN=true python evaluate_basic.py
"""
import os
import uuid

DRY_RUN = os.environ.get("ATLASENT_DRY_RUN") == "true"


def main() -> None:
    action_type = "data.export"
    actor_id = "user-123"
    context = {
        "email": "alice@example.com",
        "resource_id": "dataset-456",
        "sensitivity": "confidential",
        "environment": "production",
    }

    if DRY_RUN:
        # Dry-run stub: no SDK client, no network. Mirror the live output shape.
        print("[atlasent] dry-run mode — no live API keys needed\n")
        decision = "allow"
        risk = {"level": "medium", "score": 62}
        permit_id = "permit_dryrun_001"
        print(f"Decision:   {decision}")
        print(f"Risk Level: {risk['level']} (score: {risk['score']}/100)")
        print(f"Permit ID:  {permit_id}")
        print("\n[atlasent] dry-run smoke test passed")
        return

    # Live path — construct the real SDK client and call /v1-evaluate.
    from atlasent import AtlaSentClient
    from atlasent.exceptions import AtlaSentDenied

    client = AtlaSentClient(
        os.environ["ATLASENT_API_KEY"],
        base_url=os.environ.get("ATLASENT_API_URL", "https://api.atlasent.io/functions/v1"),
    )

    try:
        result = client.evaluate(
            action_type,
            actor_id,
            context,
            resource_id="dataset-456",
            environment="production",
        )
    except AtlaSentDenied as denied:
        # evaluate() is fail-closed: a non-allow decision raises.
        print(f"Decision:   {denied.decision}")
        print(f"Reason:     {denied.reason}")
        raise SystemExit(1) from None
    finally:
        client.close()

    print(f"Decision:   {result.decision}")
    risk_class = getattr(result, "risk_class", None)
    risk_score = getattr(result, "risk_score", None)
    if risk_class is not None or risk_score is not None:
        print(f"Risk Level: {risk_class} (score: {risk_score}/100)")
    print(f"Permit ID:  {result.permit_token}")


if __name__ == "__main__":
    main()
