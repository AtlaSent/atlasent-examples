/**
 * salesforce-change.ts — Salesforce / NetSuite / ServiceNow / Jira / AWS
 * (Terraform) business-system change → AtlaSent `production.deploy` gate
 * (fail-closed).
 *
 * This file is a STUB demonstrating the business-system change-gate pattern.
 * No Salesforce, NetSuite, ServiceNow, Jira, or Terraform CLI is called by
 * default — sample change payloads are hardcoded to match the real shape.
 * Replace the stubs with real `sf project deploy` / SuiteCloud (SDF) /
 * `terraform show -json` calls, or a real ServiceNow/Jira REST API read, for
 * a pilot.
 *
 * Integration pattern:
 *   1. A change is raised in the system of record (metadata deploy, SDF deploy,
 *      ServiceNow change request, or a live config edit) and approved through
 *      change management (CAB).
 *   2. This handler normalizes the change into AtlaSent's `production.deploy`
 *      action + a bound payload digest (and, for a live config edit, a before/after
 *      state snapshot — the state-snapshot execution profile).
 *   3. evaluate -> require allow + permit_token  (else BLOCK).
 *   4. verify-permit AT THE DEPLOY BOUNDARY -> require valid=true (single-use;
 *      swapped payload / wrong env / replay all fail closed).
 *   5. Only then run the real deploy.
 *
 * Action vocabulary mapping (no new action class — reuse production.deploy):
 *   Salesforce metadata deploy (sf project deploy)  -> production.deploy (artifact-bound)
 *   NetSuite SuiteCloud/SDF project deploy           -> production.deploy (artifact-bound)
 *   ServiceNow change request (Table API record)     -> production.deploy (artifact-bound; the record IS the plan)
 *   Jira issue (change/incident issue type)          -> production.deploy (artifact-bound; the issue IS the plan)
 *   AWS infra change (terraform show -json plan)      -> production.deploy (artifact-bound)
 *   Live Salesforce config edit (Flow/approval rule) -> production.deploy (state-snapshot profile)
 *
 * Usage:
 *   npm run demo            # offline stub — prints the evaluate/verify bodies, no network
 *   ATLASENT_API_KEY=... ATLASENT_API_URL=.../functions/v1 npm run demo   # live path
 */
import { createHash } from "node:crypto";
import {
  buildChangeRequestFromApi,
  buildJiraIssueFromApi,
  buildMetadataDeployFromCli,
  buildSdfDeployFromCli,
  buildTerraformPlanFromCli,
} from "./connectors.js";

// ---------------------------------------------------------------------------
// Business-system change payload shapes (hardcoded sample payloads)
// ---------------------------------------------------------------------------

/** A Salesforce metadata deploy — an artifact-bound release (sandbox -> prod). */
interface SalesforceMetadataDeploy {
  system: "salesforce";
  changeKind: "metadata_deploy";
  org: string;                 // target org alias, e.g. "acme-prod"
  environment: "production" | "sandbox";
  requestedBy: string;         // e.g. "release.alice@acme.com"
  changeRequest: string;       // CAB change ticket
  approvals: number;           // number of CAB approvals on the change
  changeWindow: boolean;       // inside an approved change window
  package: {                   // the deploy plan (illustrative package.xml components)
    apiVersion: string;
    components: Array<{ type: string; member: string }>;
  };
}

/** A live Salesforce config edit — no build artifact; binds a before/after state. */
interface SalesforceConfigEdit {
  system: "salesforce";
  changeKind: "config_edit";
  org: string;
  environment: "production";
  requestedBy: string;
  changeRequest: string;
  approvals: number;
  changeWindow: boolean;
  configPath: string;          // e.g. "Flow/Opportunity_Approval"
  before: Record<string, unknown>;   // config state before the edit
  after: Record<string, unknown>;    // config state after the edit
}

/** A NetSuite SuiteCloud (SDF) project deploy — an artifact-bound release. */
interface NetSuiteSdfDeploy {
  system: "netsuite";
  changeKind: "sdf_deploy";
  account: string;             // NetSuite account id, e.g. "1234567"
  environment: "production" | "sandbox";
  requestedBy: string;
  changeRequest: string;
  approvals: number;
  changeWindow: boolean;
  project: {                   // the SDF deploy plan (illustrative objects)
    projectName: string;
    objects: Array<{ scriptId: string; type: string }>;
  };
}

