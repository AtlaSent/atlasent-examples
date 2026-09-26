"""SIEM setup example.

Demonstrates: configuring SIEM export to Splunk HEC, verifying connectivity,
then fetching the saved config.

Flow:
    upsert_siem_config (splunk_hec, bearer auth)
    -> siem_test_delivery
    -> get_siem_config

Requires: ATLASENT_API_KEY, ATLASENT_BASE_URL, ATLASENT_ORG_ID,
          SPLUNK_HEC_URL, SPLUNK_HEC_TOKEN env vars.

Note: SIEM export requires an enterprise plan. The API returns HTTP 402
when the plan gate blocks access.
"""

import os
import sys

from atlasent import AtlaSentClient
from atlasent.exceptions import AtlaSentError
from atlasent.siem import get_siem_config, siem_test_delivery, upsert_siem_config

API_KEY = os.environ.get("ATLASENT_API_KEY")
BASE_URL = os.environ.get("ATLASENT_BASE_URL")
ORG_ID = os.environ.get("ATLASENT_ORG_ID")
SPLUNK_HEC_URL = os.environ.get("SPLUNK_HEC_URL")
SPLUNK_HEC_TOKEN = os.environ.get("SPLUNK_HEC_TOKEN")

if not all([API_KEY, BASE_URL, ORG_ID, SPLUNK_HEC_URL, SPLUNK_HEC_TOKEN]):
    print(
        "ATLASENT_API_KEY, ATLASENT_BASE_URL, ATLASENT_ORG_ID, SPLUNK_HEC_URL, "
        "and SPLUNK_HEC_TOKEN are all required.",
        file=sys.stderr,
    )
    sys.exit(1)


def main() -> None:
    client = AtlaSentClient(api_key=API_KEY, base_url=BASE_URL)

    # ── Step 1: configure SIEM export to Splunk HEC ──────────────────────────
    print("Configuring SIEM export...")
    print("  destination:", SPLUNK_HEC_URL)
    print("  format:     splunk_hec")
    print("  auth_type:  bearer")

    saved_config = upsert_siem_config(
        client,
        ORG_ID,
        destination_url=SPLUNK_HEC_URL,
        format="splunk_hec",
        auth_type="bearer",
        credential=SPLUNK_HEC_TOKEN,
        enabled=True,
        included_event_types=["permit", "deny", "override", "governance"],
        batch_size=100,
        retry_count=3,
    )
    print("  Saved config updated_at:", saved_config.get("updatedAt"))
    print("  enabled:", saved_config.get("enabled"))

    # ── Step 2: verify connectivity with a test delivery ─────────────────────
    print("Testing SIEM delivery...")
    test_result = siem_test_delivery(client, ORG_ID)

    if test_result.get("success"):
        latency_ms = test_result.get("latencyMs")
        latency = f"{latency_ms}ms" if latency_ms is not None else "n/a"
        print("  Delivery succeeded. Latency:", latency)
    else:
        # Connectivity failure is not a fatal error for this example — print it
        # and continue to show the saved config fetch below.
        print(
            "  Delivery test failed:",
            test_result.get("error") or "unknown error",
            file=sys.stderr,
        )

    # ── Step 3: fetch the saved config ───────────────────────────────────────
    # The credential field is never returned by the server (write-only).
    print("Fetching saved SIEM config...")
    fetched_config = get_siem_config(client, ORG_ID)
    print("  org_id:          ", fetched_config.get("orgId"))
    print("  destination_url: ", fetched_config.get("destinationUrl"))
    print("  format:          ", fetched_config.get("format"))
    print("  auth_type:       ", fetched_config.get("authType"))
    event_types = fetched_config.get("includedEventTypes") or []
    print("  event_types:     ", ", ".join(event_types))
    print("  batch_size:      ", fetched_config.get("batchSize"))
    print("  retry_count:     ", fetched_config.get("retryCount"))


if __name__ == "__main__":
    try:
        main()
    except AtlaSentError as exc:
        print(f"AtlaSent error (status={exc.status_code}): {exc}", file=sys.stderr)
        sys.exit(1)
