#!/usr/bin/env python3
"""gxp-hipaa-phi-access: HIPAA ePHI Access Authorization Demo

Demonstrates non-bypassable authorization for electronic protected health
information (ePHI) access, export, and deletion under the HIPAA Security Rule
(45 CFR §164.312) using the AtlaSent SDK fail-closed enforcement model.

Four scenarios:
  1. ALLOW   — authorized clinician reads ePHI (phi.access)
  2. DENY    — unauthorized role attempts ePHI export without dual-officer approval
  3. DENY    — AI agent attempts phi.delete (machine_executable=false)
  4. ESCALATE — privacy officer requests ePHI export (requires dual sign-off)

Runs offline (in-process stub) by default.
Set ATLASENT_API_KEY to switch to the live AtlaSent API.

Regulatory references:
  45 CFR 164.312(a) — Access controls
  45 CFR 164.312(b) — Audit controls
  45 CFR 164.312(c) — Integrity controls
  45 CFR 164.312(e) — Transmission security
  HITECH Act §13402 — Breach notification
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

AUTHORIZED_PHI_ROLES: frozenset[str] = frozenset({
    "clinician",
    "health_information_manager",
    "privacy_officer",
    "authorized_workforce",
})

EXPORT_AUTHORIZED_ROLES: frozenset[str] = frozenset({
    "privacy_officer",
    "health_information_manager",
    "ciso",
    "compliance_officer",
})

DUAL_EXPORT_ROLES: frozenset[str] = frozenset({
    "privacy_officer",
    "ciso",
    "compliance_officer",
})

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
    regulatory_ref: str = ""
    context_snapshot: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# In-process stub engine — HIPAA Security Rule policy
# ---------------------------------------------------------------------------


class _HipaaStub(AtlaSentClient):
    """In-process stub — no HTTP calls, deterministic HIPAA policy engine.

    Implements the hipaa-security pack from atlasent-gxp-starter/policies/:
      phi.access   — allow for authorized roles with training + audit trail
      phi.export   — escalate (dual officer approval required)
      phi.delete   — escalate (dual approval + supervisor review)
      phi.share    — escalate (Privacy Officer + Legal Counsel required)

    machine_executable=false enforced on phi.export and phi.delete.
    """

    def __init__(self) -> None:
        super().__init__(
            "ask_test_hipaastu0000000000000000000",
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
        reg_ref = stored.get("_regulatory_ref", "45 CFR 164.312")
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
                regulatory_ref=reg_ref,
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
        """Return a V1-shaped response dict for HIPAA Security Rule policy."""

        def _allow(reason: str, reg_ref: str = "45 CFR 164.312") -> dict[str, Any]:
            pt = f"pt_{uuid.uuid4().hex[:16]}"
            return {
                "decision": "allow",
                "permit_token": pt,
                "reasons": [reason],
                "audit_hash": uuid.uuid4().hex[:32],
                "_regulatory_ref": reg_ref,
            }

        def _deny(reason: str) -> dict[str, Any]:
            return {"decision": "deny", "reasons": [reason]}

        def _escalate(reason: str) -> dict[str, Any]:
            return {"decision": "escalate", "reasons": [reason]}

        role = ctx.get("role", "")
        patient_id = ctx.get("patientId", "")
        purpose = ctx.get("accessPurpose", "")

        # ── phi.access (hipaa-001) ────────────────────────────────────────────
        if action == "phi.access":
            if not role:
                return _deny("DENY_NO_ROLE: role is required for ePHI access")
            if role not in AUTHORIZED_PHI_ROLES:
                return _deny(
                    f"DENY_UNAUTHORIZED_ROLE: '{role}' is not authorized for ePHI access "
                    f"per 45 CFR 164.308(a)(4) workforce clearance — minimum necessary access denied"
                )
            if not purpose:
                return _deny(
                    "DENY_PURPOSE_MISSING: access purpose required per 45 CFR 164.514(d) "
                    "minimum necessary standard"
                )
            training_verified = ctx.get("hipaaTrainingCurrent", False)
            if not training_verified:
                return _deny(
                    "DENY_TRAINING_INCOMPLETE: 45 CFR 164.308(a)(5) — workforce must "
                    "complete HIPAA training before ePHI access is granted"
                )
            return _allow(
                f"ePHI access ALLOWED for {role} — patient {patient_id}, "
                f"purpose: {purpose}, training verified",
                reg_ref="45 CFR 164.312(a)(1) / 164.308(a)(5)",
            )

        # ── phi.export (hipaa-002) ────────────────────────────────────────────
        if action == "phi.export":
            if role not in EXPORT_AUTHORIZED_ROLES:
                return _deny(
                    f"DENY_UNAUTHORIZED_ROLE: '{role}' cannot authorize ePHI exports — "
                    f"requires privacy_officer, health_information_manager, ciso, or compliance_officer "
                    f"per 45 CFR 164.312(a)(2)(iv)"
                )
            # machine_executable=false — AI agents blocked
            is_ai_agent = ctx.get("isAiAgent", False)
            if is_ai_agent:
                return _deny(
                    "DENY_MACHINE_NOT_EXECUTABLE: ePHI export cannot be authorized by an "
                    "AI agent — human Privacy Officer and Security Officer dual approval required "
                    "per 45 CFR 164.312(a)(2)(iv)"
                )
            # dual approval required
            second_approver = ctx.get("secondApproverRole", "")
            if not second_approver or second_approver not in DUAL_EXPORT_ROLES:
                return _escalate(
                    "ESCALATE_DUAL_APPROVAL_REQUIRED: 45 CFR 164.312(a) — ePHI export "
                    "requires dual officer approval (Privacy Officer + Security Officer); "
                    "second approver not yet confirmed — request sent for review"
                )
            encryption_verified = ctx.get("encryptionVerified", False)
            if not encryption_verified:
                return _deny(
                    "DENY_ENCRYPTION_MISSING: 45 CFR 164.312(e)(2)(ii) — ePHI must be "
                    "encrypted before export; encryption status not verified"
                )
            return _allow(
                f"ePHI export ALLOWED — dual officer approval: {role} + {second_approver}, "
                f"encryption verified",
                reg_ref="45 CFR 164.312(a)(2)(iv) / 164.312(e)(1)",
            )

        # ── phi.delete (hipaa-003) ────────────────────────────────────────────
        if action == "phi.delete":
            is_ai_agent = ctx.get("isAiAgent", False)
            if is_ai_agent:
                return _deny(
                    "DENY_MACHINE_NOT_EXECUTABLE: ePHI deletion cannot be authorized by an "
                    "AI agent — human Privacy Officer authorization required per "
                    "45 CFR 164.312(c)(1). HITECH §13405(d) limits permissible destruction."
                )
            if role not in {"privacy_officer", "health_information_manager", "ciso"}:
                return _deny(
                    f"DENY_UNAUTHORIZED_ROLE: '{role}' is not authorized to delete ePHI — "
                    f"requires privacy_officer, health_information_manager, or ciso "
                    f"per 45 CFR 164.312(c)"
                )
            return _escalate(
                "ESCALATE_DUAL_APPROVAL_REQUIRED: 45 CFR 164.312(c) — ePHI deletion "
                "requires dual approval (Privacy Officer + supervising clinician) and "
                "supervisor review for retention compliance — request sent for review"
            )

        # ── catch-all ─────────────────────────────────────────────────────────
        return _deny(
            f"DENY_NOT_REGISTERED: action '{action}' is not registered in the "
            "HIPAA Security Rule policy — deny per 45 CFR 164.312(b) audit controls"
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


def _escalated(reason: str) -> None:
    print(f"  ⏸ ESCALATED  {_HOLD_TAG_RE.sub('', reason)}")


def _permit_line(p: Permit) -> None:
    print(f"  ✔ PERMITTED  {p.reason}")
    print(f"               permit_id:   {p.permit_id}")
    print(f"               audit_hash:  {p.audit_hash}")
    print(f"               permit_hash: {p.permit_hash}")


def _execute(msg: str) -> None:
    print(f"               → {msg}")


# ---------------------------------------------------------------------------
# Simulated clinical system state mutations
# Only reachable after protect() returns a verified Permit.
# ---------------------------------------------------------------------------


def _sys_access_phi(patient_id: str, role: str, purpose: str) -> None:
    _execute(f"ePHI record for patient {patient_id} opened in audit-logged viewer")
    _execute(f"access event written to HIPAA audit log (45 CFR 164.312(b))")
    _execute(f"role: {role}, purpose: {purpose}")


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------


def run(client: AtlaSentClient, stub: _HipaaStub | None) -> None:
    _bar("gxp-hipaa-phi-access   HIPAA ePHI Access Authorization Demo")
    print(f"  mode:        {'offline stub' if stub else 'live AtlaSent API'}")
    print(f"  regulation:  45 CFR Part 164 Subpart C — HIPAA Security Rule")
    print(f"  policy pack: hipaa-security (atlasent-gxp-starter/policies/)")

    # 1 ── ALLOW: authorized clinician reads ePHI ────────────────────────────
    _scenario(
        1,
        "phi.access",
        "ALLOWED: authorized clinician with verified training, purpose documented",
    )
    try:
        p = client.protect(
            agent="dr.chen@hospital.example",
            action="phi.access",
            context={
                "role": "clinician",
                "patientId": "PT-20260011-882",
                "accessPurpose": "clinical_treatment",
                "hipaaTrainingCurrent": True,
                "accessScope": "encounter_summary",
                "regulatoryRef": "45 CFR 164.312(a)(1)",
            },
        )
        _permit_line(p)
        _sys_access_phi("PT-20260011-882", "clinician", "clinical_treatment")
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)

    # 2 ── DENY: wrong role attempts ePHI export without dual-officer approval -
    _scenario(
        2,
        "phi.export",
        "BLOCKED: 'data_analyst' role not authorized for ePHI export",
    )
    try:
        client.protect(
            agent="analyst@hospital.example",
            action="phi.export",
            context={
                "role": "data_analyst",  # not in EXPORT_AUTHORIZED_ROLES
                "patientId": "PT-20260011-882",
                "exportFormat": "csv",
                "encryptionVerified": True,
                "regulatoryRef": "45 CFR 164.312(a)(2)(iv)",
            },
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)
        print(f"               evaluation_id: {exc.evaluation_id}")
        _execute("ePHI NOT exported — role authorization denied")

    # 3 ── DENY: AI agent attempts phi.delete (machine_executable=false) ──────
    _scenario(
        3,
        "phi.delete",
        "BLOCKED: AI agent cannot authorize ePHI deletion — machine_executable=false",
    )
    try:
        client.protect(
            agent="ai-cleanup-agent@hospital.example",
            action="phi.delete",
            context={
                "role": "privacy_officer",
                "isAiAgent": True,  # machine_executable=false blocks this
                "patientId": "PT-20260011-882",
                "deletionJustification": "retention_period_expired",
                "regulatoryRef": "45 CFR 164.312(c)(1)",
            },
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)
        print(f"               evaluation_id: {exc.evaluation_id}")
        _execute("ePHI NOT deleted — human Privacy Officer authorization required")

    # 4 ── ESCALATE: privacy officer requests ePHI export (dual approval) ─────
    _scenario(
        4,
        "phi.export",
        "ESCALATED: Privacy Officer export request awaits dual officer sign-off",
    )
    try:
        p = client.protect(
            agent="privacy.officer@hospital.example",
            action="phi.export",
            context={
                "role": "privacy_officer",
                "patientId": "PT-20260011-882",
                "exportFormat": "encrypted_pdf",
                "exportRecipient": "state_health_dept",
                "encryptionVerified": True,
                "isAiAgent": False,
                # secondApproverRole absent — triggers escalate
                "regulatoryRef": "45 CFR 164.312(a)(2)(iv) / 164.312(e)(1)",
            },
        )
        _permit_line(p)
    except AtlaSentDeniedError as exc:
        _escalated(exc.reason) if "ESCALATE" in exc.reason else _blocked(exc.reason)
        print(f"               evaluation_id: {exc.evaluation_id}")
        _execute(
            "ePHI export HELD — approval request queued for Security Officer review"
        )

    # ── Audit trail ─────────────────────────────────────────────────────────
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
            print(f"      reg ref:   {rec.regulatory_ref}")
            print(f"      reason:    {rec.reason}")
            if i < len(chain) - 1:
                print()
        if chain:
            print()
            print(f"  chain length : {len(chain)} events")
            print(f"  head hash    : {chain[-1].audit_hash}")

    _bar()
    print("  Enforcement summary:")
    print("    BLOCKED   2 actions (unauthorized role + AI agent machine_executable=false)")
    print("    ESCALATED 1 action  (dual officer approval required for ePHI export)")
    print("    ALLOWED   1 action  (permit-verified before ePHI access)")
    print()


def main() -> None:
    api_key = os.environ.get("ATLASENT_API_KEY", "")
    if api_key:
        run(AtlaSentClient(api_key=api_key, base_url=os.environ.get("ATLASENT_API_URL", "https://api.atlasent.io/functions/v1")), stub=None)
    else:
        stub = _HipaaStub()
        run(stub, stub)


if __name__ == "__main__":
    main()
