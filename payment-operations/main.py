#!/usr/bin/env python3
"""payment-operations: Payment Operations Lifecycle Authorization Demo

Demonstrates non-bypassable authorization for the full payment lifecycle state
machine using the AtlaSent SDK fail-closed enforcement model.

Action types:
  payment.approval.approve      — AP manager approves an invoice payment
  payment.approval.deny         — AP manager denies a payment
  payment.execute.approved      — Treasury executes an approved payment
  payment.execute.held          — Payment held by fraud/compliance system
  payment.execute.policy_error  — Execution blocked by policy violation
  qb.transaction.approve        — QuickBooks transaction approval

Three flows:
  1. Full approved → executed flow
  2. Approved → held for fraud review
  3. policy_error on execution attempt

Note: This example mirrors a production ledger implementation
where these actions are already in production use.

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

AP_MANAGERS: frozenset[str] = frozenset(
    {"ap.mgr@acme.example", "ap.director@acme.example"}
)
TREASURY_STAFF: frozenset[str] = frozenset(
    {"treasury.ops@acme.example", "treasury.mgr@acme.example"}
)
FRAUD_SYSTEM = "fraud-compliance-system"

HIGH_VALUE_THRESHOLD = 50_000  # USD
CFO_THRESHOLD = 250_000  # USD

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


class _PaymentStub(AtlaSentClient):
    """In-process stub — no HTTP calls, deterministic payment lifecycle policy.

    Implements policies for all six payment operations action types.
    """

    def __init__(self) -> None:
        super().__init__(
            "ask_test_demostubdemostubdemostubdemo00",
            base_url="https://stub.local",
        )
        self._decisions: dict[str, dict[str, Any]] = {}
        self._audit_chain: list[AuditRecord] = []
        self._approved_payments: set[str] = set()

    def mark_approved(self, payment_id: str) -> None:
        self._approved_payments.add(payment_id)

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
        """Return a V1-shaped response dict for payment operations policy."""

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

        # -- payment.approval.approve -----------------------------------------
        if action == "payment.approval.approve":
            payment_id = ctx.get("paymentId", "")
            amount = float(ctx.get("amount", 0))
            approved_by = ctx.get("approvedBy", "")
            invoice_id = ctx.get("invoiceId", "")
            vendor_id = ctx.get("vendorId", "")

            if not payment_id:
                return deny("missing required field: paymentId")
            if not approved_by:
                return deny("missing required field: approvedBy")
            if approved_by not in AP_MANAGERS:
                return deny(
                    f"DENY_AUTHORITY: '{approved_by}' does not have ap_manager role "
                    f"required to approve payments"
                )
            if not invoice_id:
                return deny("missing required field: invoiceId")
            if not vendor_id:
                return deny("missing required field: vendorId")
            if amount > CFO_THRESHOLD:
                return deny(
                    f"DENY_EXCEEDS_LIMIT: payment {payment_id} (${amount:,.0f}) exceeds "
                    f"${CFO_THRESHOLD:,.0f} AP manager limit — CFO approval required"
                )
            return allow(
                f"payment {payment_id} (${amount:,.0f}) approved by {approved_by} "
                f"for invoice {invoice_id}"
            )

        # -- payment.approval.deny --------------------------------------------
        if action == "payment.approval.deny":
            payment_id = ctx.get("paymentId", "")
            denied_by = ctx.get("deniedBy", "")
            reason_str = ctx.get("reason", "")

            if not payment_id:
                return deny("missing required field: paymentId")
            if not denied_by:
                return deny("missing required field: deniedBy")
            if denied_by not in AP_MANAGERS:
                return deny(
                    f"DENY_AUTHORITY: '{denied_by}' does not have ap_manager role"
                )
            if not reason_str:
                return deny("missing required field: reason")
            return allow(
                f"payment {payment_id} denied by {denied_by}: {reason_str[:60]}"
            )

        # -- payment.execute.approved -----------------------------------------
        if action == "payment.execute.approved":
            payment_id = ctx.get("paymentId", "")
            executed_by = ctx.get("executedBy", "")
            bank_reference = ctx.get("bankReference", "")

            if not payment_id:
                return deny("missing required field: paymentId")
            if not executed_by:
                return deny("missing required field: executedBy")
            if executed_by not in TREASURY_STAFF:
                return deny(
                    f"DENY_AUTHORITY: '{executed_by}' does not have treasury role "
                    f"required to execute payments"
                )
            if payment_id not in self._approved_payments:
                return deny(
                    f"DENY_NOT_APPROVED: payment {payment_id} has not been approved — "
                    f"payment.approval.approve must precede execution"
                )
            if not bank_reference:
                return deny("missing required field: bankReference")
            return allow(
                f"payment {payment_id} executed by {executed_by} "
                f"(bank_ref={bank_reference})"
            )

        # -- payment.execute.held ---------------------------------------------
        if action == "payment.execute.held":
            payment_id = ctx.get("paymentId", "")
            held_by = ctx.get("heldBy", "")
            hold_reason = ctx.get("holdReason", "")

            if not payment_id:
                return deny("missing required field: paymentId")
            if not held_by:
                return deny("missing required field: heldBy")
            if not hold_reason:
                return deny("missing required field: holdReason")
            return allow(
                f"payment {payment_id} placed on HOLD by {held_by}: {hold_reason[:60]}"
            )

        # -- payment.execute.policy_error -------------------------------------
        if action == "payment.execute.policy_error":
            payment_id = ctx.get("paymentId", "")
            policy_rule = ctx.get("policyRule", "")
            error_code = ctx.get("errorCode", "")

            if not payment_id:
                return deny("missing required field: paymentId")
            # policy_error is a terminal state — always deny execution
            return deny(
                f"DENY_POLICY_VIOLATION: payment {payment_id} blocked by policy rule "
                f"'{policy_rule}' (errorCode={error_code}) — execution not permitted"
            )

        # -- qb.transaction.approve -------------------------------------------
        if action == "qb.transaction.approve":
            transaction_id = ctx.get("transactionId", "")
            amount = float(ctx.get("amount", 0))
            account_code = ctx.get("accountCode", "")
            approved_by = ctx.get("approvedBy", "")

            if not transaction_id:
                return deny("missing required field: transactionId")
            if not approved_by:
                return deny("missing required field: approvedBy")
            if approved_by not in AP_MANAGERS:
                return deny(
                    f"DENY_AUTHORITY: '{approved_by}' does not have ap_manager role "
                    f"required to approve QuickBooks transactions"
                )
            if not account_code:
                return deny("missing required field: accountCode")
            return allow(
                f"QB transaction {transaction_id} (${amount:,.0f}) approved by "
                f"{approved_by} → account {account_code}"
            )

        return deny(f"action '{action}' not registered in payment-operations policy")


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


def _execute(msg: str) -> None:
    print(f"               → {msg}")


# ---------------------------------------------------------------------------
# Simulated payment system state mutations
# Only reachable after protect() returns a verified Permit.
# ---------------------------------------------------------------------------


def _sys_approve_payment(payment_id: str, amount: float, invoice_id: str) -> None:
    _execute(f"payment {payment_id} (${amount:,.0f}) status → APPROVED (invoice={invoice_id})")


def _sys_deny_payment(payment_id: str, reason: str) -> None:
    _execute(f"payment {payment_id} status → DENIED: {reason[:60]}")


def _sys_execute_payment(payment_id: str, bank_ref: str) -> None:
    _execute(f"payment {payment_id} status → EXECUTED (bank_ref={bank_ref})")
    _execute("wire transfer initiated in banking system")


def _sys_hold_payment(payment_id: str, hold_reason: str) -> None:
    _execute(f"payment {payment_id} status → HELD: {hold_reason[:60]}")
    _execute("compliance review ticket created, payment escalated")


def _sys_approve_qb(transaction_id: str, amount: float, account: str) -> None:
    _execute(f"QB transaction {transaction_id} (${amount:,.0f}) → APPROVED → {account}")


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------


def run(client: AtlaSentClient, stub: _PaymentStub | None) -> None:  # noqa: C901
    _bar("payment-operations   Payment Lifecycle Authorization Demo")
    print(f"  mode:   {'offline stub' if stub else 'live AtlaSent API'}")
    print(
        "  Note: mirrors a production ledger implementation "
        "(production use)"
    )

    # =========================================================================
    # Flow 1: Full approved → executed flow
    # =========================================================================
    _bar("Flow 1 — Full approved → executed payment flow")
    payment_id_1 = "PMT-2026-00881"

    _scenario(
        "1a",
        "payment.approval.approve",
        "ALLOWED: AP manager approves invoice payment",
    )
    try:
        p = client.protect(
            agent="ap.mgr@acme.example",
            action="payment.approval.approve",
            context={
                "paymentId": payment_id_1,
                "amount": 18_750.00,
                "approvedBy": "ap.mgr@acme.example",
                "invoiceId": "INV-2026-4420",
                "vendorId": "VND-00142",
            },
        )
        _permit_line(p)
        _sys_approve_payment(payment_id_1, 18_750.00, "INV-2026-4420")
        if stub:
            stub.mark_approved(payment_id_1)
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)

    _scenario(
        "1b",
        "qb.transaction.approve",
        "ALLOWED: AP manager approves corresponding QB transaction",
    )
    try:
        p = client.protect(
            agent="ap.mgr@acme.example",
            action="qb.transaction.approve",
            context={
                "transactionId": "QB-2026-99104",
                "amount": 18_750.00,
                "accountCode": "2000-ACCOUNTS-PAYABLE",
                "approvedBy": "ap.mgr@acme.example",
            },
        )
        _permit_line(p)
        _sys_approve_qb("QB-2026-99104", 18_750.00, "2000-ACCOUNTS-PAYABLE")
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)

    _scenario(
        "1c",
        "payment.execute.approved",
        "ALLOWED: treasury executes the approved payment",
    )
    try:
        p = client.protect(
            agent="treasury.ops@acme.example",
            action="payment.execute.approved",
            context={
                "paymentId": payment_id_1,
                "executedBy": "treasury.ops@acme.example",
                "bankReference": "WIRE-20260529-00142",
            },
        )
        _permit_line(p)
        _sys_execute_payment(payment_id_1, "WIRE-20260529-00142")
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)

    # =========================================================================
    # Flow 2: Approved → held for fraud review
    # =========================================================================
    _bar("Flow 2 — Approved → held for fraud review")
    payment_id_2 = "PMT-2026-00882"

    _scenario(
        "2a",
        "payment.approval.approve",
        "ALLOWED: AP manager approves payment (later flagged by fraud system)",
    )
    try:
        p = client.protect(
            agent="ap.mgr@acme.example",
            action="payment.approval.approve",
            context={
                "paymentId": payment_id_2,
                "amount": 47_200.00,
                "approvedBy": "ap.mgr@acme.example",
                "invoiceId": "INV-2026-4421",
                "vendorId": "VND-00889",
            },
        )
        _permit_line(p)
        _sys_approve_payment(payment_id_2, 47_200.00, "INV-2026-4421")
        if stub:
            stub.mark_approved(payment_id_2)
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)

    _scenario(
        "2b",
        "payment.execute.held",
        "ALLOWED: fraud system places payment on hold for compliance review",
    )
    try:
        p = client.protect(
            agent=FRAUD_SYSTEM,
            action="payment.execute.held",
            context={
                "paymentId": payment_id_2,
                "heldBy": FRAUD_SYSTEM,
                "holdReason": "vendor VND-00889 added to watchlist 2026-05-28",
            },
        )
        _permit_line(p)
        _sys_hold_payment(payment_id_2, "vendor VND-00889 added to watchlist 2026-05-28")
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)

    # =========================================================================
    # Flow 3: policy_error on execution attempt
    # =========================================================================
    _bar("Flow 3 — policy_error blocks execution attempt")
    payment_id_3 = "PMT-2026-00883"

    _scenario(
        3,
        "payment.execute.policy_error",
        "BLOCKED: execution blocked by policy violation (policy_error is terminal)",
    )
    try:
        client.protect(
            agent="treasury.ops@acme.example",
            action="payment.execute.policy_error",
            context={
                "paymentId": payment_id_3,
                "policyRule": "DUPLICATE_PAYMENT_DETECTED",
                "errorCode": "ERR-PAY-4001",
            },
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)
        print(f"               evaluation_id: {exc.evaluation_id}")
        _execute("payment NOT executed — policy_error is a terminal blocking state")

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
    print("    BLOCKED  1 action  (policy_error terminal state)")
    print("    ALLOWED  5 actions (permit-verified before each state transition)")
    print()


def main() -> None:
    api_key = os.environ.get("ATLASENT_API_KEY", "")
    if api_key:
        run(AtlaSentClient(api_key=api_key, base_url=os.environ.get("ATLASENT_API_URL", "https://api.atlasent.io/functions/v1")), stub=None)
    else:
        stub = _PaymentStub()
        run(stub, stub)


if __name__ == "__main__":
    main()
