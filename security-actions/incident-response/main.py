#!/usr/bin/env python3
"""security-incident-response: Security Incident Escalation & Access Quarantine Demo

Demonstrates non-bypassable authorization for critical security operations
using the AtlaSent SDK fail-closed enforcement model.

Four scenarios:
  1. ALLOW  — critical incident, authorized SOC lead, all required fields present
  2. DENY   — policy denies (SOC lead identity not verified)
  3. ALLOW  — access quarantine, authorized SOC lead, target identified
  4. DENY   — missing quarantineReason field (blocked before evaluate call)

Runs offline (in-process stub) by default.
Set ATLASENT_API_KEY to switch to the live AtlaSent API.
"""
from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from atlasent import AtlaSentClient, AtlaSentDeniedError, Permit

AUTHORIZED_SOC_LEADS: frozenset[str] = frozenset(
    {"soc:lead-alice", "soc:lead-charlie", "ciso:eve"}
)

WIDTH = 72


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


class _SecurityStub(AtlaSentClient):
    """In-process stub — no HTTP calls, deterministic policy engine.

    Overrides ``_request`` to handle evaluate / verify locally.
    Implements the security incident escalation / quarantine policy:
      - fail_closed: true
      - machine_executable: false (SOC lead sign-off required)
      - authorizedBy must be on the authorized SOC leads list
      - For escalate: incidentId + severity required
      - For quarantine: targetId + quarantineReason required
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
            return {"verified": False, "permit_hash": "", "outcome": "invalid", "timestamp": ts}
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
        return {"verified": True, "permit_hash": permit_hash, "outcome": "verified", "timestamp": ts}

    def _decide(self, action: str, agent: str, ctx: dict[str, Any]) -> dict[str, Any]:
        def allow(reason: str) -> dict[str, Any]:
            permit_token = f"pt_{uuid.uuid4().hex[:16]}"
            return {"decision": "allow", "permit_token": permit_token, "reasons": [reason], "audit_hash": uuid.uuid4().hex[:32]}

        def deny(reason: str) -> dict[str, Any]:
            return {"decision": "deny", "reasons": [reason]}

        authorized_by = ctx.get("authorizedBy", "")

        if action == "security.incident.escalate":
            incident_id = ctx.get("incidentId", "")
            severity = ctx.get("severity", "")
            if not incident_id:
                return deny("DENY_MISSING_FIELD: missing required field: incidentId")
            if not severity:
                return deny("DENY_MISSING_FIELD: missing required field: severity")
            if authorized_by not in AUTHORIZED_SOC_LEADS:
                return deny(
                    f"DENY_AUTHORITY: '{authorized_by}' is not an authorized SOC lead — "
                    f"only SOC leads may authorize incident escalation"
                )
            return allow(
                f"incident {incident_id} (severity={severity}) escalation authorized by {authorized_by}"
            )

        if action == "security.access.quarantine":
            target_id = ctx.get("targetId", "")
            quarantine_reason = ctx.get("quarantineReason", "")
            if not target_id:
                return deny("DENY_MISSING_FIELD: missing required field: targetId")
            if not quarantine_reason:
                return deny("DENY_MISSING_FIELD: missing required field: quarantineReason")
            if authorized_by not in AUTHORIZED_SOC_LEADS:
                return deny(
                    f"DENY_AUTHORITY: '{authorized_by}' is not an authorized SOC lead — "
                    f"only SOC leads may authorize access quarantine"
                )
            return allow(
                f"access quarantine for {target_id} authorized by {authorized_by}: {quarantine_reason}"
            )

        return deny(f"action '{action}' not registered in security-actions policy")


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


def _permitted(p: Permit) -> None:
    print(f"  ✔ PERMITTED  security action authorized")
    print(f"               permit_id:   {p.permit_id}")
    print(f"               audit_hash:  {p.audit_hash}")
    print(f"               permit_hash: {p.permit_hash}")


def _blocked(reason: str) -> None:
    print(f"  ✗ BLOCKED    {reason}")


def _execute(msg: str) -> None:
    print(f"               → {msg}")


def run(client: AtlaSentClient, stub: _SecurityStub | None) -> None:
    _bar("security-incident-response   Security Operations Authorization Demo")
    print(f"  mode:   {'offline stub' if stub else 'live AtlaSent API'}")
    print(f"  actions: security.incident.escalate, security.access.quarantine")
    print(f"  policy:  fail-closed, machine_executable=False, 1h quorum window")

    # 1 ── ALLOW: critical incident escalation ----------------------------------
    _scenario(
        1,
        "security.incident.escalate",
        "ALLOWED: critical incident, authorized SOC lead, all required fields present",
    )
    try:
        p = client.protect(
            agent="soc:lead-alice",
            action="security.incident.escalate",
            context={
                "incidentId": "INC-2026-CRIT-001",
                "severity": "critical",
                "authorizedBy": "soc:lead-alice",
                "affectedSystems": ["prod-api", "auth-service"],
                "detectedAt": "2026-05-29T07:00:00Z",
            },
        )
        _permitted(p)
        _execute("incident escalation workflow triggered")
        _execute("SOC team notified via PagerDuty")
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)

    # 2 ── DENY: unauthorized SOC analyst (not on approved list) ----------------
    _scenario(
        2,
        "security.incident.escalate",
        "BLOCKED: unauthorized SOC analyst — not on authorized SOC leads list",
    )
    try:
        client.protect(
            agent="soc:analyst-intern",
            action="security.incident.escalate",
            context={
                "incidentId": "INC-2026-HIGH-007",
                "severity": "high",
                "authorizedBy": "soc:analyst-intern",  # not on authorized list
            },
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)
        print(f"               evaluation_id: {exc.evaluation_id}")
        _execute("incident NOT escalated — SOC lead authorization required")

    # 3 ── ALLOW: access quarantine -------------------------------------------
    _scenario(
        3,
        "security.access.quarantine",
        "ALLOWED: compromised principal, authorized SOC lead, quarantine reason provided",
    )
    try:
        p = client.protect(
            agent="soc:lead-alice",
            action="security.access.quarantine",
            context={
                "targetId": "user:compromised-carol",
                "quarantineReason": "suspected credential compromise via spear phishing",
                "authorizedBy": "soc:lead-alice",
                "incidentReference": "INC-2026-CRIT-001",
            },
        )
        _permitted(p)
        _execute("all access for user:compromised-carol revoked")
        _execute("access revocation cascade initiated: okta-idp, github-enterprise, slack")
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)

    # 4 ── DENY: missing quarantineReason ---------------------------------------
    _scenario(
        4,
        "security.access.quarantine",
        "BLOCKED: missing quarantineReason field",
    )
    try:
        client.protect(
            agent="soc:lead-alice",
            action="security.access.quarantine",
            context={
                "targetId": "user:some-target",
                "authorizedBy": "soc:lead-alice",
                # quarantineReason intentionally omitted
            },
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)
        print(f"               evaluation_id: {exc.evaluation_id}")
        _execute("quarantine NOT executed — quarantineReason required")

    # ── Audit trail -------------------------------------------------------------
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
    print("    BLOCKED  2 actions (unauthorized actor / missing required field)")
    print("    ALLOWED  2 actions (permit-verified before security action execution)")
    print()


def main() -> None:
    api_key = os.environ.get("ATLASENT_API_KEY", "")
    if api_key:
        run(AtlaSentClient(api_key=api_key, base_url=os.environ.get("ATLASENT_API_URL", "https://api.atlasent.io/functions/v1")), stub=None)
    else:
        stub = _SecurityStub()
        run(stub, stub)


if __name__ == "__main__":
    main()