/** A ServiceNow change request — the record IS the plan (no separate build artifact). */
interface ServiceNowChangeRequest {
  system: "servicenow";
  changeKind: "change_request";
  instance: string;            // ServiceNow instance name, e.g. "acmecorp"
  environment: "production" | "sandbox";
  requestedBy: string;
  changeRequest: string;       // the change number, e.g. "CHG0000123" — also the CAB ticket
  approvals: number;
  changeWindow: boolean;
  record: {                    // the change_request record fields (the plan itself)
    number: string;
    short_description: string;
    cmdb_ci: string;
    state: string;
    planned_start_date: string;
    planned_end_date: string;
  };
}

/** A Jira issue — the record IS the plan (no separate build artifact). */
interface JiraIssueChange {
  system: "jira";
  changeKind: "issue";
  site: string;                // Jira site name, e.g. "acmecorp"
  environment: "production" | "sandbox";
  requestedBy: string;
  changeRequest: string;       // the issue key, e.g. "CHG-123" — also the CAB ticket
  approvals: number;
  changeWindow: boolean;
  issue: {                     // the issue fields (the plan itself)
    key: string;
    summary: string;
    status: string;
    issuetype: string;
    duedate: string;
    assignee: string;
  };
}

/** An AWS infrastructure change — an artifact-bound release (a Terraform plan). */
interface TerraformPlanChange {
  system: "aws";
  changeKind: "terraform_plan";
  account: string;             // AWS account id, e.g. "123456789012"
  environment: "production" | "sandbox";
  requestedBy: string;
  changeRequest: string;
  approvals: number;
  changeWindow: boolean;
  plan: {                      // the deploy plan (illustrative resource changes)
    workspace: string;
    resources: Array<{ type: string; member: string }>;
  };
}

type BusinessSystemChange =
  | SalesforceMetadataDeploy
  | SalesforceConfigEdit
  | NetSuiteSdfDeploy
  | ServiceNowChangeRequest
  | JiraIssueChange
  | TerraformPlanChange;

// ---------------------------------------------------------------------------
// Sample hardcoded changes (stub — not live Salesforce events)
// ---------------------------------------------------------------------------

const SAMPLE_METADATA_DEPLOY: SalesforceMetadataDeploy = {
  system: "salesforce",
  changeKind: "metadata_deploy",
  org: "acme-prod",
  environment: "production",
  requestedBy: "release.alice@acme.com",
  changeRequest: "CHG-2026-0421",
  approvals: 2,
  changeWindow: true,
  package: {
    apiVersion: "61.0",
    components: [
      { type: "Flow", member: "Opportunity_Approval" },
      { type: "PermissionSet", member: "Deal_Desk_Approver" },
      { type: "ValidationRule", member: "Opportunity.Require_Close_Reason" },
    ],
  },
};

const SAMPLE_CONFIG_EDIT: SalesforceConfigEdit = {
  system: "salesforce",
  changeKind: "config_edit",
  org: "acme-prod",
  environment: "production",
  requestedBy: "admin.bob@acme.com",
  changeRequest: "CHG-2026-0422",
  approvals: 2,
  changeWindow: true,
  configPath: "Flow/Opportunity_Approval",
  before: { active: true, approverStep: "RegionalVP", entryThreshold: 50000 },
  after: { active: true, approverStep: "RegionalVP+Finance", entryThreshold: 25000 },
};

const SAMPLE_SDF_DEPLOY: NetSuiteSdfDeploy = {
  system: "netsuite",
  changeKind: "sdf_deploy",
  account: "1234567",
  environment: "production",
  requestedBy: "release.dana@acme.com",
  changeRequest: "CHG-2026-0423",
  approvals: 2,
  changeWindow: true,
  project: {
    projectName: "AcmeRevenueAutomation",
    objects: [
      { scriptId: "customworkflow_ap_approval", type: "workflow" },
      { scriptId: "customscript_tax_calc", type: "scheduledscript" },
    ],
  },
};

