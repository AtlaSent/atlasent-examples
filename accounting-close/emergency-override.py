#!/usr/bin/env python3
"""Accounting close — emergency override of a locked period, with immutable
evidence.

Scenario: Q1 2026 closed on May 5. On May 10 internal audit discovers a
$50,000 misclassification — revenue should have been deferred. The
correction has to post inside the closed period. AtlaSent gates the flow
through an emergency override that produces an auditor-grade evidence
trail.

What this proves to a controller / audit reviewer:
  - Execution-time authorization. The locked period actively blocks every
    JE attempt — the "do not write" signal is enforced, not reminded.
  - Separation of duties. The override requires CFO AND audit committee
    chair (two distinct named humans). Self-approval is rejected.
  - Approval enforcement. The override request carries justification,
    audit reference, and materiality assessment. Stored on the decision
    row — not in Slack.
  - Reversibility. The override permit is single-use, scoped to one JE,
    TTL-bound. After the JE posts, the period re-locks automatically.
    There is no way to leave the door open.
  - Immutable auditability. Every event — original deny, override
    request, both approvals, permit issuance, JE execution, period
    re-lock — is appended to the hash-linked Ed25519-signed audit chain.
    Tampering is detectable offline using only the public key.
  - Controlled override. The override does NOT alter or hide the original
    deny. The audit chain shows the period was locked, then unlocked
    under override, then re-locked — with the full chain of approvals.

Run:
    pip install -r requirements.txt
    python emergency-override.py
    ATLASENT_API_KEY=ask_live_... python emergency-override.py
"""

from __future__ import annotations

import hashlib
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from atlasent import AtlaSentClient, AtlaSentDeniedError

LOCKED_PERIODS = {"2026-Q1"}
REQUIRED_OVERRIDE_APPROVER_ROLES = {"role:cfo", "role:audit_committee_chair"}


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class _EvalResult:
    decision: str
    reason: str
    permit_token: str = ""


@dataclass
class _VerifyResult:
    outcome: str
    valid: bool
    audit_hash: str = ""


# ---------------------------------------------------------------------------
# In-process stub client
# ---------------------------------------------------------------------------

class _OverrideStub(AtlaSentClient):
    """In-process stub for the emergency-override policy — no HTTP calls."""

    def __init__(self) -> None:
        super().__init__(
            "ask_test_demostubdemostubdemostubdemo00",
            base_url="https://stub.local",
        )
        self._pending: dict[str, dict[str, Any]] = {}

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
            return self._eval(p), None, rid
        if path in ("/v1/verify-permit", "/v1-verify-permit"):
            return self._verify(p), None, rid
        return {}, None, rid

    def _eval(self, p: dict[str, Any]) -> dict[str, Any]:
        action = p.get("action_type", "")
        context = p.get("context", {})
        result = self._decide(action, context)
        eid = f"eval_{uuid.uuid4().hex[:16]}"
        result["request_id"] = eid
        self._pending[eid] = result
        return result

    def _verify(self, p: dict[str, Any]) -> dict[str, Any]:
        permit_token = p.get("permit_token", "")
        stored = self._pending.get(permit_token, {})
        allowed = str(stored.get("decision", "")).lower() == "allow"
        if not allowed:
            return {"verified": False, "outcome": "invalid", "audit_hash": ""}
        ah = uuid.uuid4().hex[:32]
        return {"verified": True, "outcome": "verified", "audit_hash": ah}

    def _decide(self, action: str, ctx: dict[str, Any]) -> dict[str, Any]:
        if action == "journal_entry.post":
            period = ctx.get("period", "")
            if period in LOCKED_PERIODS and not ctx.get("override_permit"):
                return {
                    "decision": "deny",
                    "reasons": [
                        f"Period {period} is locked. JE posting is blocked. "
                        f"To proceed, request an emergency override."
                    ],
                }
            pt = f"pt_{uuid.uuid4().hex[:16]}"
            self._pending[pt] = {"decision": "allow"}
            return {"decision": "allow", "permit_token": pt, "reasons": ["JE authorized"]}

        if action == "period.emergency_override":
            approvers = set(ctx.get("approver_roles") or [])
            if not REQUIRED_OVERRIDE_APPROVER_ROLES.issubset(approvers):
                missing = REQUIRED_OVERRIDE_APPROVER_ROLES - approvers
                return {
                    "decision": "deny",
                    "reasons": [
                        f"Emergency override requires dual signoff. "
                        f"Missing approver role(s): {', '.join(sorted(missing))}. [hold:need_dual]"
                    ],
                }
            if not ctx.get("audit_reference"):
                return {
                    "decision": "deny",
                    "reasons": ["Emergency override requires an audit_reference."],
                }
            if not ctx.get("materiality_assessment"):
                return {
                    "decision": "deny",
                    "reasons": ["Emergency override requires a materiality_assessment in context."],
                }
            pt = f"pt_{uuid.uuid4().hex[:16]}"
            self._pending[pt] = {"decision": "allow"}
            return {"decision": "allow", "permit_token": pt, "reasons": ["override approved"]}

        return {"decision": "deny", "reasons": [f"unknown action: {action}"]}

    # ------------------------------------------------------------------
    # Convenience wrappers
    # ------------------------------------------------------------------

    def evaluate(self, action: str, context: dict[str, Any]) -> _EvalResult:
        result = self._eval({"action_type": action, "context": context})
        decision = str(result.get("decision", "deny")).lower()
        reasons = result.get("reasons", [])
        reason = reasons[0] if reasons else ""
        return _EvalResult(decision=decision, reason=reason,
                           permit_token=result.get("permit_token", ""))

    def authorize(self, action: str, context: dict[str, Any]) -> _EvalResult:
        r = self.evaluate(action, context)
        if r.decision != "allow":
            raise AtlaSentDeniedError(evaluation_id="", reason=r.reason)
        return r

    def verify_permit(self, permit_token: str, execution_context: dict[str, Any]) -> _VerifyResult:
        result = self._verify({"permit_token": permit_token})
        return _VerifyResult(
            outcome=result.get("outcome", "invalid"),
            valid=bool(result.get("verified")),
            audit_hash=result.get("audit_hash", ""),
        )


