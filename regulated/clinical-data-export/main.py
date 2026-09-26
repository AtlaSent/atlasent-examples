#!/usr/bin/env python3
"""03 · Clinical Data Export — batch-authorize an export of patient records.

One protect() call per record, parallelized. Denied records drop out of the
export, allowed records are written to a signed bundle. The bundle sha is
bound to the issued permit tokens so an auditor can prove every row was gated.
"""
import hashlib
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from atlasent import AtlaSentClient, AtlaSentDeniedError, Permit

API_KEY = os.environ.get("ATLASENT_API_KEY")
if not API_KEY:
    sys.exit("ATLASENT_API_KEY is required. export ATLASENT_API_KEY=... and re-run.")

client = AtlaSentClient(
    api_key=API_KEY,
    base_url=os.environ.get("ATLASENT_API_URL", "https://api.atlasent.io/functions/v1"),
)

# A synthetic patient cohort — replace with your real query.
COHORT = [
    {"patientId": "P-0001", "mrn": "MRN-100001", "study": "ATLAS-01", "country": "US"},
    {"patientId": "P-0002", "mrn": "MRN-100002", "study": "ATLAS-01", "country": "US"},
    {"patientId": "P-0003", "mrn": "MRN-100003", "study": "ATLAS-01", "country": "DE"},
    {"patientId": "P-0004", "mrn": "MRN-100004", "study": "ATLAS-02", "country": "US"},
    {"patientId": "P-0005", "mrn": "MRN-100005", "study": "ATLAS-02", "country": "JP"},
]


def authorize_row(
    row: dict, requester: str, purpose: str
) -> tuple[dict, Permit | None, str | None]:
    """Return ``(row, permit, deny_reason)``.

    On allow, ``permit`` is the verified :class:`Permit` and
    ``deny_reason`` is ``None``. On deny, ``permit`` is ``None`` and
    ``deny_reason`` carries the policy explanation. ``protect()`` is
    fail-closed: any deny becomes :class:`AtlaSentDeniedError`.
    """
    try:
        permit = client.protect(
            agent=requester,
            action="clinical.export",
            context={
                "patient_id": row["patientId"],
                "mrn": row["mrn"],
                "study": row["study"],
                "country": row["country"],
                "sensitivity": "phi",
                "environment": "production",
                "purpose": purpose,
            },
        )
    except AtlaSentDeniedError as exc:
        return row, None, exc.reason or "denied"
    return row, permit, None


def main() -> int:
    print("=== 03 · Clinical Data Export ===\n")
    requester = os.environ.get("REQUESTER", "cdm-alice")
    purpose = os.environ.get("PURPOSE", "Monthly safety monitoring export")
    out_path = Path(os.environ.get("OUT", "./export-bundle.json"))

    print(f"Requester: {requester}")
    print(f"Purpose:   {purpose}")
    print(f"Cohort:    {len(COHORT)} patients\n")

    allowed: list[dict] = []
    denied: list[dict] = []
    permits: list[str] = []
    audit_hashes: list[str] = []

    with ThreadPoolExecutor(max_workers=8) as pool:
        for row, permit, deny_reason in pool.map(
            lambda r: authorize_row(r, requester, purpose), COHORT
        ):
            if permit is not None:
                allowed.append(row)
                permits.append(permit.permit_id)
                if permit.audit_hash:
                    audit_hashes.append(permit.audit_hash)
                print(f"  OK  {row['patientId']} allowed")
            else:
                denied.append({**row, "reason": deny_reason or "denied"})
                print(f"  NO  {row['patientId']} denied   · {deny_reason or 'denied'}")

    if not allowed:
        print("\nNothing authorized. Bundle not written.")
        return 2

    bundle_body = json.dumps(
        {
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "requester": requester,
            "purpose": purpose,
            "records": allowed,
            "permits": permits,
            "auditHashes": audit_hashes,
        },
        indent=2,
        sort_keys=True,
    )
    sha = hashlib.sha256(bundle_body.encode("utf-8")).hexdigest()
    bundle = json.loads(bundle_body)
    bundle["sha256"] = sha
    out_path.write_text(json.dumps(bundle, indent=2, sort_keys=True))

    # The server writes each decision to the hash-chained audit trail
    # during protect(). The bundle's sha256 + every permit_id +
    # audit_hash in it are independently verifiable after the fact —
    # no client-side "consume" step is required or supported.

    print(f"\nWrote {len(allowed)} records to {out_path}")
    print(f"sha256:       {sha}")
    print(f"permits:      {len(permits)} bound to the bundle")
    print(f"audit hashes: {len(audit_hashes)} bound to the bundle")
    if denied:
        print(f"\n{len(denied)} patient(s) excluded:")
        for r in denied:
            print(f"  - {r['patientId']} ({r['country']}) · {r['reason']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
