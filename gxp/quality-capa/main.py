#!/usr/bin/env python3
"""gxp-quality-capa: GxP Quality CAPA Lifecycle Authorization Demo

Demonstrates non-bypassable authorization for the full CAPA (Corrective and
Preventive Action) lifecycle across 5 action types using the AtlaSent SDK.

Action types:
  quality.capa.initiate        — QA manager initiates a CAPA
  quality.capa.assign          — Assigns owner to the CAPA
  quality.capa.progress        — Progress update from owner
  quality.capa.effectiveness_check — 90-day effectiveness verification
  quality.capa.close           — Final closure (dual approval)

Three flows:
  1. Full happy-path CAPA from initiation to closure
  2. Closure blocked due to missing dual approval
  3. Effectiveness check denied for unauthorized reviewer

Runs offline (in-process stub) by default.
Set ATLASENT_API_KEY to switch to the live AtlaSent API.
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

QA_MANAGERS: frozenset[str] = frozenset(
    {"qa.mgr@pharma.example", "qa.director@pharma.example"}
)
QA_STAFF: frozenset[str] = frozenset(
    {"qa.mgr@pharma.example", "qa.director@pharma.example", "qa.lead@pharma.example"}
)
EFFECTIVENESS_MIN_DAYS = 90

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


class _CapaStub(AtlaSentClient):
    """In-process stub — no HTTP calls, deterministic CAPA policy engine.

    Implements policies for all five quality.capa.* action types:
      - initiate:            requires qa_manager role (initiatedBy in QA_MANAGERS)
      - assign:              requires qa_manager or authorized assignor
      - progress:            any authenticated staff member, capaId present
      - effectiveness_check: requires qa_manager + effectivenessScore present
      - close:               requires dual approval (closedBy + secondClosedBy,
                             both in QA_STAFF, distinct)
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
        """Return a V1-shaped response dict for the quality.capa.* policy."""

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

        capa_id = ctx.get("capaId", "")

        # -- quality.capa.initiate --------------------------------------------
        if action == "quality.capa.initiate":
            initiated_by = ctx.get("initiatedBy", "")
            source = ctx.get("source", "")
            severity = ctx.get("severity", "")
            description = ctx.get("description", "")
            if not capa_id:
                return deny("missing required field: capaId")
            if not initiated_by:
                return deny("missing required field: initiatedBy")
            if initiated_by not in QA_MANAGERS:
                return deny(
                    f"DENY_AUTHORITY: '{initiated_by}' does not have qa_manager role "
                    f"required to initiate a CAPA"
                )
            if not source:
                return deny("missing required field: source")
            if not severity:
                return deny("missing required field: severity")
            return allow(
                f"CAPA {capa_id} initiated by {initiated_by} "
                f"(source={source}, severity={severity})"
            )

        # -- quality.capa.assign ----------------------------------------------
        if action == "quality.capa.assign":
            assigned_by = ctx.get("assignedBy", "")
            assigned_to = ctx.get("assignedTo", "")
            due_date = ctx.get("dueDate", "")
            if not capa_id:
                return deny("missing required field: capaId")
            if not assigned_by:
                return deny("missing required field: assignedBy")
            if assigned_by not in QA_STAFF:
                return deny(
                    f"DENY_AUTHORITY: '{assigned_by}' is not authorized to assign CAPA tasks"
                )
            if not assigned_to:
                return deny("missing required field: assignedTo")
            if not due_date:
                return deny("missing required field: dueDate")
            return allow(
                f"CAPA {capa_id} assigned to {assigned_to} by {assigned_by} "
                f"(due {due_date})"
            )

        # -- quality.capa.progress --------------------------------------------
        if action == "quality.capa.progress":
            updated_by = ctx.get("updatedBy", "")
            progress_note = ctx.get("progressNote", "")
            percent_complete = ctx.get("percentComplete", None)
            if not capa_id:
                return deny("missing required field: capaId")
            if not updated_by:
                return deny("missing required field: updatedBy")
            if not progress_note:
                return deny("missing required field: progressNote")
            if percent_complete is None:
                return deny("missing required field: percentComplete")
            return allow(
                f"CAPA {capa_id} progress updated by {updated_by} "
                f"({percent_complete}% complete)"
            )

        # -- quality.capa.effectiveness_check ---------------------------------
        if action == "quality.capa.effectiveness_check":
            checked_by = ctx.get("checkedBy", "")
            effectiveness_score = ctx.get("effectivenessScore", None)
            evidence_uri = ctx.get("evidenceUri", "")
            if not capa_id:
                return deny("missing required field: capaId")
            if not checked_by:
                return deny("missing required field: checkedBy")
            if checked_by not in QA_MANAGERS:
                return deny(
                    f"DENY_AUTHORITY: '{checked_by}' does not have qa_manager role "
                    f"required to perform an effectiveness check"
                )
            if effectiveness_score is None:
                return deny("missing required field: effectivenessScore")
            if not evidence_uri:
                return deny("missing required field: evidenceUri")
            return allow(
                f"CAPA {capa_id} effectiveness check by {checked_by}: "
                f"score={effectiveness_score}, evidence={evidence_uri}"
            )

        # -- quality.capa.close -----------------------------------------------
        if action == "quality.capa.close":
            closed_by = ctx.get("closedBy", "")
            second_closed_by = ctx.get("secondClosedBy", "")
            closure_rationale = ctx.get("closureRationale", "")
            if not capa_id:
                return deny("missing required field: capaId")
            if not closed_by:
                return deny("DENY_DUAL_APPROVER_MISSING: missing required field: closedBy")
            if not second_closed_by:
                return deny(
                    f"DENY_DUAL_APPROVER_MISSING: CAPA closure requires dual approval — "
                    f"secondClosedBy is absent"
                )
            if closed_by == second_closed_by:
                return deny(
                    f"DENY_DUAL_APPROVER_MISSING: closedBy and secondClosedBy must be "
                    f"distinct individuals — same person ({closed_by}) cannot provide dual sign-off"
                )
            if closed_by not in QA_STAFF:
                return deny(
                    f"DENY_AUTHORITY: '{closed_by}' is not authorized to close a CAPA"
                )
            if second_closed_by not in QA_STAFF:
                return deny(
                    f"DENY_AUTHORITY: '{second_closed_by}' is not authorized to provide "
                    f"second closure sign-off"
                )
            if not closure_rationale:
                return deny("missing required field: closureRationale")
            return allow(
                f"CAPA {capa_id} closed by {closed_by} + {second_closed_by}: "
                f"{closure_rationale[:60]}"
            )

        return deny(f"action '{action}' not registered in quality-capa policy")


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


