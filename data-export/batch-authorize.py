#!/usr/bin/env python3
"""batch-authorize.py — Standalone batch export authorizer

Evaluates a list of data-export rows against AtlaSent's customer.data.export
policy. Returns allowed rows and denied rows with decision codes.

Row-cap enforcement: if rowsRequested > ROW_CAP, the entire batch is denied
before any row-level evaluation takes place.

Usage:
  python batch-authorize.py                    # demo with built-in sample rows
  python batch-authorize.py --rows rows.json  # evaluate rows from a JSON file

  rows.json format:
  [
    {
      "rowId": "R001",
      "containsPii": true,
      "destination": "snowflake://acme/analytics",
      "purpose": "monthly-retention-report",
      "requestedBy": "analyst@acme.com"
    },
    ...
  ]

Exit codes:
  0 — at least one row allowed
  1 — all rows denied
  2 — batch denied before row-level evaluation (row cap exceeded)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from typing import Any

from atlasent import AtlaSentClient, AtlaSentDeniedError, Permit


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ROW_CAP = 100_000
MAX_WORKERS = 8

VERIFIED_DESTINATIONS: frozenset[str] = frozenset(
    {"s3://acme-exports-verified", "bigquery://acme-prod/exports", "snowflake://acme/analytics"}
)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class AllowedRow:
    row: dict[str, Any]
    permit_id: str
    audit_hash: str
    reason: str

@dataclass
class DeniedRow:
    row: dict[str, Any]
    decision_code: str
    reason: str
    evaluation_id: str


@dataclass
class BatchResult:
    allowed: list[AllowedRow]
    denied: list[DeniedRow]
    batch_decision: str   # "ALLOWED", "PARTIAL", "DENIED", "BATCH_DENIED_ROW_CAP"
    total_rows: int
    allowed_count: int
    denied_count: int


# ---------------------------------------------------------------------------
# Row authorization
# ---------------------------------------------------------------------------

def _authorize_row(
    client: AtlaSentClient,
    row: dict[str, Any],
    agent: str,
) -> tuple[dict[str, Any], Permit | None, str | None, str | None, str | None]:
    """Return (row, permit, decision_code, reason, evaluation_id).

    On allow: permit is set, decision_code/reason/evaluation_id are None.
    On deny:  permit is None, decision_code and reason are set.
    """
    try:
        permit = client.protect(
            agent=agent,
            action="customer.data.export",
            context={
                "datasetId": row.get("datasetId", f"row-{row.get('rowId', uuid.uuid4().hex[:8])}"),
                "containsPii": row.get("containsPii", False),
                "destination": row.get("destination", ""),
                "purpose": row.get("purpose", ""),
                "rowsRequested": row.get("rowsRequested", 1),
                "requestedBy": row.get("requestedBy", agent),
            },
        )
        return row, permit, None, None, None
    except AtlaSentDeniedError as exc:
        reason = exc.reason or "denied"
        decision_code = reason.split(":")[0].strip() if ":" in reason else "DENY"
        return row, None, decision_code, reason, str(exc.evaluation_id or "")


# ---------------------------------------------------------------------------
# Batch authorizer
# ---------------------------------------------------------------------------

def batch_authorize(
    rows: list[dict[str, Any]],
    agent: str,
    client: AtlaSentClient | None = None,
) -> BatchResult:
    """Authorize a list of rows for customer.data.export.

    Args:
        rows:    List of row dicts. Each row should include: rowId, containsPii,
                 destination, purpose, requestedBy. See module docstring for schema.
        agent:   The agent/service identity requesting the export.
        client:  AtlaSentClient instance. If None, one is created from ATLASENT_API_KEY.

    Returns:
        BatchResult with allowed rows (with permits) and denied rows (with codes).

    Raises:
        SystemExit(2) if the batch total exceeds ROW_CAP.
    """
    if client is None:
        api_key = os.environ.get("ATLASENT_API_KEY", "")
        if not api_key:
            raise ValueError("ATLASENT_API_KEY is required when client is not provided")
        client = AtlaSentClient(api_key=api_key, base_url=os.environ.get("ATLASENT_API_URL", "https://api.atlasent.io/functions/v1"))

    # Row-cap enforcement: deny the entire batch before row-level evaluation
    total_rows = sum(row.get("rowsRequested", 1) for row in rows)
    if total_rows > ROW_CAP:
        print(
            f"[batch-authorize] BATCH_DENIED_ROW_CAP: {total_rows:,} rows requested "
            f"exceeds cap of {ROW_CAP:,} — escalation required",
            file=sys.stderr,
        )
        return BatchResult(
            allowed=[],
            denied=[
                DeniedRow(
                    row=row,
                    decision_code="BATCH_DENIED_ROW_CAP",
                    reason=f"batch of {total_rows:,} rows exceeds cap of {ROW_CAP:,}",
                    evaluation_id="",
                )
                for row in rows
            ],
            batch_decision="BATCH_DENIED_ROW_CAP",
            total_rows=total_rows,
            allowed_count=0,
            denied_count=len(rows),
        )

    # Row-level evaluation (parallel)
    allowed: list[AllowedRow] = []
    denied: list[DeniedRow] = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [
            pool.submit(_authorize_row, client, row, agent)
            for row in rows
        ]
        for future in futures:
            row, permit, decision_code, reason, eval_id = future.result()
            if permit is not None:
                allowed.append(AllowedRow(
                    row=row,
                    permit_id=permit.permit_id,
                    audit_hash=permit.audit_hash or "",
                    reason=permit.reason or "",
                ))
            else:
                denied.append(DeniedRow(
                    row=row,
                    decision_code=decision_code or "DENY",
                    reason=reason or "denied",
                    evaluation_id=eval_id or "",
                ))

    if not allowed:
        batch_decision = "DENIED"
    elif not denied:
        batch_decision = "ALLOWED"
    else:
        batch_decision = "PARTIAL"

    return BatchResult(
        allowed=allowed,
        denied=denied,
        batch_decision=batch_decision,
        total_rows=total_rows,
        allowed_count=len(allowed),
        denied_count=len(denied),
    )


# ---------------------------------------------------------------------------
# Sample rows for demo
# ---------------------------------------------------------------------------

SAMPLE_ROWS: list[dict[str, Any]] = [
    {
        "rowId": "R001",
        "datasetId": "CRM-SEGMENT-A",
        "containsPii": True,
        "destination": "snowflake://acme/analytics",
        "purpose": "Q1-churn-analysis",
        "rowsRequested": 1000,
        "requestedBy": "analyst.alice@acme.com",
    },
    {
        "rowId": "R002",
        "datasetId": "EVENTS-ANON",
        "containsPii": False,
        "destination": "s3://personal-bucket-bob",   # unverified, but non-PII → allowed
        "purpose": "ad-hoc-analysis",
        "rowsRequested": 500,
        "requestedBy": "analyst.bob@acme.com",
    },
    {
        "rowId": "R003",
        "datasetId": "CRM-SEGMENT-B",
        "containsPii": True,
        "destination": "s3://personal-bucket-bob",   # unverified + PII → denied
        "purpose": "ad-hoc-analysis",
        "rowsRequested": 250,
        "requestedBy": "analyst.bob@acme.com",
    },
    {
        "rowId": "R004",
        "datasetId": "REVENUE-SUMMARY",
        "containsPii": False,
        "destination": "bigquery://acme-prod/exports",
        "purpose": "finance-reporting",
        "rowsRequested": 200,
        "requestedBy": "finance.team@acme.com",
    },
    {
        "rowId": "R005",
        "datasetId": "CRM-SEGMENT-C",
        "containsPii": True,
        "destination": "bigquery://acme-prod/exports",
        "purpose": "",   # missing purpose → denied
        "rowsRequested": 300,
        "requestedBy": "analyst.carol@acme.com",
    },
]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Batch export authorizer — evaluates rows for customer.data.export",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--rows", metavar="PATH", help="JSON file with row array")
    parser.add_argument("--agent", default="pipeline-bot@acme.com", help="Agent identity")
    parser.add_argument("--json", dest="json_output", action="store_true",
                        help="Output results as JSON")
    args = parser.parse_args()

    if args.rows:
        with open(args.rows) as f:
            rows = json.load(f)
    else:
        rows = SAMPLE_ROWS
        print(f"Using {len(rows)} built-in sample rows (pass --rows rows.json for custom input)\n")

    # Use offline stub if no API key
    from main import _ExportStub  # type: ignore[import]
    api_key = os.environ.get("ATLASENT_API_KEY", "")
    client: AtlaSentClient
    if api_key:
        client = AtlaSentClient(api_key=api_key, base_url=os.environ.get("ATLASENT_API_URL", "https://api.atlasent.io/functions/v1"))
    else:
        client = _ExportStub()

    result = batch_authorize(rows, agent=args.agent, client=client)

    if args.json_output:
        output = {
            "batch_decision": result.batch_decision,
            "total_rows": result.total_rows,
            "allowed_count": result.allowed_count,
            "denied_count": result.denied_count,
            "allowed": [asdict(r) for r in result.allowed],
            "denied": [asdict(r) for r in result.denied],
        }
        print(json.dumps(output, indent=2))
    else:
        print(f"Batch result: {result.batch_decision}")
        print(f"  {result.allowed_count} allowed / {result.denied_count} denied "
              f"({result.total_rows:,} total rows)\n")

        if result.allowed:
            print("Allowed rows:")
            for r in result.allowed:
                print(f"  ✔  {r.row.get('rowId', '?'):6}  permit={r.permit_id}")

        if result.denied:
            print("\nDenied rows:")
            for r in result.denied:
                print(f"  ✗  {r.row.get('rowId', '?'):6}  {r.decision_code}")

    if result.batch_decision == "BATCH_DENIED_ROW_CAP":
        return 2
    if result.batch_decision == "DENIED":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
