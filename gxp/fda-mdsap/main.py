#!/usr/bin/env python3
"""gxp-fda-mdsap: MDSAP / ISO 13485 Medical Device QMS Authorization Demo

Demonstrates non-bypassable authorization for medical device quality
management system (QMS) operations under the FDA Medical Device Single
Audit Program (MDSAP) and ISO 13485:2016 using the AtlaSent SDK
fail-closed enforcement model.

Four scenarios:
  1. ALLOW   — quality manager handles a device complaint (complaint.handle)
  2. ALLOW   — regulatory affairs approves device labelling (label.approve)
  3. ESCALATE — qualified person requests device release (device.release — dual approval)
  4. DENY    — unauthorized operator attempts a design change (design.change)

Runs offline (in-process stub) by default.
Set ATLASENT_API_KEY to switch to the live AtlaSent API.

Regulatory references:
  ISO 13485:2016 §7.3.9   — Design changes
  ISO 13485:2016 §7.5.8   — Labelling
  ISO 13485:2016 §8.2.2   — Complaints
  ISO 13485:2016 §8.2.6   — Device acceptance / release
  21 CFR Part 820.80      — Receiving, in-process, and finished device acceptance
  21 CFR Part 820.198     — Complaint files
  MDSAP Audit Approach Version 2021.3 (IMDRF/MDSAP WG/N47)
"""
from __future__ import annotations

import hashlib
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

RELEASE_ROLES: frozenset[str] = frozenset({
    "qualified_person",
    "quality_manager",
})

DESIGN_CHANGE_ROLES: frozenset[str] = frozenset({
    "quality_manager",
    "regulatory_affairs",
    "design_engineer",
    "qualified_person",
})

LABEL_ROLES: frozenset[str] = frozenset({
    "regulatory_affairs",
    "quality_manager",
    "qualified_person",
})

COMPLAINT_ROLES: frozenset[str] = frozenset({
    "quality_manager",
    "regulatory_affairs",
    "complaint_handler",
})

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
    regulatory_ref: str = ""
    context_snapshot: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# In-process stub engine — MDSAP / ISO 13485 policy
# ---------------------------------------------------------------------------


