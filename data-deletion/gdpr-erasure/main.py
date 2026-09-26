#!/usr/bin/env python3
"""gdpr-erasure: GDPR Article 17 Right-to-Erasure Authorization Demo

Demonstrates non-bypassable authorization for GDPR customer data deletion
requests using the AtlaSent SDK fail-closed enforcement model.

Three scenarios:
  1. ALLOW  — verified erasure request with DPO sign-off, within 30-day window
  2. DENY   — unverified erasure request (identity not verified)
  3. DENY   — expired request window (request older than 30 days)

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

AUTHORIZED_DPO_LIST: frozenset[str] = frozenset(
    {"dpo@acme.com", "privacy.lead@acme.com", "dpo.deputy@acme.com"}
)
ERASURE_WINDOW_DAYS = 30  # GDPR Article 17 — response within 30 days

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


class _GdprStub(AtlaSentClient):
    """In-process stub — no HTTP calls, deterministic policy engine.

    Overrides ``_request`` to handle evaluate / verify locally.
    Implements the customer.data.delete policy:
      - fail_closed: true
      - machine_executable: false (DPO sign-off required)
      - identityVerified must be true
      - dpoSignOffBy must be on the authorized DPO list
      - requestWindowExpired must be false (within 30-day GDPR timeline)
      - legalBasisForRetention check (if active, blocking grounds must be absent)
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
        """Return a V1-shaped response dict for customer.data.delete policy."""

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

        if action != "customer.data.delete":
            return deny(f"action '{action}' not registered in gdpr-erasure policy")

        request_id = ctx.get("requestId", "")
        customer_id = ctx.get("customerId", "")
        identity_verified = ctx.get("identityVerified", False)
        dpo_sign_off_by = ctx.get("dpoSignOffBy", "")
        request_received_date = ctx.get("requestReceivedDate", "")
        request_window_expired = ctx.get("requestWindowExpired", False)
        legal_basis_for_retention = ctx.get("legalBasisForRetention", "")
        data_categories = ctx.get("dataCategories", [])

        # Required field checks
        if not request_id:
            return deny("DENY_MISSING_FIELD: missing required field: requestId")
        if not customer_id:
            return deny("DENY_MISSING_FIELD: missing required field: customerId")
        if not request_received_date:
            return deny("DENY_MISSING_FIELD: missing required field: requestReceivedDate")

        # GDPR Article 17: identity must be verified before deletion
        if not identity_verified:
            return deny(
                f"DENY_IDENTITY_NOT_VERIFIED: erasure request {request_id} cannot be "
                f"processed — data subject identity has not been verified; complete "
                f"identity verification before proceeding with deletion"
            )

        # GDPR Article 17: 30-day response window
        if request_window_expired:
            return deny(
                f"DENY_REQUEST_WINDOW_EXPIRED: erasure request {request_id} received "
                f"on {request_received_date} has exceeded the {ERASURE_WINDOW_DAYS}-day "
                f"GDPR Article 17 response window — log as compliance breach and "
                f"escalate to DPO; a new deletion workflow must be initiated"
            )

        # Legal basis for retention check — if an active legal hold exists, block
        if legal_basis_for_retention and legal_basis_for_retention not in (
            "none",
            "",
            "no_hold",
        ):
            return deny(
                f"DENY_LEGAL_BASIS_RETENTION: erasure request {request_id} is blocked "
                f"by an active legal basis for retention: '{legal_basis_for_retention}'; "
                f"resolve the legal hold before proceeding with deletion"
            )

        # DPO sign-off required
        if not dpo_sign_off_by:
            return deny(
                f"DENY_DPO_SIGNOFF_MISSING: erasure request {request_id} requires "
                f"DPO sign-off — dpoSignOffBy is absent"
            )
        if dpo_sign_off_by not in AUTHORIZED_DPO_LIST:
            return deny(
                f"DENY_DPO_SIGNOFF_MISSING: '{dpo_sign_off_by}' is not on the "
                f"authorized DPO list — only the Data Protection Officer may authorize "
                f"customer data deletion"
            )

        categories_note = (
            f", categories: {', '.join(data_categories)}" if data_categories else ""
        )
        return allow(
            f"GDPR erasure request {request_id} for customer {customer_id} "
            f"approved by {dpo_sign_off_by} (received {request_received_date})"
            f"{categories_note}"
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
# Simulated data platform mutations
# Only reachable after protect() returns a verified Permit.
# ---------------------------------------------------------------------------


def _sys_delete_customer_data(
    request_id: str,
    customer_id: str,
    dpo_sign_off_by: str,
    data_categories: list[str],
) -> None:
    _execute(f"erasure request {request_id} status set to IN_PROGRESS")
    _execute(f"customer {customer_id} data deletion initiated")
    for cat in data_categories:
        _execute(f"queued deletion for data category: {cat}")
    _execute(f"DPO confirmation logged: {dpo_sign_off_by}")
    _execute("erasure completion certificate will be generated on finish")


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------


def run(client: AtlaSentClient, stub: _GdprStub | None) -> None:
    _bar("gdpr-erasure   GDPR Article 17 Right-to-Erasure Authorization Demo")
    print(f"  mode:   {'offline stub' if stub else 'live AtlaSent API'}")
    print(f"  action: customer.data.delete")
    print(f"  policy: fail-closed, DPO sign-off required, 30-day window enforced")

    # 1 ── ALLOW: verified request with DPO sign-off --------------------------
    _scenario(
        1,
        "customer.data.delete",
        "ALLOWED: verified erasure request, DPO sign-off, within 30-day window",
    )
    data_categories = ["profile", "purchase_history", "marketing_preferences", "support_tickets"]
    try:
        p = client.protect(
            agent="dpo@acme.com",
            action="customer.data.delete",
            context={
                "requestId": "DSR-2026-04821",
                "customerId": "CUST-88420",
                "identityVerified": True,
                "dpoSignOffBy": "dpo@acme.com",
                "requestReceivedDate": "2026-05-15",
                "requestWindowExpired": False,
                "legalBasisForRetention": "none",
                "dataCategories": data_categories,
                "verificationMethod": "email_otp",
                "gdprArticle": "17",
                "jurisdiction": "EU",
            },
        )
        _permit_line(p)
        _sys_delete_customer_data("DSR-2026-04821", "CUST-88420", "dpo@acme.com", data_categories)
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)

    # 2 ── DENY: unverified identity -------------------------------------------
    _scenario(
        2,
        "customer.data.delete",
        "BLOCKED: identityVerified=False — cannot process without identity verification",
    )
    try:
        client.protect(
            agent="dpo@acme.com",
            action="customer.data.delete",
            context={
                "requestId": "DSR-2026-04822",
                "customerId": "CUST-91003",
                "identityVerified": False,  # <-- identity not verified
                "dpoSignOffBy": "dpo@acme.com",
                "requestReceivedDate": "2026-05-20",
                "requestWindowExpired": False,
                "legalBasisForRetention": "none",
                "dataCategories": ["profile", "purchase_history"],
                "gdprArticle": "17",
                "jurisdiction": "EU",
            },
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)
        print(f"               evaluation_id: {exc.evaluation_id}")
        _execute("data NOT deleted — complete identity verification first")

    # 3 ── DENY: expired request window ----------------------------------------
    _scenario(
        3,
        "customer.data.delete",
        f"BLOCKED: requestWindowExpired=True — exceeds {ERASURE_WINDOW_DAYS}-day GDPR timeline",
    )
    try:
        client.protect(
            agent="dpo@acme.com",
            action="customer.data.delete",
            context={
                "requestId": "DSR-2026-03991",
                "customerId": "CUST-72210",
                "identityVerified": True,
                "dpoSignOffBy": "dpo@acme.com",
                "requestReceivedDate": "2026-04-10",  # >30 days ago
                "requestWindowExpired": True,  # <-- window has expired
                "legalBasisForRetention": "none",
                "dataCategories": ["profile"],
                "gdprArticle": "17",
                "jurisdiction": "EU",
            },
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)
        print(f"               evaluation_id: {exc.evaluation_id}")
        _execute("data NOT deleted — log compliance breach and escalate to DPO")

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
    print("    BLOCKED  2 actions (unverified identity / expired window)")
    print("    ALLOWED  1 action  (permit-verified before customer data deletion)")
    print()


def main() -> None:
    api_key = os.environ.get("ATLASENT_API_KEY", "")
    if api_key:
        run(AtlaSentClient(api_key=api_key, base_url=os.environ.get("ATLASENT_API_URL", "https://api.atlasent.io/functions/v1")), stub=None)
    else:
        stub = _GdprStub()
        run(stub, stub)


if __name__ == "__main__":
    main()
