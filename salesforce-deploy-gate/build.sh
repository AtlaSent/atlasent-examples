#!/usr/bin/env bash
# Package the illustrative Salesforce metadata into out/ and print the sha256
# digest the permit binds to. In a real pipeline this is `sf project convert` /
# `sf project deploy start --dry-run` producing the deploy plan you hash.
set -euo pipefail
cd "$(dirname "$0")"

rm -rf out
mkdir -p out
cp -R sample-metadata/* out/

# Deterministic digest of the deploy plan (sorted file list + contents).
DIGEST=$(cd out && find . -type f | LC_ALL=C sort | xargs cat | sha256sum | cut -d' ' -f1)

echo "packaged: $(cd out && find . -type f | wc -l | tr -d ' ') files"
# NOTE: the value sent as `execution_payload_hash` must be BARE 64-char hex.
# v1-evaluate binds it only when it matches /^[0-9a-f]{64}$/i; a "sha256:"
# prefix is DROPPED, not rejected — the permit then binds to the server's own
# request hash and every verify returns PAYLOAD_MISMATCH, with no error at
# evaluate time. The prefix below is display only; out/.digest is what the
# workflow actually reads and sends.
echo "execution_payload_hash (display only, prefixed): sha256:${DIGEST}"
echo "${DIGEST}" > out/.digest
