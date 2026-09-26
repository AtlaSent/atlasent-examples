#!/usr/bin/env python3
"""access-certification/cert-revoke — Python API shape example

Shows the generic protect() call for access.cert.revoke with certId and
revocationReason in context. Concise reference for the API surface.

Full runnable scenario: see main.py
Docs: governance-kits/access-certification-kit.md
"""
from __future__ import annotations

from atlasent import AtlaSentClient, AtlaSentDeniedError

client = AtlaSentClient(api_key="ask_live_...", base_url="https://api.atlasent.io/functions/v1")


def revoke_cert(cert_id: str, revocation_reason: str) -> None:
    try:
        permit = client.protect(
            agent="iam:security-admin",
            action="access.cert.revoke",
            context={
                "certId": cert_id,
                "revocationReason": revocation_reason,
                "authorizedBy": "iam:security-admin",
            },
        )
        # Permit verified — proceed with certificate revocation
        print(f"Access cert revocation permit: {permit.permit_id}")
        pki_store.revoke(cert_id, permit)
        crl_manager.update(cert_id)

    except AtlaSentDeniedError as exc:
        print(f"Cert revocation BLOCKED: {exc.reason}")
        # evaluation_id links to the denial record in the audit chain
        print(f"Evaluation ID: {exc.evaluation_id}")


# Usage
revoke_cert(
    "cert:2026-Q2-ENG-42",
    "access no longer required — engineer offboarded 2026-05-28",
)


# Stub references — replace with real implementations
class _PkiStore:
    def revoke(self, cert_id: str, permit: object) -> None: ...
class _CrlManager:
    def update(self, cert_id: str) -> None: ...
pki_store = _PkiStore()
crl_manager = _CrlManager()
