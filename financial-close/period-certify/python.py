#!/usr/bin/env python3
"""financial-close/period-certify — Python API shape example

Shows protect_period_close_certify with period_id, certified_by, and
financial_controller. Concise reference for the API surface.

Full runnable scenario: see main.py
Docs: governance-kits/financial-close-kit.md / close-governance-kit.md
"""
from __future__ import annotations

from atlasent import AtlaSentClient, AtlaSentDeniedError

client = AtlaSentClient(api_key="ask_live_...", base_url="https://api.atlasent.io/functions/v1")


def certify_period_close(
    period_id: str,
    certified_by: str,
    financial_controller: str,
) -> None:
    try:
        permit = client.protect_period_close_certify(
            period_id=period_id,
            certified_by=certified_by,
            financial_controller=financial_controller,
        )
        # Permit verified — proceed with period close certification
        print(f"Period close permit: {permit.permit_id}")
        erp.close_period(period_id, permit)
        evidence_store.seal(period_id, permit)

    except AtlaSentDeniedError as exc:
        print(f"Period close BLOCKED: {exc.reason}")
        # evaluation_id links to the denial record in the audit chain
        print(f"Evaluation ID: {exc.evaluation_id}")


# Usage
certify_period_close("2026-Q1", "controller:jane", "fc:bob")


# Stub references — replace with real implementations
class _Erp:
    def close_period(self, period_id: str, permit: object) -> None: ...
class _EvidenceStore:
    def seal(self, period_id: str, permit: object) -> None: ...
erp = _Erp()
evidence_store = _EvidenceStore()
