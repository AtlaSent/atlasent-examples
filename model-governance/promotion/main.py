#!/usr/bin/env python3
"""model-governance-promotion: ML Model Promotion Authorization Demo

Demonstrates non-bypassable authorization for ML model promotion to production
using the AtlaSent SDK fail-closed enforcement model.

Three scenarios:
  1. ALLOW  — validated model with safety sign-off, staged, all checks passing
  2. DENY   — model with failing safety checks (safetyChecksPassed=False)
  3. DENY   — production promote without prior staging validation

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

AUTHORIZED_MODEL_APPROVERS: frozenset[str] = frozenset(
    {
        "ml.lead@acme.com",
        "ml.director@acme.com",
        "ai.safety@acme.com",
        "mlops.lead@acme.com",
    }
)
SAFETY_SIGN_OFF_REQUIRED: frozenset[str] = frozenset({"ai.safety@acme.com"})

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


class _ModelGovStub(AtlaSentClient):
    """In-process stub — no HTTP calls, deterministic policy engine.

    Overrides ``_request`` to handle evaluate / verify locally.
    Implements the ml.model.promote policy:
      - fail_closed: true
      - machine_executable: false (ML lead + safety sign-off required)
      - safetyChecksPassed must be true
      - stagingValidationComplete must be true for production target
      - approvedBy must be on the authorized approver list
      - safetySignOffBy must be on the safety sign-off list
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
        """Return a V1-shaped response dict for ml.model.promote policy."""

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

        if action != "ml.model.promote":
            return deny(f"action '{action}' not registered in model-governance policy")

        model_id = ctx.get("modelId", "")
        model_version = ctx.get("modelVersion", "")
        target_environment = ctx.get("targetEnvironment", "")
        approved_by = ctx.get("approvedBy", "")
        safety_sign_off_by = ctx.get("safetySignOffBy", "")
        safety_checks_passed = ctx.get("safetyChecksPassed", False)
        staging_validation_complete = ctx.get("stagingValidationComplete", False)
        risk_tier = ctx.get("riskTier", "")
        eval_report_uri = ctx.get("evalReportUri", "")

        # Required field checks
        if not model_id:
            return deny("DENY_MISSING_FIELD: missing required field: modelId")
        if not model_version:
            return deny("DENY_MISSING_FIELD: missing required field: modelVersion")
        if not target_environment:
            return deny("DENY_MISSING_FIELD: missing required field: targetEnvironment")
        if not approved_by:
            return deny("DENY_MISSING_FIELD: missing required field: approvedBy")

        # Safety checks must pass
        if not safety_checks_passed:
            return deny(
                f"DENY_SAFETY_CHECKS_FAILED: model {model_id} v{model_version} has "
                f"failing safety checks — all safety evaluations must pass before "
                f"promotion; review the safety evaluation report and remediate failures"
            )

        # Safety sign-off required from designated safety reviewer
        if not safety_sign_off_by:
            return deny(
                f"DENY_SAFETY_SIGNOFF_MISSING: model {model_id} v{model_version} "
                f"requires a safety sign-off — safetySignOffBy is absent"
            )
        if safety_sign_off_by not in SAFETY_SIGN_OFF_REQUIRED:
            return deny(
                f"DENY_SAFETY_SIGNOFF_MISSING: '{safety_sign_off_by}' is not on the "
                f"authorized safety sign-off list — AI safety reviewer sign-off required"
            )

        # Staging validation required for production targets
        if target_environment == "production" and not staging_validation_complete:
            return deny(
                f"DENY_STAGING_VALIDATION_MISSING: promotion of {model_id} v{model_version} "
                f"to production requires stagingValidationComplete=true — complete "
                f"staging validation before promoting to production"
            )

        # Approver authorization check
        if approved_by not in AUTHORIZED_MODEL_APPROVERS:
            return deny(
                f"DENY_AUTHORITY: '{approved_by}' is not on the authorized model "
                f"approver list — ML lead or director sign-off required"
            )

        if not eval_report_uri:
            return deny("DENY_MISSING_FIELD: missing required field: evalReportUri")

        risk_note = f" [risk_tier={risk_tier}]" if risk_tier else ""
        return allow(
            f"model {model_id} v{model_version} promoted to {target_environment} "
            f"by {approved_by} (safety={safety_sign_off_by}){risk_note}"
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
# Simulated model registry state mutations
# Only reachable after protect() returns a verified Permit.
# ---------------------------------------------------------------------------


def _sys_promote_model(
    model_id: str,
    model_version: str,
    target_environment: str,
    approved_by: str,
) -> None:
    _execute(
        f"model {model_id} v{model_version} status set to "
        f"PROMOTED:{target_environment.upper()}"
    )
    _execute(f"model registry updated by {approved_by}")
    _execute("deployment pipeline triggered for target environment")
    _execute("promotion certificate written to audit store")


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------


def run(client: AtlaSentClient, stub: _ModelGovStub | None) -> None:
    _bar("model-governance-promotion   ML Model Promotion Authorization Demo")
    print(f"  mode:   {'offline stub' if stub else 'live AtlaSent API'}")
    print(f"  action: ml.model.promote")
    print(f"  policy: fail-closed, safety sign-off required, staging gate for production")

    # 1 ── ALLOW: validated model with safety sign-off ------------------------
    _scenario(
        1,
        "ml.model.promote",
        "ALLOWED: validated model, safety sign-off present, staging complete",
    )
    try:
        p = client.protect(
            agent="ml.lead@acme.com",
            action="ml.model.promote",
            context={
                "modelId": "fraud-detection-v3",
                "modelVersion": "3.2.1",
                "targetEnvironment": "production",
                "approvedBy": "ml.lead@acme.com",
                "safetySignOffBy": "ai.safety@acme.com",
                "safetyChecksPassed": True,
                "stagingValidationComplete": True,
                "riskTier": "high",
                "evalReportUri": "s3://ml-governance/fraud-detection-v3/eval-report-3.2.1.pdf",
                "biasAuditComplete": True,
                "fairnessScore": 0.94,
            },
        )
        _permit_line(p)
        _sys_promote_model(
            "fraud-detection-v3", "3.2.1", "production", "ml.lead@acme.com"
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)

    # 2 ── DENY: failing safety checks ----------------------------------------
    _scenario(
        2,
        "ml.model.promote",
        "BLOCKED: safetyChecksPassed=False — safety evaluation failures must be remediated",
    )
    try:
        client.protect(
            agent="ml.lead@acme.com",
            action="ml.model.promote",
            context={
                "modelId": "content-classifier-v2",
                "modelVersion": "2.0.4",
                "targetEnvironment": "production",
                "approvedBy": "ml.lead@acme.com",
                "safetySignOffBy": "ai.safety@acme.com",
                "safetyChecksPassed": False,  # <-- safety checks failing
                "stagingValidationComplete": True,
                "riskTier": "high",
                "evalReportUri": "s3://ml-governance/content-classifier-v2/eval-report-2.0.4.pdf",
                "failedSafetyChecks": ["bias_audit", "adversarial_robustness"],
            },
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)
        print(f"               evaluation_id: {exc.evaluation_id}")
        _execute("model NOT promoted — remediate safety failures before retrying")

    # 3 ── DENY: production promote without staging validation ----------------
    _scenario(
        3,
        "ml.model.promote",
        "BLOCKED: stagingValidationComplete=False for production target",
    )
    try:
        client.protect(
            agent="ml.lead@acme.com",
            action="ml.model.promote",
            context={
                "modelId": "recommendation-engine-v5",
                "modelVersion": "5.1.0",
                "targetEnvironment": "production",
                "approvedBy": "ml.lead@acme.com",
                "safetySignOffBy": "ai.safety@acme.com",
                "safetyChecksPassed": True,
                "stagingValidationComplete": False,  # <-- no staging validation
                "riskTier": "medium",
                "evalReportUri": "s3://ml-governance/reco-v5/eval-report-5.1.0.pdf",
            },
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)
        print(f"               evaluation_id: {exc.evaluation_id}")
        _execute("model NOT promoted — complete staging validation first")

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
    print("    BLOCKED  2 actions (failing safety checks / no staging validation)")
    print("    ALLOWED  1 action  (permit-verified before model promotion)")
    print()


def main() -> None:
    api_key = os.environ.get("ATLASENT_API_KEY", "")
    if api_key:
        run(AtlaSentClient(api_key=api_key, base_url=os.environ.get("ATLASENT_API_URL", "https://api.atlasent.io/functions/v1")), stub=None)
    else:
        stub = _ModelGovStub()
        run(stub, stub)


if __name__ == "__main__":
    main()
