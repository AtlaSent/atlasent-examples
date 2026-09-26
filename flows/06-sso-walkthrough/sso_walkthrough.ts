// WARNING: This example uses a disabled endpoint that is not deployed in production.
// The `/v1/sso/connections` routes are served by the `v1-sso` edge function,
// which the AtlaSent API lists as disabled (not deployed in production).
// Calls to these routes will return 404 in production.

/**
 * flows/06-sso-walkthrough/sso_walkthrough.ts
 *
 * End-to-end Okta SSO integration: connect → JIT rule → evaluate → audit.
 *
 * Run (live):
 *   ATLASENT_API_URL=https://api.atlasent.io/functions/v1 \
 *   ATLASENT_API_KEY=ask_live_xx \
 *   ATLASENT_ORG_ID=org_xx \
 *   OKTA_ISSUER=https://dev-XXXXXX.okta.com/oauth2/default \
 *   OKTA_CLIENT_ID=0oa... \
 *   OKTA_CLIENT_SECRET=... \
 *   npx tsx sso_walkthrough.ts
 *
 * Run (dry-run):
 *   ATLASENT_DRY_RUN=true npx tsx sso_walkthrough.ts
 */

const DRY_RUN = process.env.ATLASENT_DRY_RUN === "true";

const API_URL = DRY_RUN
  ? "https://api.atlasent.io/functions/v1"
  : required("ATLASENT_API_URL");
const API_KEY = DRY_RUN ? "dry-run" : required("ATLASENT_API_KEY");
const ORG_ID = DRY_RUN ? "org_dry_run" : required("ATLASENT_ORG_ID");
const OKTA_ISSUER = DRY_RUN
  ? "https://dev-000000.okta.com/oauth2/default"
  : required("OKTA_ISSUER");
const OKTA_CLIENT_ID = DRY_RUN ? "0oaDryRun" : required("OKTA_CLIENT_ID");
const OKTA_CLIENT_SECRET = DRY_RUN ? "secret" : required("OKTA_CLIENT_SECRET");

function required(key: string): string {
  const v = process.env[key];
  if (!v) throw new Error(`Missing required env var: ${key}`);
  return v;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  if (DRY_RUN) {
    console.log(`  [dry-run] POST ${path}`, JSON.stringify(body, null, 2));
    // Return plausible stub responses keyed on path
    if (path.includes("/sso/connections") && !path.includes("jit")) {
      return { connection_id: "conn_dry_run_001" } as T;
    }
    if (path.includes("jit-rules")) {
      return { rule_id: "rule_dry_run_001" } as T;
    }
    if (path.includes("/v1-evaluate")) {
      return { decision: "allow", permit_token: "permit_dry_run_001" } as T;
    }
    return {} as T;
  }
  const r = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${API_KEY}`,
    },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`${path} → ${r.status}: ${text}`);
  }
  return r.json() as Promise<T>;
}

async function get<T>(path: string): Promise<T> {
  if (DRY_RUN) {
    console.log(`  [dry-run] GET ${path}`);
    return {
      events: [
        {
          event_id: "evt_dry_run_001",
          sso_subject: "alice@example.com",
          action: "production.deploy",
          decision: "allow",
        },
      ],
    } as T;
  }
  const r = await fetch(`${API_URL}${path}`, {
    headers: { authorization: `Bearer ${API_KEY}` },
  });
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`${path} → ${r.status}: ${text}`);
  }
  return r.json() as Promise<T>;
}

async function main() {
  if (DRY_RUN) console.log("[atlasent] dry-run mode — no live credentials needed\n");

  // Step 1 — Register SSO connection
  console.log("Step 1: Registering Okta SSO connection...");
  const { connection_id } = await post<{ connection_id: string }>(
    "/v1/sso/connections",
    {
      org_id: ORG_ID,
      provider: "okta",
      issuer: OKTA_ISSUER,
      client_id: OKTA_CLIENT_ID,
      client_secret: OKTA_CLIENT_SECRET,
    },
  );
  console.log(`  connection_id: ${connection_id}\n`);

  // Step 2 — Define JIT rule
  console.log("Step 2: Creating JIT provisioning rule...");
  const { rule_id } = await post<{ rule_id: string }>(
    `/v1/sso/connections/${connection_id}/jit-rules`,
    {
      claim: "groups",
      claim_value: "engineering",
      role: "developer",
    },
  );
  console.log(`  rule_id: ${rule_id}\n`);

  // Step 3 — Evaluate an action as the SSO-provisioned user
  console.log("Step 3: Evaluating action as SSO user sso:alice@example.com...");
  const evalResult = await post<{ decision: string; permit_token?: string }>(
    "/v1-evaluate",
    {
      actor_id: "sso:alice@example.com",
      action_type: "production.deploy",
      resource: "checkout-api",
    },
  );
  console.log(`  decision: ${evalResult.decision}`);
  if (evalResult.permit_token) console.log(`  permit_token: ${evalResult.permit_token}`);
  console.log();

  // Step 4 — Retrieve the audit event
  console.log("Step 4: Retrieving audit event for sso:alice@example.com...");
  const auditResult = await get<{ events: Array<Record<string, unknown>> }>(
    "/v1/audit/events?subject=sso:alice@example.com&limit=1",
  );
  const event = auditResult.events?.[0];
  if (!event) {
    console.error("  No audit event found — check that the evaluate call was recorded.");
    process.exit(1);
  }
  console.log(`  event_id: ${event.event_id}`);
  console.log(`  sso_subject: ${event.sso_subject}`);
  console.log(`  decision: ${event.decision}`);
  console.log();

  console.log("SSO walkthrough complete.");
  if (DRY_RUN) console.log("[atlasent] dry-run smoke test passed");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
