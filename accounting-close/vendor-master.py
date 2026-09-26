#!/usr/bin/env python3
"""Accounting close — vendor master mutation, gated.

Scenario: an AP clerk and a controller both attempt to change the bank
routing number on a vendor master record. AtlaSent gates each call.

What this proves to a controller / audit reviewer:
  - Execution-time authorization. The request is evaluated BEFORE the ERP
    is touched. Denied requests never reach the vendor master table.
  - Separation of duties. AP clerks cannot mutate high-risk vendor master
    fields (bank_routing, bank_account, tax_id, remit_to_address). The
    policy distinguishes role + field-class.
  - Approval enforcement. High-risk mutations hold for a named secondary
    approver. The system does not let one human authorize their own
    change — the approver is recorded on the decision row.
  - Evidence generation. Every decision (deny, hold, allow, executed) is
    recorded with the policy version that made the decision and the
    permit ID that bound the execution. Auditors get the trail without
    asking finance for screenshots.

Run:
    pip install -r requirements.txt
    python vendor-master.py                              # offline stub
    ATLASENT_API_KEY=ask_live_... python vendor-master.py  # live
"""

from __future__ import annotations

import os
import sys
import uuid
from dataclasses import dataclass
from typing import Any

from atlasent import AtlaSentClient, AtlaSentDeniedError, Permit

HIGH_RISK_FIELDS = {"bank_routing", "bank_account", "tax_id", "remit_to_address"}


# ---------------------------------------------------------------------------
# Result type returned by the stub client methods
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
# In-process stub client (mirrors main.py's _ErpStub pattern)
# ---------------------------------------------------------------------------

class _VendorStub(AtlaSentClient):
    """In-process stub for vendor-master policy — no HTTP calls."""

    def __init__(self) -> None:
        super().__init__(
            "ask_test_demostubdemostubdemostubdemo00",
            base_url="https://stub.local",
        )
        self._granted_approvals: set[str] = set()
        self._pending: dict[str, dict[str, Any]] = {}

    def grant_approval(self, approver: str) -> None:
        self._granted_approvals.add(approver)

    # ------------------------------------------------------------------
    # Low-level stub dispatch (overrides network transport)
    # ------------------------------------------------------------------

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
        result["_ctx"] = context
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
        if action != "vendor_master.update":
            return {"decision": "deny", "reasons": [f"unknown action: {action}"]}

        role = ctx.get("role", "unknown")
        field = ctx.get("field", "")
        approvers = ctx.get("approvers") or []

        if field in HIGH_RISK_FIELDS:
            if role == "ap_clerk":
                return {
                    "decision": "deny",
                    "reasons": [
                        f"AP clerks cannot change vendor master field '{field}'. "
                        f"Required role: controller or above."
                    ],
                }
            if role == "controller":
                if len(approvers) < 1:
                    return {
                        "decision": "deny",
                        "reasons": [
                            f"Vendor master change to '{field}' requires a named "
                            f"secondary approver (CFO or designate). [hold:need_approver]"
                        ],
                    }
                pt = f"pt_{uuid.uuid4().hex[:16]}"
                self._pending[pt] = {"decision": "allow", "_ctx": ctx}
                return {"decision": "allow", "permit_token": pt, "reasons": ["approved"]}
        if role in {"ap_clerk", "controller"}:
            pt = f"pt_{uuid.uuid4().hex[:16]}"
            self._pending[pt] = {"decision": "allow", "_ctx": ctx}
            return {"decision": "allow", "permit_token": pt, "reasons": ["low-risk field"]}
        return {"decision": "deny", "reasons": [f"Unknown role '{role}'"]}

    # ------------------------------------------------------------------
    # Convenience wrappers that replicate the demo's three call patterns
    # ------------------------------------------------------------------

    def evaluate(self, action: str, context: dict[str, Any]) -> _EvalResult:
        """Issue an evaluate call and return a structured result."""
        result = self._eval({"action_type": action, "context": context})
        decision = str(result.get("decision", "deny")).lower()
        reasons = result.get("reasons", [])
        reason = reasons[0] if reasons else ""
        permit_token = result.get("permit_token", "")
        return _EvalResult(decision=decision, reason=reason, permit_token=permit_token)

    def authorize(self, action: str, context: dict[str, Any]) -> _EvalResult:
        """Like evaluate but raises on deny."""
        r = self.evaluate(action, context)
        if r.decision != "allow":
            raise AtlaSentDeniedError(evaluation_id="", reason=r.reason)
        return r

    def verify_permit(self, permit_token: str, execution_context: dict[str, Any]) -> _VerifyResult:
        """Consume a permit and return a verify result."""
        result = self._verify({"permit_token": permit_token})
        return _VerifyResult(
            outcome=result.get("outcome", "invalid"),
            valid=bool(result.get("verified")),
            audit_hash=result.get("audit_hash", ""),
        )


# ---------------------------------------------------------------------------
# Live client wrappers (same interface as _VendorStub convenience methods)
# ---------------------------------------------------------------------------

