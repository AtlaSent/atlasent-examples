#!/usr/bin/env python3
"""contract-execution: Contract Execution and Amendment Authorization Demo

Demonstrates non-bypassable authorization for contract execution and amendment
using the AtlaSent SDK fail-closed enforcement model.

Three scenarios:
  1. ALLOW  — execute with full legal approval (legal + CFO sign-off present)
  2. DENY   — execute without CFO sign-off (high-value contract, CFO required)
  3. ALLOW  — amend material term (legal sign-off present, escalation note recorded)

Action types:
  contract.execute  — execute a new or renewed contract
  contract.amend    — amend a material term of an existing contract

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

AUTHORIZED_LEGAL_APPROVERS: frozenset[str] = frozenset(
    {"legal.counsel@acme.com", "general.counsel@acme.com", "legal.vp@acme.com"}
)
AUTHORIZED_CFO_LIST: frozenset[str] = frozenset(
    {"cfo@acme.com", "cfo.deputy@acme.com"}
)
# Contracts above this value require CFO sign-off (SOX)
CFO_APPROVAL_THRESHOLD_USD = 250_000

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


class _ContractStub(AtlaSentClient):
    """In-process stub — no HTTP calls, deterministic policy engine.

    Overrides ``_request`` to handle evaluate / verify locally.
    Implements the contract.execute and contract.amend policies:

    contract.execute:
      - fail_closed: true
      - legalApprovedBy must be on the authorized legal approver list
      - contracts above CFO_APPROVAL_THRESHOLD require cfoSignOffBy
      - contractValue must be present

    contract.amend:
      - fail_closed: true
      - amendmentType must be "material" — requires legal sign-off
      - legalApprovedBy must be on the authorized legal approver list
      - escalationNote required for material amendments
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
        """Return a V1-shaped response dict for contract.execute / contract.amend."""

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

        # ── contract.execute --------------------------------------------------
        if action == "contract.execute":
            contract_id = ctx.get("contractId", "")
            contract_value = ctx.get("contractValue", None)
            legal_approved_by = ctx.get("legalApprovedBy", "")
            cfo_sign_off_by = ctx.get("cfoSignOffBy", "")
            counterparty = ctx.get("counterparty", "")
            effective_date = ctx.get("effectiveDate", "")

            if not contract_id:
                return deny("DENY_MISSING_FIELD: missing required field: contractId")
            if not counterparty:
                return deny("DENY_MISSING_FIELD: missing required field: counterparty")
            if not effective_date:
                return deny("DENY_MISSING_FIELD: missing required field: effectiveDate")
            if contract_value is None:
                return deny("DENY_MISSING_FIELD: missing required field: contractValue")

            # Legal approval required for all contracts
            if not legal_approved_by:
                return deny(
                    f"DENY_LEGAL_APPROVAL_MISSING: contract {contract_id} requires "
                    f"legal sign-off — legalApprovedBy is absent"
                )
            if legal_approved_by not in AUTHORIZED_LEGAL_APPROVERS:
                return deny(
                    f"DENY_LEGAL_APPROVAL_MISSING: '{legal_approved_by}' is not on the "
                    f"authorized legal approver list"
                )

            # CFO sign-off required for high-value contracts (SOX)
            if float(contract_value) > CFO_APPROVAL_THRESHOLD_USD:
                if not cfo_sign_off_by:
                    return deny(
                        f"DENY_CFO_SIGNOFF_MISSING: contract {contract_id} value "
                        f"${float(contract_value):,.0f} exceeds "
                        f"${CFO_APPROVAL_THRESHOLD_USD:,.0f} threshold — "
                        f"CFO sign-off required; cfoSignOffBy is absent"
                    )
                if cfo_sign_off_by not in AUTHORIZED_CFO_LIST:
                    return deny(
                        f"DENY_CFO_SIGNOFF_MISSING: '{cfo_sign_off_by}' is not on the "
                        f"authorized CFO list"
                    )

            cfo_note = f", CFO={cfo_sign_off_by}" if cfo_sign_off_by else ""
            return allow(
                f"contract {contract_id} executed with {counterparty} "
                f"(${float(contract_value):,.0f}, legal={legal_approved_by}{cfo_note}, "
                f"effective {effective_date})"
            )

        # ── contract.amend ----------------------------------------------------
        if action == "contract.amend":
            contract_id = ctx.get("contractId", "")
            amendment_id = ctx.get("amendmentId", "")
            amendment_type = ctx.get("amendmentType", "")
            legal_approved_by = ctx.get("legalApprovedBy", "")
            escalation_note = ctx.get("escalationNote", "")
            amended_clause = ctx.get("amendedClause", "")

            if not contract_id:
                return deny("DENY_MISSING_FIELD: missing required field: contractId")
            if not amendment_id:
                return deny("DENY_MISSING_FIELD: missing required field: amendmentId")
            if not amendment_type:
                return deny("DENY_MISSING_FIELD: missing required field: amendmentType")
            if not amended_clause:
                return deny("DENY_MISSING_FIELD: missing required field: amendedClause")

            # Material amendments always require legal sign-off
            if not legal_approved_by:
                return deny(
                    f"DENY_LEGAL_APPROVAL_MISSING: amendment {amendment_id} to "
                    f"contract {contract_id} requires legal sign-off — "
                    f"legalApprovedBy is absent"
                )
            if legal_approved_by not in AUTHORIZED_LEGAL_APPROVERS:
                return deny(
                    f"DENY_LEGAL_APPROVAL_MISSING: '{legal_approved_by}' is not on the "
                    f"authorized legal approver list"
                )

            # Material amendments require an escalation note
            if amendment_type == "material" and not escalation_note:
                return deny(
                    f"DENY_ESCALATION_NOTE_MISSING: material amendment {amendment_id} "
                    f"requires an escalationNote documenting the business rationale — "
                    f"provide escalationNote before re-submitting"
                )

            escalation_marker = " [escalated]" if amendment_type == "material" else ""
            return allow(
                f"amendment {amendment_id} to contract {contract_id} "
                f"({amendment_type}: {amended_clause}) approved by "
                f"{legal_approved_by}{escalation_marker}"
            )

        return deny(f"action '{action}' not registered in contract-execution policy")


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
# Simulated contract management system mutations
# Only reachable after protect() returns a verified Permit.
# ---------------------------------------------------------------------------


