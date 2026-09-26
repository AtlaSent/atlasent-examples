"""21 CFR Part 11 GxP compliance scenario using AtlaSent authorization.

Policy assignment (which policy bundle an action hits) is set per-key in the
console and is not an SDK-level concept. This script only exercises evaluate
against whatever policies the configured API key is bound to.
"""
import os
import sys
from atlasent import AtlaSentClient, AtlaSentDeniedError
from atlasent.exceptions import AtlaSentError

API_KEY = os.environ["ATLASENT_API_KEY"]

client = AtlaSentClient(api_key=API_KEY, base_url=os.environ.get("ATLASENT_API_URL", "https://api.atlasent.io/functions/v1"))


def check(action: str, context: dict | None = None) -> str:
    try:
        client.protect(
            agent="pharma-agent",
            action=action,
            context=context or {},
        )
        return "ALLOW"
    except AtlaSentDeniedError:
        return "DENY"
    except AtlaSentError as exc:
        return f"ERROR: {exc}"


SCENARIOS = [
    {
        "name": "Read batch record (21 CFR 11.10 - authorized view)",
        "action": "batch_records.read",
        "context": {"user_role": "analyst", "record_id": "BATCH-2026-001"},
        "expect": "ALLOW",
    },
    {
        "name": "Electronic signature - dual authorization present",
        "action": "batch_records.sign",
        "context": {"user_role": "supervisor", "dual_auth": True, "record_id": "BATCH-2026-001"},
        "expect": "ALLOW",
    },
    {
        "name": "Electronic signature - no dual authorization (should deny)",
        "action": "batch_records.sign",
        "context": {"user_role": "analyst", "dual_auth": False},
        "expect": "DENY",
    },
    {
        "name": "Delete audit log (21 CFR 11.10(e) - must always deny)",
        "action": "audit_log.delete",
        "context": {"user_role": "admin"},
        "expect": "DENY",
    },
]


if __name__ == "__main__":
    print("AtlaSent GxP Scenario - 21 CFR Part 11\n")

    failures = 0
    for s in SCENARIOS:
        result = check(s["action"], s["context"])
        passed = result == s["expect"]
        status = "PASS" if passed else f"FAIL (expected {s['expect']}, got {result})"
        icon = "OK" if passed else "NO"
        print(f"  [{icon}] {s['name']}")
        print(f"       Action: {s['action']} => {result} [{status}]")
        if not passed:
            failures += 1

    print(f"\n{len(SCENARIOS) - failures} passed, {failures} failed")
    if failures:
        sys.exit(1)
