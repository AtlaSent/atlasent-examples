"""Audit bundle builder and offline verifier.

Used by ``main.py --export`` to produce a signed, hash-linked evidence pack,
and by ``verify-audit.py --bundle`` to verify one offline.

Pure stdlib + ``cryptography``. No ``atlasent`` SDK import, so an auditor's
laptop can verify a bundle without installing our SDK.

Bundle shape (version 1):

    {
      "atlasent_audit_bundle_version": "1",
      "exported_at":   "<ISO-8601 UTC>",
      "period":        {"from": "...", "to": "..."},
      "actor_filter":  null | "<email>",
      "key_id":        "atlasent-demo-key-1",
      "public_key_ed25519_b64": "<base64>",
      "algorithm":     "none" | "hmac-sha256",  # V1: always present
      "signature":     "<base64>" | null,         # V1: null when algorithm=="none"
      "events": [
        {
          "event_id":       "evt_...",
          "timestamp":      "<ISO-8601 UTC>",
          "actor":          "<agent or email>",
          "action":         "<action.type>",
          "decision":       "allow",
          "permit_id":      "pt_...",
          "reason":         "<text>",
          "previous_hash":  "<32 hex>" | "",
          "audit_hash":     "<32 hex>",
          "context_snapshot": {...}
        },
        ...
      ],
      "head_hash":           "<32 hex>",
      "signature_ed25519_b64": "<base64> | null",  # retained for back-compat; prefer `signature`
      "demo": true
    }

Each event's ``audit_hash`` is SHA-256 over the canonical JSON of every
evidence field except ``audit_hash`` itself — ``event_id``, ``timestamp``,
``actor``, ``action``, ``decision``, ``permit_id``, ``reason``,
``context_snapshot`` (recursively sort-keyed), and ``previous_hash`` —
truncated to 32 hex chars. Tampering with any of those fields (including
swapping a JE amount in ``context_snapshot``, flipping ``decision`` from
``allow`` to ``deny``, or rewriting a ``timestamp``), reordering events,
or breaking the chain is detected at verify time. The Ed25519 signature
is over the ``head_hash`` bytes and is checked with the embedded public
key (or a caller-supplied one for stricter trust roots).

The demo keypair is derived from a fixed seed (``DEMO_SEED``). It is for
demo use only — production deployments use ``keys.atlasent.io`` published
keys. Never sign real customer audit chains with the demo key.
"""
from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
)

BUNDLE_VERSION = "1"
DEMO_KEY_ID = "atlasent-demo-key-1"

# 32 bytes derived from a fixed string. DEMO ONLY. Production signing keys
# live in the AtlaSent KMS and are never embedded in source.
DEMO_SEED = hashlib.sha256(b"atlasent-close-ops-demo-key:v1").digest()

