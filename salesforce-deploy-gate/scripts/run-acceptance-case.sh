#!/usr/bin/env bash
# Salesforce/NetSuite change gate — buyer-observable acceptance case driver.
#
# Runs ONE acceptance case against the live AtlaSent API and asserts the expected
# runtime code and that no deploy would run. Every result is a real API response —
# nothing is fabricated. Gates a business-system change on production.deploy (BSCM;
# no new action class).
#
# Usage:   run-acceptance-case.sh SF-1|SF-2|...|SF-10
# Env:     ATLASENT_API_KEY   (ask_* scoped evaluate:write + verify:execute)
#          ATLASENT_BASE_URL  (…/functions/v1)
#          ATLASENT_ACTOR     (default github:github-actions[bot] — must be in allow_actors;
#                              this is what seed_saas_production_safeguard bakes in)
#          TARGET_SYSTEM      (salesforce|netsuite|servicenow|jira|aws; default salesforce)
#          TARGET_REF         (org alias / NetSuite account id; defaults per system)
#          PERMIT_TTL_SECONDS (optional; if <=60, SF-10 waits then verifies expired)
#
# The SAME case set runs against either target system — Salesforce and NetSuite are
# reference scenarios for one vendor-neutral contract, not two integrations. Run the
# suite once per system; a Salesforce run does NOT evidence NetSuite (and vice versa).
set -uo pipefail

CASE="${1:?usage: run-acceptance-case.sh SF-N}"
KEY="${ATLASENT_API_KEY:?set ATLASENT_API_KEY}"
BASE="${ATLASENT_BASE_URL:?set ATLASENT_BASE_URL (…/functions/v1)}"
ACTOR="${ATLASENT_ACTOR:-github:github-actions[bot]}"
SYSTEM="${TARGET_SYSTEM:-salesforce}"
# Bare lowercase 64-char hex — NOT prefixed with "sha256:". v1-evaluate validates
# execution_payload_hash against /^[0-9a-f]{64}$/i; a prefixed
# value fails that regex, so the hash is silently treated as absent — no binding is
# recorded, and v1-verify-permit's payload-hash check
# then has nothing to compare against and returns valid:true for ANY payload_hash,
# including a genuinely swapped one. This previously masked SF-6 (expected
# PAYLOAD_MISMATCH, silently passed instead) — see the preflight check below, which
# exists specifically so this class of regression fails loudly instead of silently.
DIGEST_A="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
DIGEST_B="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
STATE_DIGEST="cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
CHANGE_REQUEST="${CHANGE_REQUEST:-CR-2026-0142}"
AUTHORITY_PATH="${AUTHORITY_PATH:-change-advisory-board}"

# Regression guard: fail loudly, at driver-startup, if any payload-hash constant is
# not bare 64-char lowercase hex. Without this, a future edit that reintroduces a
# "sha256:" prefix (or any other decoration) degrades SF-6 back into a silent pass —
# the exact defect this fix closes. Do not weaken/remove this check.
for _atlasent_digest in "$DIGEST_A" "$DIGEST_B" "$STATE_DIGEST"; do
  if ! [[ "$_atlasent_digest" =~ ^[0-9a-f]{64}$ ]]; then
    echo "❌ internal driver error: payload-hash constant '$_atlasent_digest' is not bare 64-char lowercase hex." >&2
    echo "   v1-evaluate's execution_payload_hash validation (/^[0-9a-f]{64}\$/i) silently rejects anything else —" >&2
    echo "   no binding is recorded, and SF-6's PAYLOAD_MISMATCH check degrades into a silent pass. Fix DIGEST_*." >&2
    exit 2
  fi
done
unset _atlasent_digest

