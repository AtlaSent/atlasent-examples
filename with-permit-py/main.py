"""AtlaSent Python SDK — `with_permit()` lexically-scoped form.

`with_permit()` is the lexically-scoped peer of `protect()`. Same wire
contract (evaluate + verifyPermit), same fail-closed matrix, same
audit-chain entry — but binds the action body to the permit's lifetime
via a callback. The body runs only on a verified permit; on deny, hold,
escalate, verification failure, or transport error it is never invoked.

Use `with_permit()` when the action body is a single lexical scope.
Use `protect()` (../python-sdk-quickstart/) when you need the verified
Permit as a value to pass across a boundary or interleave with
non-trivial control flow.
"""

import asyncio
import os
from datetime import datetime, timezone

from atlasent import (
    AsyncAtlaSentClient,
    AtlaSentDeniedError,
    AtlaSentError,
    Permit,
    aio,
    with_permit,
)


def write_patient_record(permit: Permit, patient_id: str, payload: dict) -> dict:
    """Stand-in for the EHR write. In production this would POST to the EHR."""
    return {
        "patientId": patient_id,
        "payload": payload,
        "writtenAt": datetime.now(timezone.utc).isoformat(),
        # The audit-chain link: the Permit ID is what makes the AtlaSent
        # decision and your system-of-record row two-way navigable.
        "atlasentPermitId": permit.permit_id,
    }


def sync_example() -> None:
    # The action body executes only on a verified permit. The Permit
    # is visible inside the callback for audit-chain linkage; outside
    # the callback, `with_permit` returns whatever the body returned.
    record = with_permit(
        agent="agent-001",
        action="ehr.write",
        context={"environment": "production", "patient_id": "patient-42"},
        fn=lambda permit: write_patient_record(
            permit,
            "patient-42",
            {"medication": "metformin", "dose_mg": 500},
        ),
    )
    print("Sync result:", record)


async def async_example() -> None:
    # Async sibling via `atlasent.aio.with_permit`. Same contract; takes
    # an explicit AsyncAtlaSentClient since v1 has no global async singleton.
    async with AsyncAtlaSentClient(api_key=os.environ["ATLASENT_API_KEY"], base_url=os.environ.get("ATLASENT_API_URL", "https://api.atlasent.io/functions/v1")) as client:
        record = await aio.with_permit(
            client,
            agent="agent-001",
            action="ehr.write",
            context={"environment": "production", "patient_id": "patient-43"},
            fn=lambda permit: write_patient_record(
                permit,
                "patient-43",
                {"medication": "lisinopril", "dose_mg": 10},
            ),
        )
        print("Async result:", record)


if __name__ == "__main__":
    if not os.environ.get("ATLASENT_API_KEY"):
        raise SystemExit("ATLASENT_API_KEY is required.")

    try:
        sync_example()
    except AtlaSentDeniedError as exc:
        print(f"Denied: {exc.reason or exc}")
    except AtlaSentError as exc:
        print(f"Fail-closed: {exc}")

    try:
        asyncio.run(async_example())
    except AtlaSentDeniedError as exc:
        print(f"Denied: {exc.reason or exc}")
    except AtlaSentError as exc:
        print(f"Fail-closed: {exc}")
