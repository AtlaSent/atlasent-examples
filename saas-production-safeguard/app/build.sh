#!/usr/bin/env bash
# Harmless "build": emit a static artifact into $1 (default out/). No real build.
set -euo pipefail
OUT="${1:-out}"
mkdir -p "$OUT"
cat > "$OUT/index.html" <<HTML
<!doctype html>
<title>hello-safeguard</title>
<h1>hello, safeguard</h1>
<p>Built at commit ${GITHUB_SHA:-local}. This app does nothing consequential —
the product being demonstrated is the AtlaSent authorization chain, not the deploy.</p>
HTML
echo "built $OUT/index.html"
