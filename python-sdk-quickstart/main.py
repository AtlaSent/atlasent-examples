"""AtlaSent Python SDK quickstart.

Canonical execution-boundary surface. `protect()` mints and verifies
a Permit end-to-end and returns it on success; on deny, hold,
escalate, verification failure, or transport error it raises. There
is no `permitted=False` return path — if `protect()` returns, the
action is authorized end-to-end.

Mirror of typescript-sdk-quickstart/main.ts. See also
../with-permit-py/ for the lexically-scoped `with_permit()` form.
"""

import asyncio
import os
from datetime import datetime, timezone

from atlasent import (
    AsyncAtlaSentClient,
    AtlaSentDeniedError,
    AtlaSentError,
    configure,
    protect,
)

# The SDK's built-in default base URL is the bare host; the AtlaSent API is
# served under /functions/v1, so set it explicitly. api_key=None falls back
# to the ATLASENT_API_KEY environment variable.
BASE_URL = os.environ.get("ATLASENT_BASE_URL", "https://api.atlasent.io/functions/v1")
configure(base_url=BASE_URL)


def generate_report(report_id: str) -> str:
    # `protect()` is fail-closed. If it returns, the action is authorized
    # end-to-end. Persist permit.permit_id alongside your record so the
    # audit chain stays two-way navigable.
    permit = protect(
        agent="assistant",
        action="report.generate",
        context={"report_id": report_id},
    )
    return (
        f"Report {report_id} generated at {datetime.now(timezone.utc).isoformat()} "
        f"(permit={permit.permit_id})"
    )


async def export_data(dataset: str) -> dict:
    # Async sibling. `AsyncAtlaSentClient.protect()` follows the same
    # fail-closed contract as the sync top-level `protect()` above.
    async with AsyncAtlaSentClient(api_key=os.environ["ATLASENT_API_KEY"], base_url=BASE_URL) as client:
        permit = await client.protect(
            agent="assistant",
            action="data.export",
            context={"dataset": dataset, "format": "csv"},
        )
    return {"dataset": dataset, "rows": 42, "permit_id": permit.permit_id}


if __name__ == "__main__":
    if not os.environ.get("ATLASENT_API_KEY"):
        raise SystemExit("ATLASENT_API_KEY is required.")

    # Sync
    try:
        print("Report:", generate_report("Q1-2026"))
    except AtlaSentDeniedError as exc:
        print(f"Denied: {exc.reason or exc}")
    except AtlaSentError as exc:
        print(f"Fail-closed: {exc}")

    # Async
    async def run_async() -> None:
        try:
            print("Export:", await export_data("sales"))
        except AtlaSentDeniedError as exc:
            print(f"Denied: {exc.reason or exc}")
        except AtlaSentError as exc:
            print(f"Fail-closed: {exc}")

    asyncio.run(run_async())
