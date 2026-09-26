#!/usr/bin/env python3
"""vendor-payment-release: Vendor Payment Release Authorization Quickstart

Demonstrates non-bypassable authorization for AP payment release workflows
using the AtlaSent SDK fail-closed enforcement model.

3 scenarios:
  1. Auto-approve  — payment below $50k, authorized submitter  → ALLOW
  2. Dual-approval hold — payment $50k–$250k, no second approver → HOLD_DUAL_APPROVAL
  3. Deny unauthorized — submitter not in ap-certifiers list     → DENY_AUTHORITY

Runs offline (in-process stub) by default.
Set ATLASENT_API_KEY to switch to the live AtlaSent API.
"""
from __future__ import annotations

import argparse
import hashlib
import json
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

AP_CERTIFIERS: frozenset[str] = frozenset(
    {"ap.alice@acme.com", "ap.bob@acme.com", "ap.carol@acme.com"}
)
DUAL_APPROVAL_THRESHOLD = 50_000    # USD — payments above this require dual approval
CFO_APPROVAL_THRESHOLD  = 250_000   # USD — payments above this require CFO role approval

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


class _ErpStub(AtlaSentClient):
    """In-process stub — no HTTP calls, deterministic policy engine.

    Overrides ``_request`` to handle evaluate / verify locally.
    Use :meth:`grant_approval` to simulate console approval of a hold.
    """

    def __init__(self) -> None:
        super().__init__(
            "ask_test_demostubdemostubdemostubdemo00",
            base_url="https://stub.local",
        )
        self._granted_approvals: set[str] = set()
        self._decisions: dict[str, dict[str, Any]] = {}
        self._audit_chain: list[AuditRecord] = []

    def grant_approval(self, key: str) -> None:
        self._granted_approvals.add(key)
        print(f"  [console] approval granted: {key}")

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
        meta  = stored.get("_meta", {})
        prev  = self._audit_chain[-1].audit_hash if self._audit_chain else ""
        event_id = f"evt_{uuid.uuid4().hex[:12]}"
        actor  = meta.get("actor_id", "")
        action = meta.get("action_type", "")
        reasons = stored.get("reasons", [])
        reason  = reasons[0] if reasons else ""
        context = meta.get("context", {})
        audit_hash = _compute_audit_hash(
            event_id=event_id,
            timestamp=ts,
            actor=actor,
            action=action,
            decision="allow",
            permit_id=permit_token,
            reason=reason,
            context_snapshot=context,
            previous_hash=prev,
        )
        permit_hash = hashlib.sha256(permit_token.encode()).hexdigest()[:32]
        self._audit_chain.append(AuditRecord(
            event_id=event_id, timestamp=ts, actor=actor, action=action,
            decision="allow", permit_id=permit_token, audit_hash=audit_hash,
            previous_hash=prev, reason=reason, context_snapshot=context,
        ))
        return {"verified": True, "permit_hash": permit_hash, "outcome": "verified", "timestamp": ts}

    def _decide(self, action: str, agent: str, ctx: dict[str, Any]) -> dict[str, Any]:
        def allow(reason: str) -> dict[str, Any]:
            token = f"pt_{uuid.uuid4().hex[:16]}"
            return {"decision": "allow", "permit_token": token,
                    "reasons": [reason], "audit_hash": uuid.uuid4().hex[:32]}

        def deny(reason: str, hold_key: str = "") -> dict[str, Any]:
            tag = f" [hold:{hold_key}]" if hold_key else ""
            return {"decision": "deny", "reasons": [reason + tag]}

        if action != "vendor.payment.release":
            return deny(f"action '{action}' not registered in vendor payment policy")

        authorized_by = ctx.get("authorizedBy", "")
        if authorized_by not in AP_CERTIFIERS:
            return deny(
                f"DENY_AUTHORITY: '{authorized_by}' is not in the ap-certifiers group"
            )

        amount = float(ctx.get("amount", 0))
        vendor_id = ctx.get("vendorId", "UNKNOWN")
        po = ctx.get("purchaseOrder", "")
        hold_key = f"payment_dual:{vendor_id}:{po}"

        if amount > CFO_APPROVAL_THRESHOLD:
            if hold_key not in self._granted_approvals:
                return deny(
                    f"HOLD_CFO_APPROVAL: payment of ${amount:,.0f} to {vendor_id} "
                    f"exceeds ${CFO_APPROVAL_THRESHOLD:,.0f} — CFO approval required",
                    hold_key=hold_key,
                )

        if amount > DUAL_APPROVAL_THRESHOLD:
            second = ctx.get("secondApprover", "")
            if not second and hold_key not in self._granted_approvals:
                return deny(
                    f"HOLD_DUAL_APPROVAL: payment of ${amount:,.0f} to {vendor_id} "
                    f"exceeds ${DUAL_APPROVAL_THRESHOLD:,.0f} — second approver required",
                    hold_key=hold_key,
                )

        return allow(
            f"payment of ${amount:,.0f} {ctx.get('currency','USD')} to {vendor_id} "
            f"authorized by {authorized_by}"
        )


# ---------------------------------------------------------------------------
# Minimal offline audit-hash (mirrors accounting-close/_bundle.py logic)
# ---------------------------------------------------------------------------

def _compute_audit_hash(**kwargs: Any) -> str:
    canonical = json.dumps(kwargs, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:32]


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
    print(f"\n▸ Scenario {num} — vendor.payment.release")
    print(f"  {note}")

