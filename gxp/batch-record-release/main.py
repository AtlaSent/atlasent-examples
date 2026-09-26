#!/usr/bin/env python3
"""gxp-batch-record-release: GxP Batch Record Release Authorization Demo

Demonstrates non-bypassable authorization for manufacturing batch record
release using the AtlaSent SDK fail-closed enforcement model.

Three scenarios:
  1. ALLOW  — complete batch record, both QA signatories present
  2. DENY   — incomplete batch record (batchRecordComplete=False)
  3. DENY   — missing QA dual-signoff (only one approver)

Runs offline (in-process stub) by default.
Set ATLASENT_API_KEY to switch to the live AtlaSent API.

This example is part of the GxP pilot starter kit at atlasent-gxp-starter/.
"""
from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from atlasent import AtlaSentClient, AtlaSentDeniedError, Permit

# ---------------------------------------------------------------------------
# Demo constants
# ---------------------------------------------------------------------------

AUTHORIZED_QA_SIGNATORIES: frozenset[str] = frozenset(
    {"qa.mgr@pharma.example", "qa.lead@pharma.example", "qp.europe@pharma.example"}
)

WIDTH = 72


# ---------------------------------------------------------------------------
# Audit record
# ---------------------------------------------------------------------------


@dataclass
class AuditRecord:
    event_id: str
    timestamp: str
    actor: str
    action: str
    decision: str
    permit_id: str
    audit_hash: str
    previous_hash: str
    reason: str
    context_snapshot: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# In-process stub engine
# ---------------------------------------------------------------------------


