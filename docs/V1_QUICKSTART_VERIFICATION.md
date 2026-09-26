# V1 Quickstart Verification

**Status:** snapshot · **Date:** 2026-05-28 · **Scope:** V1 convergence P0 lockfile alignment

Audits the four V1 pilot quickstarts for reproducible installs. Out of scope:
the ~30 other examples in this repo (tracked separately).

## Quickstarts in scope

| Quickstart                  | Kind             | Pin source              | Lockfile                                  |
| --------------------------- | ---------------- | ----------------------- | ----------------------------------------- |
| `github-action-deploy/`     | GH Actions       | `action.yml` ref in CI  | N/A — no package.json (GH Actions consumer) |
| `python-sdk-quickstart/`    | Python SDK       | `requirements.txt`      | Pinned to `atlasent==2.10.0`              |
| `typescript-sdk-quickstart/`| TypeScript SDK   | `package.json`          | `package-lock.json` regenerated at `2.10.0` |
| `basic-evaluate/`           | Raw HTTP (httpx) | `requirements.txt`      | Uses `httpx` only; SDK not consumed       |

## What changed

### `typescript-sdk-quickstart/`

- **Before:** `package.json` had `"@atlasent/sdk": "^2.5.0"`. `package-lock.json`
  existed but resolved to `2.5.0` — well behind the V1 pilot floor.
- **After:** Pinned to exact `"@atlasent/sdk": "2.10.0"` (latest npm). Lockfile
  regenerated; SDK resolves to `2.10.0` in `node_modules/@atlasent/sdk`.
- Snippet check: `main.ts` imports `atlasent.protect`, `AtlaSentError`,
  `AtlaSentDeniedError`. All three are exported from `@atlasent/sdk@2.10.0`.
  No code change needed.

### `python-sdk-quickstart/`

- **Before:** `requirements.txt` had `atlasent>=0.1` — effectively unpinned;
  fresh installs would pull `2.10.0` today but the contract was not stable.
- **After:** Pinned exact `atlasent==2.10.0` (latest PyPI). No dev/test deps
  were touched.
- Snippet check: `main.py` imports `AsyncAtlaSentClient`,
  `AtlaSentDeniedError`, `AtlaSentError`, `protect`. All four are exported
  from `atlasent==2.10.0`. No code change needed.

### `basic-evaluate/`

- **Before:** `requirements.txt` had `httpx>=0.27`. No `atlasent` import.
- **After:** `httpx` pin unchanged. This example deliberately demonstrates the
  raw HTTP wire shape (`POST /v1-evaluate` → `POST /v1-verify-permit`) without
  the SDK. `httpx` is a transport dep, not the V1 pilot SDK; the instruction
  was to "only tighten the pins for the V1 pilot SDK; don't touch dev/test
  deps". Leaving `>=0.27` as-is. The endpoint paths were normalized to the
  org-canonical dash form (`/v1-evaluate`, `/v1-verify-permit`) in the
  2026-07-11 hygiene pass.
- Snippet check: `main.py` uses `httpx.post` against `/v1-evaluate` and
  `/v1-verify-permit` — both are V1 stable endpoints. No issue.

### `github-action-deploy/`

- **Before / after:** No `package.json` / no `requirements.txt`. The quickstart
  is consumed via a GitHub Actions workflow that references
  `atlasent-systems-inc/atlasent-action@vX` — the version is pinned at the
  workflow level by the *user* of the quickstart, not in this repo. README
  documents step-pinning explicitly.
- Snippet check: README references `atlasent-action` step inputs that map to
  the action's `src/index.ts` input schema (verified in companion PR to
  `atlasent-action`). Compatible.

## Breakage found

**None.** All four quickstarts install and import cleanly against the latest
published SDK artifacts.

## Risks remaining

- **Published versions lag source.** The TS source in `atlasent-sdk/typescript/`
  has since advanced to `2.19.0` (and `@atlasent/agent` source to `1.2.0`); the
  documented published npm/PyPI canonical is still `2.10.0`. All example pins
  were standardized on `2.10.0` in the 2026-07-11 hygiene pass. When the current
  published version is confirmed (likely higher than `2.10.0`), these pins should
  be bumped in lockstep — this is a known follow-up, not a per-example gap.
- **`basic-evaluate/` will not catch wire-shape drift** between the example
  and the API because it hard-codes the request body. If `/v1-evaluate`
  changes shape, this example breaks silently. Tracked in the API parity
  matrix, not here.
- **~~Other ~30 examples in this repo remain unpinned~~ (resolved 2026-07-11).**
  The full examples surface has since been standardized: every non-quickstart
  `package.json` now pins `@atlasent/sdk: "2.10.0"` and every core-SDK
  `requirements.txt` pins `atlasent==2.10.0`, matching the quickstart canonical.
  Excluded by design: the `v2/` historical examples (guardrail-preserved,
  intentionally on their `@atlasent/sdk@^2` / `atlasent>=2.0.0` era pins) and
  the framework-guard packages (`@atlasent/langchain`, `@atlasent/cursor`,
  `@atlasent/llamaindex`, `@atlasent/enforce`, `atlasent-langchain`), which
  version independently per Doctrine 5.
  **Correction 2026-09-25:** of those, only `@atlasent/enforce` is published.
  `@atlasent/langchain`, `@atlasent/cursor`, `@atlasent/llamaindex` (npm) and
  `atlasent-langchain` (PyPI) all return 404, so the examples that depended on
  them could never install. They now carry a small local guard on the pinned
  `@atlasent/sdk@2.10.0` / `atlasent==2.10.0` (`withPermit` / `with_permit`)
  until those packages are released.
