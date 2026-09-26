/**
 * connectors.test.ts — unit tests for the pure parsing/extraction logic in
 * connectors.ts. Does NOT invoke the real `sf` / `suitecloud` CLIs or a real
 * ServiceNow/Jira instance (no such binaries, instance, or credentials in
 * CI) — exercises `extractComponents` / `extractRecordFields` /
 * `extractJiraFields` and the builders against fixture JSON matching the
 * documented default mappings. `runDeployCli` is exercised against a real
 * (harmless, always-installed) process, and `fetchChangeRequest` /
 * `buildChangeRequestFromApi` / `fetchJiraIssue` / `buildJiraIssueFromApi`
 * against a real local HTTP server (`node:http`, loopback only), so the
 * shellout / HTTP + JSON-parse plumbing itself is genuinely proven, not just
 * the pure parser.
 *
 * Run: npm test  (tsx test/connectors.test.ts)
 */
import assert from "node:assert/strict";
import { createServer } from "node:http";
import {
  DEFAULT_JIRA_ISSUE_MAPPING,
  DEFAULT_SDF_MAPPING,
  DEFAULT_SERVICENOW_CHANGE_MAPPING,
  DEFAULT_SF_MAPPING,
  DEFAULT_TERRAFORM_MAPPING,
  buildChangeRequestFromApi,
  buildJiraIssueFromApi,
  buildMetadataDeployFromCli,
  buildSdfDeployFromCli,
  buildTerraformPlanFromCli,
  extractComponents,
  extractJiraFields,
  extractRecordFields,
  fetchChangeRequest,
  fetchJiraIssue,
  runDeployCli,
} from "../connectors.js";

let passed = 0;
function test(name: string, fn: () => void): void {
  try {
    fn();
    passed++;
    console.log(`  ok — ${name}`);
  } catch (err) {
    console.error(`  FAIL — ${name}`);
    console.error(err);
    process.exitCode = 1;
  }
}
async function testAsync(name: string, fn: () => Promise<void>): Promise<void> {
  try {
    await fn();
    passed++;
    console.log(`  ok — ${name}`);
  } catch (err) {
    console.error(`  FAIL — ${name}`);
    console.error(err);
    process.exitCode = 1;
  }
}

console.log("=== connectors.test.ts ===");

// ---------------------------------------------------------------------------
// extractComponents — the pure parser, against fixture JSON matching the
// documented DEFAULT_SF_MAPPING / DEFAULT_SDF_MAPPING shapes.
// ---------------------------------------------------------------------------

test("extractComponents: sf project deploy validate --json shape (result.files[])", () => {
  const fixture = {
    status: 0,
    result: {
      id: "0Af000000000000ABC",
      checkOnly: true,
      done: true,
      success: true,
      files: [
        { type: "Flow", fullName: "Opportunity_Approval", state: "Changed" },
        { type: "PermissionSet", fullName: "Deal_Desk_Approver", state: "Add" },
      ],
    },
  };
  const components = extractComponents(fixture, DEFAULT_SF_MAPPING);
  assert.deepEqual(components, [
    { type: "Flow", member: "Opportunity_Approval" },
    { type: "PermissionSet", member: "Deal_Desk_Approver" },
  ]);
});

test("extractComponents: suitecloud project:deploy dry-run shape (data.objects[])", () => {
  const fixture = {
    data: {
      objects: [
        { type: "workflow", scriptId: "customworkflow_ap_approval" },
        { type: "scheduledscript", scriptId: "customscript_tax_calc" },
      ],
    },
  };
  const components = extractComponents(fixture, DEFAULT_SDF_MAPPING);
  assert.deepEqual(components, [
    { type: "workflow", member: "customworkflow_ap_approval" },
    { type: "scheduledscript", member: "customscript_tax_calc" },
  ]);
});