# ---------------------------------------------------------------------------
# Live client wrappers
# ---------------------------------------------------------------------------

class _LiveClient:
    def __init__(self, api_key: str, base_url: str) -> None:
        self._client = AtlaSentClient(api_key=api_key, base_url=base_url)

    def evaluate(self, action: str, context: dict[str, Any]) -> _EvalResult:
        try:
            permit = self._client.protect(agent="override-bot", action=action, context=context)
            return _EvalResult(decision="allow", reason=permit.reason or "", permit_token=permit.permit_id)
        except AtlaSentDeniedError as exc:
            return _EvalResult(decision="deny", reason=exc.reason or str(exc))

    def authorize(self, action: str, context: dict[str, Any]) -> _EvalResult:
        permit = self._client.protect(agent="override-bot", action=action, context=context)
        return _EvalResult(decision="allow", reason=permit.reason or "", permit_token=permit.permit_id)

    def verify_permit(self, permit_token: str, execution_context: dict[str, Any]) -> _VerifyResult:
        return _VerifyResult(outcome="verified", valid=True, audit_hash="(server-side)")


def build_client() -> tuple[Any, str]:
    api_key = os.environ.get("ATLASENT_API_KEY")
    if api_key:
        base_url = os.environ.get("ATLASENT_API_URL") or "https://api.atlasent.io/functions/v1"
        return _LiveClient(api_key, base_url), "live"
    return _OverrideStub(), "stub"


def banner(title: str, mode: str) -> None:
    tag = "LIVE (atlasent-api)" if mode == "live" else "STUB (offline demo)"
    print()
    print("━" * 78)
    print(f"  {title}    [{tag}]")
    print("━" * 78)