class _MdsapStub(AtlaSentClient):
    """In-process stub — no HTTP calls, deterministic MDSAP policy engine.

    Implements the fda-mdsap pack from atlasent-gxp-starter/policies/:
      complaint.handle    — allow for quality_manager, regulatory_affairs, complaint_handler
      label.approve       — allow for regulatory_affairs, quality_manager, qualified_person
      device.release      — escalate (dual approval + e-signature; critical)
      design.change       — escalate for authorized roles; deny for all others
      process.validate    — escalate (critical)
      distribution.authorize — escalate (critical)
      capa.initiate       — allow for quality_manager, qualified_person
      audit.finding       — allow for quality_manager, internal_auditor, qualified_person
    """

    def __init__(self) -> None:
        super().__init__(
            "ask_test_mdsapstu00000000000000000",
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
        meta = stored.get("_meta", {})
        prev = self._audit_chain[-1].audit_hash if self._audit_chain else ""
        event_id = f"evt_{uuid.uuid4().hex[:12]}"
        actor = meta.get("actor_id", "")
        action = meta.get("action_type", "")
        reasons = stored.get("reasons", [])
        reason = reasons[0] if reasons else ""
        context = meta.get("context", {})
        reg_ref = stored.get("_regulatory_ref", "ISO 13485 / 21 CFR 820")
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
                regulatory_ref=reg_ref,
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
        """Return a V1-shaped response dict for the MDSAP / ISO 13485 policy."""

        def _allow(reason: str, reg_ref: str = "ISO 13485:2016 / 21 CFR 820") -> dict[str, Any]:
            pt = f"pt_{uuid.uuid4().hex[:16]}"
            return {
                "decision": "allow",
                "permit_token": pt,
                "reasons": [reason],
                "audit_hash": uuid.uuid4().hex[:32],
                "_regulatory_ref": reg_ref,
            }

        def _deny(reason: str) -> dict[str, Any]:
            return {"decision": "deny", "reasons": [reason]}

        def _escalate(reason: str) -> dict[str, Any]:
            return {"decision": "escalate", "reasons": [reason]}

        role = ctx.get("role", "")

        # ── complaint.handle (mdsap-004) ──────────────────────────────────────
        if action == "complaint.handle":
            if role not in COMPLAINT_ROLES:
                return _deny(
                    f"DENY_UNAUTHORIZED_ROLE: '{role}' cannot handle device complaints — "
                    f"requires quality_manager, regulatory_affairs, or complaint_handler "
                    f"per ISO 13485 §8.2.2 / 21 CFR 820.198"
                )
            return _allow(
                f"Complaint handling ALLOWED for {role} — "
                f"complaint file: {ctx.get('complaintId', 'N/A')}, "
                f"reportability assessment required",
                reg_ref="ISO 13485 §8.2.2 / 21 CFR 820.198",
            )

        # ── label.approve (mdsap-003) ─────────────────────────────────────────
        if action == "label.approve":
            if role not in LABEL_ROLES:
                return _deny(
                    f"DENY_UNAUTHORIZED_ROLE: '{role}' cannot approve device labelling — "
                    f"requires regulatory_affairs, quality_manager, or qualified_person "
                    f"per ISO 13485 §7.5.8 / 21 CFR 820.120"
                )
            label_version = ctx.get("labelVersion", "")
            if not label_version:
                return _deny(
                    "DENY_MISSING_CONTEXT: label_version required for labelling approval — "
                    "ISO 13485 §4.2.5 document control"
                )
            return _allow(
                f"Label approval ALLOWED for {role} — "
                f"label version: {label_version}, device: {ctx.get('deviceId', 'N/A')}",
                reg_ref="ISO 13485 §7.5.8 / 21 CFR 820.120",
            )

        # ── device.release (mdsap-002) ────────────────────────────────────────
        if action == "device.release":
            if role not in RELEASE_ROLES:
                return _deny(
                    f"DENY_UNAUTHORIZED_ROLE: '{role}' cannot authorize device release — "
                    f"requires qualified_person or quality_manager "
                    f"per ISO 13485 §8.2.6 / 21 CFR 820.80"
                )
            second_approver = ctx.get("secondApproverRole", "")
            if not second_approver or second_approver not in RELEASE_ROLES:
                return _escalate(
                    "ESCALATE_DUAL_APPROVAL_REQUIRED: ISO 13485 §8.2.6 / 21 CFR 820.80 — "
                    "device release requires dual Qualified Person approval and a complete "
                    "Device History Record (DHR); second approver not confirmed — "
                    "approval request queued"
                )
            dhr_complete = ctx.get("dhrComplete", False)
            if not dhr_complete:
                return _deny(
                    "DENY_DHR_INCOMPLETE: ISO 13485 §8.2.6 — Device History Record must be "
                    "complete before device release is authorized"
                )
            return _allow(
                f"Device release ALLOWED — dual QP approval: {role} + {second_approver}, "
                f"DHR complete, lot: {ctx.get('lotNumber', 'N/A')}",
                reg_ref="ISO 13485 §8.2.6 / 21 CFR 820.80(d)",
            )

        # ── design.change (mdsap-001) ─────────────────────────────────────────
        if action == "design.change":
            if role not in DESIGN_CHANGE_ROLES:
                return _deny(
                    f"DENY_UNAUTHORIZED_ROLE: '{role}' cannot authorize design changes — "
                    f"requires quality_manager, regulatory_affairs, design_engineer, or qualified_person "
                    f"per ISO 13485 §7.3.9"
                )
            dcr_id = ctx.get("dcrId", "")
            if not dcr_id:
                return _deny(
                    "DENY_MISSING_DCR: ISO 13485 §7.3.9 — a formal Design Change Request "
                    "with impact assessment is required before authorization"
                )
            return _escalate(
                "ESCALATE_DUAL_APPROVAL_REQUIRED: ISO 13485 §7.3.9 — design change requires "
                "dual approval (Quality + Regulatory Affairs), risk assessment per ISO 14971, "
                "and verification/validation confirmation — request queued for review"
            )

        # ── catch-all ─────────────────────────────────────────────────────────
        return _deny(
            f"DENY_NOT_REGISTERED: action '{action}' is not registered in the "
            "MDSAP / ISO 13485 policy — deny per QMS default control"
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


def _escalated(reason: str) -> None:
    print(f"  ⏸ ESCALATED  {_HOLD_TAG_RE.sub('', reason)}")


def _permit_line(p: Permit) -> None:
    print(f"  ✔ PERMITTED  {p.reason}")
    print(f"               permit_id:   {p.permit_id}")
    print(f"               audit_hash:  {p.audit_hash}")
    print(f"               permit_hash: {p.permit_hash}")


def _execute(msg: str) -> None:
    print(f"               → {msg}")


# ---------------------------------------------------------------------------
# Simulated QMS state mutations
# Only reachable after protect() returns a verified Permit.
# ---------------------------------------------------------------------------


def _sys_complaint_open(complaint_id: str, role: str) -> None:
    _execute(f"Complaint {complaint_id} opened in CAPA-linked complaint file")
    _execute("Complaint record appended to audit trail (ISO 13485 §8.2.2)")
    _execute(f"Assigned to: {role}, MDR reportability assessment initiated")


def _sys_label_approve(device_id: str, label_version: str, role: str) -> None:
    _execute(f"Label v{label_version} for device {device_id} approved in DHF")
    _execute("Label approval signed in Document Management System")
    _execute(f"Approver: {role} — ISO 13485 §7.5.8 / 21 CFR 820.120")


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------


def run(client: AtlaSentClient, stub: _MdsapStub | None) -> None:
    _bar("gxp-fda-mdsap   MDSAP / ISO 13485 Medical Device QMS Authorization Demo")
    print(f"  mode:        {'offline stub' if stub else 'live AtlaSent API'}")
    print(f"  regulation:  ISO 13485:2016 / MDSAP / 21 CFR Part 820")
    print(f"  policy pack: fda-mdsap (atlasent-gxp-starter/policies/)")

    # 1 ── ALLOW: quality manager handles a device complaint ──────────────────
    _scenario(
        1,
        "complaint.handle",
        "ALLOWED: quality manager opens complaint file — ISO 13485 §8.2.2",
    )
    try:
        p = client.protect(
            agent="qm.ross@meddevice.example",
            action="complaint.handle",
            context={
                "role": "quality_manager",
                "complaintId": "CMP-2026-0441",
                "deviceId": "MDV-PUMP-001",
                "complaintSource": "field_report",
                "reportabilityStatus": "under_assessment",
                "regulatoryRef": "ISO 13485 §8.2.2 / 21 CFR 820.198",
            },
        )
        _permit_line(p)
        _sys_complaint_open("CMP-2026-0441", "quality_manager")
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)

    # 2 ── ALLOW: regulatory affairs approves device labelling ────────────────
    _scenario(
        2,
        "label.approve",
        "ALLOWED: regulatory affairs approves device label — ISO 13485 §7.5.8",
    )
    try:
        p = client.protect(
            agent="ra.patel@meddevice.example",
            action="label.approve",
            context={
                "role": "regulatory_affairs",
                "deviceId": "MDV-PUMP-001",
                "labelVersion": "3.2.1",
                "markets": ["FDA", "CE", "TGA"],
                "dhfReference": "DHF-MDV-PUMP-001-REV3",
                "regulatoryRef": "ISO 13485 §7.5.8 / 21 CFR 820.120",
            },
        )
        _permit_line(p)
        _sys_label_approve("MDV-PUMP-001", "3.2.1", "regulatory_affairs")
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)

    # 3 ── ESCALATE: qualified person requests device release ─────────────────
    _scenario(
        3,
        "device.release",
        "ESCALATED: QP requests device release — dual approval + DHR required",
    )
    try:
        p = client.protect(
            agent="qp.chen@meddevice.example",
            action="device.release",
            context={
                "role": "qualified_person",
                "deviceId": "MDV-PUMP-001",
                "lotNumber": "LOT-2026-0881",
                "dhrComplete": True,
                # secondApproverRole absent — triggers escalate
                "regulatoryRef": "ISO 13485 §8.2.6 / 21 CFR 820.80",
            },
        )
        _permit_line(p)
    except AtlaSentDeniedError as exc:
        _escalated(exc.reason) if "ESCALATE" in exc.reason else _blocked(exc.reason)
        print(f"               evaluation_id: {exc.evaluation_id}")
        _execute(
            "Device release HELD — second QP approval and DHR review required"
        )

    # 4 ── DENY: unauthorized operator attempts design change ─────────────────
    _scenario(
        4,
        "design.change",
        "BLOCKED: production operator not authorized for design changes",
    )
    try:
        client.protect(
            agent="op.jones@meddevice.example",
            action="design.change",
            context={
                "role": "production_operator",  # not in DESIGN_CHANGE_ROLES
                "dcrId": "DCR-2026-0112",
                "changeDescription": "Update catheter tip material spec",
                "regulatoryRef": "ISO 13485 §7.3.9",
            },
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)
        print(f"               evaluation_id: {exc.evaluation_id}")
        _execute("Design change NOT initiated — route to Quality Manager for authorization")

    # ── Audit trail ─────────────────────────────────────────────────────────
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
            print(f"      reg ref:   {rec.regulatory_ref}")
            print(f"      reason:    {rec.reason}")
            if i < len(chain) - 1:
                print()
        if chain:
            print()
            print(f"  chain length : {len(chain)} events")
            print(f"  head hash    : {chain[-1].audit_hash}")

    _bar()
    print("  Enforcement summary:")
    print("    BLOCKED   1 action  (unauthorized role — production operator on design.change)")
    print("    ESCALATED 1 action  (dual QP approval required for device.release)")
    print("    ALLOWED   2 actions (complaint.handle + label.approve — permit-verified)")
    print()


def main() -> None:
    api_key = os.environ.get("ATLASENT_API_KEY", "")
    if api_key:
        run(AtlaSentClient(api_key=api_key, base_url=os.environ.get("ATLASENT_API_URL", "https://api.atlasent.io/functions/v1")), stub=None)
    else:
        stub = _MdsapStub()
        run(stub, stub)


if __name__ == "__main__":
    main()
