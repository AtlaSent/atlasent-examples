#!/usr/bin/env bash
# SaaS Production Safeguard Pack — buyer-observable acceptance case driver.
#
# Runs ONE of the eight acceptance cases against the live AtlaSent API and asserts
# the expected runtime code and that no deploy would run. Every result is a real
# API response — nothing is fabricated (Golden Path Rule #1). Prints a one-page
# summary per case: action · caller · policy result · permit · verification · PASS/FAIL.
#
# Usage:   run-acceptance-case.sh AC-1|AC-2|...|AC-8
# Env:     ATLASENT_API_KEY (ask_* scoped evaluate:write + verify:execute)
#          ATLASENT_BASE_URL (…/functions/v1)
#          ATLASENT_ACTOR        (default github:github-actions[bot] — must be in allow_actors)
#          PERMIT_TTL_SECONDS    (optional; if <=60, AC-7 waits then verifies expired)
set -uo pipefail

CASE="${1:?usage: run-acceptance-case.sh AC-N}"
KEY="${ATLASENT_API_KEY:?set ATLASENT_API_KEY}"
BASE="${ATLASENT_BASE_URL:?set ATLASENT_BASE_URL (…/functions/v1)}"
ACTOR="${ATLASENT_ACTOR:-github:github-actions[bot]}"
ACTION="production.deploy"
DIGEST_A="sha256:aaaa000000000000000000000000000000000000000000000000000000000000"
DIGEST_B="sha256:bbbb000000000000000000000000000000000000000000000000000000000000"

# Declared expected result per case — stamped into context.acceptance_expected so
# the console acceptance-run view (EvaluationDetail) can compute the pass/fail
# verdict (observed vs expected). The RUN declares expectation; the RUNTIME
# provides observed; the console only compares — no drift-prone claims table.
case "$CASE" in
  AC-1) ACCEPT_EXPECTED='{"decision":"allow","verify_outcome":"verified"}' ;;
  AC-2) ACCEPT_EXPECTED='{"decision":"deny","deny_code":"ACTOR_NOT_ALLOWED"}' ;;
  AC-3) ACCEPT_EXPECTED='{"decision":"deny","deny_code":"INSUFFICIENT_APPROVALS"}' ;;
  AC-5) ACCEPT_EXPECTED='{"verify_outcome":"mismatch","verify_error_code":"PAYLOAD_MISMATCH"}' ;;
  AC-6) ACCEPT_EXPECTED='{"verify_outcome":"mismatch","verify_error_code":"ENVIRONMENT_MISMATCH"}' ;;
  AC-7) ACCEPT_EXPECTED='{"verify_outcome":"expired","verify_error_code":"PERMIT_EXPIRED"}' ;;
  AC-8) ACCEPT_EXPECTED='{"verify_outcome":"replay_blocked","verify_error_code":"PERMIT_ALREADY_USED"}' ;;
  *)    ACCEPT_EXPECTED='{}' ;;
esac

evaluate() { # $1=actor $2=approvals $3=change_window $4=payload_hash
  curl -sS -X POST "$BASE/v1-evaluate" -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
    -d "$(jq -nc --arg a "$1" --argjson ap "$2" --argjson cw "$3" --arg d "$4" \
              --arg case "$CASE" --argjson exp "$ACCEPT_EXPECTED" '{
          action_type:"production.deploy", actor_id:$a, environment:"production",
          target_id:"service:hello-safeguard", execution_payload_hash:$d,
          context:{ environment:"production", approvals:$ap, change_window:$cw, state_snapshot:$d,
                    acceptance_case:$case, acceptance_expected:$exp } }')"
}
verify() { # $1=permit_token $2=environment $3=payload_hash
  curl -sS -X POST "$BASE/v1-verify-permit" -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
    -d "$(jq -nc --arg t "$1" --arg env "$2" --arg d "$3" --arg a "$ACTOR" '{
          permit_token:$t, action_type:"production.deploy", actor_id:$a, environment:$env, payload_hash:$d }')"
}
say()  { echo "  $*"; }
pass() { echo "✅ $CASE PASS — $*"; exit 0; }
fail() { echo "❌ $CASE FAIL — $*"; exit 1; }

echo "── $CASE ── action=$ACTION caller=$ACTOR ──"

