#!/usr/bin/env python3
"""verify-audit.py — Export and verify an AtlaSent audit bundle.

Two modes:

  Live (requires atlasent SDK + ATLASENT_API_KEY):
    python verify-audit.py --from 2026-01-01 --to 2026-03-31
    python verify-audit.py --from 2026-01-01 --to 2026-03-31 --actor alice.chen@acme.com
    python verify-audit.py --from 2026-01-01 --to 2026-03-31 --out q1-audit.json

  Offline (no SDK, no network — auditor-side verification of a delivered bundle):
    python verify-audit.py --bundle path/to/audit-bundle.json
    python verify-audit.py --bundle path/to/audit-bundle.json --pubkey <base64>

Exit codes:
  0  bundle exported and chain integrity + signatures verified OK
  1  chain integrity failure or Ed25519 signature mismatch
  2  AtlaSent API unavailable or export failed

Live mode requires:  pip install atlasent  +  ATLASENT_API_KEY in env
Offline mode requires: pip install cryptography  (no SDK, no key, no network)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _run_offline(bundle_path: str, pubkey_b64: str | None) -> int:
    """Verify a bundle file produced by ``main.py --export`` or the live API.

    Pure stdlib + cryptography. No atlasent SDK import, no network.
    """
    from _bundle import verify_bundle

    path = Path(bundle_path)
    if not path.exists():
        print(f"[audit] bundle not found: {path}", file=sys.stderr)
        return 2
    bundle = json.loads(path.read_text())

    is_demo = bool(bundle.get("demo"))
    key_id = bundle.get("key_id", "(none)")
    print(f"[audit] verifying bundle: {path}")
    print(f"[audit] bundle key_id: {key_id}{'  (DEMO)' if is_demo else ''}")
    if pubkey_b64 is None and is_demo:
        print(
            "[audit] WARNING: using embedded public key from a demo bundle. "
            "For real audits, pass --pubkey with a key pinned out-of-band "
            "(e.g. from https://keys.atlasent.io)."
        )

    result = verify_bundle(bundle, pubkey_b64=pubkey_b64)

    if not result.chain_valid:
        print(
            f"[audit] CHAIN INTEGRITY FAILURE at event index {result.first_bad_index}",
            file=sys.stderr,
        )
        print(f"        expected: {result.expected_hash}", file=sys.stderr)
        print(f"        got:      {result.actual_hash}", file=sys.stderr)
        if result.error:
            print(f"        detail:   {result.error}", file=sys.stderr)
        return 1
    if not result.signatures_valid:
        print(
            "[audit] SIGNATURE VERIFICATION FAILED "
            "-- bundle may have been tampered with",
            file=sys.stderr,
        )
        if result.error:
            print(f"        detail:   {result.error}", file=sys.stderr)
        return 1

    print(
        f"[audit] OK  {result.event_count} events  "
        f"chain=valid  signatures=valid"
    )
    print(f"[audit] head hash: {result.head_hash}")
    return 0


def _run_live(from_date: str, to_date: str, actor: str | None, out_path: str) -> int:
    """Export from the live API + verify. Requires atlasent SDK and API key."""
    from atlasent import configure
    from atlasent.audit import create_audit_export, verify_audit_bundle

    # Reads ATLASENT_API_KEY from the environment. The SDK default base URL is
    # the bare host; the AtlaSent API lives under /functions/v1.
    configure(base_url=os.environ.get("ATLASENT_API_URL", "https://api.atlasent.io/functions/v1"))

    summary = f"{from_date} → {to_date}"
    if actor:
        summary += f"  actor={actor}"
    print(f"[audit] exporting bundle: {summary}")

    try:
        bundle = create_audit_export(
            from_date=from_date, to_date=to_date, actor=actor
        )
    except Exception as exc:
        print(f"[audit] export failed: {exc}", file=sys.stderr)
        return 2

    out = Path(out_path)
    out.write_text(json.dumps(bundle, indent=2))
    event_count = len(bundle.get("events", []))
    print(f"[audit] bundle written to {out}  ({event_count} events)")

    print("[audit] verifying hash chain and Ed25519 signatures ...")
    result = verify_audit_bundle(bundle)

    if not result.chain_valid:
        print(
            f"[audit] CHAIN INTEGRITY FAILURE at event index {result.first_bad_index}",
            file=sys.stderr,
        )
        print(f"        expected: {result.expected_hash}", file=sys.stderr)
        print(f"        got:      {result.actual_hash}", file=sys.stderr)
        return 1
    if not result.signatures_valid:
        print(
            "[audit] SIGNATURE VERIFICATION FAILED "
            "-- bundle may have been tampered with",
            file=sys.stderr,
        )
        return 1

    print(
        f"[audit] OK  {result.event_count} events  "
        f"chain=valid  signatures=valid"
    )
    print(f"[audit] head hash: {result.head_hash}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export and verify an AtlaSent audit bundle",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exit 0 = verified OK; exit 1 = integrity failure; exit 2 = export error\n"
            "Live mode: --from/--to/--actor/--out (requires atlasent SDK + ATLASENT_API_KEY)\n"
            "Offline mode: --bundle/--pubkey (no SDK, no network)"
        ),
    )
    parser.add_argument(
        "--bundle", default=None, metavar="PATH",
        help="Verify a bundle file offline (no SDK, no network).",
    )
    parser.add_argument(
        "--pubkey", default=None, metavar="BASE64",
        help="Ed25519 public key (base64) to pin during offline verification. "
             "Overrides the public key embedded in the bundle.",
    )
    parser.add_argument(
        "--from", dest="from_date", default=None, metavar="YYYY-MM-DD",
        help="Live mode: start of audit window (inclusive).",
    )
    parser.add_argument(
        "--to", dest="to_date", default=None, metavar="YYYY-MM-DD",
        help="Live mode: end of audit window (inclusive).",
    )
    parser.add_argument(
        "--actor", default=None, metavar="EMAIL",
        help="Live mode: filter to a specific actor (optional).",
    )
    parser.add_argument(
        "--out", default="audit-bundle.json", metavar="PATH",
        help="Live mode: output file path (default: audit-bundle.json).",
    )
    args = parser.parse_args()

    if args.bundle is not None:
        sys.exit(_run_offline(args.bundle, args.pubkey))

    if not (args.from_date and args.to_date):
        parser.error(
            "either --bundle PATH (offline verify) or both --from and --to "
            "(live export) are required"
        )

    sys.exit(_run_live(args.from_date, args.to_date, args.actor, args.out))


if __name__ == "__main__":
    main()
