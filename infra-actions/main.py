#!/usr/bin/env python3
"""infra-actions: Infrastructure Actions Authorization Demo

Demonstrates non-bypassable authorization for destructive infrastructure
operations using the AtlaSent SDK fail-closed enforcement model.

Five scenarios:
  1. aws.ec2.stop_instance  — ALLOWED: on-call engineer, changeTicket present
  2. aws.ec2.terminate_instance — DENIED: actor has only engineer role
                                   (incident_commander required)
  3. github.repos.delete    — DENIED: human review always required
                               (machine_executable=False)
  4. database.table.drop    — DENIED: backupVerified=False
  5. database.volume.delete — ALLOWED: incident commander, backupVerified=True,
                               changeTicket present

Note: These actions are also demonstrated in atlasent-examples/protected-actions/
(the original examples); this example consolidates them with full policy context.

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
ON_CALL_ENGINEERS: frozenset[str] = frozenset(
    {
        "ic.oncall@acme.example",
        "sre.lead@acme.example",
        "eng.director@acme.example",
        "oncall.sre@acme.example",
    }
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
# Risk classification helper
# (mirrors classifyToolRisk() from @atlasent/sdk in TypeScript)
# ---------------------------------------------------------------------------


def classify_tool_risk(action: str) -> str:
    """Classify infrastructure action risk level.

    Maps action strings to risk levels:
      CRITICAL  — terminate, delete, drop (irreversible data/resource loss)
      HIGH      — stop, disable, drain (recoverable but impactful)
      MEDIUM    — restart, reboot, scale (temporary disruption)
      LOW       — read, describe, list (no modification)
    """
    action_lower = action.lower()
    critical_keywords = ("terminate", "delete", "drop", "destroy", "remove", "purge")
    high_keywords = ("stop", "disable", "drain", "detach", "deregister")
    medium_keywords = ("restart", "reboot", "scale", "resize", "modify")
    if any(kw in action_lower for kw in critical_keywords):
        return "CRITICAL"
    if any(kw in action_lower for kw in high_keywords):
        return "HIGH"
    if any(kw in action_lower for kw in medium_keywords):
        return "MEDIUM"
    return "LOW"


# ---------------------------------------------------------------------------
# In-process stub engine
# ---------------------------------------------------------------------------


class _InfraStub(AtlaSentClient):
    """In-process stub — no HTTP calls, deterministic infra action policy.

    Policy rules:
      - terminate/delete: always require incident_commander role
      - stop: requires on_call_engineer minimum
      - all: require changeTicket
      - data-destructive (drop/delete): require backupVerified=True
      - github.repos.delete: machine_executable=False (human review always required)
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
        """Return a V1-shaped response dict for infra action policies."""

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

        # -- aws.ec2.stop_instance --------------------------------------------
        if action == "aws.ec2.stop_instance":
            instance_id = ctx.get("instanceId", "")
            authorized_by = ctx.get("authorizedBy", "")
            change_ticket = ctx.get("changeTicket", "")
            if not instance_id:
                return deny("missing required field: instanceId")
            if not authorized_by:
                return deny("missing required field: authorizedBy")
            if authorized_by not in ON_CALL_ENGINEERS:
                return deny(
                    f"DENY_AUTHORITY: '{authorized_by}' does not have on_call_engineer role "
                    f"required to stop an EC2 instance"
                )
            if not change_ticket:
                return deny(
                    "DENY_MISSING_CHANGE_TICKET: changeTicket is required for all "
                    "infrastructure stop actions"
                )
            return allow(
                f"EC2 instance {instance_id} stop authorized by {authorized_by} "
                f"(change={change_ticket})"
            )

        # -- aws.ec2.terminate_instance ---------------------------------------
        if action == "aws.ec2.terminate_instance":
            instance_id = ctx.get("instanceId", "")
            authorized_by = ctx.get("authorizedBy", "")
            change_ticket = ctx.get("changeTicket", "")
            if not instance_id:
                return deny("missing required field: instanceId")
            if not authorized_by:
                return deny("missing required field: authorizedBy")
            if authorized_by not in INCIDENT_COMMANDERS:
                return deny(
                    f"DENY_AUTHORITY: '{authorized_by}' does not have incident_commander role "
                    f"required to terminate an EC2 instance (irreversible)"
                )
            if not change_ticket:
                return deny(
                    "DENY_MISSING_CHANGE_TICKET: changeTicket is required for "
                    "terminate actions"
                )
            return allow(
                f"EC2 instance {instance_id} termination authorized by {authorized_by} "
                f"(change={change_ticket})"
            )

        # -- github.repos.delete ----------------------------------------------
        if action == "github.repos.delete":
            # machine_executable=False: human review always required
            return deny(
                "DENY_HUMAN_REVIEW_REQUIRED: github.repos.delete has machine_executable=false "
                "— repository deletion always requires human review in the AtlaSent console; "
                "no automated pipeline may delete a repository"
            )

        # -- database.table.drop ----------------------------------------------
        if action == "database.table.drop":
            object_name = ctx.get("objectName", "")
            database = ctx.get("database", "")
            authorized_by = ctx.get("authorizedBy", "")
            backup_verified = ctx.get("backupVerified", False)
            change_ticket = ctx.get("changeTicket", "")
            if not object_name:
                return deny("missing required field: objectName")
            if not authorized_by:
                return deny("missing required field: authorizedBy")
            if authorized_by not in INCIDENT_COMMANDERS:
                return deny(
                    f"DENY_AUTHORITY: '{authorized_by}' does not have incident_commander role "
                    f"required to drop a database table (irreversible)"
                )
            if not backup_verified:
                return deny(
                    f"DENY_BACKUP_NOT_VERIFIED: backupVerified must be true before dropping "
                    f"table {object_name!r} in database {database!r}"
                )
            if not change_ticket:
                return deny(
                    "DENY_MISSING_CHANGE_TICKET: changeTicket is required for "
                    "data-destructive actions"
                )
            return allow(
                f"table {object_name!r} drop authorized by {authorized_by} "
                f"(db={database}, change={change_ticket})"
            )

        # -- database.volume.delete -------------------------------------------
        if action == "database.volume.delete":
            object_name = ctx.get("objectName", "")
            database = ctx.get("database", "")
            authorized_by = ctx.get("authorizedBy", "")
            backup_verified = ctx.get("backupVerified", False)
            change_ticket = ctx.get("changeTicket", "")
            if not object_name:
                return deny("missing required field: objectName")
            if not authorized_by:
                return deny("missing required field: authorizedBy")
            if authorized_by not in INCIDENT_COMMANDERS:
                return deny(
                    f"DENY_AUTHORITY: '{authorized_by}' does not have incident_commander role "
                    f"required to delete a database volume (irreversible)"
                )
            if not backup_verified:
                return deny(
                    f"DENY_BACKUP_NOT_VERIFIED: backupVerified must be true before deleting "
                    f"volume {object_name!r} in database {database!r}"
                )
            if not change_ticket:
                return deny(
                    "DENY_MISSING_CHANGE_TICKET: changeTicket is required for "
                    "volume delete actions"
                )
            return allow(
                f"volume {object_name!r} delete authorized by {authorized_by} "
                f"(db={database}, change={change_ticket})"
            )

        return deny(f"action '{action}' not registered in infra-actions policy")


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


