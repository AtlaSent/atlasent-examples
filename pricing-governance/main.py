#!/usr/bin/env python3
"""pricing-governance: Pricing Rule and Discount Authorization Demo

Demonstrates non-bypassable authorization for pricing governance using the
AtlaSent SDK fail-closed enforcement model.

Three scenarios:
  1. ALLOW  — small discount within auto-approval threshold (no CFO required)
  2. ALLOW  — large discount requiring CFO escalation (CFO sign-off present)
  3. DENY   — discount exceeding delegated authority ceiling (no override path)

Action types:
  pricing.rule.publish     — publish a new pricing rule to the pricing engine
  pricing.discount.approve — approve a discount for a customer / deal

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

AUTHORIZED_PRICING_MANAGERS: frozenset[str] = frozenset(
    {"pricing.mgr@acme.com", "pricing.director@acme.com", "revenue.ops@acme.com"}
)
AUTHORIZED_CFO_LIST: frozenset[str] = frozenset(
    {"cfo@acme.com", "cfo.deputy@acme.com"}
)

# Discount authority tiers
AUTO_APPROVE_CEILING_PCT = 10.0      # <= 10%: auto-approved by pricing manager
CFO_REQUIRED_THRESHOLD_PCT = 10.0   # > 10%: CFO escalation required
AUTHORITY_CEILING_PCT = 40.0        # > 40%: exceeds maximum delegated authority

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


class _PricingStub(AtlaSentClient):
    """In-process stub — no HTTP calls, deterministic policy engine.

    Overrides ``_request`` to handle evaluate / verify locally.
    Implements pricing.rule.publish and pricing.discount.approve policies:

    pricing.rule.publish:
      - fail_closed: true
      - publishedBy must be on the authorized pricing manager list
      - effectiveDate must be present
      - ruleType must be present

    pricing.discount.approve:
      - fail_closed: true
      - discountPct <= AUTO_APPROVE_CEILING_PCT: auto-approved (pricing manager only)
      - discountPct > CFO_REQUIRED_THRESHOLD_PCT: CFO escalation required
      - discountPct > AUTHORITY_CEILING_PCT: denied, exceeds maximum authority
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
        """Return a V1-shaped response dict for pricing governance policies."""

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

        # ── pricing.rule.publish -----------------------------------------------
        if action == "pricing.rule.publish":
            rule_id = ctx.get("ruleId", "")
            rule_type = ctx.get("ruleType", "")
            published_by = ctx.get("publishedBy", "")
            effective_date = ctx.get("effectiveDate", "")
            target_segments = ctx.get("targetSegments", [])

            if not rule_id:
                return deny("DENY_MISSING_FIELD: missing required field: ruleId")
            if not rule_type:
                return deny("DENY_MISSING_FIELD: missing required field: ruleType")
            if not effective_date:
                return deny("DENY_MISSING_FIELD: missing required field: effectiveDate")
            if not published_by:
                return deny(
                    f"DENY_AUTHORITY: publishedBy is absent — pricing manager "
                    f"sign-off required to publish pricing rules"
                )
            if published_by not in AUTHORIZED_PRICING_MANAGERS:
                return deny(
                    f"DENY_AUTHORITY: '{published_by}' is not on the authorized "
                    f"pricing manager list"
                )

            segments_note = (
                f", segments: {', '.join(target_segments)}" if target_segments else ""
            )
            return allow(
                f"pricing rule {rule_id} ({rule_type}) published by {published_by} "
                f"(effective {effective_date}){segments_note}"
            )

        # ── pricing.discount.approve -------------------------------------------
        if action == "pricing.discount.approve":
            discount_id = ctx.get("discountId", "")
            customer_id = ctx.get("customerId", "")
            discount_pct = ctx.get("discountPct", None)
            approved_by = ctx.get("approvedBy", "")
            cfo_sign_off_by = ctx.get("cfoSignOffBy", "")
            deal_value_usd = ctx.get("dealValueUsd", 0.0)
            business_justification = ctx.get("businessJustification", "")

            if not discount_id:
                return deny("DENY_MISSING_FIELD: missing required field: discountId")
            if not customer_id:
                return deny("DENY_MISSING_FIELD: missing required field: customerId")
            if discount_pct is None:
                return deny("DENY_MISSING_FIELD: missing required field: discountPct")
            if not approved_by:
                return deny(
                    "DENY_AUTHORITY: approvedBy is absent — pricing manager required"
                )

            pct = float(discount_pct)

            # Exceeds maximum delegated authority — hard deny, no escalation path
            if pct > AUTHORITY_CEILING_PCT:
                return deny(
                    f"DENY_EXCEEDS_AUTHORITY: discount {discount_id} requests "
                    f"{pct:.1f}% which exceeds the maximum delegated authority of "
                    f"{AUTHORITY_CEILING_PCT:.0f}% — this discount level is not "
                    f"permittable under any approval path; escalate to board-level "
                    f"commercial approval committee"
                )

            # Large discount: CFO escalation required
            if pct > CFO_REQUIRED_THRESHOLD_PCT:
                if not cfo_sign_off_by:
                    return deny(
                        f"DENY_CFO_SIGNOFF_MISSING: discount {discount_id} ({pct:.1f}%) "
                        f"exceeds the {CFO_REQUIRED_THRESHOLD_PCT:.0f}% auto-approval "
                        f"ceiling — CFO sign-off required; cfoSignOffBy is absent"
                    )
                if cfo_sign_off_by not in AUTHORIZED_CFO_LIST:
                    return deny(
                        f"DENY_CFO_SIGNOFF_MISSING: '{cfo_sign_off_by}' is not on the "
                        f"authorized CFO list"
                    )
                if approved_by not in AUTHORIZED_PRICING_MANAGERS:
                    return deny(
                        f"DENY_AUTHORITY: '{approved_by}' is not on the authorized "
                        f"pricing manager list"
                    )
                cfo_note = f", CFO={cfo_sign_off_by}"
                return allow(
                    f"discount {discount_id} ({pct:.1f}% on ${float(deal_value_usd):,.0f} "
                    f"deal for {customer_id}) approved by {approved_by}{cfo_note} "
                    f"[escalated: above auto-approval ceiling]"
                )

            # Small discount: auto-approved by pricing manager
            if approved_by not in AUTHORIZED_PRICING_MANAGERS:
                return deny(
                    f"DENY_AUTHORITY: '{approved_by}' is not on the authorized "
                    f"pricing manager list"
                )
            return allow(
                f"discount {discount_id} ({pct:.1f}% on ${float(deal_value_usd):,.0f} "
                f"deal for {customer_id}) auto-approved by {approved_by} "
                f"[within {AUTO_APPROVE_CEILING_PCT:.0f}% ceiling]"
            )

        return deny(f"action '{action}' not registered in pricing-governance policy")


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
# Simulated pricing engine state mutations
# Only reachable after protect() returns a verified Permit.
# ---------------------------------------------------------------------------


