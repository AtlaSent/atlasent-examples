# Compliance Evidence Example

Trigger an evidence collection run and display the results, highlighting any controls with gaps or findings.

The example shown below uses SOC 2 controls. The same evidence pipeline produces evidence for finance-control workflows (SOX-style segregation-of-duties, journal-entry approval thresholds, period-close authorisation chains, vendor master change controls). Pass `--regime sox` instead of the default `--regime soc2` once the live API exposes finance-flavoured control mappings; until then, point the example at any AtlaSent org running the [`accounting-close/`](../accounting-close/) protected actions and the same evidence shape comes back, with the SOC 2 control-id labels swapped for the SOX-equivalent labels in your control matrix.

## What it demonstrates

- Triggering a `v1-compliance-evidence` run via the AtlaSent API
- Polling until the run reaches a terminal status
- Using the `@atlasent/sdk` helpers (`evidenceRunPasses`, `nonPassingControls`) to evaluate results
- Printing a formatted control summary to stdout — pass / gap / finding for each control, with the actor counts, attempted-but-blocked counts, and approval-chain provenance the auditor will ask about

## Setup

```bash
cd compliance-evidence
npm install
```

Create a `.env` file:

```
ATLASENT_API_KEY=ask_live_your_key_here
ATLASENT_API_URL=https://api.atlasent.io/functions/v1
```

## Run

```bash
npm start
```

Example output (SOC 2 framing):

```
Triggering SOC 2 evidence run...
Run ID: cev_01abc  Status: running
Polling...
Run complete.

✅ CC6.1 — Logical and Physical Access Controls (pass)
   • 847 authorization evaluations in period
   • 0 unauthorized access attempts
   • All access decisions cryptographically recorded

✅ CC6.3 — Role-Based Access Control (pass)
   • 12 distinct roles in use

⚠️  CC7.2 — System Monitoring (gap)
   • Runtime verification enabled
   • 2 anomaly events in period — review recommended

✅ CC8.1 — Change Management (pass)
✅ CC3.2 — Risk Assessment (pass)

Summary: 4 pass, 1 gap, 0 finding
All controls pass: false
```

## Period

By default the script runs against the last 90 days. Pass `--start` and `--end` to override:

```bash
npm start -- --start 2026-01-01 --end 2026-03-31
```

## Pairing with the accounting-close runbook

For a finance-control evidence package — JE approval chains, vendor master separation of duties, emergency-override approvers — run the [`accounting-close/`](../accounting-close/) scripts first to seed the audit chain, then point this script at the same org and time window. The output will include:

- The count of JE approvals that hit the delegation threshold and went through CFO sign-off (vs. straight `allow`).
- The count of vendor master mutations that were `deny`'d for separation-of-duties before the secondary approver was named.
- Every emergency override in the period, with the dual-approval roster (CFO + audit committee chair) attached.
- The auto-re-lock event that closed the override's TTL window.

The console's audit page produces the same evidence shape via the **Export CSV (evidence package)** button — see the [Governed close operations](https://docs.atlasent.io/runbooks/governed-close-operations) runbook for the side-by-side flow.
