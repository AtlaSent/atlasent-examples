> **Later-phase reference.** This document is not part of the Deploy Gate V1 pilot. Keep first pilots focused on GitHub Actions + `production.deploy` + `/v1-evaluate` + `/v1-verify-permit`.

# First Hour Runbook — "Protect an API Action"

> Concrete, minute-by-minute walkthrough of what the AtlaSent wizard
> materializes when an engineer picks the **Protect an API action**
> Golden Path, plus the verification steps that prove the integration
> works end-to-end.
>
> Audience: a backend engineer at a biotech / regulated SaaS who has
> never seen AtlaSent before, has a service running locally, and has 60
> uninterrupted minutes.
>
> Outcome: one production endpoint is gated by AtlaSent in staging, one
> deny is reproducible on demand, and one audit record is queryable in
> the proof page.

---

## The user story

> "I'm a senior backend engineer at a clinical-trial SaaS. We have a
> `POST /v1/studies/:id/exports` endpoint that lets a coordinator pull
> subject data out of our EDC. Today it's protected by a role check and
> a feature flag, and we audit it by `console.log`. The compliance team
> wants real authorization decisions and a tamper-evident audit trail
> before we onboard the next sponsor. I want to wire AtlaSent into that
> one endpoint, in staging, before lunch."

The Golden Path the wizard runs for that user is **Protect an API
action** — it scaffolds an `evaluate → execute → consume` triplet
around one HTTP handler and gives the engineer a deny scenario they
can re-run.

This runbook documents what they see, what the wizard writes, and how
to confirm each step worked.

---

## The 60-minute timeline

| Min   | Phase                          | What the engineer is doing                             |
|-------|--------------------------------|--------------------------------------------------------|
| 0–5   | Install + auth                 | `npx @atlasent/wizard init`, paste API key             |
| 5–15  | Pick the path                  | Wizard interview: action type, target shape, language  |
| 15–25 | Materialization                | Wizard writes files; engineer reads the diff           |
| 25–40 | First green run                | Run the local server, hit the endpoint, see `ALLOW`    |
| 40–50 | First red run                  | Flip a context field, see `DENY` + override hint       |
| 50–60 | Proof page + handoff           | Open the audit record, copy link into a PR description |

If any phase blows past its budget, the wizard logs a `wizard:phase`
event so we can see where we're losing engineers in the funnel.

---

## Phase 1 · Install + auth (0–5 min)

```bash
npx @atlasent/wizard@latest init
```

The wizard prompts for:

1. **API key** (`ATLASENT_API_KEY`). Paste a staging key that starts
   with `ask_test_`. The wizard `POST`s `/v1/whoami` once to confirm
   the key resolves to a tenant + environment, then writes the key to
   `.env.local` — never to a tracked file.
2. **Environment** (defaults to `staging`). The wizard refuses to wire
   `production` on first run.
3. **Language** (TypeScript / Python / Go). The rest of this runbook
   shows TypeScript; the file shapes are equivalent in the other two.

Exit criteria:

- `.env.local` exists and contains `ATLASENT_API_KEY=ask_test_REPLACE_ME`.
- `.env.local` is in `.gitignore` (the wizard adds it if missing).
- `npx @atlasent/wizard doctor` prints a green "tenant: <slug>" line.

---

## Phase 2 · Pick the Golden Path (5–15 min)

The wizard shows five Golden Paths; the engineer picks **Protect an
API action**. It then runs a short interview:

| Question                                 | Engineer answers (example)             |
|------------------------------------------|----------------------------------------|
| What HTTP framework?                     | Express                                |
| Path of the route handler file?          | `src/routes/exports.ts`                |
| Method + path of the action to protect?  | `POST /v1/studies/:id/exports`         |
| What is the **action type**?             | `clinical.export`                      |
| What is the **target** shape?            | `study` keyed by `:id`                 |
| Who is the **actor** in the request?     | `req.user.email` (JWT subject)         |
| What runs after authorization succeeds?  | `runExport(study, opts)`               |
| Is the action regulated (Part 11/GxP)?   | Yes → enable permit consume + seal     |

The wizard names everything from those answers — no free-form prompts
later. The action type, target shape, and actor selector are the three
fields that uniquely identify a Golden Path instance, and they map
1:1 onto the `evaluate` request body.

Exit criteria:

- A diff preview is on screen.
- Nothing has been written to disk yet — the engineer must press `y`.