const SAMPLE_SERVICENOW_CHANGE: ServiceNowChangeRequest = {
  system: "servicenow",
  changeKind: "change_request",
  instance: "acmecorp",
  environment: "production",
  requestedBy: "release.erin@acme.com",
  changeRequest: "CHG0000123",
  approvals: 2,
  changeWindow: true,
  record: {
    number: "CHG0000123",
    short_description: "Increase Deal Desk approval threshold to $25,000",
    cmdb_ci: "Opportunity Approval Workflow",
    state: "Scheduled",
    planned_start_date: "2026-08-20 22:00:00",
    planned_end_date: "2026-08-21 02:00:00",
  },
};

const SAMPLE_JIRA_ISSUE: JiraIssueChange = {
  system: "jira",
  changeKind: "issue",
  site: "acmecorp",
  environment: "production",
  requestedBy: "release.frank@acme.com",
  changeRequest: "CHG-4501",
  approvals: 2,
  changeWindow: true,
  issue: {
    key: "CHG-4501",
    summary: "Raise Deal Desk approval threshold to $25,000",
    status: "Approved",
    issuetype: "Change",
    duedate: "2026-08-21",
    assignee: "Frank Nguyen",
  },
};

const SAMPLE_TERRAFORM_PLAN: TerraformPlanChange = {
  system: "aws",
  changeKind: "terraform_plan",
  account: "123456789012",
  environment: "production",
  requestedBy: "release.grace@acme.com",
  changeRequest: "CHG-7801",
  approvals: 2,
  changeWindow: true,
  plan: {
    workspace: "prod-us-east-1",
    resources: [
      { type: "aws_iam_role", member: "aws_iam_role.deal_desk_approver" },
      { type: "aws_lambda_function", member: "aws_lambda_function.approval_threshold_check" },
    ],
  },
};

// ---------------------------------------------------------------------------
// Digests
// ---------------------------------------------------------------------------

const sha256hex = (s: string): string => createHash("sha256").update(s).digest("hex");

/** Deterministic canonical JSON (sorted keys) so the digest is reproducible. */
function canonical(value: unknown): string {
  if (Array.isArray(value)) return "[" + value.map(canonical).join(",") + "]";
  if (value && typeof value === "object") {
    const keys = Object.keys(value as Record<string, unknown>).sort();
    return "{" + keys.map((k) => JSON.stringify(k) + ":" + canonical((value as Record<string, unknown>)[k])).join(",") + "}";
  }
  return JSON.stringify(value);
}

// ---------------------------------------------------------------------------
// Normalization: business-system change -> production.deploy request
// ---------------------------------------------------------------------------

interface EvaluateRequest {
  action_type: "production.deploy";
  actor_id: string;
  target_id: string;
  environment: string;
  execution_payload_hash: string;
  context: Record<string, unknown>;
}

