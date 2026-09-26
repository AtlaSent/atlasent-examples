#!/usr/bin/env python3
"""database-actions/schema-drop — Python API shape example

Shows protect_database_schema_drop (critical, destructive) with
backup_verified=True and recovery_point_id. Concise reference for the
API surface.

Docs: governance-kits/database-operations-kit.md
"""
from __future__ import annotations

from atlasent import AtlaSentClient, AtlaSentDeniedError

client = AtlaSentClient(api_key="ask_live_...", base_url="https://api.atlasent.io/functions/v1")


def on_permit_evidence(evidence: dict) -> None:
    """Write permit evidence before executing schema drop — append-only audit row."""
    audit_store.append({
        "action": "database.schema.drop",
        "target_schema": evidence["targetSchema"],
        "permit_id": evidence["permitId"],
        "audit_hash": evidence["auditHash"],
        "approvers": evidence["approvers"],
        "backup_verified": evidence["backupVerified"],
        "recovery_point_id": evidence["recoveryPointId"],
        "timestamp": evidence["issuedAt"],
    })


def on_denial_evidence(evidence: dict) -> None:
    """Write denial evidence — schema NOT dropped, record why."""
    audit_store.append({
        "action": "database.schema.drop",
        "target_schema": evidence.get("targetSchema"),
        "decision": "deny",
        "reason": evidence["reason"],
        "evaluation_id": evidence["evaluationId"],
    })


def drop_production_schema(target_schema: str, recovery_point_id: str) -> None:
    try:
        permit = client.protect_database_schema_drop(
            target_schema=target_schema,
            backup_verified=True,
            recovery_point_id=recovery_point_id,
            environment="production",
            on_permit_evidence=on_permit_evidence,
            on_denial_evidence=on_denial_evidence,
        )
        # Permit verified — proceed with schema drop (irreversible)
        print(f"Schema drop permit: {permit.permit_id}")
        dba_tools.drop_schema(target_schema, permit)

    except AtlaSentDeniedError as exc:
        print(f"Schema drop BLOCKED: {exc.reason}")
        # evaluation_id links to the denial record in the audit chain
        print(f"Evaluation ID: {exc.evaluation_id}")


# Usage
drop_production_schema("legacy_billing_v1", "rp-2026-05-29-0300")


# Stub references — replace with real implementations
class _AuditStore:
    def append(self, record: dict) -> None: ...
class _DbaTools:
    def drop_schema(self, schema: str, permit: object) -> None: ...
audit_store = _AuditStore()
dba_tools = _DbaTools()
