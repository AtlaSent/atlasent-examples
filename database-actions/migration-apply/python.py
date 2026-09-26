#!/usr/bin/env python3
"""database-actions/migration-apply — Python API shape example

Shows protect_database_migration for production with rollback_plan and
evidence callbacks showing evidence recording. Concise reference for the
API surface.

Docs: governance-kits/database-operations-kit.md
"""
from __future__ import annotations

from atlasent import AtlaSentClient, AtlaSentDeniedError

client = AtlaSentClient(api_key="ask_live_...", base_url="https://api.atlasent.io/functions/v1")


def on_permit_evidence(evidence: dict) -> None:
    """Write permit evidence before executing migration — append-only audit row."""
    audit_store.append({
        "action": "database.migration.apply",
        "migration_id": evidence["migrationId"],
        "permit_id": evidence["permitId"],
        "audit_hash": evidence["auditHash"],
        "approved_by": evidence["approvedBy"],
        "environment": evidence["environment"],
        "timestamp": evidence["issuedAt"],
    })


def on_denial_evidence(evidence: dict) -> None:
    """Write denial evidence — migration blocked, record why."""
    audit_store.append({
        "action": "database.migration.apply",
        "migration_id": evidence.get("migrationId"),
        "decision": "deny",
        "reason": evidence["reason"],
        "evaluation_id": evidence["evaluationId"],
    })


def apply_production_migration(migration_id: str, checksum: str) -> None:
    try:
        permit = client.protect_database_migration(
            migration_id=migration_id,
            checksum=checksum,
            environment="production",
            rollback_plan=f"rollback/{migration_id}.sql",
            on_permit_evidence=on_permit_evidence,
            on_denial_evidence=on_denial_evidence,
        )
        # Permit verified — proceed with migration
        print(f"Migration permit: {permit.permit_id}")
        migration_runner.apply(migration_id, permit)

    except AtlaSentDeniedError as exc:
        print(f"Migration BLOCKED: {exc.reason}")
        # evaluation_id links to the denial record in the audit chain
        print(f"Evaluation ID: {exc.evaluation_id}")


# Usage
apply_production_migration(
    "20260529_add_user_preferences_index",
    "sha256:a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
)


# Stub references — replace with real implementations
class _AuditStore:
    def append(self, record: dict) -> None: ...
class _MigrationRunner:
    def apply(self, migration_id: str, permit: object) -> None: ...
audit_store = _AuditStore()
migration_runner = _MigrationRunner()
