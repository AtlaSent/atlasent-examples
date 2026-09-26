#!/usr/bin/env python3
"""deployment-v2/rollback.py: Deployment Rollback Authorization Demo

Demonstrates non-bypassable authorization for deployment rollbacks using
the `deployment.rollback.execute` action with fail-closed enforcement.

Rollbacks are a high-stakes action that require incident commander authorization.
The policy is fail-closed: if the AtlaSent API is unavailable, the rollback
is blocked to prevent unauthorized changes to production.

Context: incidentId, rollbackTarget, authorizedBy, reason

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

INCIDENT_COMMANDERS: frozenset[str] = frozenset(
    {"ic.oncall@acme.example", "sre.lead@acme.example", "eng.director@acme.example"}
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


class _RollbackStub(AtlaSentClient):
    """In-process stub — no HTTP calls, deterministic rollback policy.

    Policy:
      - fail_closed: true
      - authorizedBy must be incident commander
      - incidentId, rollbackTarget, and reason are required
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

        if action not in (
            "deployment.production.execute",
            "deployment.staging.execute",
            "deployment.rollback.execute",
        ):
            return deny(f"action '{action}' not registered in deployment-v2 policy")

        incident_id = ctx.get("incidentId", "")
        rollback_target = ctx.get("rollbackTarget", "")
        authorized_by = ctx.get("authorizedBy", "")
        reason_str = ctx.get("reason", "")

        if action == "deployment.rollback.execute":
            if not incident_id:
                return deny("missing required field: incidentId")
            if not rollback_target:
                return deny("missing required field: rollbackTarget")
            if not authorized_by:
                return deny("missing required field: authorizedBy")
            if authorized_by not in INCIDENT_COMMANDERS:
                return deny(
                    f"DENY_AUTHORITY: '{authorized_by}' does not have incident_commander role "
                    f"required to authorize a production rollback"
                )
            if not reason_str:
                return deny("missing required field: reason")
            return allow(
                f"rollback to {rollback_target} authorized by {authorized_by} "
                f"(incident={incident_id})"
            )

        if action == "deployment.production.execute":
            build_sha = ctx.get("buildSha", "")
            change_ticket = ctx.get("changeTicket", "")
            if not build_sha:
                return deny("missing required field: buildSha")
            if not change_ticket:
                return deny(
                    "DENY_MISSING_CHANGE_TICKET: production deployment requires changeTicket"
                )
            return allow(
                f"production deployment authorized: sha={build_sha[:8]}, "
                f"change_ticket={change_ticket}"
            )

        if action == "deployment.staging.execute":
            build_sha = ctx.get("buildSha", "")
            if not build_sha:
                return deny("missing required field: buildSha")
            return allow(f"staging deployment authorized: sha={build_sha[:8]}")

        return deny(f"action '{action}' not handled")


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
# Simulated deployment mutations
# Only reachable after protect() returns a verified Permit.
# ---------------------------------------------------------------------------


def _sys_execute_rollback(rollback_target: str, incident_id: str) -> None:
    _execute(f"rolling back to {rollback_target} (incident={incident_id})")
    _execute("rollback initiated in deployment system, old version being restored")


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------


def run(client: AtlaSentClient, stub: _RollbackStub | None) -> None:
    _bar("deployment-v2/rollback   Deployment Rollback Authorization Demo")
    print(f"  mode:   {'offline stub' if stub else 'live AtlaSent API'}")
    print(f"  action: deployment.rollback.execute")
    print(f"  policy: fail-closed, incident_commander role required")

    # 1 ── ALLOW: incident commander authorizes rollback ----------------------
    _scenario(
        1,
        "deployment.rollback.execute",
        "ALLOWED: incident commander authorizes rollback",
    )
    try:
        p = client.protect(
            agent="ic.oncall@acme.example",
            action="deployment.rollback.execute",
            context={
                "incidentId": "INC-2026-00847",
                "rollbackTarget": "sha256:a1b2c3d4e5f6",
                "authorizedBy": "ic.oncall@acme.example",
                "reason": "P0: checkout-api returning 503 after deploy, rolling back",
            },
        )
        _permit_line(p)
        _sys_execute_rollback("sha256:a1b2c3d4e5f6", "INC-2026-00847")
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)

    # 2 ── DENY: engineer (not incident commander) attempts rollback ----------
    _scenario(
        2,
        "deployment.rollback.execute",
        "BLOCKED: engineer does not have incident_commander role",
    )
    try:
        client.protect(
            agent="swe.dev@acme.example",
            action="deployment.rollback.execute",
            context={
                "incidentId": "INC-2026-00848",
                "rollbackTarget": "sha256:b2c3d4e5f6a1",
                "authorizedBy": "swe.dev@acme.example",  # not incident commander
                "reason": "Trying to self-authorize rollback",
            },
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)
        print(f"               evaluation_id: {exc.evaluation_id}")
        _execute("rollback NOT executed — incident_commander authorization required")

    # 3 ── DENY: missing incident ID ------------------------------------------
    _scenario(
        3,
        "deployment.rollback.execute",
        "BLOCKED: incidentId missing — fail-closed requires incident reference",
    )
    try:
        client.protect(
            agent="ic.oncall@acme.example",
            action="deployment.rollback.execute",
            context={
                # incidentId intentionally omitted
                "rollbackTarget": "sha256:c3d4e5f6a1b2",
                "authorizedBy": "ic.oncall@acme.example",
                "reason": "Emergency rollback",
            },
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)
        print(f"               evaluation_id: {exc.evaluation_id}")
        _execute("rollback NOT executed — incidentId required")

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

    _bar()
    print("  Enforcement summary:")
    print("    BLOCKED  2 actions (unauthorized actor / missing incidentId)")
    print("    ALLOWED  1 action  (incident commander, full context)")
    print()


def main() -> None:
    api_key = os.environ.get("ATLASENT_API_KEY", "")
    if api_key:
        run(AtlaSentClient(api_key=api_key, base_url=os.environ.get("ATLASENT_API_URL", "https://api.atlasent.io/functions/v1")), stub=None)
    else:
        stub = _RollbackStub()
        run(stub, stub)


if __name__ == "__main__":
    main()
