#!/usr/bin/env python3
"""Batch authorization example using the async AtlaSent Python SDK.

The Python SDK does not expose a single batch/`authorize_many` call, so this
example fans out over `AsyncAtlaSentClient.evaluate(...)` concurrently with
`asyncio.gather`. Each evaluation is fail-closed: a non-allow decision raises
`AtlaSentDenied`, which we catch per-item so one deny does not abort the batch.

Run (live):
    export ATLASENT_API_URL=https://api.atlasent.io/functions/v1
    export ATLASENT_API_KEY=ask_live_xx   # or ask_test_xx
    python authorize_many.py

Run (dry-run / smoke — no live API keys needed):
    ATLASENT_DRY_RUN=true python authorize_many.py
"""
import asyncio
import os

DRY_RUN = os.environ.get("ATLASENT_DRY_RUN") == "true"

ACTIONS = [
    "tool.web_search",
    "tool.code_execute",
    "data.read",
    "data.write",
    "model.invoke",
]


def _print_header() -> None:
    print(f"{'Action':<25} {'Decision':<12} Risk")
    print("-" * 50)


def _dry_run() -> None:
    print("[atlasent] dry-run mode — no live API keys needed\n")
    # Representative stubbed decisions — mirror the live output shape.
    stub = {
        "tool.web_search": ("allow", "low"),
        "tool.code_execute": ("deny", "high"),
        "data.read": ("allow", "medium"),
        "data.write": ("hold", "high"),
        "model.invoke": ("allow", "low"),
    }
    _print_header()
    allowed = 0
    for action in ACTIONS:
        decision, level = stub[action]
        if decision == "allow":
            allowed += 1
        print(f"{action:<25} {decision:<12} {level}")
    print(f"\n{allowed}/{len(ACTIONS)} actions allowed")
    print("\n[atlasent] dry-run smoke test passed")


async def _live() -> None:
    from atlasent import AsyncAtlaSentClient
    from atlasent.exceptions import AtlaSentDenied

    actor = "agent-001"
    async with AsyncAtlaSentClient(
        os.environ["ATLASENT_API_KEY"],
        base_url=os.environ.get("ATLASENT_API_URL", "https://api.atlasent.io/functions/v1"),
    ) as client:

        async def one(action: str):
            try:
                result = await client.evaluate(
                    action, actor, {"environment": "production"}
                )
                return action, result.decision, getattr(result, "risk_class", None)
            except AtlaSentDenied as denied:
                return action, denied.decision, None

        results = await asyncio.gather(*(one(a) for a in ACTIONS))

    _print_header()
    allowed = 0
    for action, decision, level in results:
        if decision == "allow":
            allowed += 1
        print(f"{action:<25} {decision:<12} {level}")
    print(f"\n{allowed}/{len(results)} actions allowed")


def main() -> None:
    if DRY_RUN:
        _dry_run()
        return
    asyncio.run(_live())


if __name__ == "__main__":
    main()
