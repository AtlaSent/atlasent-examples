#!/usr/bin/env python3
"""behavior-events: Behavior Event Sharing Authorization Demo

Demonstrates non-bypassable authorization for behavioral event sharing
using the AtlaSent SDK with the `behavior.event.share` action.

Four scenarios:
  1. ALLOWED: non-sensitive event, consent verified, valid purpose, verified destination
  2. DENIED:  behavior.health.mental category, consentVerified=False
  3. DENIED:  behavior.minor category → HOLD_HUMAN_REVIEW_REQUIRED
              (machine cannot auto-approve for minors)
  4. DENIED:  no purpose documented → DENY_PURPOSE_MISSING

NOTE: Behavior events are Phase 3 and require a privacy review before
production use. See README.md for the privacy review checklist.

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

# Sensitive categories require consentVerified=True
SENSITIVE_CATEGORIES: frozenset[str] = frozenset(
    {
        "behavior.health.mental",
        "behavior.health.physical",
        "behavior.health.reproductive",
        "behavior.financial",
        "behavior.minor",
        "behavior.location.precise",
    }
)

# Minor category always requires human review (machine_executable=False)
MINOR_CATEGORIES: frozenset[str] = frozenset({"behavior.minor"})

# Verified destination allowlist
VERIFIED_DESTINATIONS: frozenset[str] = frozenset(
    {
        "analytics.internal.example",
        "research.partner-a.example",
        "compliance-archive.example",
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
# In-process stub engine
# ---------------------------------------------------------------------------


class _BehaviorStub(AtlaSentClient):
    """In-process stub — no HTTP calls, deterministic behavior event policy.

    Policy rules:
      - sensitive categories (health.*, financial, minor) require consentVerified=True
      - minor categories require human review (machine_executable=False)
      - purpose must be documented (non-empty)
      - destination must be in the verified allowlist
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
        """Return a V1-shaped response dict for the behavior.event.share policy."""

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

        if action != "behavior.event.share":
            return deny(f"action '{action}' not registered in behavior-events policy")

        event_category = ctx.get("eventCategory", "")
        consent_verified = ctx.get("consentVerified", False)
        purpose = ctx.get("purpose", "")
        destination = ctx.get("destination", "")
        subject_id = ctx.get("subjectId", "")

        # Minor category — always requires human review
        if event_category in MINOR_CATEGORIES:
            return deny(
                "HOLD_HUMAN_REVIEW_REQUIRED: behavior.minor data cannot be auto-approved — "
                "machine_executable=false for minor categories; "
                "a human privacy reviewer must approve before this event may be shared"
            )

        # Purpose is required
        if not purpose:
            return deny(
                "DENY_PURPOSE_MISSING: purpose field is required for behavior event sharing; "
                "provide a documented purpose"
            )

        # Sensitive categories require consent
        is_sensitive = any(event_category.startswith(prefix) for prefix in
                          ["behavior.health", "behavior.financial", "behavior.minor",
                           "behavior.location.precise"])
        if is_sensitive and not consent_verified:
            return deny(
                f"DENY_CONSENT_NOT_VERIFIED: category '{event_category}' is a sensitive "
                f"category — consentVerified must be true before sharing"
            )

        # Destination must be verified
        if destination not in VERIFIED_DESTINATIONS:
            return deny(
                f"DENY_DESTINATION_NOT_VERIFIED: destination '{destination}' is not in the "
                f"verified destination allowlist"
            )

        return allow(
            f"behavior event {event_category!r} for subject {subject_id} "
            f"shared to {destination} (purpose={purpose})"
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
# Simulated behavior event dispatch
# Only reachable after protect() returns a verified Permit.
# ---------------------------------------------------------------------------


def _sys_share_event(
    event_category: str, subject_id: str, destination: str, purpose: str
) -> None:
    _execute(
        f"event {event_category!r} for subject {subject_id} "
        f"dispatched to {destination}"
    )
    _execute(f"event logged in behavior audit trail (purpose={purpose})")


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------


def run(client: AtlaSentClient, stub: _BehaviorStub | None) -> None:
    _bar("behavior-events   Behavior Event Sharing Authorization Demo")
    print(f"  mode:   {'offline stub' if stub else 'live AtlaSent API'}")
    print(f"  action: behavior.event.share")
    print(f"  note:   Phase 3 feature — requires privacy review before production use")

    # 1 ── ALLOW: non-sensitive, consent verified, valid purpose, verified dest
    _scenario(
        1,
        "behavior.event.share",
        "ALLOWED: non-sensitive category, consent verified, valid purpose and destination",
    )
    try:
        p = client.protect(
            agent="analytics-pipeline",
            action="behavior.event.share",
            context={
                "subjectId": "usr-88412",
                "eventCategory": "behavior.product.click",
                "consentVerified": True,
                "purpose": "product-analytics",
                "destination": "analytics.internal.example",
            },
        )
        _permit_line(p)
        _sys_share_event(
            "behavior.product.click",
            "usr-88412",
            "analytics.internal.example",
            "product-analytics",
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)

    # 2 ── DENY: sensitive category (health.mental), consentVerified=False ----
    _scenario(
        2,
        "behavior.event.share",
        "BLOCKED: behavior.health.mental category, consentVerified=False",
    )
    try:
        client.protect(
            agent="health-analytics-pipeline",
            action="behavior.event.share",
            context={
                "subjectId": "usr-88413",
                "eventCategory": "behavior.health.mental",
                "consentVerified": False,  # <-- no consent
                "purpose": "mental-health-research",
                "destination": "research.partner-a.example",
            },
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)
        print(f"               evaluation_id: {exc.evaluation_id}")
        _execute("event NOT shared — consent required for health category data")

    # 3 ── DENY: behavior.minor category → HOLD_HUMAN_REVIEW_REQUIRED ---------
    _scenario(
        3,
        "behavior.event.share",
        "BLOCKED: behavior.minor category → HOLD_HUMAN_REVIEW_REQUIRED",
    )
    print("  Note: machine cannot auto-approve minor data — human privacy review required")
    try:
        client.protect(
            agent="analytics-pipeline",
            action="behavior.event.share",
            context={
                "subjectId": "usr-child-001",
                "eventCategory": "behavior.minor",
                "consentVerified": True,
                "purpose": "child-safety-research",
                "destination": "research.partner-a.example",
            },
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)
        print(f"               evaluation_id: {exc.evaluation_id}")
        _execute("event NOT shared — human privacy reviewer must approve minor data sharing")

    # 4 ── DENY: no purpose documented ----------------------------------------
    _scenario(
        4,
        "behavior.event.share",
        "BLOCKED: purpose field empty → DENY_PURPOSE_MISSING",
    )
    try:
        client.protect(
            agent="analytics-pipeline",
            action="behavior.event.share",
            context={
                "subjectId": "usr-88414",
                "eventCategory": "behavior.product.view",
                "consentVerified": True,
                "purpose": "",  # <-- missing purpose
                "destination": "analytics.internal.example",
            },
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)
        print(f"               evaluation_id: {exc.evaluation_id}")
        _execute("event NOT shared — purpose must be documented")

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

    _bar()
    print("  Enforcement summary:")
    print("    BLOCKED  3 actions (consent missing / minor data / missing purpose)")
    print("    ALLOWED  1 action  (non-sensitive, consent verified, valid context)")
    print()


def main() -> None:
    api_key = os.environ.get("ATLASENT_API_KEY", "")
    if api_key:
        run(AtlaSentClient(api_key=api_key, base_url=os.environ.get("ATLASENT_API_URL", "https://api.atlasent.io/functions/v1")), stub=None)
    else:
        stub = _BehaviorStub()
        run(stub, stub)


if __name__ == "__main__":
    main()