# Fail closed on an unrecognized system rather than silently running Salesforce.
case "$SYSTEM" in
  salesforce) TARGET="salesforce:${TARGET_REF:-acme-prod}"; ARTIFACT_PLAN_FORMAT="salesforce-change-set";      SYSTEM_REF_KEY="org" ;;
  netsuite)   TARGET="netsuite:${TARGET_REF:-1234567}";     ARTIFACT_PLAN_FORMAT="netsuite-sdf-project";       SYSTEM_REF_KEY="account" ;;
  servicenow) TARGET="servicenow:${TARGET_REF:-acmecorp}";  ARTIFACT_PLAN_FORMAT="servicenow-change-request";  SYSTEM_REF_KEY="instance" ;;
  jira)       TARGET="jira:${TARGET_REF:-acmecorp}";        ARTIFACT_PLAN_FORMAT="jira-issue";                 SYSTEM_REF_KEY="site" ;;
  aws)        TARGET="aws:${TARGET_REF:-123456789012}";     ARTIFACT_PLAN_FORMAT="terraform-plan";             SYSTEM_REF_KEY="account" ;;
  *) echo "❌ unknown TARGET_SYSTEM '$SYSTEM' (expected salesforce|netsuite|servicenow|jira|aws)" >&2; exit 2 ;;
esac
SYSTEM_REF="${TARGET#*:}"

sha256_hex() { # $1=payload → bare lowercase hex
  if command -v sha256sum >/dev/null 2>&1; then printf '%s' "$1" | sha256sum | awk '{print $1}'
  else printf '%s' "$1" | shasum -a 256 | awk '{print $1}'; fi
}

evaluate() { # $1=actor $2=approvals $3=change_window $4=payload_hash $5=extra_context_json $6=plan_format
  local pf="${6:-$ARTIFACT_PLAN_FORMAT}"
  # evidence_set_digest is a REAL digest over the approval evidence this case
  # actually presents (jq -S = deterministic key order), not a fixed constant.
  local esd="sha256:$(sha256_hex "$(jq -nc -S --argjson ap "$2" --arg cr "$CHANGE_REQUEST" '{approvals:$ap, change_request:$cr}')")"
  curl -sS -X POST "$BASE/v1-evaluate" -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
    -d "$(jq -nc --arg a "$1" --argjson ap "$2" --argjson cw "$3" --arg d "$4" --arg t "$TARGET" \
              --arg sys "$SYSTEM" --arg pf "$pf" --arg auth "$AUTHORITY_PATH" --arg esd "$esd" \
              --arg cr "$CHANGE_REQUEST" --arg refk "$SYSTEM_REF_KEY" --arg refv "$SYSTEM_REF" \
              --argjson extra "${5:-{\}}" '{
          action_type:"production.deploy", actor_id:$a, environment:"production", target_id:$t,
          execution_payload_hash:$d,
          context:({ environment:"production", system:$sys,
                     approvals:$ap, change_window:$cw, state_snapshot:$d,
                     # Vendor-neutral change-plan conventions. They ride the
                     # OPEN evaluate context; canonical_plan_digest IS the execution_payload_hash
                     # the permit binds — no wire change. The lane runbook §5 asserts these in the
                     # exported evidence, so the driver must actually emit them.
                     target_system:$sys, plan_format:$pf, authority_path:$auth,
                     canonical_plan_digest:$d, evidence_set_digest:$esd,
                     change_request:$cr }
                   + { ($refk): $refv } + $extra) }')"
}
verify() { # $1=permit_token $2=environment $3=payload_hash
  curl -sS -X POST "$BASE/v1-verify-permit" -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
    -d "$(jq -nc --arg t "$1" --arg env "$2" --arg d "$3" --arg a "$ACTOR" '{
          permit_token:$t, action_type:"production.deploy", actor_id:$a, environment:$env, payload_hash:$d }')"
}
say()  { echo "  $*"; }
pass() { echo "✅ $CASE PASS — $*"; exit 0; }
fail() { echo "❌ $CASE FAIL — $*"; exit 1; }

echo "── $CASE ── action=production.deploy caller=$ACTOR target=$TARGET system=$SYSTEM ──"