function normalize(change: BusinessSystemChange): EvaluateRequest {
  const actor_id = "github:acme-release-bot"; // the approved deployer (matches allow_actors)
  const targetRef = change.system === "netsuite"
    ? change.account
    : change.system === "servicenow"
    ? change.instance
    : change.system === "jira"
    ? change.site
    : change.system === "aws"
    ? change.account
    : change.org;
  const target_id = `${change.system}:${targetRef}`;

  if (change.changeKind === "metadata_deploy") {
    // Artifact-bound: the payload digest is the sha256 of the deploy plan.
    const payload_hash = sha256hex(canonical(change.package));
    return {
      action_type: "production.deploy",
      actor_id,
      target_id,
      environment: change.environment,
      execution_payload_hash: payload_hash,
      context: {
        environment: change.environment,
        // Vendor-neutral change-plan conventions. They ride the OPEN
        // evaluate context; canonical_plan_digest maps onto the existing permit
        // payload-hash binding — no wire change.
        target_system: change.system,
        plan_format: "salesforce-change-set",
        authority_path: "change-advisory-board",
        canonical_plan_digest: payload_hash,
        evidence_set_digest: sha256hex(canonical({ approvals: change.approvals, change_request: change.changeRequest })),
        org: change.org,
        change_request: change.changeRequest,
        approvals: change.approvals,
        change_window: change.changeWindow,
        component_count: change.package.components.length,
      },
    };
  }

  if (change.changeKind === "sdf_deploy") {
    // Artifact-bound: hash the SDF deploy plan (SuiteCloud project objects).
    const payload_hash = sha256hex(canonical(change.project));
    return {
      action_type: "production.deploy",
      actor_id,
      target_id,
      environment: change.environment,
      execution_payload_hash: payload_hash,
      context: {
        environment: change.environment,
        target_system: change.system,
        plan_format: "netsuite-sdf-project",
        authority_path: "change-advisory-board",
        canonical_plan_digest: payload_hash,
        evidence_set_digest: sha256hex(canonical({ approvals: change.approvals, change_request: change.changeRequest })),
        account: change.account,
        change_request: change.changeRequest,
        approvals: change.approvals,
        change_window: change.changeWindow,
        object_count: change.project.objects.length,
      },
    };
  }

  if (change.changeKind === "change_request") {
    // Artifact-bound: the "artifact" for ServiceNow is the change_request
    // record itself — there is no separate build package, so the record's
    // fields ARE the plan being digested (mirrors how a metadata package's
    // component list IS the plan for Salesforce).
    const payload_hash = sha256hex(canonical(change.record));
    return {
      action_type: "production.deploy",
      actor_id,
      target_id,
      environment: change.environment,
      execution_payload_hash: payload_hash,
      context: {
        environment: change.environment,
        target_system: change.system,
        plan_format: "servicenow-change-request",
        authority_path: "change-advisory-board",
        canonical_plan_digest: payload_hash,
        evidence_set_digest: sha256hex(canonical({ approvals: change.approvals, change_request: change.changeRequest })),
        instance: change.instance,
        change_request: change.changeRequest,
        approvals: change.approvals,
        change_window: change.changeWindow,
        cmdb_ci: change.record.cmdb_ci,
      },
    };
  }

  if (change.changeKind === "issue") {
    // Artifact-bound: the "artifact" for Jira is the issue itself — there is
    // no separate build package, so the issue's fields ARE the plan being
    // digested (mirrors the ServiceNow change_request treatment above).
    const payload_hash = sha256hex(canonical(change.issue));
    return {
      action_type: "production.deploy",
      actor_id,
      target_id,
      environment: change.environment,
      execution_payload_hash: payload_hash,
      context: {
        environment: change.environment,
        target_system: change.system,
        plan_format: "jira-issue",
        authority_path: "change-advisory-board",
        canonical_plan_digest: payload_hash,
        evidence_set_digest: sha256hex(canonical({ approvals: change.approvals, change_request: change.changeRequest })),
        site: change.site,
        change_request: change.changeRequest,
        approvals: change.approvals,
        change_window: change.changeWindow,
        issue_status: change.issue.status,
      },
    };
  }

  if (change.changeKind === "terraform_plan") {
    // Artifact-bound: hash the Terraform plan's resource changes — same
    // treatment as an SDF deploy plan (an ordered, typed component list).
    const payload_hash = sha256hex(canonical(change.plan));
    return {
      action_type: "production.deploy",
      actor_id,
      target_id,
      environment: change.environment,
      execution_payload_hash: payload_hash,
      context: {
        environment: change.environment,
        target_system: change.system,
        plan_format: "terraform-plan",
        authority_path: "change-advisory-board",
        canonical_plan_digest: payload_hash,
        evidence_set_digest: sha256hex(canonical({ approvals: change.approvals, change_request: change.changeRequest })),
        account: change.account,
        change_request: change.changeRequest,
        approvals: change.approvals,
        change_window: change.changeWindow,
        resource_count: change.plan.resources.length,
      },
    };
  }

  // config_edit: no build artifact — bind the before/after STATE SNAPSHOT.
  const state_snapshot = sha256hex(canonical({ before: change.before, after: change.after }));
  return {
    action_type: "production.deploy",
    actor_id,
    target_id,
    environment: change.environment,
    execution_payload_hash: state_snapshot, // the profile binds the state digest as the payload
    context: {
      environment: change.environment,
      target_system: change.system,
      plan_format: "salesforce-config-edit",
      authority_path: "salesforce-approval-process",
      canonical_plan_digest: state_snapshot,   // the before/after state IS the plan digest for a config edit
      org: change.org,
      change_request: change.changeRequest,
      approvals: change.approvals,
      change_window: change.changeWindow,
      profile: "state_snapshot",
      config_path: change.configPath,
      state_snapshot,
    },
  };
}

// ---------------------------------------------------------------------------
// Gate: evaluate -> require allow+permit -> verify -> require valid (fail-closed)
// ---------------------------------------------------------------------------

