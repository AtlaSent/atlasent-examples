# GitLab CI Deploy Gate (V1)

Gate a production deploy on an AtlaSent permit from **GitLab CI** — the same
Deploy Gate V1 story as [`github-action-deploy`](../github-action-deploy), for
teams who aren't on GitHub Actions. `checkout-api` deploying to `production`
under `production.deploy`, fail-closed.

This is the zero-dependency `curl` + `jq` path (no published action needed), so
it drops into any GitLab runner.

## Setup

1. **Mint an API key** in the AtlaSent console (`ask_live_*` for production,
   `ask_test_*` to try it against a test policy).
2. **Add two CI/CD variables** — GitLab → *Settings → CI/CD → Variables*
   (mark both **Masked**; mark `ATLASENT_API_KEY` **Protected** if `main` is
   protected):

   | Variable | Value |
   |----------|-------|
   | `ATLASENT_API_KEY` | your `ask_live_*` / `ask_test_*` key |
   | `ATLASENT_API_URL` | `https://api.atlasent.io/functions/v1` (the AtlaSent API base URL — **must end in `/functions/v1`**) |

   > **`ATLASENT_API_URL` must end in `/functions/v1`** — use
   > `https://api.atlasent.io/functions/v1` (self-hosted: your own deployment's
   > `https://<project-ref>.supabase.co/functions/v1`). Set it explicitly — a
   > wrong/absent base URL makes the gate fail closed (the deploy is blocked) on
   > every run.

3. **Copy [`.gitlab-ci.yml`](./.gitlab-ci.yml)** into your repo root (or merge
   the `deploy_checkout_api` job into your existing pipeline) and replace the
   final `echo "deployed …"` line with your real deploy command.

## The flow (fail-closed)

1. **Evaluate** — `POST $ATLASENT_API_URL/v1-evaluate` with
   `{ action_type: "production.deploy", actor_id, context }`.
2. **Gate** — require `decision == "allow"` **and** a `permit_token`; any
   `deny`/`hold`/`escalate` (or missing permit) exits non-zero.
3. **Verify** — `POST $ATLASENT_API_URL/v1-verify-permit` and require
   `valid == true` (this consumes the single-use permit).
4. **Execute** — the deploy command runs **only** after both pass.
5. **Audit** — the job logs the permit prefix + `audit_entry_hash` as evidence.

If AtlaSent does not authorize the deploy, the job fails and your deploy step
never runs — there is no fail-open path.

## Policy note

The example context sends `approvals: 2` and `change_window: true` so the
canonical `allow-2-approvals-change-window` deploy-gate template returns `allow`
out of the box. Adjust the context to match your own policy, or remove those
fields to see the gate **hold** for human approval — then approve it in the
console at **`/approvals`** and re-run the pipeline.

## Verifying the evidence

Every gated deploy is recorded in the hash-linked, signed audit chain. Export a
proof bundle from the console (**Audit → Export**) and verify it offline at
**`/verify/audit`** — no AtlaSent account required. See
[`../evidence-bundle`](../evidence-bundle).
