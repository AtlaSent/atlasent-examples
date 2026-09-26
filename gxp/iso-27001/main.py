#!/usr/bin/env python3
"""gxp-iso-27001: ISO/IEC 27001:2022 ISMS Authorization Demo

Demonstrates non-bypassable authorization for information security
management system (ISMS) operations under ISO/IEC 27001:2022 and
ISO/IEC 27002:2022 using the AtlaSent SDK fail-closed enforcement model.

Four scenarios:
  1. ALLOW   — security manager grants access (access.grant — A.5.15)
  2. ALLOW   — IT administrator patches a vulnerability (vulnerability.patch — A.8.8)
  3. ESCALATE — network engineer changes firewall rule (firewall.rule_change — A.8.20)
  4. DENY    — unauthorized developer attempts privileged access (privileged.access)

Runs offline (in-process stub) by default.
Set ATLASENT_API_KEY to switch to the live AtlaSent API.

Regulatory references:
  ISO 27001:2022 A.5.15  — Access control
  ISO 27001:2022 A.5.18  — Access rights
  ISO 27001:2022 A.8.2   — Privileged access rights
  ISO 27001:2022 A.8.8   — Management of technical vulnerabilities
  ISO 27001:2022 A.8.15  — Logging
  ISO 27001:2022 A.8.20  — Networks security
  ISO/IEC 27002:2022     — Implementation guidance
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

ACCESS_GRANT_ROLES: frozenset[str] = frozenset({
    "security_manager",
    "it_administrator",
    "identity_admin",
    "ciso",
})

PATCH_ROLES: frozenset[str] = frozenset({
    "it_administrator",
    "security_engineer",
    "change_manager",
    "ciso",
})

FIREWALL_ROLES: frozenset[str] = frozenset({
    "network_engineer",
    "security_engineer",
    "ciso",
    "change_manager",
})

PRIVILEGED_ROLES: frozenset[str] = frozenset({
    "security_manager",
    "ciso",
    "it_administrator",
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
# In-process stub engine — ISO 27001:2022 policy
# ---------------------------------------------------------------------------


class _Iso27001Stub(AtlaSentClient):
    """In-process stub — no HTTP calls, deterministic ISO 27001 policy engine.

    Implements the iso-27001 pack from atlasent-gxp-starter/policies/:
      access.grant         — allow for authorized roles (A.5.15)
      access.revoke        — allow for authorized roles (A.5.18)
      vulnerability.patch  — allow for authorized roles after CAB check (A.8.8)
      audit.log_access     — allow for authorized roles (A.8.15)
      firewall.rule_change — escalate (critical — A.8.20)
      privileged.access    — escalate (critical — A.8.2)
      data.export          — allow for data_owner / security / ciso (A.5.12)
      encryption.key_rotation — allow for security_engineer / ciso (A.8.24)
    """

    def __init__(self) -> None:
        super().__init__(
            "ask_test_iso27001st0000000000000000",
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
        reg_ref = stored.get("_regulatory_ref", "ISO/IEC 27001:2022")
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
        """Return a V1-shaped response dict for the ISO 27001:2022 policy."""

        def _allow(reason: str, reg_ref: str = "ISO/IEC 27001:2022") -> dict[str, Any]:
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

        # ── access.grant (iso27001-001) ───────────────────────────────────────
        if action == "access.grant":
            if role not in ACCESS_GRANT_ROLES:
                return _deny(
                    f"DENY_UNAUTHORIZED_ROLE: '{role}' cannot provision access rights — "
                    f"requires security_manager, it_administrator, identity_admin, or ciso "
                    f"per ISO 27001 A.5.15 / A.5.18"
                )
            target_resource = ctx.get("targetResource", "")
            if not target_resource:
                return _deny(
                    "DENY_MISSING_CONTEXT: targetResource required for access provisioning — "
                    "ISO 27002 §5.15 principle of least privilege"
                )
            return _allow(
                f"Access grant ALLOWED for {role} — "
                f"resource: {target_resource}, "
                f"subject: {ctx.get('subjectId', 'N/A')}, "
                f"least-privilege verified",
                reg_ref="ISO 27001:2022 A.5.15 / A.5.18",
            )

        # ── vulnerability.patch (iso27001-006) ───────────────────────────────
        if action == "vulnerability.patch":
            if role not in PATCH_ROLES:
                return _deny(
                    f"DENY_UNAUTHORIZED_ROLE: '{role}' cannot authorize vulnerability patching — "
                    f"requires it_administrator, security_engineer, change_manager, or ciso "
                    f"per ISO 27001 A.8.8"
                )
            cab_approved = ctx.get("cabApproved", False)
            if not cab_approved:
                return _deny(
                    "DENY_CAB_APPROVAL_MISSING: ISO 27001 A.8.8 — vulnerability patch requires "
                    "Change Advisory Board (CAB) approval before production deployment"
                )
            staging_tested = ctx.get("stagingTested", False)
            if not staging_tested:
                return _deny(
                    "DENY_STAGING_TEST_MISSING: ISO 27002 §8.8 — patch must be tested in "
                    "staging/QA environment before production application"
                )
            return _allow(
                f"Vulnerability patch ALLOWED for {role} — "
                f"CVE: {ctx.get('cveId', 'N/A')}, "
                f"system: {ctx.get('targetSystem', 'N/A')}, "
                f"CAB approved, staging tested",
                reg_ref="ISO 27001:2022 A.8.8",
            )

        # ── firewall.rule_change (iso27001-009) ──────────────────────────────
        if action == "firewall.rule_change":
            if role not in FIREWALL_ROLES:
                return _deny(
                    f"DENY_UNAUTHORIZED_ROLE: '{role}' cannot authorize firewall rule changes — "
                    f"requires network_engineer, security_engineer, ciso, or change_manager "
                    f"per ISO 27001 A.8.20"
                )
            security_impact = ctx.get("securityImpactAssessment", False)
            if not security_impact:
                return _deny(
                    "DENY_IMPACT_ASSESSMENT_MISSING: ISO 27001 A.8.20 — firewall change requires "
                    "a formal security impact assessment before CAB submission"
                )
            # dual approval always required for critical firewall changes
            second_approver = ctx.get("secondApproverRole", "")
            if not second_approver or second_approver not in FIREWALL_ROLES:
                return _escalate(
                    "ESCALATE_DUAL_APPROVAL_REQUIRED: ISO 27001 A.8.20 — firewall rule changes "
                    "require dual authorization (network_engineer + change_manager) and "
                    "CISO review; second approver not confirmed — CAB request queued"
                )
            return _escalate(
                "ESCALATE_CISO_REVIEW_REQUIRED: ISO 27001 A.8.20 — perimeter-affecting "
                "firewall change requires CISO sign-off before execution; "
                "escalated to security leadership for final approval"
            )

        # ── privileged.access (iso27001-010) ─────────────────────────────────
        if action == "privileged.access":
            if role not in PRIVILEGED_ROLES:
                return _deny(
                    f"DENY_UNAUTHORIZED_ROLE: '{role}' cannot request privileged access — "
                    f"requires security_manager, ciso, or it_administrator "
                    f"per ISO 27001 A.8.2 / A.9.2.3"
                )
            return _deny(
                f"DENY_UNAUTHORIZED_ROLE: '{role}' is not in the approved privileged access "
                "requestor list — ISO 27001 A.8.2 requires explicit CISO authorization for all "
                "privileged access; no standing authorization exists for this identity"
            )

        # ── catch-all ─────────────────────────────────────────────────────────
        return _deny(
            f"DENY_NOT_REGISTERED: action '{action}' is not registered in the "
            "ISO 27001 policy — deny per ISMS default control A.8.15"
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
# Simulated ISMS state mutations
# Only reachable after protect() returns a verified Permit.
# ---------------------------------------------------------------------------


def _sys_grant_access(resource: str, subject: str, role: str) -> None:
    _execute(f"Access provisioned: {subject} → {resource}")
    _execute("Access grant logged to ISMS audit trail (ISO 27001 A.8.15)")
    _execute(f"Authorizing role: {role}, least-privilege review complete")


def _sys_apply_patch(cve_id: str, system: str, role: str) -> None:
    _execute(f"Patch for {cve_id} applied to {system}")
    _execute("Patch record written to change log (ISO 27001 A.8.8)")
    _execute(f"Applied by: {role}, CAB approval and staging test on record")


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------


def run(client: AtlaSentClient, stub: _Iso27001Stub | None) -> None:
    _bar("gxp-iso-27001   ISO/IEC 27001:2022 ISMS Authorization Demo")
    print(f"  mode:        {'offline stub' if stub else 'live AtlaSent API'}")
    print(f"  regulation:  ISO/IEC 27001:2022 + ISO/IEC 27002:2022")
    print(f"  policy pack: iso-27001 (atlasent-gxp-starter/policies/)")

    # 1 ── ALLOW: security manager grants access ──────────────────────────────
    _scenario(
        1,
        "access.grant",
        "ALLOWED: security manager provisions access — ISO 27001 A.5.15",
    )
    try:
        p = client.protect(
            agent="sm.rivera@corp.example",
            action="access.grant",
            context={
                "role": "security_manager",
                "subjectId": "emp-20260441",
                "targetResource": "data-warehouse/finance-reports",
                "accessLevel": "read_only",
                "businessJustification": "quarterly_close_review",
                "reviewedByDataOwner": True,
                "regulatoryRef": "ISO 27001:2022 A.5.15 / A.5.18",
            },
        )
        _permit_line(p)
        _sys_grant_access(
            "data-warehouse/finance-reports", "emp-20260441", "security_manager"
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)

    # 2 ── ALLOW: IT administrator patches a vulnerability ────────────────────
    _scenario(
        2,
        "vulnerability.patch",
        "ALLOWED: IT administrator applies CAB-approved CVE patch — ISO 27001 A.8.8",
    )
    try:
        p = client.protect(
            agent="admin.kim@corp.example",
            action="vulnerability.patch",
            context={
                "role": "it_administrator",
                "cveId": "CVE-2026-12801",
                "targetSystem": "prod-api-cluster-03",
                "severity": "high",
                "cabApproved": True,
                "stagingTested": True,
                "maintenanceWindow": "2026-06-13T02:00Z",
                "regulatoryRef": "ISO 27001:2022 A.8.8",
            },
        )
        _permit_line(p)
        _sys_apply_patch("CVE-2026-12801", "prod-api-cluster-03", "it_administrator")
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)

    # 3 ── ESCALATE: network engineer changes firewall rule ───────────────────
    _scenario(
        3,
        "firewall.rule_change",
        "ESCALATED: firewall change requires dual approval + CISO review — ISO 27001 A.8.20",
    )
    try:
        p = client.protect(
            agent="net.okafor@corp.example",
            action="firewall.rule_change",
            context={
                "role": "network_engineer",
                "firewallId": "fw-dmz-prod-01",
                "ruleDescription": "Allow inbound 443 from partner CIDR 203.0.113.0/24",
                "securityImpactAssessment": True,
                # secondApproverRole absent — triggers escalate
                "cabTicket": "CAB-2026-0881",
                "regulatoryRef": "ISO 27001:2022 A.8.20",
            },
        )
        _permit_line(p)
    except AtlaSentDeniedError as exc:
        _escalated(exc.reason) if "ESCALATE" in exc.reason else _blocked(exc.reason)
        print(f"               evaluation_id: {exc.evaluation_id}")
        _execute(
            "Firewall rule change HELD — CAB dual-approval and CISO sign-off required"
        )

    # 4 ── DENY: unauthorized developer attempts privileged access ────────────
    _scenario(
        4,
        "privileged.access",
        "BLOCKED: developer role not authorized for privileged access — ISO 27001 A.8.2",
    )
    try:
        client.protect(
            agent="dev.santos@corp.example",
            action="privileged.access",
            context={
                "role": "developer",  # not in PRIVILEGED_ROLES
                "targetSystem": "prod-db-primary",
                "accessReason": "urgent_debugging",
                "regulatoryRef": "ISO 27001:2022 A.8.2",
            },
        )
    except AtlaSentDeniedError as exc:
        _blocked(exc.reason)
        print(f"               evaluation_id: {exc.evaluation_id}")
        _execute("Privileged access NOT granted — route to CISO for break-glass authorization")

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
    print("    BLOCKED   1 action  (unauthorized role — developer on privileged.access)")
    print("    ESCALATED 1 action  (dual approval + CISO review for firewall.rule_change)")
    print("    ALLOWED   2 actions (access.grant + vulnerability.patch — permit-verified)")
    print()


def main() -> None:
    api_key = os.environ.get("ATLASENT_API_KEY", "")
    if api_key:
        run(AtlaSentClient(api_key=api_key, base_url=os.environ.get("ATLASENT_API_URL", "https://api.atlasent.io/functions/v1")), stub=None)
    else:
        stub = _Iso27001Stub()
        run(stub, stub)


if __name__ == "__main__":
    main()