---

## Phase 3 · What the wizard materializes (15–25 min)

On `y`, the wizard writes (or amends) **exactly five files**:

```
src/
├── atlasent/
│   ├── client.ts          ← shared SDK client, reads ATLASENT_API_KEY
│   └── guard.ts           ← evaluate → execute → consume helper
├── routes/
│   └── exports.ts         ← route handler, edited to call guard()
.env.example               ← appends ATLASENT_API_KEY=
package.json               ← adds @atlasent/sdk dependency
```

Nothing else is touched. The wizard never reformats the rest of the
file, never reorders imports outside the lines it added, and never
touches lockfiles — `npm install` is the engineer's call.

### `src/atlasent/client.ts` (new)

```ts
import { AtlaSentClient } from '@atlasent/sdk';

const apiKey = process.env.ATLASENT_API_KEY;
if (!apiKey) {
  throw new Error('ATLASENT_API_KEY is required (see .env.example)');
}

export const atlasent = new AtlaSentClient({
  baseUrl: process.env.ATLASENT_API_URL ?? 'https://api.atlasent.io/functions/v1',
  apiKey,
});
```

### `src/atlasent/guard.ts` (new)

```ts
import { atlasent } from './client';

export interface GuardInput {
  actor: string;
  action: string;
  target: { id: string; type: string };
  context?: Record<string, unknown>;
}

export type GuardResult =
  | { ok: true; permitId: string; seal: () => Promise<void> }
  | { ok: false; reason: string; overridePath?: string };

export async function guard(input: GuardInput): Promise<GuardResult> {
  const decision = await atlasent.evaluate({
    agent: input.actor,
    action: input.action,
    target: input.target,
    context: input.context,
  });

  if (decision.decision !== 'ALLOW' || !decision.permitId) {
    return {
      ok: false,
      reason: decision.reason ?? 'denied',
      overridePath: decision.overridePath,
    };
  }

  const permitId = decision.permitId;
  return {
    ok: true,
    permitId,
    seal: async () => {
      await atlasent.consumePermit({ permitId });
    },
  };
}
```

### `src/routes/exports.ts` (edited, additions only)

```ts
import { guard } from '../atlasent/guard';

router.post('/v1/studies/:id/exports', async (req, res) => {
  const study = await loadStudy(req.params.id);

  // ── AtlaSent guard (added by wizard) ─────────────────────────────
  const decision = await guard({
    actor: req.user.email,
    action: 'clinical.export',
    target: { id: study.id, type: 'study' },
    context: {
      rows: req.body.rowCount,
      destination: req.body.destination,
      sponsorTier: study.sponsorTier,
    },
  });

  if (!decision.ok) {
    return res.status(403).json({
      error: decision.reason,
      override: decision.overridePath,
    });
  }
  // ─────────────────────────────────────────────────────────────────

  const result = await runExport(study, req.body);
  await decision.seal();        // sealed audit on success only
  res.json({ exportId: result.id, permitId: decision.permitId });
});
```

### `.env.example` (appended)

```
ATLASENT_API_KEY=
# ATLASENT_API_URL=https://api.atlasent.io/functions/v1   # override for staging
```

Exit criteria:

- The diff is small enough to read in one screen.
- `git diff --stat` shows ≤ 5 files touched, ≤ 80 lines added.
- The wizard prints a `Next:` block with the exact two curl commands
  used in Phase 4 and Phase 5 below.

---

## Phase 4 · First green run (25–40 min)

```bash
npm install
npm run dev
```

In a second terminal, run the curl the wizard printed:

```bash
curl -sS -X POST http://localhost:3000/v1/studies/CT-2099/exports \
  -H "Authorization: Bearer $LOCAL_DEV_JWT" \
  -H 'content-type: application/json' \
  -d '{"rowCount": 50, "destination": "vault://approved-bucket"}'
```

Expected response:

```json
{
  "exportId": "exp_01HZ…",
  "permitId": "prm_01HZ…"
}
```

Server log:

```
[atlasent] evaluate clinical.export → ALLOW (permit prm_01HZ…)
[atlasent] consume prm_01HZ… → SEALED (audit hash 9f2c…)
```

Exit criteria:

- HTTP 200 with a `permitId`.
- Server log shows both the `ALLOW` and the `SEALED` line — if the
  seal line is missing, the success path is committing data that is
  not in the audit chain. Treat as a P1.

