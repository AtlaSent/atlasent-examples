# 02 · LIMS Write

Gate a write into a Laboratory Information Management System (LIMS).

Lab result writes are the classic GxP boundary: the actor, sample, assay,
and value must all be checked, and the write must be bound to an audit
trail. This flow uses the canonical fail-closed surface — `client.protect()`
— which evaluates the policy, verifies the issued Permit, and returns the
verified Permit in a single call. If `protect()` returns, the LIMS write
is authorized end-to-end; on deny, hold, escalate, verify failure, or
transport error the write body is never reached.

## Run it (<3 min)

```bash
export ATLASENT_API_KEY=ask_test_REPLACE_ME
just install   # one-time
just run
```

No `just`? Equivalent fallback:

```bash
pip install -r requirements.txt
python3 main.py
```

Optional overrides:

| Env var            | Default                                     |
|--------------------|---------------------------------------------|
| `ATLASENT_API_URL` | `https://staging.atlasent.dev/functions/v1` |
| `SAMPLE_ID`        | `S-2026-0001`                               |
| `ASSAY`            | `hba1c`                                     |
| `VALUE`            | `6.3`                                       |
| `ANALYST`          | `analyst-alice`                             |
| `LIMS_ENV`         | `production`                                |

## Exit codes

| Code | Meaning                                              |
|------|------------------------------------------------------|
| `0`  | Written, Permit verified and linked to the audit row |
| `2`  | AtlaSent denied the write (deny / hold / escalate)   |
| `3`  | Fail-closed — transport, 5xx, or auth failure        |

## What to look at next

- `regulated/clinical-data-export` — read-side counterpart.
- `../../with-permit-py/` — the lexically-scoped `with_permit()` peer of `protect()`.
- `../../python-sdk-quickstart/` — minimal `protect()` example without the GxP framing.
- `docs/` — GxP / 21 CFR Part 11 mappings for this flow.
