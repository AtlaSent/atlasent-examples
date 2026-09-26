# SMS OTP Secondary Challenge

An AtlaSent-level secondary challenge layer for high-privilege operations.
When a policy rule requires `challenge: sms_otp`, AtlaSent puts the evaluation
into `hold` and requires the actor to prove phone possession before a permit
is issued. This is distinct from Supabase Auth MFA: it is enforced by the
AtlaSent authorization engine, not the identity layer, and it applies to
individual consequential actions rather than to login sessions.

## When to use this

| Trigger | Example actions |
|---|---|
| Break-glass | `database.production.break_glass`, `iam.superuser.assume` |
| API key creation | `api_key.create` with `environment: production` |
| Governance holds requiring human confirmation | `policy.publish`, `schema.migrate.production` |
| High-value financial actions | `payment.wire_transfer` above a threshold |

## Flow

```
Actor                     App                        AtlaSent
  |                        |                              |
  |-- "open break-glass" ->|                              |
  |                        |-- POST /v1-evaluate -------->|
  |                        |<-- decision: hold ----------|
  |                        |   challenge: sms_otp        |
  |                        |                              |
  |                        |-- POST /v1-sms-otp/send --->|
  |                        |   { phone_e164,              |
  |                        |     action_context }         |
  |                        |<-- { otp_id, expires_at } --|
  |<-- "Enter SMS code" ---|                              |
  |-- "123456" ----------->|                              |
  |                        |-- POST /v1-sms-otp/verify ->|
  |                        |   { otp_id, code }           |
  |                        |<-- { valid, challenge_token}|
  |                        |                              |
  |                        |-- POST /v1-evaluate (retry)->|
  |                        |   context: {challenge_token} |
  |                        |<-- decision: allow ----------|
  |                        |   permit_token: pt.v2.*     |
  |                        |                              |
  |                        |-- POST /v1-verify-permit --->|
  |                        |<-- { valid: true } ----------|
  |                        |                              |
  |                        |-- [execute action] -------->|
```

## Prerequisites

1. **Phone enrollment.** The actor's E.164 phone number must be enrolled in
   AtlaSent. Use the Console at **Settings → Identity → Phone Numbers** or the
   `POST /v1/actors/{id}/phone` API before the first OTP send.

2. **Twilio credentials** (production). AtlaSent calls Twilio on your behalf.
   Set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `TWILIO_FROM_NUMBER` as
   org-level secrets in the AtlaSent console.

3. **Policy rule.** Add `challenge: sms_otp` to the rule that covers the
   action you want to gate:

   ```yaml
   - id: break-glass-requires-otp
     action: database.production.break_glass
     decision: hold
     challenge: sms_otp
     reason: "Break-glass requires SMS OTP confirmation"
   ```

4. **Dry-run mode** (local dev). Set `DRY_RUN=true` in your AtlaSent org
   settings. AtlaSent will accept the mock code `000000` and write the OTP
   to the audit trail instead of dispatching to Twilio.

## Required environment variables

| Variable | Required | Description |
|---|---|---|
| `ATLASENT_API_KEY` | yes | API key with `evaluate:write` and `sms_otp:write` scopes. |
| `ATLASENT_ORG_ID` | yes | Your AtlaSent org ID. |
| `ATLASENT_BASE_URL` | no | Defaults to `https://api.atlasent.io/functions/v1`. |
| `ACTOR_PHONE_E164` | no | Phone in E.164 format. Defaults to `+15550100001` (dry-run demo). |

## Run

```bash
npm install
export ATLASENT_API_KEY=ask_live_...
export ATLASENT_ORG_ID=org_acme
npx tsx index.ts
```

## Expected output (dry-run mode)

```
Step 1: requesting break-glass access...
  actor_id:    ops-lead@acme.internal
  action_type: database.production.break_glass
  decision:    hold
  request_id:  req_01HZ...
  Challenge:   SMS OTP required for break-glass operations

Step 2: sending SMS OTP...
  phone_e164:      +15550100001
  action_context:  break_glass
  otp_id:          otp_01HZ...
  destination:     ***-***-0001
  expires_at:      2026-06-10T12:10:00Z

Step 3: collecting OTP from user...
  [mock] OTP sent to ***-***-0001 — simulating user input.
  [mock] User entered: 000000

Step 4: verifying OTP...
  OTP valid — challenge_token received.

Step 5: re-evaluating with challenge_token...
  decision:    allow
  permit_token: pt.v2.eyJ...
  expires_at:   2026-06-10T13:00:00Z

Step 6: verifying permit before executing...
  Permit verified — outcome: allow

Step 7: executing break-glass action...
  [action] Granting temporary read access to prod-postgres-primary
  [action] Permit: pt.v2.eyJ...
  [action] Break-glass session opened. Expires in 1 hour.

Done. Full audit trail recorded in AtlaSent.
  Review at: https://console.atlasent.io/decisions/req_01HZ...
```

## Security properties

- **10-minute OTP TTL.** The `otp_id` returned by `/v1-sms-otp/send` expires
  after 10 minutes. Expired OTPs always return `valid: false`.
- **Single-use.** Each OTP code is consumed on first successful verification.
  Replaying the same code always returns `valid: false`.
- **SHA-256 hash storage.** AtlaSent never stores the raw OTP code — only
  `SHA-256(code + otp_id)` is persisted. The plaintext code is discarded after
  hashing.
- **challenge_token is opaque and scoped.** The token returned by verify is
  bound to the `otp_id` and the actor. It cannot be reused across actors or
  action types.
- **Fail-closed.** If `/v1-sms-otp/send` or `/v1-sms-otp/verify` returns an
  error, the re-evaluate call will not include a valid `challenge_token` and
  AtlaSent will continue to return `hold`. The action is never executed.

## Audit trail

Every step writes an immutable event to the AtlaSent audit chain:

| Event | Written by |
|---|---|
| `evaluation.hold` | Step 1 — initial evaluate |
| `sms_otp.sent` | Step 2 — /v1-sms-otp/send |
| `sms_otp.verified` | Step 4 — /v1-sms-otp/verify |
| `evaluation.completed` (allow) | Step 5 — re-evaluate |
| `permit.verified` | Step 6 — /v1-verify-permit |

The full chain is available in the AtlaSent console under
**Decisions → {request_id}** and in evidence bundles exported via
`/v1/evidence-exports`.

## Next steps

- See [`../flows/06-sso-walkthrough/`](../flows/06-sso-walkthrough/) for the
  SSO integration that complements OTP challenges.
- See [`../security-actions/`](../security-actions/) for more high-privilege
  action gating patterns.
- See the [AtlaSent documentation](https://docs.atlasent.io) for the full API
  reference and integration patterns.
