# Accounting Close Authorization — Close-Ops Pilot

> **Status:** This is the runnable substrate for the close-ops pilot tenant.
> Companion to `docs/PILOT_RUNBOOK_2026-04-29.md`
> (operator-internal) and
> `docs/CLOSE_OPS_PILOT_OFFER.md`
> (what the pilot tenant gets, in business terms).

AtlaSent enforces non-bypassable authorization for accounting close workflows
and produces an immutable, offline-verifiable audit-evidence pack for every
permitted action.

## What you get in 30 seconds

```bash
pip install -r requirements.txt
./demo-and-verify.sh
```

That runs the close-cycle demo end-to-end, exports a signed evidence bundle,
and verifies it offline. Exit code 0 means the hash chain and Ed25519
signature both check out.

For the SDK-free auditor path (no `atlasent` install required, just
`cryptography`):

```bash
python _sample.py --out sample-audit-bundle.json
python verify-audit.py --bundle sample-audit-bundle.json
```

A pre-generated, reproducible bundle lives at
[`sample-audit-bundle.json`](./sample-audit-bundle.json) — auditors can
inspect it before running anything.

## The deliverable, in one sentence

A close-cycle authorization gate that issues single-use cryptographic permits
for every protected action, captures every decision (allow, deny, hold) in a
SHA-256 hash-linked, Ed25519-signed audit chain, and exports a bundle an
external auditor verifies offline with no AtlaSent dependency beyond
`cryptography`.

## Run

```bash
pip install -r requirements.txt

# Full close-cycle demo (7 scenarios, in-process stub, no API key)
python main.py

# Same demo, but also export a signed evidence bundle
python main.py --export bundle.json

# Vendor master mutation — separation of duties
python vendor-master.py

# Locked-period emergency override — immutable evidence
python emergency-override.py

# Verify a delivered bundle offline (no SDK, no network)
python verify-audit.py --bundle bundle.json

# Verify with a pinned public key (recommended for real audits)
python verify-audit.py --bundle bundle.json --pubkey <base64-from-keys.atlasent.io>
```

Set `ATLASENT_API_KEY` to switch any of the demo scripts to the live
AtlaSent API. Verification has both modes: `--bundle PATH` for offline
file verification, `--from/--to/--actor/--out` for live-API export.

## Protected actions

| Action | Enforcement rule |
|---|---|
| `close_task.complete` | Requires `task_id`, `completed_by`, and matching period |
| `reconciliation.certify` | Certifier must be on the authorized controller list; dual approval enforced when required |
| `journal_entry.approve` | JEs above $100k delegation threshold escalate to a CFO hold |
| `journal_entry.post` | Posting to a locked period denies unless an active emergency override permit is supplied |
| `vendor_master.update` | High-risk fields (`bank_routing`, `bank_account`, `tax_id`, `remit_to_address`) require controller role + named secondary approver |
| `adjustment.submit` | Submitter must be on the authorized submitter list |
| `period.close` | All tasks must be complete; requires CFO sign-off |
| `period.emergency_override` | Requires CFO + audit committee chair dual signoff, `audit_reference`, `materiality_assessment`; permit is single-use, TTL-bound, scoped to a single JE |

## Scenarios

### `main.py` — close-cycle pilot (7 cases)

1. `close_task.complete` — **BLOCKED**: missing context fields
2. `reconciliation.certify` — **ALLOWED**: full context → verified permit → audit record
3. `journal_entry.approve` — **HOLD** ($250k > $100k limit) → CFO approval → permit → execution
4. `adjustment.submit` — **BLOCKED**: unauthorized submitter
5. `adjustment.submit` — **ALLOWED**: authorized submitter
6. `period.close` — **BLOCKED**: outstanding tasks remain
7. `period.close` — **HOLD** → CFO sign-off → permit → execution

### `vendor-master.py` — vendor master mutation

1. AP clerk attempts a bank-routing change → **BLOCKED** (role insufficient — separation of duties)
2. Controller submits the change with no secondary approver → **HOLD** (dual signoff required)
3. Controller resubmits with CFO as secondary approver → **ALLOWED** → execute → verify → audit row

What the audit trail captures:

```
evt_001  vendor_master.update  u_alice (ap_clerk)   deny     Role insufficient for high-risk field
evt_002  vendor_master.update  u_bob   (controller) hold     Secondary approver required
evt_003  vendor_master.update  u_bob   (controller) allow    Approver: u_carol (CFO)
evt_004  permit.consume        u_bob   (controller) verified permit=pt_…
```

### `emergency-override.py` — emergency override of a locked period

The hardest case: a JE that must post inside an already-locked period, with auditor-grade evidence.

