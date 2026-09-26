"""Evidence bundle generation example.

Demonstrates: generating a SOC 2 Type II evidence bundle for the last 90 days,
printing the sha256 for auditor handoff, then listing all bundles.

Flow:
    create_evidence_export (soc2_type_ii)
    -> print sha256
    -> list_evidence_exports

Requires: ATLASENT_API_KEY, ATLASENT_BASE_URL, ATLASENT_ORG_ID env vars.

The server defaults the evidence window to the 90 days preceding the request
when no window is supplied.
"""

import os
import sys

from atlasent import AtlaSentClient
from atlasent.evidence_exports import create_evidence_export, list_evidence_exports
from atlasent.exceptions import AtlaSentError

API_KEY = os.environ.get("ATLASENT_API_KEY")
BASE_URL = os.environ.get("ATLASENT_BASE_URL")
ORG_ID = os.environ.get("ATLASENT_ORG_ID")

if not API_KEY or not BASE_URL or not ORG_ID:
    print(
        "ATLASENT_API_KEY, ATLASENT_BASE_URL, and ATLASENT_ORG_ID are all required.",
        file=sys.stderr,
    )
    sys.exit(1)


def main() -> None:
    client = AtlaSentClient(api_key=API_KEY, base_url=BASE_URL)

    # ── Step 1: generate SOC 2 Type II evidence bundle ───────────────────────
    # Omitting `window` lets the server default to the last 90 days.
    print("Generating SOC 2 Type II evidence bundle (last 90 days)...")
    result = create_evidence_export(client, ORG_ID, regime="soc2_type_ii")

    record = result["export"]
    bundle = result["bundle"]

    print("  export id:         ", record["id"])
    print("  regime:            ", record["regime"])
    print("  window from:       ", record["window_from"])
    print("  window to:         ", record["window_to"])
    print("  controls total:    ", record["controls_total"])
    print("  controls evidenced:", record["controls_evidenced"])
    print("  controls partial:  ", record["controls_partial"])
    print("  controls missing:  ", record["controls_missing"])
    print("  generated_at:      ", record["generated_at"])

    # ── Step 2: print the sha256 for auditor handoff ─────────────────────────
    # The sha256 is the hex digest of the canonical bundle bytes. Hand this to
    # your auditor so they can verify the bundle has not been tampered with.
    print("\nBundle sha256 (provide to auditor for verification):")
    print(" ", result["sha256"])
    print("  bundle_id:", bundle["bundle_id"])

    # ── Step 3: list all evidence exports ────────────────────────────────────
    print("\nListing all evidence exports for this org...")
    list_result = list_evidence_exports(client, ORG_ID)

    exports = list_result.get("exports") or []
    if not exports:
        print("  No exports found.")
    else:
        for exp in exports:
            print(
                f"  {exp['id']}  regime={exp['regime']}"
                f"  window=[{exp['window_from']} -> {exp['window_to']}]"
                f"  sha256={exp['bundle_sha256']}"
            )


if __name__ == "__main__":
    try:
        main()
    except AtlaSentError as exc:
        print(f"AtlaSent error (status={exc.status_code}): {exc}", file=sys.stderr)
        sys.exit(1)
