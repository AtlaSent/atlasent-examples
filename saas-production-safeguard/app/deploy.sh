#!/usr/bin/env bash
# Harmless "deploy": publish the static artifact. No real infrastructure is touched.
# In the reference environment this can push $1 to a static host; here it is a no-op
# that proves the deploy step only runs when the permit verified at the boundary.
set -euo pipefail
OUT="${1:-out}"
echo "deploying $OUT ... (no-op static publish)"
ls -la "$OUT"
echo "deployed."
