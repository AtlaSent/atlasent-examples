#!/usr/bin/env python3
"""02 · LIMS Write — gate a sample-result write into a Laboratory
Information Management System with AtlaSent.

Uses the canonical fail-closed surface: `client.protect()` issues both
the evaluate and verify calls and returns a verified Permit. If
`protect()` returns, the action is authorized end-to-end. On any
non-allow outcome (deny, hold, escalate, verification failure) it
raises `AtlaSentDenied`; on transport / 5xx / auth failure it raises
`AtlaSentError`. The action body runs only when both calls succeed.
"""
import os
import sys
from datetime import datetime, timezone

from atlasent import AtlaSentClient
from atlasent.exceptions import AtlaSentDenied, AtlaSentError

API_KEY = os.environ.get("ATLASENT_API_KEY")
if not API_KEY:
    sys.exit("ATLASENT_API_KEY is required. export ATLASENT_API_KEY=... and re-run.")

client = AtlaSentClient(
    api_key=API_KEY,
    base_url=os.environ.get("ATLASENT_API_URL", "https://api.atlasent.io/functions/v1"),
)


def write_sample_result(sample_id: str, assay: str, value: float, permit_id: str) -> dict:
    """Stand-in for the LIMS write. In production this would POST to the LIMS."""
    return {
        "sampleId": sample_id,
        "assay": assay,
        "value": value,
        "writtenAt": datetime.now(timezone.utc).isoformat(),
        "atlasentPermitId": permit_id,
    }


def main() -> int:
    print("=== 02 · LIMS Write ===\n")

    sample_id = os.environ.get("SAMPLE_ID", "S-2026-0001")
    assay = os.environ.get("ASSAY", "hba1c")
    value = float(os.environ.get("VALUE", "6.3"))
    analyst = os.environ.get("ANALYST", "analyst-alice")

    print(f"Analyst {analyst} wants to write {assay}={value} for sample {sample_id}")

    context = {
        "sample_id": sample_id,
        "assay": assay,
        "value": value,
        "system": "lims",
        "environment": os.environ.get("LIMS_ENV", "production"),
    }

    # protect() = evaluate + verify in one call, fail-closed by construction.
    # Replaces the older two-call evaluate() + verify() pattern with the
    # canonical execution-boundary surface. Same wire calls under the hood,
    # same audit-chain entry, but the action body is unreachable without a
    # verified permit.
    try:
        permit = client.protect(agent=analyst, action="lims.write", context=context)
    except AtlaSentDenied as exc:
        print(f"\nDecision: deny")
        print(f"Reason:   {exc.reason or 'policy denied'}")
        print("\nLIMS write blocked. Not writing.")
        return 2
    except AtlaSentError as exc:
        print(f"\nLIMS protect() errored ({exc.code}): {exc}")
        print("Fail-closed. LIMS write blocked.")
        return 3

    print(f"\nDecision: allow")
    print(f"Permit:   {permit.permit_id}")
    if permit.reason:
        print(f"Reason:   {permit.reason}")
    print(f"Verified: {permit.permit_hash or 'ok'}")

    record = write_sample_result(sample_id, assay, value, permit.permit_id)
    print("\nWrote to LIMS:")
    for k, v in record.items():
        print(f"  {k}: {v}")

    # The permit_id + audit_hash are the two-way navigable link between
    # this LIMS row and the AtlaSent decision in the audit chain.
    if permit.audit_hash:
        print(f"\nAudit hash: {permit.audit_hash}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
