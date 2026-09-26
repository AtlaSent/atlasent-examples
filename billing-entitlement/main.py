"""
billing-entitlement — AtlaSent billing gate example.

Shows how to:
  1. Fetch the billing entitlement for the current org
  2. Gate a governed operation on billing state
  3. Surface a friendly message when the org is in grace period

Run:
  ATLASENT_API_KEY=ask_live_xxx python main.py
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

from atlasent import AtlaSentClient
from atlasent.billing import AllowedAction, BillingClient


def main() -> None:
    api_key = os.environ.get("ATLASENT_API_KEY")
    if not api_key:
        sys.exit("ATLASENT_API_KEY is not set")

    client  = AtlaSentClient(api_key=api_key, base_url=os.environ.get("ATLASENT_API_URL", "https://api.atlasent.io/functions/v1"))
    billing = BillingClient(client)

    # ── 1. Fetch entitlement ──────────────────────────────────────────────
    print("Fetching billing entitlement...")
    ent = billing.get_entitlement()

    print(f"  org_id:        {ent.org_id}")
    print(f"  access_status: {ent.access_status.value}")
    print(f"  plan:          {ent.plan}")
    if ent.warning:
        print(f"  ⚠  {ent.warning}")

    # ── 2. Gate on a specific action ──────────────────────────────────────
    action = AllowedAction.govern
    if ent.has_action(action):
        print(f"\n✓ '{action.value}' is permitted — running governed operation...")
        run_governed_operation()
    else:
        if ent.grace_until:
            now = datetime.now(timezone.utc)
            grace_utc = ent.grace_until.replace(tzinfo=timezone.utc)
            days_left = max(0, (grace_utc - now).days)
            print(
                f"\n✗ '{action.value}' is blocked (grace period).\n"
                f"  Grace period ends: {ent.grace_until.strftime('%Y-%m-%d')} "
                f"({days_left} day{'s' if days_left != 1 else ''} remaining).\n"
                f"  Please renew your subscription to restore full access."
            )
        else:
            print(
                f"\n✗ '{action.value}' is blocked.\n"
                f"  Status:      {ent.access_status.value}\n"
                f"  Deny reason: {ent.deny_reason}"
            )
        sys.exit(1)


def run_governed_operation() -> None:
    print("  → Governed operation completed successfully.")


if __name__ == "__main__":
    main()