# V1 supported proof bundle algorithms
ALGORITHM_NONE = "none"
ALGORITHM_HMAC_SHA256 = "hmac-sha256"


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _from_b64(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"))


def demo_keypair() -> tuple[Ed25519PrivateKey, Ed25519PublicKey]:
    """Deterministic Ed25519 keypair for the demo bundle. Same on every run."""
    priv = Ed25519PrivateKey.from_private_bytes(DEMO_SEED)
    return priv, priv.public_key()


def _pub_b64(pub: Ed25519PublicKey) -> str:
    raw = pub.public_bytes(Encoding.Raw, PublicFormat.Raw)
    return _b64(raw)


def compute_audit_hash(
    *,
    event_id: str,
    timestamp: str,
    actor: str,
    action: str,
    decision: str,
    permit_id: str,
    reason: str,
    context_snapshot: dict[str, Any] | None,
    previous_hash: str,
) -> str:
    """SHA-256 over canonical JSON of every evidence field, truncated to 32 hex.

    All fields an auditor must trust are part of the input. Modifying any
    of them — including a JE amount in ``context_snapshot``, the
    ``decision`` outcome, the ``timestamp``, or the ``event_id`` —
    invalidates the hash at verify time. Sole authoritative implementation;
    ``main.py``'s in-process stub imports this function so the in-memory
    chain and the exported bundle agree byte-for-byte.

    ``context_snapshot`` is canonicalized recursively via ``sort_keys=True``.
    """
    blob = json.dumps(
        {
            "event_id": event_id,
            "timestamp": timestamp,
            "actor": actor,
            "action": action,
            "decision": decision,
            "permit_id": permit_id,
            "reason": reason,
            "context_snapshot": context_snapshot or {},
            "previous_hash": previous_hash,
        },
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode()).hexdigest()[:32]


@dataclass
class VerifyResult:
    chain_valid: bool
    signatures_valid: bool
    event_count: int
    head_hash: str
    first_bad_index: int | None = None
    expected_hash: str | None = None
    actual_hash: str | None = None
    error: str | None = None


def events_from_audit_records(records: Iterable[Any]) -> list[dict[str, Any]]:
    """Convert ``main.py``'s ``AuditRecord`` instances (or compatible dicts) to
    bundle event dicts. Pulls only the fields needed for the signed chain.
    """
    out: list[dict[str, Any]] = []
    for r in records:
        get = (lambda k: r.get(k)) if isinstance(r, dict) else (lambda k: getattr(r, k))
        out.append(
            {
                "event_id": get("event_id"),
                "timestamp": get("timestamp"),
                "actor": get("actor"),
                "action": get("action"),
                "decision": get("decision"),
                "permit_id": get("permit_id"),
                "reason": get("reason") or "",
                "previous_hash": get("previous_hash") or "",
                "audit_hash": get("audit_hash"),
                "context_snapshot": get("context_snapshot") or {},
            }
        )
    return out


def make_bundle(
    events: list[dict[str, Any]],
    *,
    period_from: str,
    period_to: str,
    actor_filter: str | None = None,
    exported_at: str | None = None,
    algorithm: str = ALGORITHM_HMAC_SHA256,
    demo: bool = True,
) -> dict[str, Any]:
    """Wrap ``events`` in a signed envelope. ``events`` must already carry the
    chain-correct ``previous_hash`` and ``audit_hash`` fields (i.e. produced
    by the in-process stub in ``main.py``).

    ``algorithm`` controls how the bundle is signed:
      - ``"hmac-sha256"`` (default): Ed25519 signature over the UTF-8 bytes
        of ``head_hash``. The signature is stored in both ``signature``
        (V1 canonical field) and ``signature_ed25519_b64`` (back-compat alias).
      - ``"none"``: no signature is produced; ``signature`` is ``null``.
    """
    if algorithm not in (ALGORITHM_NONE, ALGORITHM_HMAC_SHA256):
        raise ValueError(
            f"Unsupported algorithm {algorithm!r}. "
            f"Must be {ALGORITHM_NONE!r} or {ALGORITHM_HMAC_SHA256!r}."
        )

    head_hash = events[-1]["audit_hash"] if events else ""

    # Build signature — or None when algorithm == "none"
    if algorithm == ALGORITHM_HMAC_SHA256 and head_hash:
        priv, pub = demo_keypair()
        raw_signature = priv.sign(head_hash.encode("utf-8"))
        signature_b64: str | None = _b64(raw_signature)
        public_key_b64: str | None = _pub_b64(pub)
    else:
        signature_b64 = None
        public_key_b64 = None

    return {
        "atlasent_audit_bundle_version": BUNDLE_VERSION,
        "exported_at": exported_at
        or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "period": {"from": period_from, "to": period_to},
        "actor_filter": actor_filter,
        "key_id": DEMO_KEY_ID,
        "public_key_ed25519_b64": public_key_b64,   # None when algorithm=="none"
        # V1 proof bundle fields
        "algorithm": algorithm,                       # "none" | "hmac-sha256"
        "signature": signature_b64,                   # nullable: None when algorithm=="none"
        "events": events,
        "head_hash": head_hash,
        # back-compat alias for signature_ed25519_b64; prefer `signature`
        "signature_ed25519_b64": signature_b64,
        "demo": demo,
    }


def write_bundle(bundle: dict[str, Any], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(bundle, f, indent=2, sort_keys=False)
        f.write("\n")


def verify_bundle(
    bundle: dict[str, Any], *, pubkey_b64: str | None = None
) -> VerifyResult:
    """Walk the chain, re-hash each event, verify the head signature.

    Handles V1 proof bundle fields:
      - ``algorithm``: ``"none"`` | ``"hmac-sha256"`` (default assumed when absent)
      - ``signature``: nullable; ``None`` / absent means no signature to verify

    If ``pubkey_b64`` is provided, it is used to verify the signature
    instead of the bundle's embedded ``public_key_ed25519_b64``. Auditors
    SHOULD pin the public key out-of-band (e.g. via ``keys.atlasent.io``)
    rather than trust the embedded value.
    """
    if bundle.get("atlasent_audit_bundle_version") != BUNDLE_VERSION:
        return VerifyResult(
            chain_valid=False,
            signatures_valid=False,
            event_count=0,
            head_hash="",
            error=f"unsupported bundle version: {bundle.get('atlasent_audit_bundle_version')!r}",
        )

    # V1: read algorithm (default to hmac-sha256 for back-compat with older bundles)
    algorithm = str(bundle.get("algorithm", ALGORITHM_HMAC_SHA256))

    events = bundle.get("events", [])
    prev = ""
    for i, ev in enumerate(events):
        if ev.get("previous_hash", "") != prev:
            return VerifyResult(
                chain_valid=False,
                signatures_valid=False,
                event_count=len(events),
                head_hash=bundle.get("head_hash", ""),
                first_bad_index=i,
                expected_hash=prev,
                actual_hash=ev.get("previous_hash", ""),
                error=f"chain break at event {i}: previous_hash mismatch",
            )
        expected = compute_audit_hash(
            event_id=ev.get("event_id", ""),
            timestamp=ev.get("timestamp", ""),
            actor=ev.get("actor", ""),
            action=ev.get("action", ""),
            decision=ev.get("decision", ""),
            permit_id=ev.get("permit_id", ""),
            reason=ev.get("reason", ""),
            context_snapshot=ev.get("context_snapshot"),
            previous_hash=prev,
        )
        if expected != ev.get("audit_hash"):
            return VerifyResult(
                chain_valid=False,
                signatures_valid=False,
                event_count=len(events),
                head_hash=bundle.get("head_hash", ""),
                first_bad_index=i,
                expected_hash=expected,
                actual_hash=ev.get("audit_hash"),
                error=f"audit_hash mismatch at event {i}",
            )
        prev = ev["audit_hash"]

    head_hash = bundle.get("head_hash", "")
    if events and head_hash != events[-1]["audit_hash"]:
        return VerifyResult(
            chain_valid=False,
            signatures_valid=False,
            event_count=len(events),
            head_hash=head_hash,
            first_bad_index=len(events) - 1,
            expected_hash=events[-1]["audit_hash"],
            actual_hash=head_hash,
            error="head_hash does not match last event audit_hash",
        )

    # V1: when algorithm == "none", signature is expected to be absent/null — that's valid.
    if algorithm == ALGORITHM_NONE:
        sig_field = bundle.get("signature")
        if sig_field is not None:
            # Bundle claims algorithm=none but carries a signature — warn but treat chain as valid
            return VerifyResult(
                chain_valid=True,
                signatures_valid=False,
                event_count=len(events),
                head_hash=head_hash,
                error="algorithm=none but non-null signature present; signature skipped",
            )
        # algorithm=none with null/absent signature is fully valid
        return VerifyResult(
            chain_valid=True,
            signatures_valid=True,   # vacuously valid: no signature expected
            event_count=len(events),
            head_hash=head_hash,
        )

    # algorithm == hmac-sha256: verify Ed25519 signature
    # Accept V1 `signature` field; fall back to legacy `signature_ed25519_b64`
    sig_b64 = bundle.get("signature") or bundle.get("signature_ed25519_b64")
    pub_source = pubkey_b64 or bundle.get("public_key_ed25519_b64", "")
    if not pub_source or not sig_b64:
        return VerifyResult(
            chain_valid=True,
            signatures_valid=False,
            event_count=len(events),
            head_hash=head_hash,
            error="no public key or signature available for signature verification",
        )
    try:
        pub = Ed25519PublicKey.from_public_bytes(_from_b64(pub_source))
        sig = _from_b64(sig_b64)
        if head_hash:
            pub.verify(sig, head_hash.encode("utf-8"))
    except (InvalidSignature, ValueError, TypeError) as exc:
        return VerifyResult(
            chain_valid=True,
            signatures_valid=False,
            event_count=len(events),
            head_hash=head_hash,
            error=f"signature verification failed: {exc}",
        )

    return VerifyResult(
        chain_valid=True,
        signatures_valid=True,
        event_count=len(events),
        head_hash=head_hash,
    )