def _sys_execute_contract(
    contract_id: str,
    counterparty: str,
    contract_value: float,
    effective_date: str,
) -> None:
    _execute(f"contract {contract_id} status set to EXECUTED")
    _execute(f"counterparty: {counterparty}, value: ${contract_value:,.0f}")
    _execute(f"effective date: {effective_date}")
    _execute("execution certificate written to contract management system")
    _execute("revenue recognition schedule initialized")


def _sys_amend_contract(
    contract_id: str,
    amendment_id: str,
    amended_clause: str,
) -> None:
    _execute(f"contract {contract_id} amendment {amendment_id} recorded")
    _execute(f"amended clause: {amended_clause}")
    _execute("amendment logged in contract management system")
    _execute("counterparty notification queued")


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------


def run(client: AtlaSentClient, stub: _ContractStub | None) -> None:  # noqa: C901
    _bar("contract-execution   Contract Execution and Amendment Authorization Demo")
    print(f"  mode:   {'offline stub' if stub else 'live AtlaSent API'}")
    print(f"  actions: contract.execute, contract.amend")
    print(f"  policy: fail-closed, legal + CFO required above ${CFO_APPROVAL_THRESHOLD_USD:,.0f}")

    # 1 ── ALLOW: execute with full legal + CFO approval ----------------------
    _scenario(
        1,
        "contract.execute",
        f"ALLOWED: $500k contract, legal + CFO sign-off present",
    )
    try:
        p = client.protect(
            agent="legal.counsel@acme.com",
            action="contract.execute",
            context={
                "contractId": "MSA-2026-00142",
                "counterparty": "Apex Solutions Ltd",
                "contractValue": 500_000.0,
                "contractType": "master_services_agreement",
                "legalApprovedBy": "legal.counsel@acme.com",
                "cfoSignOffBy": "cfo@acme.com",
                "effectiveDate": "2026-06-01",
                "termMonths": 24,
                "revenueRecognitionMethod": "ASC_606_over_time",
            },
        )
        _permit_line(p)
        _sys_execute_contract(
            "MSA-2026-00142", "Apex Solutions Ltd", 500_000.0, "2026-06-01"
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)

    # 2 ── DENY: execute without CFO sign-off (high-value) --------------------
    _scenario(
        2,
        "contract.execute",
        f"BLOCKED: $750k contract requires CFO sign-off — cfoSignOffBy absent",
    )
    try:
        client.protect(
            agent="legal.counsel@acme.com",
            action="contract.execute",
            context={
                "contractId": "MSA-2026-00143",
                "counterparty": "Meridian Cloud Corp",
                "contractValue": 750_000.0,
                "contractType": "master_services_agreement",
                "legalApprovedBy": "legal.counsel@acme.com",
                # cfoSignOffBy intentionally omitted
                "effectiveDate": "2026-06-15",
                "termMonths": 36,
                "revenueRecognitionMethod": "ASC_606_over_time",
            },
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)
        print(f"               evaluation_id: {exc.evaluation_id}")
        _execute("contract NOT executed — obtain CFO sign-off before re-submitting")

    # 3 ── ALLOW: amend material term with escalation note --------------------
    _scenario(
        3,
        "contract.amend",
        "ALLOWED: material term amendment, legal sign-off, escalation note recorded",
    )
    try:
        p = client.protect(
            agent="legal.counsel@acme.com",
            action="contract.amend",
            context={
                "contractId": "MSA-2026-00138",
                "amendmentId": "AMD-2026-00042",
                "amendmentType": "material",
                "amendedClause": "Section 4.2 — Payment Terms",
                "legalApprovedBy": "legal.counsel@acme.com",
                "escalationNote": (
                    "Customer requested net-60 payment terms due to Q2 cash flow "
                    "constraints; approved per commercial escalation policy EP-2026-007"
                ),
                "priorTermValue": "net-30",
                "newTermValue": "net-60",
                "revenueImpact": "timing_only",
            },
        )
        _permit_line(p)
        _sys_amend_contract(
            "MSA-2026-00138", "AMD-2026-00042", "Section 4.2 — Payment Terms"
        )
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
    print("    BLOCKED  1 action  (missing CFO sign-off on high-value contract)")
    print("    ALLOWED  2 actions (execution + material amendment permit-verified)")
    print()


def main() -> None:
    api_key = os.environ.get("ATLASENT_API_KEY", "")
    if api_key:
        run(AtlaSentClient(api_key=api_key, base_url=os.environ.get("ATLASENT_API_URL", "https://api.atlasent.io/functions/v1")), stub=None)
    else:
        stub = _ContractStub()
        run(stub, stub)


if __name__ == "__main__":
    main()