1. Agent attempts the reclass JE inside locked period 2026-Q1 → **BLOCKED** (`PERIOD_LOCKED`)
2. Operator submits an emergency override request, CFO only → **HOLD** (requires audit committee chair counter-sign)
3. Audit committee chair signs on; resubmit → **ALLOWED** with override permit (TTL 120m, scoped to the single JE)
4. Agent re-posts the JE under the override permit → **ALLOWED**
5. Both permits are consumed; payload hash is bound into the proof chain
6. After TTL elapses, the period **automatically re-locks** — no door is left open
7. Audit trail shows all seven rows: original deny, override request with materiality assessment, both approvals, permit issuance, JE post, both consumes, and the auto re-lock

## What this demonstrates to a controller / audit reviewer

- **Execution-time authorization** — every protected action is evaluated *before* the ERP / GL is touched. Denied requests never reach the system of record.
- **Separation of duties** — roles + named approvers are policy primitives, not conventions. An AP clerk cannot do a controller's job; one controller cannot self-approve.
- **Approval enforcement** — `hold` decisions queue for the named human; the system does not let one human authorize their own action. Approvers are recorded on the decision row.
- **Evidence generation** — every decision (deny, hold, allow) is recorded with the policy version that made it and the permit ID that bound the execution.
- **Reversibility** — overrides are single-use, TTL-bound, scoped to a specific resource. Locked periods auto-re-lock; there is no manual "leave the door open" path.
- **Immutable auditability** — every event is appended to a SHA-256 hash-linked, Ed25519-signed chain. An auditor verifies the chain offline using only the published public key.
- **Controlled overrides** — overrides do not hide the original deny. The audit chain shows lock → unlock-under-override → re-lock with the full approver provenance.

## The signed evidence pack

`main.py --export bundle.json` writes a single JSON file with this shape:

```json
{
  "atlasent_audit_bundle_version": "1",
  "exported_at":            "2026-03-31T18:01:00+00:00",
  "period":                 {"from": "...", "to": "..."},
  "key_id":                 "atlasent-demo-key-1",
  "public_key_ed25519_b64": "<base64>",
  "events":                 [{...}, ...],
  "head_hash":              "<32 hex>",
  "signature_ed25519_b64":  "<base64>",
  "demo":                   true
}
```

Each event in the chain carries `permit_id`, `audit_hash`, `previous_hash`,
actor, action, decision, reason, timestamp, and a context snapshot.
`audit_hash` is `SHA-256` over the canonical-JSON of every other evidence
field — `event_id`, `timestamp`, `actor`, `action`, `decision`, `permit_id`,
`reason`, `context_snapshot` (recursively sort-keyed), and
`previous_hash` — truncated to 32 hex chars, applied transitively. The
`head_hash` is the last event's `audit_hash`. The `signature_ed25519_b64`
is an Ed25519 signature over the UTF-8 bytes of `head_hash`.

The bundle envelope and signing logic live in [`_bundle.py`](./_bundle.py).
That module has zero `atlasent` SDK dependency — `cryptography` is its only
external requirement — so the verifier ([`verify-audit.py`](./verify-audit.py))
runs anywhere Python and `cryptography` are available. Auditors do not need
to install our SDK to verify a delivered bundle.

> **Demo keys are demo keys.** `_bundle.py` derives a deterministic Ed25519
> keypair from a fixed seed so demo output is reproducible. Production
> deployments sign with the AtlaSent KMS; auditors pin the published public
> key from `keys.atlasent.io` via the `--pubkey` flag rather than trusting
> the value embedded in the bundle.

## What the chain catches (tamper detection)

The verifier exits non-zero on:

| Failure | Detection |
|---|---|
| Any evidence field modified — `event_id`, `timestamp`, `actor`, `action`, `decision`, `permit_id`, `reason`, or any value inside `context_snapshot` (e.g. JE amount, second approver, account id) | `audit_hash` mismatch at that event |
| An event inserted, deleted, or reordered | `previous_hash` chain break |
| The chain head modified | `head_hash` does not match last event's `audit_hash` |
| The signature modified, or a different key used | Ed25519 verify fail |

See the `verify-audit.py --bundle` exit-code contract in that file's
docstring.

## Related

- Runbook: [Governed close operations](https://docs.atlasent.io/runbooks/governed-close-operations) — the operational playbook
- Pilot runbook: `PILOT_RUNBOOK_2026-04-29.md` — operator-internal day-by-day
- Pilot offer: `CLOSE_OPS_PILOT_OFFER.md` — what the pilot tenant gets
- Audit evidence runbook: `AUDIT_EVIDENCE_RUNBOOK.md` — handing exports to an external auditor
- ERP webhook integration: [`erp-webhook.ts`](./erp-webhook.ts) — receive `evaluation.deny` / `approval.requested` events to wire AtlaSent into the close-management tool of record
- Policy bundle: [`policies/accounting-close-gate.yaml`](./policies/accounting-close-gate.yaml) — the same rules in the wire format the live API consumes