def _scenario(num: int | str, label: str, note: str) -> None:
    print(f"\n▸ Scenario {num} — {label}")
    print(f"  {note}")


_HOLD_TAG_RE = re.compile(r"\s*\[hold:[^\]]+\]")


def _blocked(reason: str) -> None:
    print(f"  ✗ BLOCKED    {_HOLD_TAG_RE.sub('', reason)}")


def _permit_line(p: Permit) -> None:
    print(f"  ✔ PERMITTED  {p.reason}")
    print(f"               permit_id:   {p.permit_id}")
    print(f"               audit_hash:  {p.audit_hash}")


def _step(action: str, note: str) -> None:
    print(f"    [{action}]  {note}")


def _execute(msg: str) -> None:
    print(f"               → {msg}")


# ---------------------------------------------------------------------------
# Simulated CAPA system mutations
# Only reachable after protect() returns a verified Permit.
# ---------------------------------------------------------------------------


def _sys_initiate_capa(capa_id: str, initiated_by: str, severity: str) -> None:
    _execute(f"CAPA {capa_id} created in QMS, status=OPEN, severity={severity}")


def _sys_assign_capa(capa_id: str, assigned_to: str, due_date: str) -> None:
    _execute(f"CAPA {capa_id} assigned to {assigned_to}, due={due_date}, status=ASSIGNED")


def _sys_progress_capa(capa_id: str, percent: int) -> None:
    _execute(f"CAPA {capa_id} progress updated: {percent}% complete")


def _sys_effectiveness_check(capa_id: str, score: float) -> None:
    _execute(f"CAPA {capa_id} effectiveness check recorded: score={score}")


def _sys_close_capa(capa_id: str) -> None:
    _execute(f"CAPA {capa_id} set to CLOSED — no further modifications permitted")


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------


