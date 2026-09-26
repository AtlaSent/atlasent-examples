# Verified-actor authorization

A runnable demonstration of AtlaSent's **verified-actor gate** — the control that
rejects a spoofable `actor_id` unless the request carries a cryptographically
verified actor identity.

The problem it solves: `actor_id` on an evaluate request is caller-controlled. A
machine can put any value (even a UUID) there. For action classes flagged
`requires_verified_actor`, AtlaSent will not reach `allow` unless the caller
presents a signed `actor_identity.v1` assertion **bound to this request** — so
the audit record proves *who* acted, not *who the caller claimed to be*.

## Run it

```bash
node mint-actor-identity.mjs    # Node >= 20, zero dependencies
```

It generates an Ed25519 issuer keypair, mints a request-bound assertion, verifies
the signature locally, and prints:

1. the `ACTOR_TRUSTED_ISSUERS` secret to configure on the runtime,
2. the SQL to enable the gate on an action class,
3. the **spoofed** request (no assertion → `deny ACTOR_UNVERIFIED`),
4. the **verified** request (assertion attached → `allow` + signed evidence).

The script's canonicalization is byte-identical to the runtime verifier
(`_shared/actor_identity.ts` / `_shared/canonical.ts`), so the signature it
produces verifies server-side unchanged. (Validated: a minted assertion returns
`{ ok: true }` from the runtime `verifyActorIdentity`.)

## What you'll see

| Request | Outcome |
|---|---|
| `actor_id` only, no `actor_identity` | `deny`, `deny_code: ACTOR_UNVERIFIED`, no permit |
| valid, in-binding `actor_identity.v1` | `allow`; `verified_actor_identity` written into the Ed25519-signed `evaluation.completed` audit record |

The runtime enforces four bindings (any mismatch → deny): `subject.principal_id`
== `actor_id`, and `binding.{action_type, tenant_id, environment}` == the request.

## Assurance levels — why Ed25519

This demo uses **Ed25519** deliberately. Both Ed25519 and HS256 (HMAC) give full
enforcement and L1 (runtime-verified, signed) evidence. Only Ed25519 puts you on
the path to **L2 — Independent Identity Verification**: because the verification
key is *public*, an auditor can one day validate the assertion themselves without
trusting AtlaSent's runtime. An HMAC secret can't be shared with an auditor
without handing them the power to mint assertions, so HMAC stays L1 by
construction.

## Next steps

- Operator setup: [`atlasent-docs/guides/verified-actor-enablement.md`](https://docs.atlasent.io)
- The `ACTOR_UNVERIFIED` deny code: `atlasent-docs/guides/deny-codes.md`
- L2 scope: `atlasent-docs/plans/independent-identity-verification.md`