def _risk(action: str) -> None:
    level = classify_tool_risk(action)
    print(f"               risk_level:  {level}  [classify_tool_risk]")


# ---------------------------------------------------------------------------
# Simulated infrastructure mutations
# Only reachable after protect() returns a verified Permit.
# ---------------------------------------------------------------------------


def _sys_stop_instance(instance_id: str, region: str) -> None:
    _execute(f"EC2 instance {instance_id} ({region}) stop command issued via AWS SDK")


def _sys_delete_volume(object_name: str, database: str) -> None:
    _execute(f"volume {object_name!r} in database {database!r} scheduled for deletion")
    _execute("pre-deletion snapshot verified, deletion job queued")


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------


def run(client: AtlaSentClient, stub: _InfraStub | None) -> None:  # noqa: C901
    _bar("infra-actions   Infrastructure Actions Authorization Demo")
    print(f"  mode:   {'offline stub' if stub else 'live AtlaSent API'}")
    print(
        "  note:   see also atlasent-examples/protected-actions/ "
        "(original protected actions examples)"
    )

    # 1 ── aws.ec2.stop_instance: ALLOWED ------------------------------------
    _scenario(
        1,
        "aws.ec2.stop_instance",
        "ALLOWED: on-call engineer, changeTicket present",
    )
    _risk("aws.ec2.stop_instance")
    try:
        p = client.protect(
            agent="oncall.sre@acme.example",
            action="aws.ec2.stop_instance",
            context={
                "instanceId": "i-0a1b2c3d4e5f6a7b8",
                "region": "us-east-1",
                "authorizedBy": "oncall.sre@acme.example",
                "changeTicket": "CHG-2026-04881",
                "reason": "Memory leak detected — stopping for snapshot before replacement",
            },
        )
        _permit_line(p)
        _sys_stop_instance("i-0a1b2c3d4e5f6a7b8", "us-east-1")
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)

    # 2 ── aws.ec2.terminate_instance: DENIED (engineer role, not IC) ---------
    _scenario(
        2,
        "aws.ec2.terminate_instance",
        "BLOCKED: actor has on_call_engineer role only — incident_commander required",
    )
    _risk("aws.ec2.terminate_instance")
    try:
        client.protect(
            agent="oncall.sre@acme.example",
            action="aws.ec2.terminate_instance",
            context={
                "instanceId": "i-0b2c3d4e5f6a7b8c9",
                "region": "us-east-1",
                "authorizedBy": "oncall.sre@acme.example",  # not incident commander
                "changeTicket": "CHG-2026-04882",
                "reason": "Compromised instance — terminate immediately",
            },
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)
        print(f"               evaluation_id: {exc.evaluation_id}")
        _execute("instance NOT terminated — incident_commander role required")

    # 3 ── github.repos.delete: DENIED (machine_executable=False) -------------
    _scenario(
        3,
        "github.repos.delete",
        "BLOCKED: machine_executable=False — human review always required",
    )
    _risk("github.repos.delete")
    try:
        client.protect(
            agent="automation-bot",
            action="github.repos.delete",
            context={
                "repoFullName": "acme-org/legacy-service",
                "deletedBy": "automation-bot",
                "changeTicket": "CHG-2026-04883",
                "reason": "Repository archived and migrated to new org",
            },
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)
        print(f"               evaluation_id: {exc.evaluation_id}")
        _execute("repository NOT deleted — human review required in AtlaSent console")

    # 4 ── database.table.drop: DENIED (backupVerified=False) -----------------
    _scenario(
        4,
        "database.table.drop",
        "BLOCKED: backupVerified=False — backup must be verified before drop",
    )
    _risk("database.table.drop")
    try:
        client.protect(
            agent="ic.oncall@acme.example",
            action="database.table.drop",
            context={
                "objectName": "staging_events_2024",
                "database": "analytics-db-prod",
                "authorizedBy": "ic.oncall@acme.example",
                "backupVerified": False,  # <-- no backup
                "changeTicket": "CHG-2026-04884",
            },
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)
        print(f"               evaluation_id: {exc.evaluation_id}")
        _execute("table NOT dropped — run backup verification first")

    # 5 ── database.volume.delete: ALLOWED (IC, backupVerified=True) ----------
    _scenario(
        5,
        "database.volume.delete",
        "ALLOWED: incident commander, backupVerified=True, changeTicket present",
    )
    _risk("database.volume.delete")
    try:
        p = client.protect(
            agent="ic.oncall@acme.example",
            action="database.volume.delete",
            context={
                "objectName": "vol-analytics-archive-2023",
                "database": "analytics-db-prod",
                "authorizedBy": "ic.oncall@acme.example",
                "backupVerified": True,
                "changeTicket": "CHG-2026-04885",
            },
        )
        _permit_line(p)
        _sys_delete_volume("vol-analytics-archive-2023", "analytics-db-prod")
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)

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
    print("    BLOCKED  3 actions (insufficient role / machine_executable / no backup)")
    print("    ALLOWED  2 actions (permit-verified before infra mutation)")
    print()


def main() -> None:
    api_key = os.environ.get("ATLASENT_API_KEY", "")
    if api_key:
        run(AtlaSentClient(api_key=api_key, base_url=os.environ.get("ATLASENT_API_URL", "https://api.atlasent.io/functions/v1")), stub=None)
    else:
        stub = _InfraStub()
        run(stub, stub)


if __name__ == "__main__":
    main()
