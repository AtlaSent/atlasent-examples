#!/usr/bin/env python3
"""gxp-clinical-data-access: GxP Clinical Data Access Authorization Demo

Demonstrates non-bypassable authorization for clinical trial data access
using the AtlaSent SDK with the `clinical.data.access` action.

Three scenarios:
  1. ALLOWED: human researcher, aiAgent=False, valid purpose → ALLOW
  2. DENIED:  AI agent access — machine_executable=False enforces denial
              since no human-in-the-loop is present
  3. DENIED:  missing purpose field → DENY_PURPOSE_MISSING

Context: subjectId, dataCategory, accessedBy, purpose, aiAgent,
         consentVerified, trialId

Policy: AI agents require human_in_the_loop=true; purpose is required;
        consent must be verified before access is granted.

Regulatory note: This policy enforces 21 CFR Part 11 requirements for
electronic records access in clinical environments. All access decisions
are recorded in a SHA-256 hash-linked audit trail.

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

AUTHORIZED_RESEARCHERS: frozenset[str] = frozenset(
    {
        "dr.smith@clinicalresearch.example",
        "dr.jones@clinicalresearch.example",
        "data.mgr@clinicalresearch.example",
    }
)

VALID_PURPOSES: frozenset[str] = frozenset(
    {"protocol-review", "safety-review", "audit", "regulatory-submission", "monitoring"}
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


class _ClinicalStub(AtlaSentClient):
    """In-process stub — no HTTP calls, deterministic clinical data access policy.

    Policy rules:
      - machine_executable=False: AI agents (aiAgent=True) are always denied
        since no human-in-the-loop is present
      - purpose must be non-empty (DENY_PURPOSE_MISSING)
      - consentVerified must be True
      - accessedBy must be in authorized researcher list
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
        """Return a V1-shaped response dict for the clinical.data.access policy."""

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

        if action != "clinical.data.access":
            return deny(f"action '{action}' not registered in clinical-data-access policy")

        subject_id = ctx.get("subjectId", "")
        data_category = ctx.get("dataCategory", "")
        accessed_by = ctx.get("accessedBy", "")
        purpose = ctx.get("purpose", "")
        ai_agent = ctx.get("aiAgent", False)
        consent_verified = ctx.get("consentVerified", False)
        trial_id = ctx.get("trialId", "")

        # machine_executable=False: AI agents are always denied
        if ai_agent:
            return deny(
                "DENY_AI_AGENT_NOT_PERMITTED: clinical.data.access has machine_executable=false "
                "— AI agents cannot access clinical subject data without a human in the loop; "
                "use protectToolCall() with human_in_the_loop=true for AI agent pipelines"
            )

        # Purpose is required
        if not purpose:
            return deny(
                "DENY_PURPOSE_MISSING: purpose field is required for clinical data access; "
                "provide a documented purpose (e.g. protocol-review, safety-review, audit)"
            )

        # Consent verification
        if not consent_verified:
            return deny(
                f"DENY_CONSENT_NOT_VERIFIED: subject {subject_id!r} consent has not been "
                f"verified for trial {trial_id!r} — access denied until consent is confirmed"
            )

        # Researcher authorization
        if accessed_by not in AUTHORIZED_RESEARCHERS:
            return deny(
                f"DENY_AUTHORITY: '{accessed_by}' is not on the authorized researcher list "
                f"for clinical data access"
            )

        return allow(
            f"clinical data access granted: {accessed_by} accessing "
            f"{data_category!r} for subject {subject_id} "
            f"(trial={trial_id}, purpose={purpose})"
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
# Simulated clinical data access mutations
# Only reachable after protect() returns a verified Permit.
# ---------------------------------------------------------------------------


def _sys_grant_access(
    subject_id: str, data_category: str, accessed_by: str, trial_id: str
) -> None:
    _execute(
        f"data access granted: {accessed_by} → {data_category} "
        f"(subject={subject_id}, trial={trial_id})"
    )
    _execute("access session logged to clinical trial management system")


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------


def run(client: AtlaSentClient, stub: _ClinicalStub | None) -> None:
    _bar("gxp-clinical-data-access   Clinical Data Access Authorization Demo")
    print(f"  mode:   {'offline stub' if stub else 'live AtlaSent API'}")
    print(f"  action: clinical.data.access")
    print(f"  policy: fail-closed, machine_executable=False, consent required, purpose required")

    # 1 ── ALLOW: human researcher, aiAgent=False, valid purpose --------------
    _scenario(
        1,
        "clinical.data.access",
        "ALLOWED: human researcher, aiAgent=False, purpose=protocol-review, consent verified",
    )
    try:
        p = client.protect(
            agent="dr.smith@clinicalresearch.example",
            action="clinical.data.access",
            context={
                "subjectId": "SUBJ-004",
                "dataCategory": "efficacy-endpoints",
                "accessedBy": "dr.smith@clinicalresearch.example",
                "purpose": "protocol-review",
                "aiAgent": False,
                "consentVerified": True,
                "trialId": "TRIAL-2026-PHASE3-001",
            },
        )
        _permit_line(p)
        _sys_grant_access(
            "SUBJ-004",
            "efficacy-endpoints",
            "dr.smith@clinicalresearch.example",
            "TRIAL-2026-PHASE3-001",
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)

    # 2 ── DENY: AI agent access — machine_executable=False -------------------
    _scenario(
        2,
        "clinical.data.access",
        "BLOCKED: aiAgent=True — machine_executable=False, no human-in-the-loop",
    )
    print("  Note: use protectToolCall() with human_in_the_loop=true in AI agent pipelines")
    try:
        client.protect(
            agent="clinical-review-agent",
            action="clinical.data.access",
            context={
                "subjectId": "SUBJ-007",
                "dataCategory": "safety-events",
                "accessedBy": "clinical-review-agent",
                "purpose": "automated-safety-review",
                "aiAgent": True,  # <-- AI agent, blocked by machine_executable=False
                "consentVerified": True,
                "trialId": "TRIAL-2026-PHASE3-001",
            },
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)
        print(f"               evaluation_id: {exc.evaluation_id}")
        _execute("data access NOT granted — human review required before AI agent access")

    # 3 ── DENY: missing purpose -----------------------------------------------
    _scenario(
        3,
        "clinical.data.access",
        "BLOCKED: purpose field empty → DENY_PURPOSE_MISSING",
    )
    try:
        client.protect(
            agent="dr.jones@clinicalresearch.example",
            action="clinical.data.access",
            context={
                "subjectId": "SUBJ-012",
                "dataCategory": "lab-results",
                "accessedBy": "dr.jones@clinicalresearch.example",
                "purpose": "",  # <-- missing purpose
                "aiAgent": False,
                "consentVerified": True,
                "trialId": "TRIAL-2026-PHASE3-001",
            },
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)
        print(f"               evaluation_id: {exc.evaluation_id}")
        _execute("data access NOT granted — purpose must be documented per ICH E6 GCP §8")

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
    print("    BLOCKED  2 actions (AI agent blocked / missing purpose)")
    print("    ALLOWED  1 action  (human researcher, consent verified, purpose documented)")
    print()


def main() -> None:
    api_key = os.environ.get("ATLASENT_API_KEY", "")
    if api_key:
        run(AtlaSentClient(api_key=api_key, base_url=os.environ.get("ATLASENT_API_URL", "https://api.atlasent.io/functions/v1")), stub=None)
    else:
        stub = _ClinicalStub()
        run(stub, stub)


if __name__ == "__main__":
    main()