def _sys_approve_discount(
    discount_id: str,
    customer_id: str,
    discount_pct: float,
    deal_value_usd: float,
) -> None:
    _execute(f"discount {discount_id} status set to APPROVED")
    _execute(f"customer {customer_id}: {discount_pct:.1f}% on ${deal_value_usd:,.0f} deal")
    _execute("CRM opportunity updated with approved discount")
    _execute("revenue recognition impact logged to rev-rec system")


def _sys_publish_rule(rule_id: str, rule_type: str, effective_date: str) -> None:
    _execute(f"pricing rule {rule_id} ({rule_type}) published to pricing engine")
    _execute(f"effective date: {effective_date}")
    _execute("cache invalidation triggered for affected SKUs")


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------


def run(client: AtlaSentClient, stub: _PricingStub | None) -> None:  # noqa: C901
    _bar("pricing-governance   Pricing Rule and Discount Authorization Demo")
    print(f"  mode:   {'offline stub' if stub else 'live AtlaSent API'}")
    print(f"  actions: pricing.rule.publish, pricing.discount.approve")
    print(
        f"  policy: auto-approve <= {AUTO_APPROVE_CEILING_PCT:.0f}%, "
        f"CFO required > {CFO_REQUIRED_THRESHOLD_PCT:.0f}%, "
        f"hard deny > {AUTHORITY_CEILING_PCT:.0f}%"
    )

    # 1 ── ALLOW: small discount, auto-approved by pricing manager ------------
    _scenario(
        1,
        "pricing.discount.approve",
        f"ALLOWED: {AUTO_APPROVE_CEILING_PCT:.0f}% discount — within auto-approval ceiling",
    )
    try:
        p = client.protect(
            agent="pricing.mgr@acme.com",
            action="pricing.discount.approve",
            context={
                "discountId": "DISC-2026-00841",
                "customerId": "CUST-55210",
                "discountPct": 8.0,
                "dealValueUsd": 120_000.0,
                "approvedBy": "pricing.mgr@acme.com",
                "businessJustification": "Volume commitment — 3-year term renewal",
                "dealStage": "proposal",
                "productLine": "platform",
            },
        )
        _permit_line(p)
        _sys_approve_discount("DISC-2026-00841", "CUST-55210", 8.0, 120_000.0)
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)

    # 2 ── ALLOW: large discount, CFO escalation with sign-off present --------
    _scenario(
        2,
        "pricing.discount.approve",
        f"ALLOWED: 25% discount — CFO escalation required and sign-off present",
    )
    try:
        p = client.protect(
            agent="pricing.director@acme.com",
            action="pricing.discount.approve",
            context={
                "discountId": "DISC-2026-00842",
                "customerId": "CUST-10010",
                "discountPct": 25.0,
                "dealValueUsd": 850_000.0,
                "approvedBy": "pricing.director@acme.com",
                "cfoSignOffBy": "cfo@acme.com",
                "businessJustification": (
                    "Strategic enterprise account — competitive displacement; "
                    "approved per commercial escalation policy EP-2026-012"
                ),
                "dealStage": "negotiation",
                "productLine": "enterprise",
                "competitorName": "RivalCorp",
            },
        )
        _permit_line(p)
        _sys_approve_discount("DISC-2026-00842", "CUST-10010", 25.0, 850_000.0)
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)

    # 3 ── DENY: discount exceeds maximum delegated authority -----------------
    _scenario(
        3,
        "pricing.discount.approve",
        f"BLOCKED: 55% discount exceeds {AUTHORITY_CEILING_PCT:.0f}% maximum authority ceiling",
    )
    try:
        client.protect(
            agent="pricing.director@acme.com",
            action="pricing.discount.approve",
            context={
                "discountId": "DISC-2026-00843",
                "customerId": "CUST-99901",
                "discountPct": 55.0,  # <-- exceeds 40% authority ceiling
                "dealValueUsd": 2_000_000.0,
                "approvedBy": "pricing.director@acme.com",
                "cfoSignOffBy": "cfo@acme.com",
                "businessJustification": "Attempting to win logo account at any cost",
                "dealStage": "final",
                "productLine": "enterprise",
            },
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)
        print(f"               evaluation_id: {exc.evaluation_id}")
        _execute("discount NOT approved — escalate to board-level commercial committee")

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
    print("    BLOCKED  1 action  (discount exceeds maximum delegated authority)")
    print("    ALLOWED  2 actions (auto-approve + CFO escalation permit-verified)")
    print()


def main() -> None:
    api_key = os.environ.get("ATLASENT_API_KEY", "")
    if api_key:
        run(AtlaSentClient(api_key=api_key, base_url=os.environ.get("ATLASENT_API_URL", "https://api.atlasent.io/functions/v1")), stub=None)
    else:
        stub = _PricingStub()
        run(stub, stub)


if __name__ == "__main__":
    main()