def run(client: AtlaSentClient, stub: _CapaStub | None) -> None:  # noqa: C901
    _bar("gxp-quality-capa   CAPA Lifecycle Authorization Demo")
    print(f"  mode:   {'offline stub' if stub else 'live AtlaSent API'}")
    print(f"  policy: fail-closed, dual-approver for closure, qa_manager for initiation")

    # =========================================================================
    # Flow 1: Full happy-path CAPA from initiation to closure
    # =========================================================================
    _bar("Flow 1 — Full happy-path CAPA lifecycle")
    capa_id = "CAPA-2026-00042"

    # 1a — initiate
    _scenario("1a", "quality.capa.initiate", "ALLOWED: QA manager initiates CAPA")
    try:
        p = client.protect(
            agent="qa.mgr@pharma.example",
            action="quality.capa.initiate",
            context={
                "capaId": capa_id,
                "initiatedBy": "qa.mgr@pharma.example",
                "source": "deviation-report-DR-2026-0081",
                "severity": "major",
                "description": "Out-of-specification pH result in final product testing",
            },
        )
        _permit_line(p)
        _sys_initiate_capa(capa_id, "qa.mgr@pharma.example", "major")
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)

    # 1b — assign
    _scenario("1b", "quality.capa.assign", "ALLOWED: QA manager assigns CAPA owner")
    try:
        p = client.protect(
            agent="qa.mgr@pharma.example",
            action="quality.capa.assign",
            context={
                "capaId": capa_id,
                "assignedBy": "qa.mgr@pharma.example",
                "assignedTo": "process.eng@pharma.example",
                "dueDate": "2026-08-15",
            },
        )
        _permit_line(p)
        _sys_assign_capa(capa_id, "process.eng@pharma.example", "2026-08-15")
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)

    # 1c — progress
    _scenario("1c", "quality.capa.progress", "ALLOWED: owner updates progress")
    try:
        p = client.protect(
            agent="process.eng@pharma.example",
            action="quality.capa.progress",
            context={
                "capaId": capa_id,
                "updatedBy": "process.eng@pharma.example",
                "progressNote": "Root cause identified: calibration drift in pH meter probe",
                "percentComplete": 50,
            },
        )
        _permit_line(p)
        _sys_progress_capa(capa_id, 50)
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)

    # 1d — effectiveness check (post 90-day window)
    _scenario(
        "1d",
        "quality.capa.effectiveness_check",
        "ALLOWED: QA manager performs 90-day effectiveness check",
    )
    try:
        p = client.protect(
            agent="qa.mgr@pharma.example",
            action="quality.capa.effectiveness_check",
            context={
                "capaId": capa_id,
                "checkedBy": "qa.mgr@pharma.example",
                "effectivenessScore": 0.92,
                "evidenceUri": "s3://qms-evidence/capa-2026-00042/effectiveness-check.pdf",
            },
        )
        _permit_line(p)
        _sys_effectiveness_check(capa_id, 0.92)
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)

    # 1e — close
    _scenario("1e", "quality.capa.close", "ALLOWED: dual QA approval for CAPA closure")
    try:
        p = client.protect(
            agent="qa.mgr@pharma.example",
            action="quality.capa.close",
            context={
                "capaId": capa_id,
                "closedBy": "qa.mgr@pharma.example",
                "secondClosedBy": "qa.director@pharma.example",
                "closureRationale": "Root cause corrected; effectiveness score 0.92 above threshold",
            },
        )
        _permit_line(p)
        _sys_close_capa(capa_id)
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)

    # =========================================================================
    # Flow 2: Closure blocked due to missing dual approval
    # =========================================================================
    _bar("Flow 2 — Closure blocked: missing secondClosedBy")
    capa_id_2 = "CAPA-2026-00043"
    _scenario(
        2,
        "quality.capa.close",
        "BLOCKED: secondClosedBy absent — dual approval required for CAPA closure",
    )
    try:
        client.protect(
            agent="qa.mgr@pharma.example",
            action="quality.capa.close",
            context={
                "capaId": capa_id_2,
                "closedBy": "qa.mgr@pharma.example",
                # secondClosedBy intentionally omitted
                "closureRationale": "Trying to self-close without second approver",
            },
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)
        print(f"               evaluation_id: {exc.evaluation_id}")
        _execute("CAPA NOT closed — second authorized QA signatory required")

    # =========================================================================
    # Flow 3: Effectiveness check denied for unauthorized reviewer
    # =========================================================================
    _bar("Flow 3 — Effectiveness check denied: unauthorized reviewer")
    capa_id_3 = "CAPA-2026-00044"
    _scenario(
        3,
        "quality.capa.effectiveness_check",
        "BLOCKED: reviewer does not have qa_manager role",
    )
    try:
        client.protect(
            agent="lab.tech@pharma.example",
            action="quality.capa.effectiveness_check",
            context={
                "capaId": capa_id_3,
                "checkedBy": "lab.tech@pharma.example",  # not in QA_MANAGERS
                "effectivenessScore": 0.85,
                "evidenceUri": "s3://qms-evidence/capa-2026-00044/check.pdf",
            },
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)
        print(f"               evaluation_id: {exc.evaluation_id}")
        _execute("effectiveness check NOT recorded — qa_manager role required")

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
    print("    BLOCKED  2 actions (missing dual approval / unauthorized reviewer)")
    print("    ALLOWED  5 actions (full happy-path CAPA lifecycle permit-verified)")
    print()


def main() -> None:
    api_key = os.environ.get("ATLASENT_API_KEY", "")
    if api_key:
        run(AtlaSentClient(api_key=api_key, base_url=os.environ.get("ATLASENT_API_URL", "https://api.atlasent.io/functions/v1")), stub=None)
    else:
        stub = _CapaStub()
        run(stub, stub)


if __name__ == "__main__":
    main()
