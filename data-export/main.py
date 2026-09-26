#!/usr/bin/env python3
"""data-export: Customer Data Export Authorization Quickstart

Demonstrates non-bypassable authorization for general-purpose (non-PHI,
non-clinical) data exports using the AtlaSent SDK fail-closed enforcement model.

3 scenarios:
  1. Approved       — PII dataset to verified destination, valid purpose  → ALLOW (all rows pass)
  2. Denied dest    — PII dataset to unverified destination               → DENY_DESTINATION_UNVERIFIED
  3. Row-level mix  — mixed PII/non-PII batch: non-PII rows approved,
                      PII rows to unverified destination denied in same batch

Action string: customer.data.export

Runs offline (in-process stub) by default.
Set ATLASENT_API_KEY to switch to the live AtlaSent API.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from atlasent import AtlaSentClient, AtlaSentDeniedError, Permit


# ---------------------------------------------------------------------------
# Demo constants
# ---------------------------------------------------------------------------

VERIFIED_DESTINATIONS: frozenset[str] = frozenset(
    {"s3://acme-exports-verified", "bigquery://acme-prod/exports", "snowflake://acme/analytics"}
)
ROW_CAP = 100_000
WIDTH = 72


# ---------------------------------------------------------------------------
# In-process stub engine
# ---------------------------------------------------------------------------


class _ExportStub(AtlaSentClient):
    """In-process stub — no HTTP calls, deterministic policy engine."""

    def __init__(self) -> None:
        super().__init__(
            "ask_test_demostubdemostubdemostubdemo00",
            base_url="https://stub.local",
        )
        self._decisions: dict[str, dict[str, Any]] = {}
        self._audit_chain: list[dict[str, Any]] = []

    @property
    def audit_chain(self) -> list[dict[str, Any]]:
        return list(self._audit_chain)

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None,
        *,
        params: dict[str, str] | None = None,
    ) -> tuple[dict[str, Any], Any, str]:
        rid = uuid.uuid4().hex[:12]
        p = payload or {}
        if path in ("/v1/evaluate", "/v1-evaluate"):
            return self._handle_evaluate(p), None, rid
        if path in ("/v1/verify-permit", "/v1-verify-permit"):
            return self._handle_verify(p), None, rid
        return {}, None, rid

    def _handle_evaluate(self, p: dict[str, Any]) -> dict[str, Any]:
        action = p.get("action_type", "")
        agent  = p.get("actor_id", "")
        context = p.get("context", {})
        result = self._decide(action, agent, context)
        evaluation_id = f"eval_{uuid.uuid4().hex[:16]}"
        result["request_id"] = evaluation_id
        result["_meta"] = {"action_type": action, "actor_id": agent, "context": context}
        # Keyed by permit_token, not evaluation_id: _handle_verify looks up
        # by the permit_token the real wire protocol sends on /v1-verify-permit.
        permit_token = result.get("permit_token")
        if permit_token:
            self._decisions[permit_token] = result
        return result

    def _handle_verify(self, p: dict[str, Any]) -> dict[str, Any]:
        permit_token = p.get("permit_token", "")
        stored = self._decisions.get(permit_token, {})
        allowed = str(stored.get("decision", "")).lower() == "allow"
        ts = datetime.now(timezone.utc).isoformat()
        if not allowed:
            return {"verified": False, "permit_hash": "", "outcome": "invalid", "timestamp": ts}
        meta = stored.get("_meta", {})
        record = {
            "event_id": f"evt_{uuid.uuid4().hex[:12]}",
            "timestamp": ts,
            "actor": meta.get("actor_id", ""),
            "action": meta.get("action_type", ""),
            "decision": "allow",
            "permit_id": permit_token,
            "context_snapshot": meta.get("context", {}),
            "previous_hash": self._audit_chain[-1].get("audit_hash", "") if self._audit_chain else "",
        }
        canonical = json.dumps(record, sort_keys=True, separators=(",", ":"))
        record["audit_hash"] = hashlib.sha256(canonical.encode()).hexdigest()[:32]
        self._audit_chain.append(record)
        permit_hash = hashlib.sha256(permit_token.encode()).hexdigest()[:32]
        return {"verified": True, "permit_hash": permit_hash, "outcome": "verified", "timestamp": ts}

    def _decide(self, action: str, agent: str, ctx: dict[str, Any]) -> dict[str, Any]:
        def allow(reason: str) -> dict[str, Any]:
            token = f"pt_{uuid.uuid4().hex[:16]}"
            return {"decision": "allow", "permit_token": token,
                    "reasons": [reason], "audit_hash": uuid.uuid4().hex[:32]}

        def deny(reason: str) -> dict[str, Any]:
            return {"decision": "deny", "reasons": [reason]}

        if action != "customer.data.export":
            return deny(f"action '{action}' not registered in data export policy")

        rows_requested = int(ctx.get("rowsRequested", 0))
        if rows_requested > ROW_CAP:
            return deny(
                f"DENY_ROW_CAP_EXCEEDED: {rows_requested:,} rows requested exceeds "
                f"cap of {ROW_CAP:,} — escalation required"
            )

        contains_pii = ctx.get("containsPii", False)
        destination = ctx.get("destination", "")
        purpose = ctx.get("purpose", "")

        if contains_pii:
            if not purpose:
                return deny("DENY_PURPOSE_MISSING: PII exports require a documented purpose code")
            if destination not in VERIFIED_DESTINATIONS:
                return deny(
                    f"DENY_DESTINATION_UNVERIFIED: destination '{destination}' is not on the "
                    "verified destination allowlist for PII exports"
                )

        return allow(
            f"export of {rows_requested:,} rows to {destination} "
            f"({'PII' if contains_pii else 'non-PII'}) authorized for purpose: {purpose or 'n/a'}"
        )


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _bar(title: str = "") -> None:
    if title:
        print(f"\n{'━' * WIDTH}")
        print(f"  {title}")
        print(f"{'━' * WIDTH}")
    else:
        print(f"  {'─' * (WIDTH - 4)}")

def _scenario(num: int | str, note: str) -> None:
    print(f"\n▸ Scenario {num} — customer.data.export")
    print(f"  {note}")

def _blocked(reason: str) -> None:
    print(f"  ✗ BLOCKED    {reason}")

def _permit_line(p: Permit) -> None:
    print(f"  ✔ PERMITTED  {p.reason}")
    print(f"               permit_id: {p.permit_id}")

def _execute(msg: str) -> None:
    print(f"               → {msg}")


# ---------------------------------------------------------------------------
# Simulated export system mutations
# ---------------------------------------------------------------------------

def _sys_write_export(destination: str, row_count: int, permit_id: str) -> None:
    _execute(f"wrote {row_count} rows to {destination} under permit {permit_id}")


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def run(client: AtlaSentClient, stub: _ExportStub | None) -> None:  # noqa: C901
    _bar("data-export   Customer Data Export Authorization Quickstart")
    print(f"  mode:   {'offline stub' if stub else 'live AtlaSent API'}")

    # 1 ── Approved: PII to verified destination, valid purpose → ALLOW -----
    _scenario(1, "ALLOW: PII dataset to verified destination with valid purpose (all rows pass)")
    try:
        p = client.protect(
            agent="analyst.alice@acme.com",
            action="customer.data.export",
            context={
                "datasetId": "CRM-CUSTOMERS-Q1",
                "containsPii": True,
                "destination": "snowflake://acme/analytics",
                "purpose": "Q1-churn-analysis",
                "rowsRequested": 5_000,
                "requestedBy": "analyst.alice@acme.com",
            },
        )
        _permit_line(p)
        _sys_write_export("snowflake://acme/analytics", 5_000, p.permit_id)
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)

    # 2 ── Denied destination: PII to unverified destination ----------------
    _scenario(2, "DENY_DESTINATION_UNVERIFIED: PII dataset to unverified destination")
    try:
        client.protect(
            agent="analyst.bob@acme.com",
            action="customer.data.export",
            context={
                "datasetId": "CRM-CUSTOMERS-Q1",
                "containsPii": True,
                "destination": "s3://personal-bucket-bob",
                "purpose": "personal-analysis",
                "rowsRequested": 500,
                "requestedBy": "analyst.bob@acme.com",
            },
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)
        print(f"               evaluation_id: {exc.evaluation_id}")
        _execute("export NOT written")

    # 3 ── Row-level partial: mixed PII/non-PII batch -----------------------
    _scenario(3, "Row-level partial: mixed PII/non-PII — non-PII rows approved, PII rows denied")

    rows = [
        # non-PII rows — destination unverified but PII=False, so approved
        {"rowId": "R001", "containsPii": False, "destination": "s3://personal-bucket-bob",
         "purpose": "reporting", "rowsRequested": 1},
        {"rowId": "R002", "containsPii": False, "destination": "s3://personal-bucket-bob",
         "purpose": "reporting", "rowsRequested": 1},
        # PII rows — destination unverified → denied
        {"rowId": "R003", "containsPii": True, "destination": "s3://personal-bucket-bob",
         "purpose": "reporting", "rowsRequested": 1},
        {"rowId": "R004", "containsPii": True, "destination": "s3://personal-bucket-bob",
         "purpose": "reporting", "rowsRequested": 1},
        # PII row — verified destination → approved
        {"rowId": "R005", "containsPii": True, "destination": "snowflake://acme/analytics",
         "purpose": "monthly-retention-report", "rowsRequested": 1},
    ]

    allowed_rows: list[dict[str, Any]] = []
    denied_rows: list[dict[str, Any]] = []

    for row in rows:
        try:
            p = client.protect(
                agent="pipeline-bot@acme.com",
                action="customer.data.export",
                context={
                    "datasetId": f"BATCH-{row['rowId']}",
                    "containsPii": row["containsPii"],
                    "destination": row["destination"],
                    "purpose": row["purpose"],
                    "rowsRequested": row["rowsRequested"],
                    "requestedBy": "pipeline-bot@acme.com",
                },
            )
            allowed_rows.append(row)
            print(f"  ✔  {row['rowId']}  {'PII' if row['containsPii'] else 'non-PII':<8}  ALLOW   {p.permit_id}")
        except AtlaSentDeniedError as exc:
            denied_rows.append({**row, "reason": exc.reason})
            reason_short = (exc.reason or "denied").split(":")[0]
            print(f"  ✗  {row['rowId']}  {'PII' if row['containsPii'] else 'non-PII':<8}  DENY    {reason_short}")

    print()
    print(f"  batch result: {len(allowed_rows)} allowed / {len(denied_rows)} denied")

    # ── Audit trail -------------------------------------------------------
    if stub:
        chain = stub.audit_chain
        _bar(f"Audit Trail   {len(chain)} permitted export(s)   immutable hash-linked chain")
        for i, rec in enumerate(chain):
            print(f"  [{i + 1}] {rec['timestamp']}")
            print(f"      actor:     {rec['actor']}")
            print(f"      permit_id: {rec['permit_id']}")
            print(f"      hash:      {rec['audit_hash']}")

    _bar()
    print(f"  Enforcement summary:")
    print(f"    ALLOWED  dataset export + 3 row-level exports")
    print(f"    BLOCKED  PII to unverified destination (2 rows + 1 dataset)")
    print()


def main() -> None:
    api_key = os.environ.get("ATLASENT_API_KEY", "")
    if api_key:
        run(AtlaSentClient(api_key=api_key, base_url=os.environ.get("ATLASENT_API_URL", "https://api.atlasent.io/functions/v1")), stub=None)
    else:
        stub = _ExportStub()
        run(stub, stub)


if __name__ == "__main__":
    main()
