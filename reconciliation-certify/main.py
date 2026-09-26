#!/usr/bin/env python3
"""reconciliation-certify: Reconciliation Certify Authorization Quickstart

Targeted extract of the reconciliation.certify scenarios from
atlasent-examples/accounting-close/main.py. Self-contained — no imports
from accounting-close.

3 scenarios:
  1. ALLOW           — authorized certifier, reconciliation complete, no dual-approval required
  2. HOLD_SECOND     — authorized certifier but balance difference exceeds dual-approval threshold
  3. DENY_CERTIFIER  — certifier not in authorized-certifiers group

Action string: reconciliation.certify

Runs offline (in-process stub) by default.
Set ATLASENT_API_KEY to switch to the live AtlaSent API.
"""
from __future__ import annotations

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

AUTHORIZED_CERTIFIERS: frozenset[str] = frozenset(
    {"alice.chen@acme.com", "bob.smith@acme.com"}
)
DUAL_APPROVAL_THRESHOLD = 10_000  # USD balance difference

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


class _CloseStub(AtlaSentClient):
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
        action  = p.get("action_type", "")
        agent   = p.get("actor_id", "")
        context = p.get("context", {})
        result  = self._decide(action, agent, context)
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
        stored  = self._decisions.get(permit_token, {})
        allowed = str(stored.get("decision", "")).lower() == "allow"
        ts = datetime.now(timezone.utc).isoformat()
        if not allowed:
            return {"verified": False, "permit_hash": "", "outcome": "invalid", "timestamp": ts}
        meta   = stored.get("_meta", {})
        prev   = self._audit_chain[-1].audit_hash if self._audit_chain else ""
        event_id = f"evt_{uuid.uuid4().hex[:12]}"
        actor  = meta.get("actor_id", "")
        action = meta.get("action_type", "")
        reasons = stored.get("reasons", [])
        reason  = reasons[0] if reasons else ""
        context = meta.get("context", {})
        canonical = json.dumps(
            dict(event_id=event_id, timestamp=ts, actor=actor, action=action,
                 decision="allow", permit_id=permit_token, reason=reason,
                 context_snapshot=context, previous_hash=prev),
            sort_keys=True, separators=(",", ":"),
        )
        audit_hash = hashlib.sha256(canonical.encode()).hexdigest()[:32]
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

        if action != "reconciliation.certify":
            return deny(f"action '{action}' not registered in reconciliation certify policy")

        certifier = ctx.get("certifiedBy", "")
        if certifier not in AUTHORIZED_CERTIFIERS:
            return deny(f"DENY_CERTIFIER_NOT_AUTHORIZED: '{certifier}' is not in the authorized-certifiers group")

        account_id = ctx.get("accountId", "")
        if not account_id:
            return deny("missing required field: accountId")

        balance_diff = float(ctx.get("balanceDifference", 0))
        dual_required = ctx.get("dualApprovalRequired", balance_diff > DUAL_APPROVAL_THRESHOLD)
        hold_key = f"recon_dual:{account_id}:{ctx.get('period', '')}"

        if dual_required:
            second = ctx.get("secondApprover", "")
            if not second and hold_key not in self._granted_approvals:
                return deny(
                    f"HOLD_SECOND_APPROVER: reconciliation for {account_id} has "
                    f"balance difference of ${balance_diff:,.2f} (>${DUAL_APPROVAL_THRESHOLD:,}) "
                    "— second approver required",
                    hold_key=hold_key,
                )

        period = ctx.get("period", "")
        return allow(
            f"reconciliation for {account_id} ({period}) certified by {certifier}"
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
    print(f"\n▸ Scenario {num} — reconciliation.certify")
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
# Simulated close system mutations
# ---------------------------------------------------------------------------

def _sys_certify_recon(account_id: str, certified_by: str, period: str) -> None:
    _execute(f"reconciliation for {account_id} ({period}) set to CERTIFIED by {certified_by}")


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def run(client: AtlaSentClient, stub: _CloseStub | None) -> None:
    _bar("reconciliation-certify   Reconciliation Certify Authorization Quickstart")
    print(f"  mode:   {'offline stub' if stub else 'live AtlaSent API'}")

    # 1 ── ALLOW: authorized certifier, no dual-approval required ----------
    _scenario(1, "ALLOW: authorized certifier, balance in tolerance, no dual-approval")
    try:
        p = client.protect(
            agent="alice.chen@acme.com",
            action="reconciliation.certify",
            context={
                "accountId": "CASH-1000",
                "period": "Q1-2026",
                "certifiedBy": "alice.chen@acme.com",
                "balanceDifference": 0.00,
                "dualApprovalRequired": False,
                "supportingEvidenceUri": "s3://close-evidence/CASH-1000-Q1-2026.pdf",
            },
        )
        _permit_line(p)
        _sys_certify_recon("CASH-1000", "alice.chen@acme.com", "Q1-2026")
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)

    # 2 ── HOLD_SECOND_APPROVER: authorized but balance > $10k threshold ---
    _scenario(2, "HOLD_SECOND_APPROVER: balance difference $15,000 > $10,000 threshold")
    recon_ctx = {
        "accountId": "AR-3000",
        "period": "Q1-2026",
        "certifiedBy": "alice.chen@acme.com",
        "balanceDifference": 15_000.00,
        "dualApprovalRequired": True,
        "supportingEvidenceUri": "s3://close-evidence/AR-3000-Q1-2026.pdf",
        # secondApprover intentionally omitted
    }
    hold_key_2 = ""
    try:
        p = client.protect(agent="alice.chen@acme.com", action="reconciliation.certify", context=recon_ctx)
        _permit_line(p)
        _sys_certify_recon("AR-3000", "alice.chen@acme.com", "Q1-2026")
    except AtlaSentDeniedError as exc:
        hold_key_2 = _parse_hold_key(exc.reason)
        _hold(exc.reason, hold_key_2) if hold_key_2 else _blocked(exc.reason)

    if hold_key_2 and stub:
        print()
        print("  [human] controller reviews in AtlaSent console and provides second approval")
        stub.grant_approval(hold_key_2)
        print()
        try:
            p = client.protect(
                agent="alice.chen@acme.com",
                action="reconciliation.certify",
                context={**recon_ctx, "secondApprover": "bob.smith@acme.com"},
            )
            _permit_line(p)
            _sys_certify_recon("AR-3000", "alice.chen@acme.com", "Q1-2026")
        except AtlaSentDeniedError as exc:
            _blocked(exc.reason)

    # 3 ── DENY_CERTIFIER_NOT_AUTHORIZED: not in authorized-certifiers -----
    _scenario(3, "DENY_CERTIFIER_NOT_AUTHORIZED: certifier not in authorized-certifiers group")
    try:
        client.protect(
            agent="temp.worker@contractor.com",
            action="reconciliation.certify",
            context={
                "accountId": "CASH-2000",
                "period": "Q1-2026",
                "certifiedBy": "temp.worker@contractor.com",
                "balanceDifference": 0.00,
                "dualApprovalRequired": False,
                "supportingEvidenceUri": "s3://close-evidence/CASH-2000-Q1-2026.pdf",
            },
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)
        print(f"               evaluation_id: {exc.evaluation_id}")
        _execute("reconciliation NOT certified")

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
    print(f"    ALLOWED  2 actions (direct allow + hold-then-approve)")
    print(f"    HOLD     1 action  (dual-approval required for $10k+ balance difference)")
    print(f"    BLOCKED  1 action  (certifier not in authorized-certifiers)")
    print()


def main() -> None:
    api_key = os.environ.get("ATLASENT_API_KEY", "")
    if api_key:
        run(AtlaSentClient(api_key=api_key, base_url=os.environ.get("ATLASENT_API_URL", "https://api.atlasent.io/functions/v1")), stub=None)
    else:
        stub = _CloseStub()
        run(stub, stub)


if __name__ == "__main__":
    main()