test("extractComponents: terraform show -json shape (resource_changes[].{type,address}), reused verbatim for AWS", () => {
  const fixture = {
    format_version: "1.2",
    terraform_version: "1.9.0",
    resource_changes: [
      {
        address: "aws_iam_role.deal_desk_approver",
        type: "aws_iam_role",
        change: { actions: ["create"] },
      },
      {
        address: "aws_lambda_function.approval_threshold_check",
        type: "aws_lambda_function",
        change: { actions: ["update"] },
      },
    ],
  };
  const components = extractComponents(fixture, DEFAULT_TERRAFORM_MAPPING);
  assert.deepEqual(components, [
    { type: "aws_iam_role", member: "aws_iam_role.deal_desk_approver" },
    { type: "aws_lambda_function", member: "aws_lambda_function.approval_threshold_check" },
  ]);
});

test("extractComponents: throws (does not silently drop) when the mapped path isn't an array", () => {
  assert.throws(() => extractComponents({ result: { files: "not-an-array" } }, DEFAULT_SF_MAPPING), /expected an array/);
});

test("extractComponents: throws on a component missing the name field, rather than skipping it", () => {
  const fixture = { result: { files: [{ type: "Flow" }] } };
  assert.throws(() => extractComponents(fixture, DEFAULT_SF_MAPPING), /missing string field "fullName"/);
});

test("extractComponents: throws on a component missing the type field", () => {
  const fixture = { result: { files: [{ fullName: "Opportunity_Approval" }] } };
  assert.throws(() => extractComponents(fixture, DEFAULT_SF_MAPPING), /missing string field "type"/);
});

test("extractComponents: an empty array is valid (extraction succeeds; caller decides zero-component policy)", () => {
  assert.deepEqual(extractComponents({ result: { files: [] } }, DEFAULT_SF_MAPPING), []);
});

// ---------------------------------------------------------------------------
// extractRecordFields — the ServiceNow Table API pure parser, against fixture
// JSON matching the documented DEFAULT_SERVICENOW_CHANGE_MAPPING shape.
// ---------------------------------------------------------------------------

test("extractRecordFields: Table API list-query shape (result[0].{...}), plain string fields", () => {
  const fixture = {
    result: [
      {
        number: "CHG0000123",
        short_description: "Increase Deal Desk approval threshold",
        cmdb_ci: "Opportunity Approval Workflow",
        state: "Scheduled",
        planned_start_date: "2026-08-20 22:00:00",
        planned_end_date: "2026-08-21 02:00:00",
      },
    ],
  };
  const fields = extractRecordFields(fixture, DEFAULT_SERVICENOW_CHANGE_MAPPING);
  assert.deepEqual(fields, {
    number: "CHG0000123",
    short_description: "Increase Deal Desk approval threshold",
    cmdb_ci: "Opportunity Approval Workflow",
    state: "Scheduled",
    planned_start_date: "2026-08-20 22:00:00",
    planned_end_date: "2026-08-21 02:00:00",
  });
});

test("extractRecordFields: accepts a reference field returned as { value, display_value }", () => {
  const fixture = {
    result: [
      {
        number: "CHG0000124",
        short_description: "x",
        cmdb_ci: { value: "a1b2c3", display_value: "Opportunity Approval Workflow" },
        state: "Scheduled",
        planned_start_date: "2026-08-20 22:00:00",
        planned_end_date: "2026-08-21 02:00:00",
      },
    ],
  };
  const fields = extractRecordFields(fixture, DEFAULT_SERVICENOW_CHANGE_MAPPING);
  assert.equal(fields.cmdb_ci, "a1b2c3");
});

test("extractRecordFields: throws (does not silently drop) when the mapped path isn't an object", () => {
  assert.throws(() => extractRecordFields({ result: [] }, DEFAULT_SERVICENOW_CHANGE_MAPPING), /expected an object/);
});

test("extractRecordFields: throws on a missing field, rather than treating it as absent", () => {
  const fixture = { result: [{ number: "CHG0000123" }] };
  assert.throws(() => extractRecordFields(fixture, DEFAULT_SERVICENOW_CHANGE_MAPPING), /field "short_description" is missing or not a string\/reference/);
});

// ---------------------------------------------------------------------------
// extractJiraFields — the Jira REST API pure parser, against fixture JSON
// matching the documented DEFAULT_JIRA_ISSUE_MAPPING shape (nested
// fields.status.name / fields.assignee.displayName reference objects).
// ---------------------------------------------------------------------------