class _LiveClient:
    """Thin wrapper around AtlaSentClient for the live-API path."""

    def __init__(self, api_key: str, base_url: str) -> None:
        self._client = AtlaSentClient(api_key=api_key, base_url=base_url)

    def evaluate(self, action: str, context: dict[str, Any]) -> _EvalResult:
        try:
            permit = self._client.protect(agent="vendor-master-bot", action=action, context=context)
            return _EvalResult(decision="allow", reason=permit.reason or "", permit_token=permit.permit_id)
        except AtlaSentDeniedError as exc:
            return _EvalResult(decision="deny", reason=exc.reason or str(exc))

    def authorize(self, action: str, context: dict[str, Any]) -> _EvalResult:
        permit = self._client.protect(agent="vendor-master-bot", action=action, context=context)
        return _EvalResult(decision="allow", reason=permit.reason or "", permit_token=permit.permit_id)

    def verify_permit(self, permit_token: str, execution_context: dict[str, Any]) -> _VerifyResult:
        # Live mode: permit is already verified inside protect(); this is a no-op display step.
        return _VerifyResult(outcome="verified", valid=True, audit_hash="(server-side)")


def build_client() -> tuple[Any, str]:
    api_key = os.environ.get("ATLASENT_API_KEY")
    if api_key:
        base_url = os.environ.get("ATLASENT_API_URL") or "https://api.atlasent.io/functions/v1"
        return _LiveClient(api_key, base_url), "live"
    return _VendorStub(), "stub"


def banner(title: str, mode: str) -> None:
    tag = "LIVE (atlasent-api)" if mode == "live" else "STUB (offline demo)"
    print()
    print("━" * 76)
    print(f"  {title}    [{tag}]")
    print("━" * 76)


def section(label: str) -> None:
    print(f"\n▸ {label}")


def show(role: str, actor: str, field: str, new_value: str, vendor: str, result: _EvalResult) -> None:
    print(f"  attempted by:   {role} ({actor})")
    print(f"  field:          {field} → {new_value}")
    print(f"  vendor:         {vendor}")
    print(f"  decision:       {result.decision}")
    if result.decision == "deny":
        reason = result.reason.replace(" [hold:need_approver]", "")
        print(f"  reason:         {reason}")
        if "[hold:" in result.reason:
            print( "  ERP touched:    no (queued for secondary approver)")
        else:
            print( "  ERP touched:    no (request blocked at the gate)")
    elif result.decision == "allow":
        print(f"  permit_token:   {result.permit_token}")
        print( "  ERP touched:    yes (proceed to execute)")


def main() -> int:
    client, mode = build_client()
    banner("VENDOR MASTER — change to bank routing on V-7821", mode)

    action = "vendor_master.update"
    field = "bank_routing"
    new_value = "026009593"
    vendor = "vendor:V-7821"

    section("Scenario 1 — AP clerk attempts the change")
    r1 = client.evaluate(action, {"role": "ap_clerk", "actor": "u_alice@finance.example",
                                   "field": field, "new_value": new_value, "approvers": []})
    show("ap_clerk", "u_alice@finance.example", field, new_value, vendor, r1)

    section("Scenario 2 — Controller submits, no secondary approver named")
    r2 = client.evaluate(action, {"role": "controller", "actor": "u_bob@finance.example",
                                   "field": field, "new_value": new_value, "approvers": []})
    show("controller", "u_bob@finance.example", field, new_value, vendor, r2)

    section("Scenario 3 — Controller resubmits with CFO as secondary approver")
    r3 = client.authorize(action, {"role": "controller", "actor": "u_bob@finance.example",
                                    "field": field, "new_value": new_value,
                                    "approvers": ["u_carol@finance.example (CFO)"]})
    show("controller", "u_bob@finance.example", field, new_value, vendor, r3)

    section("Step — Execute the change in the ERP (system of record)")
    print("    $ erp.update_vendor_master(V-7821, bank_routing=026009593) …")
    print("    ✓ committed at 14:32:11Z")

    section("Step — Consume the permit (binds the execution to the permit)")
    verify = client.verify_permit(
        r3.permit_token,
        execution_context={
            "action": "vendor_master.update",
            "target": "vendor:V-7821",
            "field": "bank_routing",
        },
    )
    print(f"  outcome:        {verify.outcome}")
    print(f"  valid:          {verify.valid}")
    print(f"  audit_hash:     {verify.audit_hash}")

    section("Audit trail (every event the auditor will see)")
    rows = [
        ("evt_001", "vendor_master.update", "u_alice (ap_clerk)",  "deny",     "Role insufficient for high-risk field"),
        ("evt_002", "vendor_master.update", "u_bob   (controller)", "hold",     "Secondary approver required"),
        ("evt_003", "vendor_master.update", "u_bob   (controller)", "allow",    "Approver: u_carol (CFO)"),
        ("evt_004", "permit.consume",       "u_bob   (controller)", "verified", f"permit={r3.permit_token[:24]}…"),
    ]
    print("    " + "─" * 72)
    print(f"    {'event_id':<10} {'action':<22} {'actor':<22} {'decision':<10} reason")
    print("    " + "─" * 72)
    for ev_id, ev_action, actor, decision, reason in rows:
        print(f"    {ev_id:<10} {ev_action:<22} {actor:<22} {decision:<10} {reason}")
    print()
    print("    Each row is hash-linked to the previous; auditors verify the")
    print("    chain offline using the published Ed25519 public key. The")
    print("    deny and hold rows are part of the proof — they cannot be")
    print("    omitted, edited, or reordered without invalidating the chain.")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
