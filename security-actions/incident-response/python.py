#!/usr/bin/env python3
"""security-actions/incident-response — Python API shape example

Shows protect_security_incident_escalate with incidentId, severity="critical",
and on_escalation_created callback. Concise reference for the API surface.

Full runnable scenario: see main.py
Docs: governance-kits/security-incident-response-kit.md
"""
from __future__ import annotations

from atlasent import AtlaSentClient, AtlaSentDeniedError

client = AtlaSentClient(api_key="ask_live_...", base_url="https://api.atlasent.io/functions/v1")


def on_escalation_created(escalation: dict) -> None:
    """Called when the escalation permit is issued — wire to PagerDuty / SIEM."""
    print(f"Escalation created: {escalation['escalationId']}")
    print(f"Permit: {escalation['permitId']}")
    print(f"Audit hash: {escalation['auditHash']}")
    notify_pagerduty(escalation["incidentId"], escalation["severity"])


def escalate_incident() -> None:
    try:
        permit = client.protect_security_incident_escalate(
            incident_id="INC-2026-CRIT-042",
            severity="critical",
            authorized_by="soc:lead-alice",
            on_escalation_created=on_escalation_created,
        )
        # Permit verified — proceed with incident escalation workflow
        print(f"Incident escalation permit: {permit.permit_id}")
        incident_tracker.escalate("INC-2026-CRIT-042", permit)

    except AtlaSentDeniedError as exc:
        print(f"Escalation BLOCKED: {exc.reason}")
        # evaluation_id links to the denial record in the audit chain
        print(f"Evaluation ID: {exc.evaluation_id}")


# Stub references — replace with real implementations
def notify_pagerduty(incident_id: str, severity: str) -> None: ...
class _IncidentTracker:
    def escalate(self, incident_id: str, permit: object) -> None: ...
incident_tracker = _IncidentTracker()


if __name__ == "__main__":
    escalate_incident()