case "$CASE" in
  SF-1) # compliant Salesforce metadata deploy
    ev=$(evaluate "$ACTOR" 2 true "$DIGEST_A" '{}'); dec=$(jq -r '.decision' <<<"$ev"); pt=$(jq -r '.permit_token // ""' <<<"$ev")
    say "policy_result=$dec permit=${pt:+present}"
    [ "$dec" = "allow" ] && [ -n "$pt" ] || fail "expected allow+permit, got decision=$dec"
    vr=$(verify "$pt" production "$DIGEST_A"); val=$(jq -r '.valid' <<<"$vr")
    say "verification=$(jq -r '.outcome // ""' <<<"$vr") (valid=$val)"
    [ "$val" = "true" ] && pass "metadata deploy: allow → permit → verified → deploy would run" || fail "expected verified, got $(jq -c '{valid,outcome,verify_error_code}' <<<"$vr")" ;;

  SF-2) # caller outside allow_actors
    ev=$(evaluate "github:not-authorized[bot]" 2 true "$DIGEST_A" '{}'); dec=$(jq -r '.decision' <<<"$ev"); code=$(jq -r '.denial.deny_code // .deny_code // ""' <<<"$ev")
    say "policy_result=$dec deny_code=$code permit=none"
    [ "$dec" != "allow" ] && [ "$code" = "ACTOR_NOT_ALLOWED" ] && pass "unapproved deployer denied ACTOR_NOT_ALLOWED — no deploy" || fail "expected ACTOR_NOT_ALLOWED, got decision=$dec code=$code" ;;

  SF-3) # missing required CAB approval
    # Expects NO_AUTHORITY, not INSUFFICIENT_APPROVALS. The reference org's
    # production.deploy bundle (seed_saas_production_safeguard, provisioned by an
    # AtlaSent API migration) intentionally
    # requires a verified human-approval ARTIFACT for this action — a bare
    # context.approvals count is not sufficient authority, so the API's evaluate handler
    # overrides the rule engine's default INSUFFICIENT_APPROVALS with the frozen
    # NO_AUTHORITY code (documented in that migration's header, "verified live
    # 2026-07-17"). This is the intended, stricter assurance model for this bundle —
    # do not weaken the policy to make this case emit INSUFFICIENT_APPROVALS. A
    # distinct numeric-approval-only scenario would need its own fixture/bundle.
    ev=$(evaluate "$ACTOR" 1 true "$DIGEST_A" '{}'); dec=$(jq -r '.decision' <<<"$ev"); code=$(jq -r '.denial.deny_code // .deny_code // ""' <<<"$ev")
    say "policy_result=$dec deny_code=$code permit=none"
    [ "$dec" != "allow" ] && [ "$code" = "NO_AUTHORITY" ] && pass "1 approval (need a verified approval artifact) denied NO_AUTHORITY — no deploy" || fail "expected NO_AUTHORITY, got decision=$dec code=$code" ;;

  SF-4) # outside the change window
    # Expects the explicit OUTSIDE_CHANGE_WINDOW deny code (added by an AtlaSent
    # API migration merged 2026-08-11). seed_saas_production_safeguard's production.deploy
    # bundle now carries a SECOND template — an explicit
    # DENY(OUTSIDE_CHANGE_WINDOW) when context.environment=production AND
    # context.change_window=false — evaluated after the existing ALLOW template,
    # so allow still wins first-match when change_window=true. Requires an
    # operator to have re-run `select public.seed_saas_production_safeguard(
    # '<reference-org-uuid>');` against the reference org AFTER PR #1970 landed
    # (the fix is not auto-reconciled onto already-provisioned orgs — see that
    # migration's own header). If this case still reports NO_TEMPLATE_MATCH, the
    # reference org has not been re-seeded yet; that is an operator action, not a
    # driver bug.
    ev=$(evaluate "$ACTOR" 2 false "$DIGEST_A" '{}'); dec=$(jq -r '.decision' <<<"$ev"); code=$(jq -r '.denial.deny_code // .deny_code // ""' <<<"$ev")
    say "policy_result=$dec deny_code=$code permit=none"
    [ "$dec" != "allow" ] && [ "$code" = "OUTSIDE_CHANGE_WINDOW" ] && pass "change outside window denied OUTSIDE_CHANGE_WINDOW — no deploy" || fail "expected OUTSIDE_CHANGE_WINDOW, got decision=$dec code=$code (if NO_TEMPLATE_MATCH: re-run seed_saas_production_safeguard on the reference org to pick up PR #1970)" ;;

  SF-5) # missing permit
    vr=$(verify "" production "$DIGEST_A"); code=$(jq -r '.verify_error_code // ""' <<<"$vr"); val=$(jq -r '.valid' <<<"$vr")
    say "verification=$(jq -r '.outcome // ""' <<<"$vr") (valid=$val, code=$code)"
    [ "$val" = "false" ] && [ "$code" = "MISSING_PERMIT" ] && pass "no permit → MISSING_PERMIT — no deploy" || fail "expected MISSING_PERMIT, got $(jq -c '{valid,outcome,verify_error_code}' <<<"$vr")" ;;

  SF-6) # swapped metadata package (altered artifact)
    ev=$(evaluate "$ACTOR" 2 true "$DIGEST_A" '{}'); pt=$(jq -r '.permit_token // ""' <<<"$ev")
    [ -n "$pt" ] || fail "expected a permit bound to package-A; got decision=$(jq -r '.decision' <<<"$ev")"
    vr=$(verify "$pt" production "$DIGEST_B"); code=$(jq -r '.verify_error_code // ""' <<<"$vr"); out=$(jq -r '.outcome // ""' <<<"$vr")
    say "permit=present(bound package-A) verification=$out (code=$code)"
    # Wire .outcome is coarse (allow|deny|revoked); the fine-grained classification
    # (mismatch/replay_blocked/…) lives in verification_events, not the response. Assert
    # the authoritative verify_error_code + the coarse outcome.
    [ "$code" = "PAYLOAD_MISMATCH" ] && [ "$out" = "deny" ] && pass "swapped metadata package → PAYLOAD_MISMATCH (deny) — no deploy" || fail "expected PAYLOAD_MISMATCH, got $(jq -c '{valid,outcome,verify_error_code}' <<<"$vr")" ;;

  SF-7) # wrong environment
    ev=$(evaluate "$ACTOR" 2 true "$DIGEST_A" '{}'); pt=$(jq -r '.permit_token // ""' <<<"$ev")
    [ -n "$pt" ] || fail "expected a permit bound to production"
    vr=$(verify "$pt" sandbox "$DIGEST_A"); code=$(jq -r '.verify_error_code // ""' <<<"$vr"); out=$(jq -r '.outcome // ""' <<<"$vr")
    say "permit=present(bound production) verification=$out (code=$code)"
    [ "$code" = "ENVIRONMENT_MISMATCH" ] && [ "$out" = "deny" ] && pass "production permit presented for sandbox → ENVIRONMENT_MISMATCH (deny) — no deploy" || fail "expected ENVIRONMENT_MISMATCH, got $(jq -c '{valid,outcome,verify_error_code}' <<<"$vr")" ;;

  SF-8) # replayed permit
    ev=$(evaluate "$ACTOR" 2 true "$DIGEST_A" '{}'); pt=$(jq -r '.permit_token // ""' <<<"$ev")
    [ -n "$pt" ] || fail "expected a permit"
    vr1=$(verify "$pt" production "$DIGEST_A"); val1=$(jq -r '.valid' <<<"$vr1"); out1=$(jq -r '.outcome // ""' <<<"$vr1")
    say "verification#1=$out1 (valid=$val1)"
    [ "$val1" = "true" ] || fail "expected first verify to succeed (valid=true), got $(jq -c '{valid,outcome,verify_error_code}' <<<"$vr1")"
    vr2=$(verify "$pt" production "$DIGEST_A"); out2=$(jq -r '.outcome // ""' <<<"$vr2"); code2=$(jq -r '.verify_error_code // ""' <<<"$vr2")
    say "verification#2=$out2 (code=$code2)"
    [ "$code2" = "PERMIT_ALREADY_USED" ] && [ "$out2" = "deny" ] && pass "second use → PERMIT_ALREADY_USED (deny; replay blocked) — no second deploy" || fail "expected PERMIT_ALREADY_USED, got $(jq -c '{valid,outcome,verify_error_code}' <<<"$vr2")" ;;

  SF-9) # live config edit — the state-snapshot execution profile of production.deploy (authorized change plan)
    # Salesforce-only by CONTRACT, not by omission: the frozen change-plan vocabulary
    # defines exactly three plan_formats — salesforce-change-set,
    # netsuite-sdf-project, salesforce-config-edit. There is no NetSuite config-edit
    # format, and minting one here would invent vocabulary the contract does not carry.
    # So under NetSuite this is a recorded SKIP with a reason, never a silent pass.
    if [ "$SYSTEM" != "salesforce" ]; then
      echo "⏭️  $CASE SKIPPED — the config-edit profile has no NetSuite plan_format in the frozen change-plan vocabulary (salesforce-config-edit is Salesforce-only). NetSuite change plans are covered by SF-1..SF-8 as netsuite-sdf-project."; exit 0
    fi
    ev=$(evaluate "$ACTOR" 2 true "$STATE_DIGEST" '{"profile":"state_snapshot","config_path":"Flow/Opportunity_Approval"}' "salesforce-config-edit")
    dec=$(jq -r '.decision' <<<"$ev"); pt=$(jq -r '.permit_token // ""' <<<"$ev")
    say "policy_result=$dec permit=${pt:+present} profile=state_snapshot"
    [ "$dec" = "allow" ] && [ -n "$pt" ] || fail "expected allow+permit for the config-edit profile, got decision=$dec"
    vr=$(verify "$pt" production "$STATE_DIGEST"); val=$(jq -r '.valid' <<<"$vr")
    say "verification=$(jq -r '.outcome // ""' <<<"$vr") (valid=$val)"
    [ "$val" = "true" ] && pass "live config edit: allow → permit bound to before/after state → verified" || fail "expected verified, got $(jq -c '{valid,outcome,verify_error_code}' <<<"$vr")" ;;

  SF-10) # expired permit — needs a short-TTL action class to run automatically
    ttl="${PERMIT_TTL_SECONDS:-3600}"
    if [ "$ttl" -gt 60 ]; then
      echo "⏭️  $CASE SKIPPED — needs a short-TTL permit. Set the reference org's production.deploy permit_ttl_seconds<=60 and PERMIT_TTL_SECONDS to run this automatically (default TTL is 1h)."; exit 0
    fi
    ev=$(evaluate "$ACTOR" 2 true "$DIGEST_A" '{}'); pt=$(jq -r '.permit_token // ""' <<<"$ev")
    [ -n "$pt" ] || fail "expected a permit"
    say "waiting $((ttl+3))s for permit to expire…"; sleep "$((ttl+3))"
    vr=$(verify "$pt" production "$DIGEST_A"); code=$(jq -r '.verify_error_code // ""' <<<"$vr"); out=$(jq -r '.outcome // ""' <<<"$vr")
    say "verification=$out (code=$code)"
    [ "$code" = "PERMIT_EXPIRED" ] && [ "$out" = "deny" ] && pass "expired permit → PERMIT_EXPIRED (deny) — no deploy" || fail "expected PERMIT_EXPIRED, got $(jq -c '{valid,outcome,verify_error_code}' <<<"$vr")" ;;

  *) fail "unknown case '$CASE' (expected SF-1..SF-10)" ;;
esac
