#!/usr/bin/env python3
"""gxp-vqp-re-derivation: Delta VQP Phase 3 — Re-derivation Audit Demo

VQPClient is TypeScript/Node.js only. This script calls the Supabase edge
functions directly via httpx, mirroring the 3 scenarios in main.ts.

  ⚠  SERVER-SIDE ONLY: uses ATLASENT_SUPABASE_SERVICE_ROLE_KEY (service role
     key). Never run this in a browser or expose the service role key to
     client-side code.

Three scenarios:
  1. Generate + Verify (hash match)
     — generate a VQP snapshot with all 6 criteria met, then verify it
     — expect: hashMatch=true, verdictChanged=false
  2. Verify only (snapshot already exists)
     — verify a pre-existing snapshot by ID without regenerating
     — expect: hashMatch=true
  3. Verify with rerun (score drift detection)
     — rerun=true re-evaluates criteria against current state
     — shows how to detect scoreDelta > 0 and verdictChanged

Offline / stub mode:
  If ATLASENT_SUPABASE_URL is not set, the script prints stub outputs
  illustrating expected responses and exits 0.

Live:
  ATLASENT_SUPABASE_URL=https://<project>.supabase.co \\
  ATLASENT_SUPABASE_SERVICE_ROLE_KEY=<service_role_key> \\
  ATLASENT_ORG_ID=org_replace_me \\
  ATLASENT_BUNDLE_ID=bundle_replace_me \\
  python main.py
"""
from __future__ import annotations

import os
import sys

import httpx

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SUPABASE_URL = os.environ.get("ATLASENT_SUPABASE_URL", "")
SERVICE_ROLE_KEY = os.environ.get("ATLASENT_SUPABASE_SERVICE_ROLE_KEY", "")
ORG_ID = os.environ.get("ATLASENT_ORG_ID", "org_replace_me")
BUNDLE_ID = os.environ.get("ATLASENT_BUNDLE_ID", "bundle_replace_me")

# STUB_MODE is active when ATLASENT_SUPABASE_URL is not configured.
STUB_MODE = not SUPABASE_URL

WIDTH = 72


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------


def bar(title: str = "") -> None:
    if title:
        print(f"\n{'━' * WIDTH}")
        print(f"  {title}")
        print(f"{'━' * WIDTH}")
    else:
        print(f"  {'─' * (WIDTH - 4)}")


def scenario(num: int | str, action: str, note: str) -> None:
    print(f"\n▸ Scenario {num} — {action}")
    print(f"  {note}")


def snapshot_line(snapshot_id: str, prompt_hash: str, score: float, verdict: str) -> None:
    print(f"  ✔ GENERATED  verdict: {verdict}")
    print(f"               snapshot_id:  {snapshot_id}")
    print(f"               prompt_hash:  {prompt_hash}")
    print(f"               score:        {score}")


def verify_line(result: dict) -> None:
    hash_match = result.get("hashMatch", False)
    icon = "✔" if hash_match else "✗"
    print(f"  {icon} VERIFIED    hash_match: {hash_match}")
    print(f"               snapshot_id:    {result.get('snapshotId', '')}")
    print(f"               audit_log_id:   {result.get('auditLogId', '')}")
    if "rerunScore" in result:
        print(f"               rerun_score:    {result['rerunScore']}")
    if "scoreDelta" in result:
        print(f"               score_delta:    {result['scoreDelta']}")
    if "verdictChanged" in result:
        print(f"               verdict_changed: {result['verdictChanged']}")


def execute(msg: str) -> None:
    print(f"               → {msg}")


# ---------------------------------------------------------------------------
# HTTP helpers — call Supabase edge functions directly
# (VQPClient is TypeScript-only; Python callers use the edge functions directly)
# ---------------------------------------------------------------------------


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }


