#!/usr/bin/env python3
"""hr-offboarding: HR Employee Offboarding Authorization Demo

Demonstrates non-bypassable authorization for HR employee offboarding
using the AtlaSent SDK fail-closed enforcement model.

Three scenarios:
  1. ALLOW  — terminated employee, HR manager authorized, proper documentation
  2. DENY   — active employee (not in terminated status), cannot offboard
  3. DENY   — missing HR authorization token (unauthenticated request)

Shows the access revocation cascade recorded in context fields.

Runs offline (in-process stub) by default.
Set ATLASENT_API_KEY to switch to the live AtlaSent API.
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

AUTHORIZED_HR_MANAGERS: frozenset[str] = frozenset(
    {"hr.mgr@acme.com", "hr.director@acme.com", "hr.vp@acme.com"}
)
AUTHORIZED_SYSTEMS: frozenset[str] = frozenset(
    {"workday", "okta-idp", "jira", "github-enterprise", "slack", "salesforce"}
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


class _HrStub(AtlaSentClient):
    """In-process stub — no HTTP calls, deterministic policy engine.

    Overrides ``_request`` to handle evaluate / verify locally.
    Implements the hr.employee.offboard policy:
      - fail_closed: true
      - machine_executable: false (HR manager sign-off required)
      - employeeStatus must be "terminated"
      - authorizedBy must be in the authorized HR manager list
      - hrAuthToken must be present (non-empty)
      - access revocation cascade systems are validated
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
        """Return a V1-shaped response dict for hr.employee.offboard policy."""

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

        if action != "hr.employee.offboard":
            return deny(f"action '{action}' not registered in hr-offboarding policy")

        employee_id = ctx.get("employeeId", "")
        employee_status = ctx.get("employeeStatus", "")
        authorized_by = ctx.get("authorizedBy", "")
        hr_auth_token = ctx.get("hrAuthToken", "")
        effective_date = ctx.get("effectiveDate", "")
        revocation_systems = ctx.get("revocationSystems", [])

        # Required field checks
        if not employee_id:
            return deny("DENY_MISSING_FIELD: missing required field: employeeId")
        if not authorized_by:
            return deny("DENY_MISSING_FIELD: missing required field: authorizedBy")

        # SOX access control: HR auth token must be present
        if not hr_auth_token:
            return deny(
                "DENY_MISSING_AUTH: hrAuthToken is absent — a valid HR system "
                "authorization token is required for offboarding actions"
            )

        # Employee must be in terminated status
        if employee_status != "terminated":
            return deny(
                f"DENY_INVALID_STATUS: employee {employee_id} has status "
                f"'{employee_status}' — offboarding requires status=terminated; "
                f"initiate a termination workflow before offboarding"
            )

        # HR manager authorization
        if authorized_by not in AUTHORIZED_HR_MANAGERS:
            return deny(
                f"DENY_AUTHORITY: '{authorized_by}' is not on the authorized HR "
                f"manager list — only HR managers may authorize offboarding"
            )

        if not effective_date:
            return deny("DENY_MISSING_FIELD: missing required field: effectiveDate")

        cascade_note = ""
        if revocation_systems:
            cascade_note = f", access revocation cascade: {', '.join(revocation_systems)}"

        return allow(
            f"employee {employee_id} offboarding authorized by {authorized_by} "
            f"(effective {effective_date}){cascade_note}"
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
# Simulated HR system state mutations
# Only reachable after protect() returns a verified Permit.
# ---------------------------------------------------------------------------


def _sys_offboard_employee(
    employee_id: str,
    authorized_by: str,
    revocation_systems: list[str],
) -> None:
    _execute(f"employee {employee_id} offboarding record created")
    _execute(f"authorized by: {authorized_by}")
    for system in revocation_systems:
        _execute(f"access revoked in: {system}")
    _execute("offboarding checklist initiated in HRIS")


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------


def run(client: AtlaSentClient, stub: _HrStub | None) -> None:
    _bar("hr-offboarding   Employee Offboarding Authorization Demo")
    print(f"  mode:   {'offline stub' if stub else 'live AtlaSent API'}")
    print(f"  action: hr.employee.offboard")
    print(f"  policy: fail-closed, machine_executable=False, SOX access controls")

    # 1 ── ALLOW: terminated employee, authorized HR manager ------------------
    _scenario(
        1,
        "hr.employee.offboard",
        "ALLOWED: terminated employee, HR manager authorized, access revocation cascade",
    )
    revocation_systems = ["okta-idp", "github-enterprise", "slack", "salesforce"]
    try:
        p = client.protect(
            agent="hr.mgr@acme.com",
            action="hr.employee.offboard",
            context={
                "employeeId": "EMP-10042",
                "employeeStatus": "terminated",
                "authorizedBy": "hr.mgr@acme.com",
                "hrAuthToken": "hrat_9f2a4c8e1d3b7f6a",
                "effectiveDate": "2026-05-30",
                "terminationReason": "voluntary_resignation",
                "revocationSystems": revocation_systems,
                "equipmentReturnRequired": True,
                "finalPayrollRun": "2026-05-31",
            },
        )
        _permit_line(p)
        _sys_offboard_employee("EMP-10042", "hr.mgr@acme.com", revocation_systems)
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)

    # 2 ── DENY: active employee, cannot offboard -----------------------------
    _scenario(
        2,
        "hr.employee.offboard",
        "BLOCKED: employeeStatus=active — termination workflow must precede offboarding",
    )
    try:
        client.protect(
            agent="hr.mgr@acme.com",
            action="hr.employee.offboard",
            context={
                "employeeId": "EMP-10099",
                "employeeStatus": "active",  # <-- not terminated
                "authorizedBy": "hr.mgr@acme.com",
                "hrAuthToken": "hrat_9f2a4c8e1d3b7f6a",
                "effectiveDate": "2026-05-30",
                "revocationSystems": ["okta-idp"],
            },
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)
        print(f"               evaluation_id: {exc.evaluation_id}")
        _execute("employee NOT offboarded — initiate termination workflow first")

    # 3 ── DENY: missing HR auth token ----------------------------------------
    _scenario(
        3,
        "hr.employee.offboard",
        "BLOCKED: hrAuthToken absent — unauthenticated request denied",
    )
    try:
        client.protect(
            agent="unknown-bot",
            action="hr.employee.offboard",
            context={
                "employeeId": "EMP-10055",
                "employeeStatus": "terminated",
                "authorizedBy": "hr.mgr@acme.com",
                # hrAuthToken intentionally omitted
                "effectiveDate": "2026-05-30",
                "revocationSystems": ["okta-idp", "slack"],
            },
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)
        print(f"               evaluation_id: {exc.evaluation_id}")
        _execute("offboarding NOT initiated — HR auth token required")

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
    print("    BLOCKED  2 actions (active employee / missing auth token)")
    print("    ALLOWED  1 action  (permit-verified before offboarding execution)")
    print()


def main() -> None:
    api_key = os.environ.get("ATLASENT_API_KEY", "")
    if api_key:
        run(AtlaSentClient(api_key=api_key, base_url=os.environ.get("ATLASENT_API_URL", "https://api.atlasent.io/functions/v1")), stub=None)
    else:
        stub = _HrStub()
        run(stub, stub)


if __name__ == "__main__":
    main()