_HOLD_TAG_RE = re.compile(r"\s*\[hold:[^\]]+\]")

def _blocked(reason: str) -> None:
    print(f"  ✗ BLOCKED    {_HOLD_TAG_RE.sub('', reason)}")

def _hold(reason: str, hold_key: str) -> None:
    print(f"  ⏸ HOLD       {_HOLD_TAG_RE.sub('', reason)}")
    print(f"               hold_key: {hold_key}")

def _permit_line(p: Permit) -> None:
    print(f"  ✔ PERMITTED  {p.reason}")
    print(f"               permit_id:   {p.permit_id}")
    print(f"               audit_hash:  {p.audit_hash}")
    print(f"               permit_hash: {p.permit_hash}")

def _execute(msg: str) -> None:
    print(f"               → {msg}")

def _parse_hold_key(reason: str) -> str:
    m = re.search(r"\[hold:([^\]]+)\]", reason)
    return m.group(1) if m else ""


# ---------------------------------------------------------------------------
# Simulated ERP state mutations
# ---------------------------------------------------------------------------

def _sys_release_payment(vendor_id: str, amount: float, currency: str) -> None:
    _execute(f"payment of {currency} {amount:,.0f} to {vendor_id} queued for release")


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def run(client: AtlaSentClient, stub: _ErpStub | None) -> None:
    _bar("vendor-payment-release   Vendor Payment Release Authorization Quickstart")
    print(f"  mode:   {'offline stub' if stub else 'live AtlaSent API'}")

    # 1 ── Auto-approve: below $50k, authorized submitter → ALLOW -----------
    _scenario(1, "ALLOW: $12,500 below dual-approval threshold, authorized AP certifier")
    try:
        p = client.protect(
            agent="ap.alice@acme.com",
            action="vendor.payment.release",
            context={
                "amount": 12_500.00,
                "currency": "USD",
                "vendorId": "VENDOR-0042",
                "authorizedBy": "ap.alice@acme.com",
                "purchaseOrder": "PO-2026-1234",
                "threeWayMatch": True,
                "ledgerAccount": "AP-TRADE",
            },
        )
        _permit_line(p)
        _sys_release_payment("VENDOR-0042", 12_500.00, "USD")
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)

    # 2 ── Dual-approval hold: $75k, no second approver → HOLD_DUAL_APPROVAL
    _scenario(2, "HOLD_DUAL_APPROVAL: $75,000 exceeds $50k threshold, no second approver")
    payment_ctx = {
        "amount": 75_000.00,
        "currency": "USD",
        "vendorId": "VENDOR-0099",
        "authorizedBy": "ap.bob@acme.com",
        "purchaseOrder": "PO-2026-5678",
        "threeWayMatch": True,
        "ledgerAccount": "AP-TRADE",
        # secondApprover intentionally omitted
    }
    hold_key_2 = ""
    try:
        p = client.protect(agent="ap.bob@acme.com", action="vendor.payment.release", context=payment_ctx)
        _permit_line(p)
        _sys_release_payment("VENDOR-0099", 75_000.00, "USD")
    except AtlaSentDeniedError as exc:
        hold_key_2 = _parse_hold_key(exc.reason)
        _hold(exc.reason, hold_key_2) if hold_key_2 else _blocked(exc.reason)

    if hold_key_2 and stub:
        print()
        print("  [human] AP manager reviews and provides second approval in AtlaSent console")
        stub.grant_approval(hold_key_2)
        print()
        try:
            p = client.protect(
                agent="ap.bob@acme.com",
                action="vendor.payment.release",
                context={**payment_ctx, "secondApprover": "ap.carol@acme.com"},
            )
            _permit_line(p)
            _sys_release_payment("VENDOR-0099", 75_000.00, "USD")
        except AtlaSentDeniedError as exc:
            _blocked(exc.reason)

    # 3 ── Deny unauthorized: submitter not in ap-certifiers → DENY_AUTHORITY
    _scenario(3, "DENY_AUTHORITY: submitter not in authorized ap-certifiers group")
    try:
        client.protect(
            agent="contractor.x@external.com",
            action="vendor.payment.release",
            context={
                "amount": 5_000.00,
                "currency": "USD",
                "vendorId": "VENDOR-0010",
                "authorizedBy": "contractor.x@external.com",
                "purchaseOrder": "PO-2026-0001",
                "threeWayMatch": False,
                "ledgerAccount": "AP-TRADE",
            },
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)
        print(f"               evaluation_id: {exc.evaluation_id}")
        _execute("payment NOT released")

    # ── Audit trail -------------------------------------------------------
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

    _bar()
    print(f"  Enforcement summary:")
    print(f"    ALLOWED  1 action  (auto-approved below threshold)")
    print(f"    HOLD     1 action  (dual-approval required for $50k+)")
    print(f"    BLOCKED  1 action  (unauthorized submitter)")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Vendor payment release authorization quickstart")
    args = parser.parse_args()

    api_key = os.environ.get("ATLASENT_API_KEY", "")
    if api_key:
        run(AtlaSentClient(api_key=api_key, base_url=os.environ.get("ATLASENT_API_URL", "https://api.atlasent.io/functions/v1")), stub=None)
    else:
        stub = _ErpStub()
        run(stub, stub)


if __name__ == "__main__":
    main()
