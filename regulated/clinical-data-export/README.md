> **Later-phase reference.** This document is not part of the Deploy Gate V1 pilot. Keep first pilots focused on GitHub Actions + `production.deploy` + `/v1-evaluate` + `/v1-verify-permit`.

# 03 · Clinical Data Export

Batch-authorize an export of patient records. Every row is evaluated
individually — denied rows drop out, allowed rows are assembled into a
SHA-256-sealed bundle whose permits are then consumed so an auditor can
prove the entire cohort passed policy.

Useful whenever you export PHI, clinical trial data, or any row-level
sensitive dataset.

## Run it (<3 min)

```bash
export ATLASENT_API_KEY=ask_test_REPLACE_ME
just install   # one-time
just run
```

Fallback without `just`:

```bash
pip install -r requirements.txt
python3 main.py
```

Optional overrides:

| Env var            | Default                                     |
|--------------------|---------------------------------------------|
| `ATLASENT_API_URL` | `https://staging.atlasent.dev/functions/v1` |
| `REQUESTER`        | `cdm-alice`                                 |
| `PURPOSE`          | `Monthly safety monitoring export`          |
| `OUT`              | `./export-bundle.json`                      |

## Output

`export-bundle.json` — the allow-listed records, the issued permit IDs,
and a `sha256` of the (sorted) body. Save it with the consumed-permit
receipts and you have a verifiable export.

## What to look at next

- `v2/typescript/audit-export` — how the signed audit bundle is produced
  server-side and how to verify its signature.
- `regulated/lims-write` — write-side counterpart.
