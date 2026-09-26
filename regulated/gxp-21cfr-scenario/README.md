> **Later-phase reference.** This document is not part of the Deploy Gate V1 pilot. Keep first pilots focused on GitHub Actions + `production.deploy` + `/v1-evaluate` + `/v1-verify-permit`.

# GxP 21 CFR Part 11 Compliance Scenario

Demonstrates AtlaSent enforcing 21 CFR Part 11 electronic records and audit trail
requirements for an AI agent operating in a regulated GxP environment.

## Run

```bash
pip install -r requirements.txt
export ATLASENT_API_KEY=your_key_here
python main.py
```

## Scenario

An AI agent attempts three actions in a pharma manufacturing context:

1. **Read a batch record** (`batch_records.read`) — allowed under 21 CFR Part 11
2. **Sign a batch record electronically** (`batch_records.sign`) — allowed only with dual authorization
3. **Delete an audit log** (`audit_log.delete`) — always denied (21 CFR Part 11 §11.10(e))

## Policy

The GxP policy bundle is loaded from `../gxp-starter/policies/21cfr11.yaml` via the AtlaSent API.
See the [gxp-starter](../gxp-starter/) example for how to provision these policies.
