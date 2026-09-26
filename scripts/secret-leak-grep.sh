#!/usr/bin/env bash
# Fail if any tracked file under flows/ (or the top-level docs) contains
# what looks like a real AtlaSent API key, OpenAI key, AWS key, or a
# Supabase URL that isn't a placeholder.
#
# This is a belt-and-braces check — the real defence is .env.example
# files and ATLASENT_API_KEY-only env loading.

set -euo pipefail

bad=0

patterns=(
  # AtlaSent: sk_live_ / sk_prod_ followed by >=16 base62 chars
  'sk_(live|prod)_[A-Za-z0-9]{16,}'
  # Generic OpenAI
  'sk-[A-Za-z0-9]{20,}'
  # AWS access key
  'AKIA[0-9A-Z]{16}'
  # Supabase project URL that is NOT the "your-project" placeholder
  'https://(?!your-project)[a-z0-9-]+\.supabase\.co'
  # Slack / GitHub PATs
  'xox[baprs]-[A-Za-z0-9-]{10,}'
  'ghp_[A-Za-z0-9]{36,}'
  'github_pat_[A-Za-z0-9_]{22,}'
)

paths=(flows README.md SECURITY.md docs v2 langchain-agent llamaindex-agent)

for pat in "${patterns[@]}"; do
  if git grep -nEI --untracked -- "$pat" -- "${paths[@]}" 2>/dev/null; then
    echo "::error::potential secret matched pattern: $pat" >&2
    bad=1
  fi
done

if [[ $bad -ne 0 ]]; then
  echo "" >&2
  echo "Secret-leak gate failed. Remove the values above or replace with" >&2
  echo "placeholders (e.g. sk_staging_REPLACE_ME, https://your-project.supabase.co)." >&2
  exit 1
fi

echo "secret-leak gate: clean"