test("extractJiraFields: GET /rest/api/3/issue/{key} shape, nested reference fields", () => {
  const fixture = {
    id: "10042",
    key: "CHG-4501",
    fields: {
      summary: "Raise Deal Desk approval threshold to $25,000",
      status: { name: "Approved" },
      issuetype: { name: "Change" },
      duedate: "2026-08-21",
      assignee: { displayName: "Frank Nguyen" },
    },
  };
  const fields = extractJiraFields(fixture, DEFAULT_JIRA_ISSUE_MAPPING);
  assert.deepEqual(fields, {
    key: "CHG-4501",
    summary: "Raise Deal Desk approval threshold to $25,000",
    status: "Approved",
    issuetype: "Change",
    duedate: "2026-08-21",
    assignee: "Frank Nguyen",
  });
});

test("extractJiraFields: throws when the response root has no string key", () => {
  assert.throws(() => extractJiraFields({ fields: {} }, DEFAULT_JIRA_ISSUE_MAPPING), /missing string field "key"/);
});

test("extractJiraFields: throws (does not silently drop) when the response root isn't an object", () => {
  assert.throws(() => extractJiraFields(null, DEFAULT_JIRA_ISSUE_MAPPING), /expected an object at the response root/);
});

test("extractJiraFields: throws on a missing nested field, rather than treating it as absent", () => {
  const fixture = { key: "CHG-4501", fields: { summary: "x", issuetype: { name: "Change" }, duedate: "2026-08-21", assignee: { displayName: "y" } } };
  assert.throws(() => extractJiraFields(fixture, DEFAULT_JIRA_ISSUE_MAPPING), /field "status" \(path fields\.status\.name\) is missing/);
});

// ---------------------------------------------------------------------------
// buildMetadataDeployFromCli / buildSdfDeployFromCli — end-to-end against a
// harmless real process (`node -e`) so the shellout + JSON.parse plumbing is
// genuinely exercised, not just the pure extractor.
// ---------------------------------------------------------------------------

const NODE_PRINT_SF_JSON = [
  "-e",
  `console.log(JSON.stringify({result:{files:[{type:"Flow",fullName:"Opportunity_Approval"},{type:"ValidationRule",fullName:"Opportunity.Require_Close_Reason"}]}}))`,
];

test("buildMetadataDeployFromCli: real shellout (node -e) + real JSON.parse produces the expected plan", () => {
  const result = buildMetadataDeployFromCli(
    { command: process.execPath, args: NODE_PRINT_SF_JSON },
    {
      org: "acme-prod",
      environment: "production",
      requestedBy: "release.alice@acme.com",
      changeRequest: "CHG-2026-9001",
      approvals: 2,
      changeWindow: true,
    },
    "61.0",
  );
  assert.equal(result.ok, true);
  if (result.ok) {
    assert.equal(result.plan.package.components.length, 2);
    assert.equal(result.plan.package.components[0].member, "Opportunity_Approval");
    assert.equal(result.plan.org, "acme-prod");
  }
});

test("buildMetadataDeployFromCli: missing CLI binary falls back to a non-throwing { ok: false }", () => {
  const result = buildMetadataDeployFromCli(
    { command: "this-binary-definitely-does-not-exist-xyz", args: [] },
    { org: "acme-prod", environment: "production", requestedBy: "a", changeRequest: "b", approvals: 1, changeWindow: true },
    "61.0",
  );
  assert.equal(result.ok, false);
  if (!result.ok) assert.match(result.reason, /not found on PATH/);
});

test("buildMetadataDeployFromCli: refuses an empty deploy plan rather than proceeding silently", () => {
  const result = buildMetadataDeployFromCli(
    { command: process.execPath, args: ["-e", `console.log(JSON.stringify({result:{files:[]}}))`] },
    { org: "acme-prod", environment: "production", requestedBy: "a", changeRequest: "b", approvals: 1, changeWindow: true },
    "61.0",
  );
  assert.equal(result.ok, false);
  if (!result.ok) assert.match(result.reason, /zero components/);
});

