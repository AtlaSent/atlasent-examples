#!/usr/bin/env python3
"""atlasent-close-pilot: Accounting Close Authorization Demo

Demonstrates non-bypassable authorization for five accounting close
actions using the AtlaSent SDK fail-closed enforcement model.

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

PERIOD = "Q1-2026"
AUTHORIZED_CONTROLLERS: frozenset[str] = frozenset(
    {"alice.chen@acme.com", "bob.smith@acme.com"}
)
AUTHORIZED_SUBMITTERS: frozenset[str] = frozenset(
    {"alice.chen@acme.com", "carol.jones@acme.com"}
)
HIGH_VALUE_THRESHOLD = 100_000  # USD

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
        # atlasent>=2.0 validates key shape (ask_(live|test)_<entropy>) and
        # https-only base_url. The stub overrides _request so neither value
        # is ever used to make a real call — they just need to pass the
        # constructor's input validation.
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
        # V1 EvaluateRequest: { actor_id, action_type, context }
        action = p.get("action_type", "")
        agent = p.get("actor_id", "")
        context = p.get("context", {})
        result = self._decide(action, agent, context)
        # V1 EvaluateResponse fields:
        #   decision:      "allow" | "deny" | "hold" | "escalate"
        #   request_id:    stable ID (present on both CP and SaaS runtimes)
        #   permit_token:  present when decision == "allow"
        #   reasons:       list[str] (replaces old singular "reason")
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
        from _bundle import compute_audit_hash  # single source of truth for chain hash

        permit_token = p.get("permit_token", "")
        stored = self._decisions.get(permit_token, {})
        # V1: check decision == "allow" (not old boolean "permitted")
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
        audit_hash = compute_audit_hash(
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
        ))
        return {"verified": True, "permit_hash": permit_hash, "outcome": "verified", "timestamp": ts}

    def _decide(self, action: str, agent: str, ctx: dict[str, Any]) -> dict[str, Any]:
        """Return a V1-shaped response dict.

        V1 shape:
          { decision: "allow"|"deny",
            request_id: str,        # added by _handle_evaluate
            permit_token: str,      # present when decision == "allow"
            reasons: list[str] }
        """
        def allow(reason: str) -> dict[str, Any]:
            permit_token = f"pt_{uuid.uuid4().hex[:16]}"
            return {
                "decision": "allow",
                "permit_token": permit_token,
                "reasons": [reason],
                "audit_hash": uuid.uuid4().hex[:32],  # internal chain field
            }

        def deny(reason: str, hold_key: str = "") -> dict[str, Any]:
            tag = f" [hold:{hold_key}]" if hold_key else ""
            return {
                "decision": "deny",
                "reasons": [reason + tag],
            }

        if action == "close_task.complete":
            if not ctx.get("task_id"):
                return deny("missing required field: task_id")
            if not ctx.get("completed_by"):
                return deny("missing required field: completed_by")
            if ctx.get("period") != PERIOD:
                return deny(f"period mismatch: expected {PERIOD!r}, got {ctx.get('period')!r}")
            return allow(f"close task {ctx['task_id']} authorized for {PERIOD}")

        if action == "reconciliation.certify":
            if not ctx.get("account_id"):
                return deny("missing required field: account_id")
            certifier = ctx.get("certified_by", "")
            if certifier not in AUTHORIZED_CONTROLLERS:
                return deny(f"'{certifier}' is not on the authorized controller list")
            if ctx.get("dual_approval_required") and not ctx.get("second_approver"):
                return deny("dual approval required but second_approver not provided")
            return allow(f"reconciliation for {ctx['account_id']} certified by {certifier}")

        if action == "journal_entry.approve":
            if not ctx.get("je_id"):
                return deny("missing required field: je_id")
            amount = float(ctx.get("amount", 0))
            hold_key = f"je_cfo:{ctx['je_id']}"
            if amount > HIGH_VALUE_THRESHOLD and hold_key not in self._granted_approvals:
                return deny(
                    f"JE {ctx['je_id']} (${amount:,.0f}) exceeds "
                    f"${HIGH_VALUE_THRESHOLD:,.0f} delegation limit -- CFO approval required",
                    hold_key=hold_key,
                )
            return allow(f"journal entry {ctx['je_id']} approved (${amount:,.0f})")

        if action == "adjustment.submit":
            if not ctx.get("adjustment_id"):
                return deny("missing required field: adjustment_id")
            submitter = ctx.get("submitted_by", "")
            if submitter not in AUTHORIZED_SUBMITTERS:
                return deny(f"'{submitter}' is not authorized to submit period adjustments")
            return allow(f"adjustment {ctx['adjustment_id']} submitted by {submitter}")

        if action == "period.close":
            period = ctx.get("period", "")
            if not period:
                return deny("missing required field: period")
            if not ctx.get("all_tasks_complete"):
                n = ctx.get("incomplete_task_count", "some")
                return deny(f"period {period}: {n} outstanding close tasks remain")
            hold_key = f"period_close_cfo:{period}"
            if not ctx.get("cfo_sign_off") and hold_key not in self._granted_approvals:
                return deny(f"period {period} close requires CFO sign-off", hold_key=hold_key)
            return allow(f"period {period} close authorized -- all conditions satisfied")

        return deny(f"action '{action}' not registered in accounting close policy")


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

# Pre-compiled regex (hoisted out of f-string expressions — backslashes
# inside f-string expression parts are a SyntaxError until Python 3.12,
# and CI runs 3.11).
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
# Helpers to extract V1 fields from a raw evaluate response dict
# (used when calling the stub's _handle_evaluate directly in tests)
# ---------------------------------------------------------------------------

def _decision_from(result: dict[str, Any]) -> str:
    """Extract canonical lowercase decision from a V1 EvaluateResponse dict."""
    return str(result.get("decision", "unknown")).lower()

def _reasons_from(result: dict[str, Any]) -> list[str]:
    """Extract reasons list from a V1 EvaluateResponse dict."""
    return result.get("reasons", [])


# ---------------------------------------------------------------------------
# Simulated accounting system state mutations
# Only reachable after protect() returns a verified Permit.
# ---------------------------------------------------------------------------

def _sys_complete_task(task_id: str, completed_by: str) -> None:
    _execute(f"task {task_id} marked COMPLETE (by {completed_by})")

def _sys_certify_recon(account_id: str, certified_by: str) -> None:
    _execute(f"reconciliation for {account_id} set to CERTIFIED by {certified_by}")

def _sys_approve_je(je_id: str, amount: float) -> None:
    _execute(f"JE {je_id} (${amount:,.0f}) moved to APPROVED state")

def _sys_submit_adj(adj_id: str, submitted_by: str) -> None:
    _execute(f"adjustment {adj_id} submitted by {submitted_by}")

def _sys_close_period(period: str) -> None:
    _execute(f"period {period} set to CLOSED -- no further postings accepted")


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def run(client: AtlaSentClient, stub: _ErpStub | None) -> None:  # noqa: C901
    _bar("atlasent-close-pilot   Accounting Close Authorization Demo")
    print(f"  mode:   {'offline stub' if stub else 'live AtlaSent API'}")
    print(f"  period: {PERIOD}")

    # 1 ── close_task.complete: BLOCKED (missing context) ----------------
    _scenario(1, "close_task.complete", "BLOCKED: missing context fields")
    try:
        client.protect(
            agent="close-automation",
            action="close_task.complete",
            context={"source": "automated-close-bot", "environment": "production"},  # task_id / completed_by / period absent
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)
        print(f"               evaluation_id: {exc.evaluation_id}")
        _execute("task NOT marked complete")

    # 2 ── reconciliation.certify: ALLOWED --------------------------------
    _scenario(2, "reconciliation.certify", "ALLOWED: full context -> verified permit -> audit")
    try:
        p = client.protect(
            agent="alice.chen@acme.com",
            action="reconciliation.certify",
            context={
                "account_id": "CASH-1000",
                "certified_by": "alice.chen@acme.com",
                "period": PERIOD,
                "balance_difference": 0.00,
                "dual_approval_required": False,
                "environment": "production",
            },
        )
        _permit_line(p)
        _sys_certify_recon("CASH-1000", "alice.chen@acme.com")
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)

    # 3 ── journal_entry.approve: HOLD -> CFO approval -> ALLOWED --------
    _scenario(3, "journal_entry.approve", "HOLD: $250k > $100k limit -> CFO approval -> permit")
    je_id, amount = "JE-2026-4821", 250_000.0
    je_ctx = {"je_id": je_id, "amount": amount, "period": PERIOD, "environment": "production"}
    hold_key_3 = ""
    try:
        p = client.protect(agent="controller-bot", action="journal_entry.approve", context=je_ctx)
        _permit_line(p)
        _sys_approve_je(je_id, amount)
    except AtlaSentDeniedError as exc:
        hold_key_3 = _parse_hold_key(exc.reason)
        _hold(exc.reason, hold_key_3) if hold_key_3 else _blocked(exc.reason)

    if hold_key_3 and stub:
        print()
        print("  [human] CFO reviews in AtlaSent console and approves")
        stub.grant_approval(hold_key_3)
        print()
        try:
            p = client.protect(agent="controller-bot", action="journal_entry.approve", context=je_ctx)
            _permit_line(p)
            _sys_approve_je(je_id, amount)
        except AtlaSentDeniedError as exc:
            _blocked(exc.reason)

    # 4 ── adjustment.submit: BLOCKED (unauthorized submitter) -----------
    _scenario(4, "adjustment.submit", "BLOCKED: dave.ops not on authorized submitter list")
    try:
        client.protect(
            agent="dave.ops@acme.com",
            action="adjustment.submit",
            context={"adjustment_id": "ADJ-2026-009", "submitted_by": "dave.ops@acme.com",
                     "period": PERIOD, "amount": 1_500.0, "environment": "production"},
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)
        _execute("adjustment NOT submitted")

    # 4b ── adjustment.submit: ALLOWED (authorized submitter) ------------
    _scenario("4b", "adjustment.submit", "ALLOWED: carol.jones is on authorized submitter list")
    try:
        p = client.protect(
            agent="carol.jones@acme.com",
            action="adjustment.submit",
            context={"adjustment_id": "ADJ-2026-009", "submitted_by": "carol.jones@acme.com",
                     "period": PERIOD, "amount": 1_500.0, "environment": "production"},
        )
        _permit_line(p)
        _sys_submit_adj("ADJ-2026-009", "carol.jones@acme.com")
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)

    # 5 ── period.close: BLOCKED (outstanding tasks) ---------------------
    _scenario(5, "period.close", "BLOCKED: 3 outstanding close tasks remain")
    try:
        client.protect(
            agent="cfo-bot",
            action="period.close",
            context={"period": PERIOD, "all_tasks_complete": False, "incomplete_task_count": 3,
                     "environment": "production"},
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)
        _execute("period NOT closed")

    # 5b ── period.close: HOLD -> CFO sign-off -> ALLOWED ----------------
    _scenario("5b", "period.close", "HOLD: tasks done, missing CFO sign-off -> approval -> permit")
    period_ctx = {"period": PERIOD, "all_tasks_complete": True, "environment": "production"}
    hold_key_5 = ""
    try:
        p = client.protect(agent="cfo-bot", action="period.close", context=period_ctx)
        _permit_line(p)
        _sys_close_period(PERIOD)
    except AtlaSentDeniedError as exc:
        hold_key_5 = _parse_hold_key(exc.reason)
        _hold(exc.reason, hold_key_5) if hold_key_5 else _blocked(exc.reason)

    if hold_key_5 and stub:
        print()
        print("  [human] CFO signs off in AtlaSent console")
        stub.grant_approval(hold_key_5)
        print()
        try:
            p = client.protect(agent="cfo-bot", action="period.close", context=period_ctx)
            _permit_line(p)
            _sys_close_period(PERIOD)
        except AtlaSentDeniedError as exc:
            _blocked(exc.reason)

    # 6 ── reconciliation.certify: BLOCKED (dual approval, missing second_approver) --
    _scenario(6, "reconciliation.certify",
              "BLOCKED: dual_approval_required=True but second_approver not provided")
    try:
        client.protect(
            agent="alice.chen@acme.com",
            action="reconciliation.certify",
            context={
                "account_id": "AR-3000",
                "certified_by": "alice.chen@acme.com",
                "period": PERIOD,
                "balance_difference": 0.00,
                "dual_approval_required": True,
                "environment": "production",
                # second_approver intentionally omitted
            },
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)
        _execute("reconciliation NOT certified")

    # 6b ── reconciliation.certify: ALLOWED (dual approval satisfied) ----
    _scenario("6b", "reconciliation.certify",
              "ALLOWED: dual_approval_required=True with second_approver provided")
    try:
        p = client.protect(
            agent="alice.chen@acme.com",
            action="reconciliation.certify",
            context={
                "account_id": "AR-3000",
                "certified_by": "alice.chen@acme.com",
                "period": PERIOD,
                "balance_difference": 0.00,
                "dual_approval_required": True,
                "second_approver": "bob.smith@acme.com",
                "environment": "production",
            },
        )
        _permit_line(p)
        _sys_certify_recon("AR-3000", "alice.chen@acme.com")
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)

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
        if chain:
            print()
            print(f"  chain length : {len(chain)} events")
            print(f"  head hash    : {chain[-1].audit_hash}")

    _bar()
    print(f"  Enforcement summary:")
    print(f"    BLOCKED  3 actions (missing context / unauthorized actor / missing dual approver)")
    print(f"    HOLD     2 actions (CFO approval required)")
    print(f"    ALLOWED  4 actions (permit-verified before execution)")
    print()


def _export_bundle(stub: "_ErpStub", path: str) -> None:
    """Dump the in-memory audit chain as a signed evidence bundle.

    Imported lazily so the demo's hot path doesn't pay for ``cryptography``
    unless the operator actually asks for an export.
    """
    from _bundle import events_from_audit_records, make_bundle, write_bundle

    chain = stub.audit_chain
    if not chain:
        print(f"[export] no permitted events to export — bundle not written")
        return
    events = events_from_audit_records(chain)
    timestamps = [e["timestamp"] for e in events if e.get("timestamp")]
    period_from = min(timestamps) if timestamps else ""
    period_to = max(timestamps) if timestamps else ""
    bundle = make_bundle(
        events, period_from=period_from, period_to=period_to, demo=True
    )
    write_bundle(bundle, path)
    print(
        f"\n[export] wrote signed bundle: {path}  "
        f"({len(events)} events, head={bundle['head_hash']})"
    )
    print(
        "[export] verify offline with: "
        f"python verify-audit.py --bundle {path}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Accounting close authorization demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--export",
        metavar="PATH",
        default=None,
        help="After scenarios run, write a signed audit-evidence bundle to PATH.",
    )
    args = parser.parse_args()

    api_key = os.environ.get("ATLASENT_API_KEY", "")
    if api_key:
        if args.export:
            print(
                "[warn] --export is only supported with the offline stub; "
                "live-API export uses /v1/audit/exports (see verify-audit.py).",
            )
        run(AtlaSentClient(api_key=api_key, base_url=os.environ.get("ATLASENT_API_URL", "https://api.atlasent.io/functions/v1")), stub=None)
    else:
        stub = _ErpStub()
        run(stub, stub)
        if args.export:
            _export_bundle(stub, args.export)


if __name__ == "__main__":
    main()