case "$CASE" in
  AC-1) # compliant deployment
    ev=$(evaluate "$ACTOR" 2 true "$DIGEST_A"); dec=$(jq -r '.decision' <<<"$ev"); pt=$(jq -r '.permit_token // ""' <<<"$ev")
    say "policy_result=$dec permit=${pt:+present}"
    [ "$dec" = "allow" ] && [ -n "$pt" ] || fail "expected allow+permit, got decision=$dec permit=${pt:+present}"
    vr=$(verify "$pt" production "$DIGEST_A"); out=$(jq -r '.outcome // ""' <<<"$vr"); val=$(jq -r '.valid' <<<"$vr")
    say "verification=$out (valid=$val)"
    [ "$val" = "true" ] && pass "allow → permit → verified → deploy would run" || fail "expected verified, got $(jq -c '{valid,outcome,verify_error_code}' <<<"$vr")" ;;

  AC-2) # caller outside authority scope
    ev=$(evaluate "github:not-authorized[bot]" 2 true "$DIGEST_A"); dec=$(jq -r '.decision' <<<"$ev"); code=$(jq -r '.denial.deny_code // .deny_code // ""' <<<"$ev")
    say "policy_result=$dec deny_code=$code permit=none"
    [ "$dec" != "allow" ] && [ "$code" = "ACTOR_NOT_ALLOWED" ] && pass "wrong caller denied ACTOR_NOT_ALLOWED — no deploy" || fail "expected deny ACTOR_NOT_ALLOWED, got decision=$dec code=$code" ;;

  AC-3) # missing required approval
    ev=$(evaluate "$ACTOR" 1 true "$DIGEST_A"); dec=$(jq -r '.decision' <<<"$ev"); code=$(jq -r '.denial.deny_code // .deny_code // ""' <<<"$ev")
    say "policy_result=$dec deny_code=$code permit=none"
    [ "$dec" != "allow" ] && [ "$code" = "INSUFFICIENT_APPROVALS" ] && pass "1 approval (need 2) denied INSUFFICIENT_APPROVALS — no deploy" || fail "expected deny INSUFFICIENT_APPROVALS, got decision=$dec code=$code" ;;

  AC-4) # missing permit
    vr=$(verify "" production "$DIGEST_A"); code=$(jq -r '.verify_error_code // ""' <<<"$vr"); val=$(jq -r '.valid' <<<"$vr")
    say "verification=$(jq -r '.outcome // ""' <<<"$vr") (valid=$val, code=$code)"
    [ "$val" = "false" ] && [ "$code" = "MISSING_PERMIT" ] && pass "no permit → MISSING_PERMIT — no deploy" || fail "expected MISSING_PERMIT, got $(jq -c '{valid,outcome,verify_error_code}' <<<"$vr")" ;;

  AC-5) # altered artifact
    ev=$(evaluate "$ACTOR" 2 true "$DIGEST_A"); pt=$(jq -r '.permit_token // ""' <<<"$ev")
    [ -n "$pt" ] || fail "expected a permit bound to digest-A; got decision=$(jq -r '.decision' <<<"$ev")"
    vr=$(verify "$pt" production "$DIGEST_B"); code=$(jq -r '.verify_error_code // ""' <<<"$vr"); out=$(jq -r '.outcome // ""' <<<"$vr")
    say "permit=present(bound digest-A) verification=$out (code=$code)"
    [ "$out" = "mismatch" ] && [ "$code" = "PAYLOAD_MISMATCH" ] && pass "swapped artifact → PAYLOAD_MISMATCH — no deploy" || fail "expected PAYLOAD_MISMATCH, got $(jq -c '{valid,outcome,verify_error_code}' <<<"$vr")" ;;

  AC-6) # wrong environment
    ev=$(evaluate "$ACTOR" 2 true "$DIGEST_A"); pt=$(jq -r '.permit_token // ""' <<<"$ev")
    [ -n "$pt" ] || fail "expected a permit bound to production"
    vr=$(verify "$pt" staging "$DIGEST_A"); code=$(jq -r '.verify_error_code // ""' <<<"$vr"); out=$(jq -r '.outcome // ""' <<<"$vr")
    say "permit=present(bound production) verification=$out (code=$code)"
    [ "$out" = "mismatch" ] && [ "$code" = "ENVIRONMENT_MISMATCH" ] && pass "staging permit for production → ENVIRONMENT_MISMATCH — no deploy" || fail "expected ENVIRONMENT_MISMATCH, got $(jq -c '{valid,outcome,verify_error_code}' <<<"$vr")" ;;

  AC-7) # expired permit — needs a short-TTL action class to run automatically
    ttl="${PERMIT_TTL_SECONDS:-3600}"
    if [ "$ttl" -gt 60 ]; then
      echo "⏭️  $CASE SKIPPED — needs a short-TTL permit. Set the reference org's production.deploy permit_ttl_seconds<=60 and PERMIT_TTL_SECONDS to run this automatically (default TTL is 1h; the runbook documents the manual expiry check)."; exit 0
    fi
    ev=$(evaluate "$ACTOR" 2 true "$DIGEST_A"); pt=$(jq -r '.permit_token // ""' <<<"$ev")
    [ -n "$pt" ] || fail "expected a permit"
    say "waiting $((ttl+3))s for permit to expire…"; sleep "$((ttl+3))"
    vr=$(verify "$pt" production "$DIGEST_A"); code=$(jq -r '.verify_error_code // ""' <<<"$vr"); out=$(jq -r '.outcome // ""' <<<"$vr")
    say "verification=$out (code=$code)"
    [ "$out" = "expired" ] && [ "$code" = "PERMIT_EXPIRED" ] && pass "expired permit → PERMIT_EXPIRED — no deploy" || fail "expected PERMIT_EXPIRED, got $(jq -c '{valid,outcome,verify_error_code}' <<<"$vr")" ;;

  AC-8) # replayed permit
    ev=$(evaluate "$ACTOR" 2 true "$DIGEST_A"); pt=$(jq -r '.permit_token // ""' <<<"$ev")
    [ -n "$pt" ] || fail "expected a permit"
    vr1=$(verify "$pt" production "$DIGEST_A"); out1=$(jq -r '.outcome // ""' <<<"$vr1")
    say "verification#1=$out1"
    [ "$out1" = "verified" ] || fail "expected first verify to succeed, got $(jq -c '{valid,outcome,verify_error_code}' <<<"$vr1")"
    vr2=$(verify "$pt" production "$DIGEST_A"); out2=$(jq -r '.outcome // ""' <<<"$vr2"); code2=$(jq -r '.verify_error_code // ""' <<<"$vr2")
    say "verification#2=$out2 (code=$code2)"
    [ "$out2" = "replay_blocked" ] && [ "$code2" = "PERMIT_ALREADY_USED" ] && pass "second use → PERMIT_ALREADY_USED (replay_blocked) — no second deploy" || fail "expected replay_blocked, got $(jq -c '{valid,outcome,verify_error_code}' <<<"$vr2")" ;;

  *) fail "unknown case '$CASE' (expected AC-1..AC-8)" ;;
esac