const NODE_PRINT_SDF_JSON = [
  "-e",
  `console.log(JSON.stringify({data:{objects:[{type:"workflow",scriptId:"customworkflow_ap_approval"}]}}))`,
];

test("buildSdfDeployFromCli: real shellout produces the expected plan", () => {
  const result = buildSdfDeployFromCli(
    { command: process.execPath, args: NODE_PRINT_SDF_JSON },
    {
      account: "1234567",
      environment: "production",
      requestedBy: "release.dana@acme.com",
      changeRequest: "CHG-2026-9002",
      approvals: 2,
      changeWindow: true,
    },
    "AcmeRevenueAutomation",
  );
  assert.equal(result.ok, true);
  if (result.ok) {
    assert.equal(result.plan.project.objects.length, 1);
    assert.equal(result.plan.project.objects[0].scriptId, "customworkflow_ap_approval");
  }
});

const NODE_PRINT_TERRAFORM_JSON = [
  "-e",
  `console.log(JSON.stringify({resource_changes:[{address:"aws_iam_role.deal_desk_approver",type:"aws_iam_role",change:{actions:["create"]}}]}))`,
];

test("buildTerraformPlanFromCli: real shellout (terraform show -json shape) produces the expected plan", () => {
  const result = buildTerraformPlanFromCli(
    { command: process.execPath, args: NODE_PRINT_TERRAFORM_JSON },
    {
      account: "123456789012",
      environment: "production",
      requestedBy: "release.erin@acme.com",
      changeRequest: "CHG-2026-9003",
      approvals: 2,
      changeWindow: true,
    },
    "acme-prod",
  );
  assert.equal(result.ok, true);
  if (result.ok) {
    assert.equal(result.plan.plan.resources.length, 1);
    assert.equal(result.plan.plan.resources[0].member, "aws_iam_role.deal_desk_approver");
    assert.equal(result.plan.account, "123456789012");
    assert.equal(result.plan.plan.workspace, "acme-prod");
  }
});

test("buildTerraformPlanFromCli: refuses an empty terraform plan rather than proceeding silently", () => {
  const result = buildTerraformPlanFromCli(
    { command: process.execPath, args: ["-e", `console.log(JSON.stringify({resource_changes:[]}))`] },
    {
      account: "123456789012",
      environment: "production",
      requestedBy: "a",
      changeRequest: "b",
      approvals: 1,
      changeWindow: true,
    },
    "acme-prod",
  );
  assert.equal(result.ok, false);
  if (!result.ok) assert.match(result.reason, /zero resource changes/);
});

test("runDeployCli: non-JSON stdout is reported, not thrown", () => {
  const result = runDeployCli({ command: process.execPath, args: ["-e", `console.log("not json")`] });
  assert.equal(result.ok, false);
  if (!result.ok) assert.match(result.reason ?? "", /did not emit valid JSON/);
});

test("runDeployCli: a nonzero exit that still emits JSON on stdout is recovered, not treated as absent", () => {
  // Mirrors a CLI's checkOnly/dry-run "would fail" result: nonzero exit, valid JSON body.
  const result = runDeployCli({
    command: process.execPath,
    args: ["-e", `console.log(JSON.stringify({result:{files:[]}}));process.exit(1)`],
  });
  assert.equal(result.ok, true);
});

// ---------------------------------------------------------------------------
// fetchChangeRequest / buildChangeRequestFromApi — end-to-end against a real
// local HTTP server (loopback only, no external network) so the fetch() +
// Basic Auth header + JSON.parse plumbing is genuinely exercised, not just
// the pure extractor.
// ---------------------------------------------------------------------------