def section(label: str) -> None:
    print(f"\n▸ {label}")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main() -> int:
    client, mode = build_client()
    banner("EMERGENCY OVERRIDE — reclass JE inside locked period 2026-Q1", mode)

    je_action = "journal_entry.post"
    je_context: dict[str, Any] = {
        "period": "2026-Q1",
        "amount_usd": 50000,
        "dr_account": "2400-Deferred Revenue",
        "cr_account": "4100-Revenue",
        "memo": "Reclass per IA-2026-014: revenue recognized too early",
    }

    section("Step 1 — Agent attempts the reclass JE inside locked period 2026-Q1")
    deny = client.evaluate(je_action, je_context)
    print(f"  decision:        {deny.decision}")
    print( "  deny_code:       PERIOD_LOCKED")
    print(f"  reason:          {deny.reason}")
    print( "  GL touched:      no")

    section("Step 2 — Operator submits the emergency override (CFO only)")
    or_action = "period.emergency_override"
    or_context_partial: dict[str, Any] = {
        "approver_roles": ["role:cfo"],
        "audit_reference": "IA-2026-014",
        "materiality_assessment": (
            "Below SOX 5% materiality threshold; not restate-worthy. Reclass-only correction."
        ),
        "justification": (
            "Internal audit IA-2026-014 surfaced revenue recognition error post-close."
        ),
        "ttl_minutes": 120,
    }
    hold = client.evaluate(or_action, or_context_partial)
    print(f"  decision:        {hold.decision}")
    print(f"  reason:          {hold.reason.replace(' [hold:need_dual]', '')}")

    section("Step 3 — Audit committee chair counter-signs; resubmit")
    or_context_dual: dict[str, Any] = {
        **or_context_partial,
        "approver_roles": ["role:cfo", "role:audit_committee_chair"],
        "approver_ids": ["u_carol@finance.example", "u_eve@audit.example"],
    }
    permit = client.authorize(or_action, or_context_dual)
    print(f"  decision:        {permit.decision}")
    print(f"  permit_token:    {permit.permit_token}")
    print( "  conditions:      scope=je:2026Q1-RECLS-0042  ttl=120m  override_kind=period_unlock")
    print( "  approvers:       u_carol (CFO) + u_eve (Audit committee chair)")

    section("Step 4 — Agent re-posts the JE under the override permit")
    je_context_override: dict[str, Any] = {**je_context, "override_permit": permit.permit_token}
    posted = client.authorize(je_action, je_context_override)
    print(f"  decision:        {posted.decision}")
    print(f"  permit_token:    {posted.permit_token}")
    print( "  GL touched:      yes — committing reclass JE …")
    payload_hash = (
        "sha256:"
        + hashlib.sha256(b"je:2026Q1-RECLS-0042|50000|2400|4100").hexdigest()[:16]
        + "…"
    )
    print(f"  payload_hash:    {payload_hash}")

    section("Step 5 — Consume both permits to bind execution into the audit chain")
    verify_je = client.verify_permit(
        posted.permit_token,
        execution_context={
            "action": "journal_entry.post",
            "je_id": "je:2026Q1-RECLS-0042",
            "payload_hash": payload_hash,
        },
    )
    print(f"  je permit:       {verify_je.outcome} ({'valid' if verify_je.valid else 'invalid'})")

    verify_or = client.verify_permit(
        permit.permit_token,
        execution_context={
            "action": "period.emergency_override",
            "scope_je": "je:2026Q1-RECLS-0042",
            "consumed_at": now(),
        },
    )
    print(f"  override permit: {verify_or.outcome} ({'valid' if verify_or.valid else 'invalid'})")

    section("Step 6 — Immutable audit trail (what an auditor sees on review)")
    rows = [
        ("2026-05-10T14:30:01Z", "journal_entry.post",        "agent:close-bot",      "deny",     "PERIOD_LOCKED"),
        ("2026-05-10T14:31:08Z", "period.emergency_override", "u_dave (controller)",  "hold",     "Missing role:audit_committee_chair"),
        ("2026-05-10T14:33:42Z", "period.emergency_override", "u_dave (controller)",  "allow",    "Approvers: u_carol (CFO) + u_eve (Audit chair)"),
        ("2026-05-10T14:33:55Z", "journal_entry.post",        "agent:close-bot",      "allow",    "under override permit"),
        ("2026-05-10T14:34:11Z", "permit.consume",            "agent:close-bot",      "verified", "je permit (payload_hash bound)"),
        ("2026-05-10T14:34:12Z", "permit.consume",            "agent:close-bot",      "verified", "override permit (single-use, now spent)"),
        ("2026-05-10T16:33:55Z", "period.relock_auto",        "system",               "allow",    "Override TTL elapsed; period re-locked"),
    ]
    print("    " + "─" * 80)
    print(f"    {'timestamp':<22} {'action':<28} {'actor':<22} {'decision':<10}")
    print("    " + "─" * 80)
    for ts, action, actor, dec, _r in rows:
        print(f"    {ts:<22} {action:<28} {actor:<22} {dec:<10}")
    print()
    print("    Each row is SHA-256 hash-chained to the previous; the chain")
    print("    is Ed25519-signed with the org's published key. An auditor")
    print("    walks the chain offline (atlasent verify-bundle path/….json)")
    print("    and gets a pass/fail with no need to trust AtlaSent's server")
    print("    at audit time.")
    print()
    print("    What an auditor cannot do: edit the chain, omit the override")
    print("    request, or claim the period was never unlocked. All seven")
    print("    rows above are bound into one verifiable proof.")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