async function post(url: string, apiKey: string, body: unknown): Promise<Record<string, unknown>> {
  const res = await fetch(url, {
    method: "POST",
    headers: { authorization: `Bearer ${apiKey}`, "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${url} -> HTTP ${res.status}`);
  return (await res.json()) as Record<string, unknown>;
}

async function gateLive(req: EvaluateRequest, apiKey: string, apiUrl: string): Promise<boolean> {
  const evalRes = await post(`${apiUrl}/v1-evaluate`, apiKey, req);
  const decision = String(evalRes.decision ?? "").toLowerCase();
  const permit = String(evalRes.permit_token ?? "");
  console.log(`  evaluate: decision=${decision} permit=${permit.slice(0, 16)}… deny_code=${evalRes.deny_code ?? ""}`);
  if (decision !== "allow" || !permit) {
    console.log("  BLOCKED at evaluate (fail-closed).");
    return false;
  }
  // Verify AT THE DEPLOY BOUNDARY, re-binding the same payload digest (single-use).
  const verifyRes = await post(`${apiUrl}/v1-verify-permit`, apiKey, {
    permit_token: permit,
    action_type: req.action_type,
    actor_id: req.actor_id,
    environment: req.environment,
    payload_hash: req.execution_payload_hash,
  });
  const valid = verifyRes.valid === true;
  console.log(`  verify: valid=${valid} outcome=${verifyRes.outcome ?? ""} ${valid ? "" : "verify_error_code=" + (verifyRes.verify_error_code ?? "")}`);
  if (!valid) {
    console.log("  BLOCKED at verify (fail-closed).");
    return false;
  }
  console.log("  ALLOWED — run the real deploy under this verified, single-use permit.");
  return true;
}

function printOffline(req: EvaluateRequest): void {
  console.log("  evaluate  POST /v1-evaluate");
  console.log("    " + JSON.stringify(req));
  console.log("  verify    POST /v1-verify-permit  (at the deploy boundary)");
  console.log("    " + JSON.stringify({
    permit_token: "<from evaluate>",
    action_type: req.action_type,
    actor_id: req.actor_id,
    environment: req.environment,
    payload_hash: req.execution_payload_hash,
  }));
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

/**
 * Attempts to build the metadata-deploy and SDF-deploy changes from a REAL CLI
 * (sf / suitecloud) dry-run, falling back to the hardcoded SAMPLE_* stub — with
 * a clearly logged reason — when the CLI is absent, fails, or its output can't
 * be parsed with the configured mapping. Opt-in via USE_REAL_CLI=true so the
 * default `npm run demo` behavior is unchanged. change_request/approvals/
 * change_window/requestedBy come from change-management env vars, not the CLI
 * (a deploy CLI's dry-run has no notion of CAB approval state).
 */
function buildMetadataDeployChange(): SalesforceMetadataDeploy {
  if (process.env.USE_REAL_CLI !== "true") return SAMPLE_METADATA_DEPLOY;
  const result = buildMetadataDeployFromCli(
    {
      command: process.env.SF_CLI_COMMAND ?? "sf",
      args: (process.env.SF_CLI_ARGS ?? "project deploy validate --json").split(" "),
      cwd: process.env.SF_PROJECT_DIR,
    },
    {
      org: process.env.SF_ORG ?? SAMPLE_METADATA_DEPLOY.org,
      environment: (process.env.SF_ENVIRONMENT as "production" | "sandbox" | undefined) ?? SAMPLE_METADATA_DEPLOY.environment,
      requestedBy: process.env.CHANGE_REQUESTED_BY ?? SAMPLE_METADATA_DEPLOY.requestedBy,
      changeRequest: process.env.CHANGE_REQUEST_ID ?? SAMPLE_METADATA_DEPLOY.changeRequest,
      approvals: Number(process.env.CHANGE_APPROVALS ?? SAMPLE_METADATA_DEPLOY.approvals),
      changeWindow: (process.env.CHANGE_WINDOW ?? "true") === "true",
    },
    process.env.SF_API_VERSION ?? "61.0",
  );
  if (result.ok) {
    console.log(`  [connectors] real sf CLI deploy plan: ${result.plan.package.components.length} component(s).`);
    return result.plan;
  }
  console.log(`  [connectors] real sf CLI unavailable (${result.reason}) — falling back to the sample stub.`);
  return SAMPLE_METADATA_DEPLOY;
}

function buildSdfDeployChange(): NetSuiteSdfDeploy {
  if (process.env.USE_REAL_CLI !== "true") return SAMPLE_SDF_DEPLOY;
  const result = buildSdfDeployFromCli(
    {
      command: process.env.SUITECLOUD_CLI_COMMAND ?? "suitecloud",
      args: (process.env.SUITECLOUD_CLI_ARGS ?? "project:deploy --dryrun --json").split(" "),
      cwd: process.env.SUITECLOUD_PROJECT_DIR,
    },
    {
      account: process.env.NETSUITE_ACCOUNT ?? SAMPLE_SDF_DEPLOY.account,
      environment: (process.env.SF_ENVIRONMENT as "production" | "sandbox" | undefined) ?? SAMPLE_SDF_DEPLOY.environment,
      requestedBy: process.env.CHANGE_REQUESTED_BY ?? SAMPLE_SDF_DEPLOY.requestedBy,
      changeRequest: process.env.CHANGE_REQUEST_ID ?? SAMPLE_SDF_DEPLOY.changeRequest,
      approvals: Number(process.env.CHANGE_APPROVALS ?? SAMPLE_SDF_DEPLOY.approvals),
      changeWindow: (process.env.CHANGE_WINDOW ?? "true") === "true",
    },
    process.env.SUITECLOUD_PROJECT_NAME ?? SAMPLE_SDF_DEPLOY.project.projectName,
  );
  if (result.ok) {
    console.log(`  [connectors] real suitecloud CLI deploy plan: ${result.plan.project.objects.length} object(s).`);
    return result.plan;
  }
  console.log(`  [connectors] real suitecloud CLI unavailable (${result.reason}) — falling back to the sample stub.`);
  return SAMPLE_SDF_DEPLOY;
}

/**
 * Attempts to build the AWS/Terraform change from a REAL `terraform show
 * -json <planfile>` shellout, falling back to the hardcoded SAMPLE_* stub —
 * with a clearly logged reason — when the CLI is absent, fails, or its
 * output can't be parsed with the configured mapping. Opt-in via
 * USE_REAL_CLI=true (the SAME flag as the sf/suitecloud connectors — this
 * genuinely is a CLI shellout, not a direct HTTP API call) so the default
 * `npm run demo` behavior is unchanged. TERRAFORM_PLAN_FILE must point at an
 * ALREADY-PRODUCED plan file (`terraform plan -out=<file>`, run by the
 * caller's own pipeline beforehand — see connectors.ts's module header on
 * why this connector never runs `terraform plan` itself).
 */
function buildTerraformPlanChange(): TerraformPlanChange {
  if (process.env.USE_REAL_CLI !== "true") return SAMPLE_TERRAFORM_PLAN;
  const planFile = process.env.TERRAFORM_PLAN_FILE;
  if (!planFile) {
    console.log("  [connectors] USE_REAL_CLI=true but TERRAFORM_PLAN_FILE not set — falling back to the sample stub.");
    return SAMPLE_TERRAFORM_PLAN;
  }
  const result = buildTerraformPlanFromCli(
    {
      command: process.env.TERRAFORM_CLI_COMMAND ?? "terraform",
      args: ["show", "-json", planFile],
      cwd: process.env.TERRAFORM_PROJECT_DIR,
    },
    {
      account: process.env.AWS_ACCOUNT_ID ?? SAMPLE_TERRAFORM_PLAN.account,
      environment: (process.env.SF_ENVIRONMENT as "production" | "sandbox" | undefined) ?? SAMPLE_TERRAFORM_PLAN.environment,
      requestedBy: process.env.CHANGE_REQUESTED_BY ?? SAMPLE_TERRAFORM_PLAN.requestedBy,
      changeRequest: process.env.CHANGE_REQUEST_ID ?? SAMPLE_TERRAFORM_PLAN.changeRequest,
      approvals: Number(process.env.CHANGE_APPROVALS ?? SAMPLE_TERRAFORM_PLAN.approvals),
      changeWindow: (process.env.CHANGE_WINDOW ?? "true") === "true",
    },
    process.env.TERRAFORM_WORKSPACE ?? SAMPLE_TERRAFORM_PLAN.plan.workspace,
  );
  if (result.ok) {
    console.log(`  [connectors] real terraform plan: ${result.plan.plan.resources.length} resource change(s).`);
    return result.plan;
  }
  console.log(`  [connectors] real terraform CLI unavailable (${result.reason}) — falling back to the sample stub.`);
  return SAMPLE_TERRAFORM_PLAN;
}

/**
 * Attempts to build the change_request change from a REAL ServiceNow Table
 * API GET, falling back to the hardcoded SAMPLE_* stub — with a clearly
 * logged reason — when credentials are absent, the request fails, or the
 * response can't be parsed with the configured mapping. Opt-in via
 * USE_REAL_SERVICENOW_API=true (separate from USE_REAL_CLI: this is a direct
 * HTTPS API call, not a CLI shellout) so the default `npm run demo` behavior
 * is unchanged. change_request/approvals/change_window/requestedBy come from
 * change-management env vars, not the API (the change_request record's own
 * `approval` field is a coarser signal than a CAB approval count and is not
 * read here — see connectors.ts's boundary statement).
 */
async function buildServiceNowChange(): Promise<ServiceNowChangeRequest> {
  if (process.env.USE_REAL_SERVICENOW_API !== "true") return SAMPLE_SERVICENOW_CHANGE;
  const instance = process.env.SERVICENOW_INSTANCE;
  const user = process.env.SERVICENOW_USER;
  const password = process.env.SERVICENOW_PASSWORD;
  if (!instance || !user || !password) {
    console.log(
      "  [connectors] USE_REAL_SERVICENOW_API=true but SERVICENOW_INSTANCE/SERVICENOW_USER/SERVICENOW_PASSWORD " +
        "not all set — falling back to the sample stub.",
    );
    return SAMPLE_SERVICENOW_CHANGE;
  }
  const result = await buildChangeRequestFromApi(
    { instance, user, password },
    {
      instance,
      environment: (process.env.SF_ENVIRONMENT as "production" | "sandbox" | undefined) ?? SAMPLE_SERVICENOW_CHANGE.environment,
      requestedBy: process.env.CHANGE_REQUESTED_BY ?? SAMPLE_SERVICENOW_CHANGE.requestedBy,
      changeRequest: process.env.CHANGE_REQUEST_ID ?? SAMPLE_SERVICENOW_CHANGE.changeRequest,
      approvals: Number(process.env.CHANGE_APPROVALS ?? SAMPLE_SERVICENOW_CHANGE.approvals),
      changeWindow: (process.env.CHANGE_WINDOW ?? "true") === "true",
    },
  );
  if (result.ok) {
    console.log(`  [connectors] real ServiceNow Table API read: change ${result.plan.record.number} (${result.plan.record.state}).`);
    return {
      system: "servicenow",
      changeKind: "change_request",
      instance: result.plan.instance,
      environment: result.plan.environment,
      requestedBy: result.plan.requestedBy,
      changeRequest: result.plan.changeRequest,
      approvals: result.plan.approvals,
      changeWindow: result.plan.changeWindow,
      record: result.plan.record,
    };
  }
  console.log(`  [connectors] real ServiceNow Table API unavailable (${result.reason}) — falling back to the sample stub.`);
  return SAMPLE_SERVICENOW_CHANGE;
}

/**
 * Attempts to build the Jira issue change from a REAL Jira REST API GET,
 * falling back to the hardcoded SAMPLE_* stub — with a clearly logged reason
 * — when credentials are absent, the request fails, or the response can't be
 * parsed with the configured mapping. Opt-in via USE_REAL_JIRA_API=true
 * (separate from USE_REAL_CLI/USE_REAL_SERVICENOW_API: this is a direct
 * HTTPS API call, not a CLI shellout) so the default `npm run demo` behavior
 * is unchanged. change_request/approvals/change_window/requestedBy come from
 * change-management env vars, not the API — Jira has no fixed "approved"
 * status vocabulary (unlike a numeric approval count), so this connector
 * does not attempt to infer CAB approval state from the issue's own status
 * field; that's a caller-supplied fact, exactly as for the other systems.
 */
async function buildJiraChange(): Promise<JiraIssueChange> {
  if (process.env.USE_REAL_JIRA_API !== "true") return SAMPLE_JIRA_ISSUE;
  const site = process.env.JIRA_SITE;
  const email = process.env.JIRA_EMAIL;
  const apiToken = process.env.JIRA_API_TOKEN;
  if (!site || !email || !apiToken) {
    console.log(
      "  [connectors] USE_REAL_JIRA_API=true but JIRA_SITE/JIRA_EMAIL/JIRA_API_TOKEN not all set — " +
        "falling back to the sample stub.",
    );
    return SAMPLE_JIRA_ISSUE;
  }
  const result = await buildJiraIssueFromApi(
    { site, email, apiToken },
    {
      site,
      environment: (process.env.SF_ENVIRONMENT as "production" | "sandbox" | undefined) ?? SAMPLE_JIRA_ISSUE.environment,
      requestedBy: process.env.CHANGE_REQUESTED_BY ?? SAMPLE_JIRA_ISSUE.requestedBy,
      changeRequest: process.env.CHANGE_REQUEST_ID ?? SAMPLE_JIRA_ISSUE.changeRequest,
      approvals: Number(process.env.CHANGE_APPROVALS ?? SAMPLE_JIRA_ISSUE.approvals),
      changeWindow: (process.env.CHANGE_WINDOW ?? "true") === "true",
    },
  );
  if (result.ok) {
    console.log(`  [connectors] real Jira REST API read: issue ${result.plan.issue.key} (${result.plan.issue.status}).`);
    return {
      system: "jira",
      changeKind: "issue",
      site: result.plan.site,
      environment: result.plan.environment,
      requestedBy: result.plan.requestedBy,
      changeRequest: result.plan.changeRequest,
      approvals: result.plan.approvals,
      changeWindow: result.plan.changeWindow,
      issue: result.plan.issue,
    };
  }
  console.log(`  [connectors] real Jira REST API unavailable (${result.reason}) — falling back to the sample stub.`);
  return SAMPLE_JIRA_ISSUE;
}

async function main(): Promise<void> {
  const apiKey = process.env.ATLASENT_API_KEY;
  const apiUrl = process.env.ATLASENT_API_URL;
  const live = Boolean(apiKey && apiUrl);
  const realCli = process.env.USE_REAL_CLI === "true";
  const realServiceNow = process.env.USE_REAL_SERVICENOW_API === "true";
  const realJira = process.env.USE_REAL_JIRA_API === "true";

  console.log("=== salesforce-change.ts — production.deploy gate ===");
  console.log(live ? "Mode: LIVE (posting to your tenant)\n" : "Mode: OFFLINE STUB (no network; prints request bodies)\n");
  if (realCli) {
    console.log("USE_REAL_CLI=true — attempting real sf/suitecloud/terraform CLI shellout (falls back to sample stub per-change on failure).\n");
  }
  if (realServiceNow) {
    console.log("USE_REAL_SERVICENOW_API=true — attempting a real ServiceNow Table API read (falls back to sample stub on failure).\n");
  }
  if (realJira) {
    console.log("USE_REAL_JIRA_API=true — attempting a real Jira REST API read (falls back to sample stub on failure).\n");
  }

  const changes: Array<{ label: string; change: BusinessSystemChange }> = [
    { label: "Salesforce metadata deploy (artifact-bound)", change: buildMetadataDeployChange() },
    { label: "NetSuite SuiteCloud/SDF deploy (artifact-bound)", change: buildSdfDeployChange() },
    { label: "ServiceNow change request (artifact-bound)", change: await buildServiceNowChange() },
    { label: "Jira issue (artifact-bound)", change: await buildJiraChange() },
    { label: "AWS infra change (terraform plan, artifact-bound)", change: buildTerraformPlanChange() },
    // config_edit stays a stub even under USE_REAL_CLI: a real before/after config
    // snapshot requires reading live Salesforce metadata state (Tooling API), a
    // separate, larger integration not built here — see connectors.ts header.
    { label: "Salesforce live config edit (state-snapshot profile)", change: SAMPLE_CONFIG_EDIT },
  ];

  for (const { label, change } of changes) {
    console.log(`--- ${label} — ${change.changeRequest} ---`);
    const req = normalize(change);
    console.log(`  target=${req.target_id} env=${req.environment} payload_hash=${req.execution_payload_hash.slice(0, 16)}…`);
    if (live) {
      await gateLive(req, apiKey as string, apiUrl as string);
    } else {
      printOffline(req);
    }
    console.log("");
  }

  if (!live) {
    console.log("Set ATLASENT_API_KEY + ATLASENT_API_URL (…/functions/v1) to run the live gate.");
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
