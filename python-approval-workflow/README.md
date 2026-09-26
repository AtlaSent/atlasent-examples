# python-approval-workflow

A Python script demonstrating a human-in-the-loop approval workflow using
AtlaSent. It submits an action for evaluation, then handles all four
canonical decision outcomes: `allow`, `deny`, `hold`, and `escalate`.

## What it does

1. Calls `POST /v1-evaluate` with an agent, action, and context.
2. On **`allow`** — prints the permit token and proceeds.
3. On **`deny`** — prints the reason and exits with code 1.
4. On **`hold`** — polls `POST /v1-verify-permit` using exponential backoff
   (2 s → 4 s → 8 s, capped at 30 s, up to 10 attempts) until the permit
   is approved or rejected by a human reviewer.
5. On **`escalate`** — prints step-by-step escalation instructions and
   exits with code 2.

## Prerequisites

- Python 3.11+
- An AtlaSent account with a policy configured for `records:approve`

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `ATLASENT_API_KEY` | Yes | Your API key (starts with `sk_`). |
| `ATLASENT_API_URL` | Yes | Base URL, e.g. `https://api.atlasent.io/functions/v1` |
| `ATLASENT_ORG_ID` | Yes | Your organisation ID. |
| `ATLASENT_AGENT` | No | Agent name. Default: `workflow-bot` |
| `ATLASENT_ACTION` | No | Action type. Default: `records:approve` |
| `RECORD_ID` | No | Record being approved. Default: `rec_demo_001` |
| `APPROVER` | No | Approver identity. Default: `alice@example.com` |

## Quick start

```bash
cd python-approval-workflow
pip install -r requirements.txt

cp ../.env.example .env
# Edit .env and fill in ATLASENT_API_KEY, ATLASENT_API_URL, ATLASENT_ORG_ID

ATLASENT_API_KEY=sk_... \
ATLASENT_API_URL=https://api.atlasent.io/functions/v1 \
ATLASENT_ORG_ID=org_... \
python main.py
```

## Polling backoff schedule

When the decision is `hold`, the script polls the permit endpoint:

| Attempt | Delay before request |
|---|---|
| 1 | 2 s |
| 2 | 4 s |
| 3 | 8 s |
| 4 | 16 s |
| 5–10 | 30 s (capped) |

If the permit is not resolved within 10 attempts (~5 min), the script
prints the permit ID and exits with code 1 so the pipeline can alert a human.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Allowed and workflow completed |
| `1` | Denied, error, or poll timeout |
| `2` | Escalation required |

## Error handling

- **401** — _"Got 401 — your ATLASENT_API_KEY may be wrong or expired"_
- **429** — _"Got 429 — rate limited (100 req/min per org)"_
- **Structured errors** — API returns `{ error: "snake_case_code", message: "...", status: N }`, all fields printed
