# Clinical Unblinding Execution-System Simulator

A reference execution system for the AtlaSent **clinical unblinding** pilot. It
models an RTSM/IRT-style system that holds sealed treatment assignments and
**refuses to release one unless AtlaSent has issued a permit for the exact
(trial, subject, action) and that permit verifies.** It enforces the real permit
contract and adds no authorization state of its own.

> The protected action is clinical unblinding — nothing broader. This is not a
> trial-management, EDC, or IRT product; it is a permit-enforcing execution
> boundary for the two clinical action classes.

## What it proves

The single customer-verifiable guarantee: **a treatment assignment cannot be
released through the protected execution path without a valid, context-bound
permit.** The simulator walks the pilot state vocabulary and fails closed at
every branch:

```
blinded → unblinding_requested → authorization_pending
  → authorized | denied
  → permit_issued → permit_verified
  → treatment_assignment_released → execution_verified
  → post_event_review_required   (emergency path, or when policy requires)
```

Two action classes, distinct paths (the emergency path never silently reuses the
standard policy):

| ACTION | Action class |
|--------|--------------|
| `standard` (default) | `trial.unblinding.execute` |
| `emergency` | `trial.unblinding.emergency` |

## Run it

**Demo mode** (no credentials — simulates the permit contract, safe for CI):

```bash
npm install
npm start
```

Demo mode runs three scenarios: an authorized release (simulated verified
permit), a **missing-permit** attempt (blocked), and a **wrong-subject** permit
(blocked) — proving the fail-closed contract without any live call.

**Live mode** (against a provisioned runtime org):

```bash
export ATLASENT_API_KEY=ask_live_xxx     # clinical:read + clinical:manage + evaluate:write + verify:execute
export ATLASENT_BASE_URL=https://api.atlasent.io/functions/v1
export TRIAL=NCT-ACC-1 SUBJECT=S-001 ACTOR=medical-monitor
npm start
```

Without an IdP-signed approval the gate correctly **denies** (fail-closed). To
exercise the authorized release, supply a real approval artifact:

```bash
export APPROVAL_ARTIFACT_FILE=./approval.json   # IdP-signed ApprovalArtifactV1
ACTION=emergency npm start                       # emergency path
```

AtlaSent verifies the IdP's approval and MFA claims; this simulator never forges
them.

## How the permit contract is enforced

`release()` accepts a treatment assignment request and a verified permit, and
throws unless the permit authorizes the **exact** release:

- **no permit** → blocked (spec case 9)
- **wrong action class** → blocked (case 14)
- **wrong study/trial** → blocked (case 13)
- **wrong subject** → blocked (case 12)

Live mode obtains the permit from `/v1-evaluate` and verifies it via
`/v1-verify-permit` before ever calling `release()`. The mapping of these
scenarios to the full acceptance suite is in the atlasent-api manifest
`docs/acceptance/clinical-unblinding-acceptance-manifest.json`.

## Boundaries

This example is validation-supporting, not validating. It demonstrates the
enforcement contract; it does not stand in for a customer's qualified RTSM/IRT
system or their complete clinical process validation.