This phase maps onto the runnable example in
[`flows/01-deploy-gate`](../flows/01-deploy-gate). That example is the
deploy-gate variant of the same `evaluate → consume` shape — read its
[`index.ts`](../flows/01-deploy-gate/index.ts) for a 50-line reference
implementation in the same style.

---

## Phase 5 · First red run (40–50 min)

Re-run the curl with a `destination` that the policy denies and a
suspiciously high `rowCount`:

```bash
curl -sS -X POST http://localhost:3000/v1/studies/CT-2099/exports \
  -H "Authorization: Bearer $LOCAL_DEV_JWT" \
  -H 'content-type: application/json' \
  -d '{"rowCount": 10000, "destination": "personal-gdrive"}'
```

Expected response (HTTP 403):

```json
{
  "error": "Separation-of-duties: bulk export to personal storage requires a second approver.",
  "override": "https://app.atlasent.io/overrides/req_01HZ…"
}
```

Server log:

```
[atlasent] evaluate clinical.export → DENY (sod-bulk-export)
```

This is the same scenario as Scene 5 in the
[golden-path demo seed](../flows/00-golden-path) (`gp-05-bulk-export`)
— the engineer can run `npm start` in `flows/00-golden-path` to see
the canonical fixture and confirm their integration matches.

Exit criteria:

- HTTP 403 with a non-empty `override` URL.
- The override URL opens an AtlaSent page that names the second
  approver group. If the override URL is empty on a deny, the policy
  is unrecoverable for the user — flag back to the policy author.

---

## Phase 6 · Proof page + handoff (50–60 min)

The wizard's final screen prints two URLs:

1. **Audit record** for the green run — opens to the sealed event with
   actor, target, context, decision, and signed hash.
2. **Policy view** for `clinical.export` — shows which rule fired on
   the deny and links to its history.

The engineer copies both into the PR description that wires the guard
into `main`. The PR template snippet the wizard suggests:

```md
### AtlaSent integration

- Action: `clinical.export`
- Allow proof: <audit URL>
- Deny proof: <override URL>
- Wired in: `src/routes/exports.ts`
```

Exit criteria:

- Both URLs resolve.
- The PR template snippet is in the clipboard / printed for paste.

---

## Verifying this runbook against `atlasent-examples`

Every claim above is testable today using existing flows in this repo:

| Runbook claim                                  | Where it's reproduced                                              |
|------------------------------------------------|--------------------------------------------------------------------|
| `evaluate → consume` shape on a green path     | [`flows/01-deploy-gate/index.ts`](../flows/01-deploy-gate/index.ts) |
| Deny with override URL on bulk export          | Scene 5 of [`flows/00-golden-path`](../flows/00-golden-path) (`gp-05-bulk-export`) |
| Sealed audit hash on success                   | [`flows/01-deploy-gate`](../flows/01-deploy-gate) — `auditHash` line in the success log |
| Step-up recovery from a deny                   | Scenes 2 → 3 of [`flows/00-golden-path`](../flows/00-golden-path) (`gp-02` → `gp-03`) |
| Regulated write with permit binding            | Scene 4 of [`flows/00-golden-path`](../flows/00-golden-path) (`gp-04-lims-write`) and [`flows/02-lims-write`](../flows/02-lims-write) |

To dry-run the deny + recovery without an API key:

```bash
cd flows/00-golden-path
npm install
npm run dry-run
```

The runner exits non-zero if any scene's decision diverges from its
declared `expect`, so the seed doubles as a smoke test for the
`Protect an API action` Golden Path's underlying decisions.

---

## Open questions

- **Wizard name.** `@atlasent/wizard` is a placeholder; once the
  package ships, replace the install line and re-test the timeline.
- **Framework coverage.** This runbook assumes Express. Fastify, Koa,
  FastAPI, and Gin variants should produce the same five-file diff
  shape — track per-framework drift in a follow-up.
- **JWT claim selector.** The wizard asks for `req.user.email` as the
  actor; for tenants on opaque-token auth we need a second prompt for
  the introspection endpoint.
- **CI gate.** Should the wizard offer to add a `dry-run` step to the
  engineer's CI on the way out? Probably yes once
  [`flows/01-deploy-gate`](../flows/01-deploy-gate) is wired into the
  `atlasent-action` Marketplace listing.
