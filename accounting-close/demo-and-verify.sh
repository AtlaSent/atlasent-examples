#!/usr/bin/env bash
# demo-and-verify.sh — end-to-end smoke for the close-ops pilot demo.
#
# Runs the in-process close-cycle demo, exports a signed audit-evidence
# bundle, and verifies it offline. No API key, no network. Exits 0 only if
# the bundle's hash chain and Ed25519 signature both check out.
#
# Usage:
#   ./demo-and-verify.sh                       # uses ./bundle.json
#   ./demo-and-verify.sh path/to/bundle.json   # writes to a custom path
#
# Python:
#   Set PYTHON=/usr/bin/python3.12 (or similar) if your default python3
#   does not have a working cryptography install. main.py also requires
#   the atlasent SDK to be importable; if it is not, skip directly to
#   _sample.py + verify-audit.py for a SDK-free demo of the verifier.

set -euo pipefail

PYTHON="${PYTHON:-python3}"
BUNDLE="${1:-bundle.json}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

echo "[smoke] python: $($PYTHON --version 2>&1)"
echo "[smoke] bundle: $BUNDLE"
echo

if $PYTHON -c "import atlasent" 2>/dev/null; then
  echo "[smoke] atlasent SDK present — running full main.py demo"
  $PYTHON main.py --export "$BUNDLE"
else
  echo "[smoke] atlasent SDK not importable — generating sample bundle from _sample.py"
  echo "        (install 'atlasent' from requirements.txt to run the full close-cycle demo)"
  $PYTHON _sample.py --out "$BUNDLE"
fi

echo
echo "[smoke] verifying bundle offline ..."
$PYTHON verify-audit.py --bundle "$BUNDLE"

echo
echo "[smoke] OK — signed audit-evidence bundle written to $BUNDLE and verified."
