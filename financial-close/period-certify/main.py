#!/usr/bin/env python3
"""financial-period-certify: Financial Period Close Certification Authorization Demo

Demonstrates non-bypassable authorization for financial period close
certification using the AtlaSent SDK fail-closed enforcement model.

Three scenarios:
  1. ALLOW  — Q1 close, authorized financial controller, all required fields present
  2. DENY   — unauthorized AP clerk attempting close certification
  3. DENY   — missing financialController field (blocked before evaluate call)

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

AUTHORIZED_FINANCIAL_CONTROLLERS: frozenset[str] = frozenset(
    {"fc:bob", "fc:carol", "cfo:alice", "controller:jane", "vp-finance:diana"}
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


class _FinancialCloseStub(AtlaSentClient):
    """In-process stub — no HTTP calls, deterministic policy engine.

    Implements the period.close.certify policy:
      - fail_closed: true
      - machine_executable: false (financial controller sign-off required)
      - periodId + certifiedBy + financialController required
      - financialController must be on the authorized controllers list
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

        if action != "period.close.certify":
            return deny(f"action '{action}' not registered in financial-close policy")

        period_id = ctx.get("periodId", "")
        certified_by = ctx.get("certifiedBy", "")
        financial_controller = ctx.get("financialController", "")

        if not period_id:
            return deny("DENY_MISSING_FIELD: missing required field: periodId")
        if not certified_by:
            return deny("DENY_MISSING_FIELD: missing required field: certifiedBy")
        if not financial_controller:
            return deny("DENY_MISSING_FIELD: missing required field: financialController")
        if financial_controller not in AUTHORIZED_FINANCIAL_CONTROLLERS:
            return deny(
                f"DENY_AUTHORITY: '{financial_controller}' is not an authorized financial controller — "
                f"only financial controllers may authorize period close certification"
            )

        return allow(
            f"period {period_id} close certified by {certified_by} "
            f"under financial controller {financial_controller}"
        )


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
    print(f"  ✔ PERMITTED  period close certification authorized")
    print(f"               permit_id:   {p.permit_id}")
    print(f"               audit_hash:  {p.audit_hash}")
    print(f"               permit_hash: {p.permit_hash}")


def _blocked(reason: str) -> None:
    print(f"  ✗ BLOCKED    {reason}")


def _execute(msg: str) -> None:
    print(f"               → {msg}")


def run(client: AtlaSentClient, stub: _FinancialCloseStub | None) -> None:
    _bar("financial-period-certify   Financial Period Close Authorization Demo")
    print(f"  mode:   {'offline stub' if stub else 'live AtlaSent API'}")
    print(f"  action: period.close.certify")
    print(f"  policy: fail-closed, machine_executable=False, simple_majority, 48h window")

    # 1 ── ALLOW: Q1 close, authorized financial controller ----------------------
    _scenario(
        1,
        "period.close.certify",
        "ALLOWED: Q1 2026 close, authorized financial controller, all fields present",
    )
    try:
        p = client.protect(
            agent="controller:jane",
            action="period.close.certify",
            context={
                "periodId": "2026-Q1",
                "certifiedBy": "controller:jane",
                "financialController": "fc:bob",
                "reconciliationComplete": True,
                "varianceResolved": True,
            },
        )
        _permitted(p)
        _execute("period 2026-Q1 status set to CLOSED in ERP")
        _execute("SOX evidence bundle generated and archived")
        _execute("audit chain sealed for Q1 2026")
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)

    # 2 ── DENY: unauthorized AP clerk ------------------------------------------
    _scenario(
        2,
        "period.close.certify",
        "BLOCKED: AP clerk not authorized — financial controller required",
    )
    try:
        client.protect(
            agent="ap-clerk:dave",
            action="period.close.certify",
            context={
                "periodId": "2026-Q1",
                "certifiedBy": "ap-clerk:dave",
                "financialController": "ap-clerk:dave",  # not on authorized list
            },
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)
        print(f"               evaluation_id: {exc.evaluation_id}")
        _execute("period close NOT executed — financial controller authorization required")

    # 3 ── DENY: missing financialController field ------------------------------
    _scenario(
        3,
        "period.close.certify",
        "BLOCKED: missing financialController field",
    )
    try:
        client.protect(
            agent="controller:jane",
            action="period.close.certify",
            context={
                "periodId": "2026-Q2",
                "certifiedBy": "controller:jane",
                # financialController intentionally omitted
            },
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)
        print(f"               evaluation_id: {exc.evaluation_id}")
        _execute("period close NOT executed — financialController required")

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
        if chain:
            print()
            print(f"  chain length : {len(chain)} events")
            print(f"  head hash    : {chain[-1].audit_hash}")

    _bar()
    print("  Enforcement summary:")
    print("    BLOCKED  2 actions (unauthorized actor / missing financialController)")
    print("    ALLOWED  1 action  (permit-verified before period close execution)")
    print()


def main() -> None:
    api_key = os.environ.get("ATLASENT_API_KEY", "")
    if api_key:
        run(AtlaSentClient(api_key=api_key, base_url=os.environ.get("ATLASENT_API_URL", "https://api.atlasent.io/functions/v1")), stub=None)
    else:
        stub = _FinancialCloseStub()
        run(stub, stub)


if __name__ == "__main__":
    main()