def vqp_generate(bundle_id: str, org_id: str, vqp_context: dict) -> dict:
    """POST {SUPABASE_URL}/functions/v1/v1-generate-vqp"""
    url = f"{SUPABASE_URL}/functions/v1/v1-generate-vqp"
    resp = httpx.post(
        url,
        headers=_headers(),
        json={"bundleId": bundle_id, "orgId": org_id, "vqpContext": vqp_context},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def vqp_verify(snapshot_id: str, rerun: bool = False) -> dict:
    """POST {SUPABASE_URL}/functions/v1/v1-verify-vqp"""
    url = f"{SUPABASE_URL}/functions/v1/v1-verify-vqp"
    payload: dict = {"snapshotId": snapshot_id}
    if rerun:
        payload["rerun"] = True
    resp = httpx.post(url, headers=_headers(), json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Stub outputs
# Printed when ATLASENT_SUPABASE_URL is not configured so the example can be
# reviewed without a live Supabase project.
# ---------------------------------------------------------------------------


STUB_GENERATE = {
    "snapshotId": "snap_stub_00000000000001",
    "promptHash": "a3f8c1d2e4b6097f5a3c2e1d8f7b4096",
    "score": 95,
    "verdict": "qualified",
    "criteria": {
        "access_control": {"criterion": "CC6.1", "score": 100, "pass": True},
        "audit_coverage": {"criterion": "CC7.2", "score": 95, "pass": True},
        "escalation_paths": {"criterion": "CC7.4", "score": 90, "pass": True},
        "deny_specificity": {"criterion": "CC8.1", "score": 100, "pass": True},
        "hold_conditions": {"criterion": "CC6.3", "score": 90, "pass": True},
        "override_governance": {"criterion": "CC5.2", "score": 95, "pass": True},
    },
}

STUB_VERIFY_HASH_MATCH = {
    "snapshotId": "snap_stub_00000000000001",
    "hashMatch": True,
    "rerunScore": None,
    "scoreDelta": None,
    "verdictChanged": False,
    "auditLogId": "alog_stub_000000000001",
}

STUB_VERIFY_EXISTING = {
    "snapshotId": "snap_existing_replace_me",
    "hashMatch": True,
    "rerunScore": None,
    "scoreDelta": None,
    "verdictChanged": False,
    "auditLogId": "alog_stub_000000000002",
}

STUB_VERIFY_RERUN = {
    "snapshotId": "snap_stub_00000000000001",
    "hashMatch": True,
    "rerunScore": 88,
    "scoreDelta": 7,
    "verdictChanged": False,
    "auditLogId": "alog_stub_000000000003",
}


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------


def run() -> None:
    bar("gxp-vqp-re-derivation   Delta VQP Phase 3 Re-derivation Audit Demo")
    print(f"  org:    {ORG_ID}")
    print(f"  bundle: {BUNDLE_ID}")
    if STUB_MODE:
        print("  mode:   offline stub (set ATLASENT_SUPABASE_URL to use live API)")
    else:
        print(f"  mode:   live ({SUPABASE_URL})")
    print("  ⚠  SERVER-SIDE ONLY: serviceRoleKey must never be exposed to clients")

    vqp_context = {
        # CC6.1 — Access Control
        "access_control": {
            "mfa_enforced": True,
            "least_privilege": True,
            "role_review_completed": True,
        },
        # CC7.2 — Audit Coverage
        "audit_coverage": {
            "all_events_logged": True,
            "retention_policy_met": True,
            "tamper_evident": True,
        },
        # CC7.4 — Escalation Paths
        "escalation_paths": {
            "defined": True,
            "tested_last_cycle": True,
            "owner_assigned": True,
        },
        # CC8.1 — Deny Specificity
        "deny_specificity": {
            "no_wildcard_denies": True,
            "scope_documented": True,
        },
        # CC6.3 — Hold Conditions
        "hold_conditions": {
            "hold_logic_tested": True,
            "release_criteria_documented": True,
        },
        # CC5.2 — Override Governance
        "override_governance": {
            "override_requires_dual_approval": True,
            "override_audit_logged": True,
            "break_glass_policy_current": True,
        },
    }

    # -----------------------------------------------------------------------
    # Scenario 1 — Generate + Verify (hash match)
    # -----------------------------------------------------------------------
    scenario(
        1,
        "generate + verify (hash match)",
        "All 6 VQP criteria met → expect verdict=qualified, hashMatch=true",
    )

    generated_snapshot_id = "snap_placeholder_replace_me"

    if STUB_MODE:
        gen = STUB_GENERATE
    else:
        gen = vqp_generate(BUNDLE_ID, ORG_ID, vqp_context)

    generated_snapshot_id = gen["snapshotId"]
    snapshot_line(
        gen["snapshotId"],
        gen["promptHash"],
        gen["score"],
        gen["verdict"],
    )
    execute("snapshot stored — use snapshotId for future verify calls")

    bar()

    if STUB_MODE:
        verify1 = STUB_VERIFY_HASH_MATCH
    else:
        verify1 = vqp_verify(generated_snapshot_id)

    verify_line(verify1)
    if verify1.get("hashMatch"):
        execute("prompt hash verified — snapshot is unmodified since generation")
    else:
        execute("ALERT: hash mismatch — snapshot may have been tampered with")
    if verify1.get("verdictChanged") is False:
        execute("verdict unchanged — qualification status is stable")

    # -----------------------------------------------------------------------
    # Scenario 2 — Verify only (snapshot already exists)
    # -----------------------------------------------------------------------
    scenario(
        2,
        "verify only (snapshot already exists)",
        "Verify a pre-existing snapshot by ID — expect hashMatch=true",
    )

    # Replace with a real snapshot ID from a previous generate call.
    existing_snapshot_id = "snap_existing_replace_me"

    if STUB_MODE:
        verify2 = STUB_VERIFY_EXISTING
    else:
        verify2 = vqp_verify(existing_snapshot_id)

    verify_line(verify2)
    if verify2.get("hashMatch"):
        execute("snapshot integrity confirmed — no re-derivation needed")
    else:
        execute("ALERT: hash mismatch — initiate re-derivation workflow")

    # -----------------------------------------------------------------------
    # Scenario 3 — Verify with rerun (score drift detection)
    # -----------------------------------------------------------------------
    scenario(
        3,
        "verify with rerun (score drift detection)",
        "rerun=True re-evaluates criteria — detect scoreDelta and verdictChanged",
    )

    if STUB_MODE:
        verify3 = STUB_VERIFY_RERUN
    else:
        verify3 = vqp_verify(generated_snapshot_id, rerun=True)

    verify_line(verify3)

    score_delta = verify3.get("scoreDelta")
    if score_delta is not None and score_delta > 0:
        execute(
            f"score drift detected: delta={score_delta} — review criteria changes"
        )
    else:
        execute("no score drift detected — criteria scores are stable")

    if verify3.get("verdictChanged"):
        execute(
            "ALERT: verdict changed — mandatory re-derivation audit required per CC7.2"
        )
        execute("open a re-derivation ticket and notify compliance team")
    else:
        execute("verdict unchanged — no re-derivation audit required")

    execute(f"audit event recorded: auditLogId={verify3.get('auditLogId', '')}")

    bar()
    print("  VQP criteria evaluated (6 total):")
    print("    access_control      (CC6.1)")
    print("    audit_coverage      (CC7.2)")
    print("    escalation_paths    (CC7.4)")
    print("    deny_specificity    (CC8.1)")
    print("    hold_conditions     (CC6.3)")
    print("    override_governance (CC5.2)")
    print()
    print("  Verdicts: qualified (score≥85, no fails)")
    print("            conditionally_qualified (score≥60, no fails)")
    print("            not_qualified")
    print()


if __name__ == "__main__":
    run()
    if STUB_MODE:
        sys.exit(0)