class _MfgStub(AtlaSentClient):
    """In-process stub — no HTTP calls, deterministic policy engine.

    Overrides ``_request`` to handle evaluate / verify locally.
    Implements the manufacturing.batch_record.release policy:
      - fail_closed: true
      - machine_executable: false (QA human sign-off required)
      - dual approver: certifiedBy + qaSignoffBy must both be present
        and distinct, both in the authorized QA signatories list
      - batchRecordComplete must be true
    """

    def __init__(self) -> None:
        super().__init__(
            "ask_test_demostubdemostubdemostubdemo00",
            base_url="https://stub.local",
        )
        self._decisions: dict[str, dict[str, Any]] = {}
        self._audit_chain: list[AuditRecord] = []

    @property
    def audit_chain(self) -> list[AuditRecord]:
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
        agent = p.get("actor_id", "")
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
        permit_token = (
            p.get("permit_token", "")
        )
        stored = self._decisions.get(permit_token, {})
        allowed = str(stored.get("decision", "")).lower() == "allow"
        ts = datetime.now(timezone.utc).isoformat()
        if not allowed:
            return {
                "verified": False,
                "permit_hash": "",
                "outcome": "invalid",
                "timestamp": ts,
            }
        import hashlib

        meta = stored.get("_meta", {})
        prev = self._audit_chain[-1].audit_hash if self._audit_chain else ""
        event_id = f"evt_{uuid.uuid4().hex[:12]}"
        actor = meta.get("actor_id", "")
        action = meta.get("action_type", "")
        reasons = stored.get("reasons", [])
        reason = reasons[0] if reasons else ""
        context = meta.get("context", {})
        chain_input = f"{event_id}{ts}{actor}{action}allow{permit_token}{reason}{prev}"
        audit_hash = hashlib.sha256(chain_input.encode()).hexdigest()[:32]
        permit_hash = hashlib.sha256(permit_token.encode()).hexdigest()[:32]
        self._audit_chain.append(
            AuditRecord(
                event_id=event_id,
                timestamp=ts,
                actor=actor,
                action=action,
                decision="allow",
                permit_id=permit_token,
                audit_hash=audit_hash,
                previous_hash=prev,
                reason=reason,
                context_snapshot=context,
            )
        )
        return {
            "verified": True,
            "permit_hash": permit_hash,
            "outcome": "verified",
            "timestamp": ts,
        }

    def _decide(self, action: str, agent: str, ctx: dict[str, Any]) -> dict[str, Any]:
        """Return a V1-shaped response dict for batch record release policy."""

        def allow(reason: str) -> dict[str, Any]:
            permit_token = f"pt_{uuid.uuid4().hex[:16]}"
            return {
                "decision": "allow",
                "permit_token": permit_token,
                "reasons": [reason],
                "audit_hash": uuid.uuid4().hex[:32],
            }

        def deny(reason: str) -> dict[str, Any]:
            return {"decision": "deny", "reasons": [reason]}

        if action != "manufacturing.batch_record.release":
            return deny(f"action '{action}' not registered in batch-record-release policy")

        # Required fields
        batch_id = ctx.get("batchId", "")
        product_code = ctx.get("productCode", "")
        lot_number = ctx.get("lotNumber", "")
        certified_by = ctx.get("certifiedBy", "")
        qa_signoff_by = ctx.get("qaSignoffBy", "")
        batch_record_complete = ctx.get("batchRecordComplete", False)
        deviation_count = ctx.get("deviationCount", 0)
        regulatory_region = ctx.get("regulatoryRegion", "")

        if not batch_id:
            return deny("DENY_BATCH_RECORD_INCOMPLETE: missing required field: batchId")
        if not product_code:
            return deny("DENY_BATCH_RECORD_INCOMPLETE: missing required field: productCode")
        if not certified_by:
            return deny("DENY_BATCH_RECORD_INCOMPLETE: missing required field: certifiedBy")

        # Batch record completeness check
        if not batch_record_complete:
            return deny(
                f"DENY_BATCH_RECORD_INCOMPLETE: batch record {batch_id} is not complete "
                f"— all batch record sections must be reviewed before release"
            )

        # Dual approver check: both certifiedBy and qaSignoffBy required
        if not qa_signoff_by:
            return deny(
                f"DENY_DUAL_APPROVER_MISSING: batch {batch_id} requires dual QA sign-off — "
                f"qaSignoffBy is absent; a second authorized QA signatory is required"
            )

        if qa_signoff_by == certified_by:
            return deny(
                f"DENY_DUAL_APPROVER_MISSING: certifiedBy and qaSignoffBy must be "
                f"distinct individuals — same person ({certified_by}) cannot provide dual sign-off"
            )

        if certified_by not in AUTHORIZED_QA_SIGNATORIES:
            return deny(
                f"DENY_DUAL_APPROVER_MISSING: '{certified_by}' is not on the authorized "
                f"QA signatory list"
            )

        if qa_signoff_by not in AUTHORIZED_QA_SIGNATORIES:
            return deny(
                f"DENY_DUAL_APPROVER_MISSING: '{qa_signoff_by}' is not on the authorized "
                f"QA signatory list"
            )

        deviation_note = (
            f", {deviation_count} open deviation(s)" if deviation_count else ""
        )
        return allow(
            f"batch {batch_id} ({product_code} lot {lot_number}) released by "
            f"{certified_by} + {qa_signoff_by}{deviation_note} [{regulatory_region}]"
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


def _scenario(num: int | str, action: str, note: str) -> None:
    print(f"\n▸ Scenario {num} — {action}")
    print(f"  {note}")


_HOLD_TAG_RE = re.compile(r"\s*\[hold:[^\]]+\]")


def _blocked(reason: str) -> None:
    print(f"  ✗ BLOCKED    {_HOLD_TAG_RE.sub('', reason)}")


def _permit_line(p: Permit) -> None:
    print(f"  ✔ PERMITTED  {p.reason}")
    print(f"               permit_id:   {p.permit_id}")
    print(f"               audit_hash:  {p.audit_hash}")
    print(f"               permit_hash: {p.permit_hash}")


def _execute(msg: str) -> None:
    print(f"               → {msg}")


# ---------------------------------------------------------------------------
# Simulated manufacturing system state mutations
# Only reachable after protect() returns a verified Permit.
# ---------------------------------------------------------------------------


def _sys_release_batch(batch_id: str, product_code: str, lot_number: str) -> None:
    _execute(
        f"batch {batch_id} ({product_code} lot {lot_number}) status set to RELEASED"
    )
    _execute("release certificate generated and posted to document management system")


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------


def run(client: AtlaSentClient, stub: _MfgStub | None) -> None:
    _bar("gxp-batch-record-release   Batch Record Release Authorization Demo")
    print(f"  mode:   {'offline stub' if stub else 'live AtlaSent API'}")
    print(f"  action: manufacturing.batch_record.release")
    print(f"  policy: fail-closed, dual-approver, machine_executable=False")

    # 1 ── ALLOW: complete record, both QA signatories present ----------------
    _scenario(
        1,
        "manufacturing.batch_record.release",
        "ALLOWED: complete batch record, both QA signatories present",
    )
    try:
        p = client.protect(
            agent="qa.mgr@pharma.example",
            action="manufacturing.batch_record.release",
            context={
                "batchId": "BATCH-2026-00147",
                "productCode": "DRUG-XYZ-100MG",
                "lotNumber": "L26-04417",
                "certifiedBy": "qa.mgr@pharma.example",
                "qaSignoffBy": "qa.lead@pharma.example",
                "batchRecordComplete": True,
                "deviationCount": 0,
                "regulatoryRegion": "US-FDA",
            },
        )
        _permit_line(p)
        _sys_release_batch("BATCH-2026-00147", "DRUG-XYZ-100MG", "L26-04417")
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)

    # 2 ── DENY: incomplete batch record (batchRecordComplete=False) ----------
    _scenario(
        2,
        "manufacturing.batch_record.release",
        "BLOCKED: batchRecordComplete=False — record sections not yet reviewed",
    )
    try:
        client.protect(
            agent="qa.mgr@pharma.example",
            action="manufacturing.batch_record.release",
            context={
                "batchId": "BATCH-2026-00148",
                "productCode": "DRUG-XYZ-100MG",
                "lotNumber": "L26-04418",
                "certifiedBy": "qa.mgr@pharma.example",
                "qaSignoffBy": "qa.lead@pharma.example",
                "batchRecordComplete": False,  # <-- incomplete
                "deviationCount": 2,
                "regulatoryRegion": "EU-EMA",
            },
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)
        print(f"               evaluation_id: {exc.evaluation_id}")
        _execute("batch NOT released — record must be completed before release")

    # 3 ── DENY: missing QA dual-signoff (only one approver) ------------------
    _scenario(
        3,
        "manufacturing.batch_record.release",
        "BLOCKED: only one QA approver — dual sign-off requires second signatory",
    )
    try:
        client.protect(
            agent="qa.mgr@pharma.example",
            action="manufacturing.batch_record.release",
            context={
                "batchId": "BATCH-2026-00149",
                "productCode": "VIAL-API-50MG",
                "lotNumber": "L26-04419",
                "certifiedBy": "qa.mgr@pharma.example",
                # qaSignoffBy intentionally omitted — only one approver
                "batchRecordComplete": True,
                "deviationCount": 0,
                "regulatoryRegion": "US-FDA",
            },
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)
        print(f"               evaluation_id: {exc.evaluation_id}")
        _execute("batch NOT released — second QA signatory required")

    # ── Audit trail -----------------------------------------------------------
    if stub:
        chain = stub.audit_chain
        _bar(f"Audit Trail   {len(chain)} permitted action(s)   immutable hash-linked chain")
        for i, rec in enumerate(chain):
            print(f"  [{i + 1}] {rec.timestamp}")
            print(f"      action:    {rec.action}")
            print(f"      actor:     {rec.actor}")
            print(f"      permit_id: {rec.permit_id}")
            print(f"      hash:      {rec.audit_hash}")
            print(f"      prev:      {rec.previous_hash or '(genesis)'}")
            print(f"      reason:    {rec.reason}")
            if i < len(chain) - 1:
                print()
        if chain:
            print()
            print(f"  chain length : {len(chain)} events")
            print(f"  head hash    : {chain[-1].audit_hash}")

    _bar()
    print("  Enforcement summary:")
    print("    BLOCKED  2 actions (incomplete record / missing dual approver)")
    print("    ALLOWED  1 action  (permit-verified before batch release)")
    print()


def main() -> None:
    api_key = os.environ.get("ATLASENT_API_KEY", "")
    if api_key:
        run(AtlaSentClient(api_key=api_key, base_url=os.environ.get("ATLASENT_API_URL", "https://api.atlasent.io/functions/v1")), stub=None)
    else:
        stub = _MfgStub()
        run(stub, stub)


if __name__ == "__main__":
    main()