async function withFixtureServer(
  respond: (req: { url?: string; headers: Record<string, string | string[] | undefined> }) => { status: number; body: unknown },
  run: (baseUrl: string) => Promise<void>,
): Promise<void> {
  const server = createServer((req, res) => {
    const { status, body } = respond({ url: req.url, headers: req.headers as Record<string, string> });
    res.writeHead(status, { "content-type": "application/json" });
    res.end(JSON.stringify(body));
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  if (address === null || typeof address === "string") throw new Error("failed to bind loopback server");
  try {
    await run(`http://127.0.0.1:${address.port}`);
  } finally {
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
}

await testAsync("fetchChangeRequest: real HTTP GET + real JSON.parse, correct Basic Auth header sent", async () => {
  let capturedAuth: string | undefined;
  let capturedUrl: string | undefined;
  await withFixtureServer(
    (req) => {
      capturedAuth = req.headers.authorization as string | undefined;
      capturedUrl = req.url;
      return {
        status: 200,
        body: { result: [{ number: "CHG0000123", short_description: "x", cmdb_ci: "y", state: "Scheduled", planned_start_date: "s", planned_end_date: "e" }] },
      };
    },
    async (baseUrl) => {
      // fetchChangeRequest always targets https://<instance>.service-now.com — to
      // exercise the real fetch()/auth/parse plumbing against our loopback fixture
      // instead, monkeypatch global.fetch to redirect to the fixture server while
      // still passing the real request through (method/headers/url shape intact).
      const realFetch = globalThis.fetch;
      globalThis.fetch = ((_url: string, init?: RequestInit) => {
        const redirected = `${baseUrl}/api/now/table/change_request?sysparm_query=number=CHG0000123&sysparm_limit=1`;
        return realFetch(redirected, init);
      }) as typeof fetch;
      try {
        const result = await fetchChangeRequest({ instance: "unused", user: "svc_atlasent", password: "s3cret" }, "CHG0000123");
        assert.equal(result.ok, true);
        if (result.ok) {
          assert.deepEqual(result.json, { result: [{ number: "CHG0000123", short_description: "x", cmdb_ci: "y", state: "Scheduled", planned_start_date: "s", planned_end_date: "e" }] });
        }
        assert.equal(capturedAuth, `Basic ${Buffer.from("svc_atlasent:s3cret").toString("base64")}`);
        assert.match(capturedUrl ?? "", /sysparm_query=number=CHG0000123/);
      } finally {
        globalThis.fetch = realFetch;
      }
    },
  );
});

await testAsync("fetchChangeRequest: non-2xx response is reported, not thrown", async () => {
  await withFixtureServer(
    () => ({ status: 401, body: { error: { message: "User Not Authenticated" } } }),
    async (baseUrl) => {
      const realFetch = globalThis.fetch;
      globalThis.fetch = ((_url: string, init?: RequestInit) => realFetch(baseUrl, init)) as typeof fetch;
      try {
        const result = await fetchChangeRequest({ instance: "unused", user: "u", password: "p" }, "CHG0000123");
        assert.equal(result.ok, false);
        if (!result.ok) assert.match(result.reason ?? "", /HTTP 401/);
      } finally {
        globalThis.fetch = realFetch;
      }
    },
  );
});

await testAsync("buildChangeRequestFromApi: real HTTP round-trip produces the expected plan", async () => {
  await withFixtureServer(
    () => ({
      status: 200,
      body: {
        result: [
          {
            number: "CHG0000123",
            short_description: "Increase Deal Desk approval threshold",
            cmdb_ci: "Opportunity Approval Workflow",
            state: "Scheduled",
            planned_start_date: "2026-08-20 22:00:00",
            planned_end_date: "2026-08-21 02:00:00",
          },
        ],
      },
    }),
    async (baseUrl) => {
      const realFetch = globalThis.fetch;
      globalThis.fetch = ((_url: string, init?: RequestInit) => realFetch(baseUrl, init)) as typeof fetch;
      try {
        const result = await buildChangeRequestFromApi(
          { instance: "unused", user: "svc_atlasent", password: "s3cret" },
          { instance: "acmecorp", environment: "production", requestedBy: "release.erin@acme.com", changeRequest: "CHG0000123", approvals: 2, changeWindow: true },
        );
        assert.equal(result.ok, true);
        if (result.ok) {
          assert.equal(result.plan.system, "servicenow");
          assert.equal(result.plan.record.number, "CHG0000123");
          assert.equal(result.plan.record.cmdb_ci, "Opportunity Approval Workflow");
          assert.equal(result.plan.instance, "acmecorp");
        }
      } finally {
        globalThis.fetch = realFetch;
      }
    },
  );
});

// ---------------------------------------------------------------------------
// fetchJiraIssue / buildJiraIssueFromApi — same real-loopback-HTTP-server
// rigor, for the Jira connector's nested-reference-object response shape.
// ---------------------------------------------------------------------------

await testAsync("fetchJiraIssue: real HTTP GET + real JSON.parse, correct Basic Auth header sent", async () => {
  let capturedAuth: string | undefined;
  let capturedUrl: string | undefined;
  await withFixtureServer(
    (req) => {
      capturedAuth = req.headers.authorization as string | undefined;
      capturedUrl = req.url;
      return {
        status: 200,
        body: { key: "CHG-4501", fields: { summary: "x", status: { name: "Approved" }, issuetype: { name: "Change" }, duedate: "2026-08-21", assignee: { displayName: "y" } } },
      };
    },
    async (baseUrl) => {
      const realFetch = globalThis.fetch;
      globalThis.fetch = ((_url: string, init?: RequestInit) => {
        const redirected = `${baseUrl}/rest/api/3/issue/CHG-4501`;
        return realFetch(redirected, init);
      }) as typeof fetch;
      try {
        const result = await fetchJiraIssue({ site: "unused", email: "svc@acme.com", apiToken: "s3cret" }, "CHG-4501");
        assert.equal(result.ok, true);
        if (result.ok) {
          assert.equal((result.json as { key: string }).key, "CHG-4501");
        }
        assert.equal(capturedAuth, `Basic ${Buffer.from("svc@acme.com:s3cret").toString("base64")}`);
        assert.match(capturedUrl ?? "", /\/rest\/api\/3\/issue\/CHG-4501/);
      } finally {
        globalThis.fetch = realFetch;
      }
    },
  );
});

await testAsync("fetchJiraIssue: non-2xx response is reported, not thrown", async () => {
  await withFixtureServer(
    () => ({ status: 401, body: { errorMessages: ["Unauthorized"] } }),
    async (baseUrl) => {
      const realFetch = globalThis.fetch;
      globalThis.fetch = ((_url: string, init?: RequestInit) => realFetch(baseUrl, init)) as typeof fetch;
      try {
        const result = await fetchJiraIssue({ site: "unused", email: "e", apiToken: "t" }, "CHG-4501");
        assert.equal(result.ok, false);
        if (!result.ok) assert.match(result.reason ?? "", /HTTP 401/);
      } finally {
        globalThis.fetch = realFetch;
      }
    },
  );
});

await testAsync("buildJiraIssueFromApi: real HTTP round-trip produces the expected plan", async () => {
  await withFixtureServer(
    () => ({
      status: 200,
      body: {
        key: "CHG-4501",
        fields: {
          summary: "Raise Deal Desk approval threshold to $25,000",
          status: { name: "Approved" },
          issuetype: { name: "Change" },
          duedate: "2026-08-21",
          assignee: { displayName: "Frank Nguyen" },
        },
      },
    }),
    async (baseUrl) => {
      const realFetch = globalThis.fetch;
      globalThis.fetch = ((_url: string, init?: RequestInit) => realFetch(baseUrl, init)) as typeof fetch;
      try {
        const result = await buildJiraIssueFromApi(
          { site: "unused", email: "svc@acme.com", apiToken: "s3cret" },
          { site: "acmecorp", environment: "production", requestedBy: "release.frank@acme.com", changeRequest: "CHG-4501", approvals: 2, changeWindow: true },
        );
        assert.equal(result.ok, true);
        if (result.ok) {
          assert.equal(result.plan.system, "jira");
          assert.equal(result.plan.issue.key, "CHG-4501");
          assert.equal(result.plan.issue.status, "Approved");
          assert.equal(result.plan.site, "acmecorp");
        }
      } finally {
        globalThis.fetch = realFetch;
      }
    },
  );
});

console.log(`\n${passed} passed.`);
if (process.exitCode) {
  console.error("SOME TESTS FAILED");
  process.exit(1);
}
