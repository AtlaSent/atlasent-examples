"""Generate a deterministic sample audit bundle.

Materializes the same audit chain ``main.py`` produces (the four ALLOW events
across the seven scenarios), with fixed event ids and timestamps so the
bundle artifact is reproducible across commits. Run as:

    python _sample.py > sample-audit-bundle.json

Or:

    python _sample.py --out sample-audit-bundle.json

The bundle is signed with the DEMO key (see ``_bundle.py``). It is NOT
representative of real customer signing — production bundles are signed by
the AtlaSent KMS and pinned via ``keys.atlasent.io``.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from _bundle import compute_audit_hash, make_bundle


# Fixed event seeds. Mirrors the four ALLOW outcomes from main.py:
#   scenario 2  reconciliation.certify  (alice)
#   scenario 3  journal_entry.approve   (controller-bot, post-CFO-approval)
#   scenario 4b adjustment.submit       (carol)
#   scenario 5b period.close            (cfo-bot, post-CFO-signoff)
# and an additional 6b reconciliation.certify with dual approval, matching
# main.py's expanded scenario set.
_SEEDS: list[dict[str, Any]] = [
    {
        "event_id":  "evt_demo000000a1",
        "timestamp": "2026-03-31T18:00:01+00:00",
        "actor":     "alice.chen@acme.com",
        "action":    "reconciliation.certify",
        "permit_id": "pt_demosample0001",
        "reason":    "reconciliation for CASH-1000 certified by alice.chen@acme.com",
        "context_snapshot": {
            "account_id": "CASH-1000",
            "certified_by": "alice.chen@acme.com",
            "period": "Q1-2026",
            "balance_difference": 0.0,
            "dual_approval_required": False,
        },
    },
    {
        "event_id":  "evt_demo000000b2",
        "timestamp": "2026-03-31T18:00:14+00:00",
        "actor":     "controller-bot",
        "action":    "journal_entry.approve",
        "permit_id": "pt_demosample0002",
        "reason":    "journal entry JE-2026-4821 approved ($250,000)",
        "context_snapshot": {
            "je_id": "JE-2026-4821",
            "amount": 250000.0,
            "period": "Q1-2026",
            "approved_by": "cfo@acme.com",
        },
    },
    {
        "event_id":  "evt_demo000000c3",
        "timestamp": "2026-03-31T18:00:27+00:00",
        "actor":     "carol.jones@acme.com",
        "action":    "adjustment.submit",
        "permit_id": "pt_demosample0003",
        "reason":    "adjustment ADJ-2026-009 submitted by carol.jones@acme.com",
        "context_snapshot": {
            "adjustment_id": "ADJ-2026-009",
            "submitted_by": "carol.jones@acme.com",
            "period": "Q1-2026",
            "amount": 1500.0,
        },
    },
    {
        "event_id":  "evt_demo000000d4",
        "timestamp": "2026-03-31T18:00:41+00:00",
        "actor":     "cfo-bot",
        "action":    "period.close",
        "permit_id": "pt_demosample0004",
        "reason":    "period Q1-2026 close authorized -- all conditions satisfied",
        "context_snapshot": {
            "period": "Q1-2026",
            "all_tasks_complete": True,
            "cfo_signoff_by": "cfo@acme.com",
        },
    },
    {
        "event_id":  "evt_demo000000e5",
        "timestamp": "2026-03-31T18:00:55+00:00",
        "actor":     "alice.chen@acme.com",
        "action":    "reconciliation.certify",
        "permit_id": "pt_demosample0005",
        "reason":    "reconciliation for AR-3000 certified by alice.chen@acme.com",
        "context_snapshot": {
            "account_id": "AR-3000",
            "certified_by": "alice.chen@acme.com",
            "period": "Q1-2026",
            "balance_difference": 0.0,
            "dual_approval_required": True,
            "second_approver": "bob.smith@acme.com",
        },
    },
]


def _build_chain(seeds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    prev = ""
    for s in seeds:
        audit_hash = compute_audit_hash(
            event_id=s["event_id"],
            timestamp=s["timestamp"],
            actor=s["actor"],
            action=s["action"],
            decision="allow",
            permit_id=s["permit_id"],
            reason=s["reason"],
            context_snapshot=s["context_snapshot"],
            previous_hash=prev,
        )
        events.append(
            {
                "event_id": s["event_id"],
                "timestamp": s["timestamp"],
                "actor": s["actor"],
                "action": s["action"],
                "decision": "allow",
                "permit_id": s["permit_id"],
                "reason": s["reason"],
                "previous_hash": prev,
                "audit_hash": audit_hash,
                "context_snapshot": s["context_snapshot"],
            }
        )
        prev = audit_hash
    return events


def main() -> None:
    p = argparse.ArgumentParser(description="Generate a deterministic sample audit bundle")
    p.add_argument("--out", default=None, help="Write to file instead of stdout")
    args = p.parse_args()

    events = _build_chain(_SEEDS)
    bundle = make_bundle(
        events,
        period_from=_SEEDS[0]["timestamp"],
        period_to=_SEEDS[-1]["timestamp"],
        # Fixed export timestamp so the artifact is byte-stable across runs.
        exported_at="2026-03-31T18:01:00+00:00",
        demo=True,
    )
    text = json.dumps(bundle, indent=2) + "\n"
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
