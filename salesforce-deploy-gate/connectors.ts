/**
 * connectors.ts — real CLI shellout / API read for the Salesforce / NetSuite /
 * ServiceNow / Jira / AWS (Terraform) change gate.
 *
 * `salesforce-change.ts` ships with hardcoded SAMPLE_* payloads (an explicit,
 * documented stub). This module replaces "hardcoded payload" with "shell out to
 * the real deploy CLI" (Salesforce/NetSuite) or "read the real change record via
 * the real Table API" (ServiceNow) and parse the real output into the same
 * BusinessSystemChange shape — the piece the file's own header names as the
 * pilot follow-up ("Replace the stubs with real `sf project deploy` / SuiteCloud
 * (SDF) calls for a pilot").
 *
 * Honesty boundary (read before wiring this into a pilot):
 *   - This module runs a REAL CLI (Salesforce CLI `sf`, or SuiteCloud CLI
 *     `suitecloud`) via child_process, or makes a REAL HTTPS call (ServiceNow
 *     Table API), and parses REAL JSON output. That part is not a stub.
 *   - The exact JSON *shape* each CLI/API emits varies by CLI version, which
 *     subcommand/flags you use, or which fields your ServiceNow instance's
 *     `change_request` table exposes. Rather than hardcode one undocumented
 *     shape and risk silently mis-parsing (or worse, silently under-counting)
 *     a real deploy plan, the extractors take a caller-supplied field mapping
 *     (`ComponentMapping` for the CLIs, `FieldMapping` for ServiceNow)
 *     describing where the data lives in the JSON and which fields to read.
 *     DEFAULT_SF_MAPPING and DEFAULT_SDF_MAPPING below match the current
 *     documented output shape of `sf project deploy validate --json`
 *     (`result.files[].{type,fullName}`) and a common SuiteCloud
 *     `project:deploy --json` shape (`data.appliedContentProtection` is NOT
 *     it — SuiteCloud's deploy JSON is less standardized; DEFAULT_SDF_MAPPING
 *     targets `data.objects[].{type,scriptId}`, the shape the `suitecloud
 *     project:deploy` command documents for its dry-run summary).
 *     DEFAULT_SERVICENOW_CHANGE_MAPPING targets the documented Table API list-
 *     query shape (`result[0].{number,short_description,cmdb_ci,state,
 *     planned_start_date,planned_end_date}`), the stock `change_request` table
 *     fields. **None of these defaults has been verified against a live
 *     CLI/instance in this environment** — confirm the mapping against your
 *     actual CLI version's output / your instance's field set before relying
 *     on it for a pilot, and pass an explicit mapping if it differs.
 *   - This module does NOT call the Salesforce or NetSuite HTTP APIs directly
 *     for the CLI-based connectors — it shells out to the CLIs your release
 *     pipeline already uses (they own auth, org selection, and the actual
 *     deploy/validate call). For ServiceNow (no equivalent official CLI), it
 *     makes a direct, read-only Table API GET using credentials the caller
 *     supplies (an itil-scoped integration user, matching the pattern proven
 *     live in AtlaSent's internal ServiceNow OAuth setup guide) — it
 *     does not call any AtlaSent-side connector-management endpoint.
 *   - **Read-only, matching the CLI connectors' own scope.** The Salesforce/
 *     NetSuite connectors run `validate`/`--dryrun` — they never execute a real
 *     deploy either (see `salesforce-change.ts`'s `gateLive()`: even the "run
 *     the real deploy" step is logged, not invoked). The ServiceNow connector
 *     mirrors that boundary: it GETs the change_request record to build the
 *     plan digest; it never PATCHes/transitions the record. Actually executing
 *     the authorized change (deploy, or a Table API write) is a separate,
 *     deliberately out-of-scope step for this reference demo.
 *   - `approvals` / `changeWindow` / `requestedBy` / `changeRequest` are NOT
 *     derivable from a deploy CLI's dry-run output or a change_request read —
 *     they come from your change management system (CAB ticket, approval
 *     count). This module accepts them as caller-supplied metadata; it does
 *     not invent or infer them.
 */
import { execFileSync } from "node:child_process";

// ---------------------------------------------------------------------------
// Component extraction — pure, no I/O, unit-testable against fixture JSON
// ---------------------------------------------------------------------------

/** Where the component/object list lives in a CLI's JSON output, and which fields to read. */
export interface ComponentMapping {
  /** Path from the parsed JSON root to the array of components, e.g. ["result","files"]. */
  componentsPath: string[];
  /** Field on each component entry holding its type (e.g. "type"). */
  typeField: string;
  /** Field on each component entry holding its name/id (e.g. "fullName" or "scriptId"). */
  nameField: string;
}

/** `sf project deploy validate --json` — component list at result.files[].{type,fullName}. */
export const DEFAULT_SF_MAPPING: ComponentMapping = {
  componentsPath: ["result", "files"],
  typeField: "type",
  nameField: "fullName",
};

/** SuiteCloud `project:deploy --json` dry-run summary — component list at data.objects[].{type,scriptId}. */
export const DEFAULT_SDF_MAPPING: ComponentMapping = {
  componentsPath: ["data", "objects"],
  typeField: "type",
  nameField: "scriptId",
};

/** `terraform show -json <planfile>` — the documented machine-readable plan
 *  representation; component list at resource_changes[].{type,address}.
 *  Reuses the SAME ComponentMapping shape as the Salesforce/NetSuite
 *  connectors above — a Terraform resource change and a metadata component
 *  are both, structurally, "a typed, named unit of the plan being applied",
 *  so no new extraction logic is needed here. */
export const DEFAULT_TERRAFORM_MAPPING: ComponentMapping = {
  componentsPath: ["resource_changes"],
  typeField: "type",
  nameField: "address",
};

function walkPath(json: unknown, path: string[]): unknown {
  let node: unknown = json;
  for (const key of path) {
    if (node === null || typeof node !== "object") return undefined;
    node = (node as Record<string, unknown>)[key];
  }
  return node;
}

/**
 * Extracts `{ type, member }` component pairs from a CLI's parsed JSON output
 * using the given mapping. Pure — no I/O, safe to unit test with fixture JSON.
 * Throws if the mapped path isn't an array, or if any entry is missing a field
 * — a deploy plan with an unparseable component is refused, not silently
 * dropped (a dropped component would understate the digest of what actually
 * deploys).
 */
export function extractComponents(
  json: unknown,
  mapping: ComponentMapping,
): Array<{ type: string; member: string }> {
  const list = walkPath(json, mapping.componentsPath);
  if (!Array.isArray(list)) {
    throw new Error(
      `extractComponents: expected an array at ${mapping.componentsPath.join(".")}, got ${typeof list}`,
    );
  }
  return list.map((entry, i) => {
    if (entry === null || typeof entry !== "object") {
      throw new Error(`extractComponents: entry ${i} is not an object`);
    }
    const rec = entry as Record<string, unknown>;
    const type = rec[mapping.typeField];
    const member = rec[mapping.nameField];
    if (typeof type !== "string" || type.length === 0) {
      throw new Error(`extractComponents: entry ${i} missing string field "${mapping.typeField}"`);
    }
    if (typeof member !== "string" || member.length === 0) {
      throw new Error(`extractComponents: entry ${i} missing string field "${mapping.nameField}"`);
    }
    return { type, member };
  });
}

// ---------------------------------------------------------------------------
// CLI shellout — real child_process calls (not exercised by unit tests)
// ---------------------------------------------------------------------------

export interface CliInvocation {
  /** Executable name or path, e.g. "sf" or "suitecloud". */
  command: string;
  args: string[];
  /** Working directory to run the CLI in (the deploy project root). */
  cwd?: string;
}

export interface CliRunResult {
  ok: boolean;
  /** Parsed JSON stdout, or undefined if the CLI failed or emitted non-JSON. */
  json?: unknown;
  /** Human-readable reason for a non-ok result (missing CLI, non-zero exit, parse error). */
  reason?: string;
}

/**
 * Runs a deploy-plan CLI (e.g. `sf project deploy validate --json`) and
 * parses its stdout as JSON. Never throws — a missing CLI, a non-zero exit
 * (both Salesforce and SuiteCloud CLIs use nonzero-with-JSON on some check
 * failures, so a nonzero exit is still parsed if valid JSON was emitted), or
 * unparseable output all resolve to `{ ok: false, reason }` so the caller can
 * fall back to a stub / fail closed rather than throw mid-run.
 */
export function runDeployCli(invocation: CliInvocation): CliRunResult {
  let stdout: string;
  try {
    stdout = execFileSync(invocation.command, invocation.args, {
      cwd: invocation.cwd,
      encoding: "utf8",
      // CLIs may exit nonzero on a "would fail" dry-run result while still
      // emitting valid JSON on stdout — capture it rather than throwing.
      stdio: ["ignore", "pipe", "pipe"],
    });
  } catch (err) {
    const e = err as NodeJS.ErrnoException & { stdout?: Buffer | string };
    // execFileSync throws on nonzero exit too; recover stdout if the CLI still
    // produced JSON (checkOnly/dry-run "failed" results are still valid JSON).
    if (e.stdout) {
      stdout = typeof e.stdout === "string" ? e.stdout : e.stdout.toString("utf8");
    } else {
      return {
        ok: false,
        reason: e.code === "ENOENT"
          ? `"${invocation.command}" not found on PATH`
          : `"${invocation.command}" failed: ${e.message}`,
      };
    }
  }
  try {
    return { ok: true, json: JSON.parse(stdout) };
  } catch {
    return { ok: false, reason: `"${invocation.command}" did not emit valid JSON on stdout` };
  }
}

// ---------------------------------------------------------------------------
// Change-plan builders — CLI output -> the BusinessSystemChange shape
// ---------------------------------------------------------------------------

export interface ChangeMetadata {
  org: string;
  environment: "production" | "sandbox";
  requestedBy: string;
  changeRequest: string;
  approvals: number;
  changeWindow: boolean;
}

export interface SalesforceMetadataDeployPlan {
  system: "salesforce";
  changeKind: "metadata_deploy";
  org: string;
  environment: "production" | "sandbox";
  requestedBy: string;
  changeRequest: string;
  approvals: number;
  changeWindow: boolean;
  package: {
    apiVersion: string;
    components: Array<{ type: string; member: string }>;
  };
}

/**
 * Builds a SalesforceMetadataDeployPlan from an `sf project deploy validate
 * --json` (or equivalent) result. Returns `{ ok: false, reason }` instead of
 * throwing on any failure (CLI absent, non-JSON, unparseable component list) —
 * the caller decides whether to fall back to a stub or fail closed.
 */
export function buildMetadataDeployFromCli(
  invocation: CliInvocation,
  meta: ChangeMetadata,
  apiVersion: string,
  mapping: ComponentMapping = DEFAULT_SF_MAPPING,
): { ok: true; plan: SalesforceMetadataDeployPlan } | { ok: false; reason: string } {
  const run = runDeployCli(invocation);
  if (!run.ok) return { ok: false, reason: run.reason ?? "CLI run failed" };
  let components: Array<{ type: string; member: string }>;
  try {
    components = extractComponents(run.json, mapping);
  } catch (err) {
    return { ok: false, reason: (err as Error).message };
  }
  if (components.length === 0) {
    return { ok: false, reason: "deploy plan has zero components — refusing an empty deploy plan" };
  }
  return {
    ok: true,
    plan: {
      system: "salesforce",
      changeKind: "metadata_deploy",
      org: meta.org,
      environment: meta.environment,
      requestedBy: meta.requestedBy,
      changeRequest: meta.changeRequest,
      approvals: meta.approvals,
      changeWindow: meta.changeWindow,
      package: { apiVersion, components },
    },
  };
}

// ---------------------------------------------------------------------------
// ServiceNow — real Table API GET (not a CLI; ServiceNow has no official one)
// ---------------------------------------------------------------------------

/** Where a single record's fields live in a Table API response, and which fields to read. */
export interface FieldMapping {
  /** Path from the parsed JSON root to the record object, e.g. ["result", 0]
   *  for a list-query GET (`?sysparm_query=...`), or ["result"] for a direct
   *  sys_id GET. */
  recordPath: Array<string | number>;
  /** Field names to read off the record, in order. */
  fields: string[];
}

/** `GET /api/now/table/change_request?sysparm_query=number=...&sysparm_limit=1`
 *  — the stock change_request table's core identifying/scheduling fields. */
export const DEFAULT_SERVICENOW_CHANGE_MAPPING: FieldMapping = {
  recordPath: ["result", 0],
  fields: ["number", "short_description", "cmdb_ci", "state", "planned_start_date", "planned_end_date"],
};

function walkAnyPath(json: unknown, path: Array<string | number>): unknown {
  let node: unknown = json;
  for (const key of path) {
    if (node === null || typeof node !== "object") return undefined;
    node = (node as Record<string | number, unknown>)[key as never];
  }
  return node;
}

/**
 * Extracts a flat `{ field: value }` record from a ServiceNow Table API
 * response using the given mapping. Pure — no I/O, safe to unit test with
 * fixture JSON. Throws (does not silently drop) if the mapped path isn't an
 * object, or if any configured field is missing — a change record with an
 * unparseable field is refused, not silently treated as absent.
 *
 * ServiceNow reference fields (e.g. `cmdb_ci`) are commonly returned as
 * `{ value, display_value }` rather than a plain string (display-value
 * decoration, on by default for many field types) — both a plain string and
 * that shape are accepted, reading `.value` from the latter.
 */
export function extractRecordFields(json: unknown, mapping: FieldMapping): Record<string, string> {
  const node = walkAnyPath(json, mapping.recordPath);
  if (node === null || typeof node !== "object" || Array.isArray(node)) {
    throw new Error(
      `extractRecordFields: expected an object at ${mapping.recordPath.join(".")}, got ${typeof node}`,
    );
  }
  const rec = node as Record<string, unknown>;
  const out: Record<string, string> = {};
  for (const field of mapping.fields) {
    const v = rec[field];
    if (typeof v === "string") {
      out[field] = v;
      continue;
    }
    if (v && typeof v === "object" && typeof (v as Record<string, unknown>).value === "string") {
      out[field] = (v as Record<string, unknown>).value as string;
      continue;
    }
    throw new Error(`extractRecordFields: field "${field}" is missing or not a string/reference on the record`);
  }
  return out;
}

export interface ServiceNowCredentials {
  /** Instance name, e.g. "acmecorp" -> https://acmecorp.service-now.com */
  instance: string;
  user: string;
  password: string;
}

export interface HttpFetchResult {
  ok: boolean;
  json?: unknown;
  reason?: string;
}

/**
 * Fetches a `change_request` record from the ServiceNow Table API by change
 * number. Real HTTPS GET via the global `fetch`, Basic Auth against a
 * scoped `itil`-role integration user — the pattern proven live in
 * AtlaSent's internal ServiceNow OAuth setup guide (a real PDI,
 * `itil` not `itil_admin`). Never throws — a network failure, non-2xx
 * response, or unparseable body all resolve to `{ ok: false, reason }` so the
 * caller can fall back to a stub rather than throw mid-run.
 */
export async function fetchChangeRequest(
  creds: ServiceNowCredentials,
  changeNumber: string,
): Promise<HttpFetchResult> {
  const url = `https://${creds.instance}.service-now.com/api/now/table/change_request` +
    `?sysparm_query=number=${encodeURIComponent(changeNumber)}&sysparm_limit=1`;
  const auth = Buffer.from(`${creds.user}:${creds.password}`).toString("base64");
  let res: Response;
  try {
    res = await fetch(url, {
      method: "GET",
      headers: { authorization: `Basic ${auth}`, accept: "application/json" },
    });
  } catch (err) {
    return { ok: false, reason: `ServiceNow Table API request failed: ${(err as Error).message}` };
  }
  if (!res.ok) {
    return { ok: false, reason: `ServiceNow Table API returned HTTP ${res.status}` };
  }
  try {
    return { ok: true, json: await res.json() };
  } catch {
    return { ok: false, reason: "ServiceNow Table API did not return valid JSON" };
  }
}

export interface ServiceNowChangeRequestPlan {
  system: "servicenow";
  changeKind: "change_request";
  instance: string;
  environment: "production" | "sandbox";
  requestedBy: string;
  changeRequest: string;
  approvals: number;
  changeWindow: boolean;
  record: {
    number: string;
    short_description: string;
    cmdb_ci: string;
    state: string;
    planned_start_date: string;
    planned_end_date: string;
  };
}

/**
 * Builds a ServiceNowChangeRequestPlan from a real Table API GET of the
 * change_request identified by `meta.changeRequest` (the CAB change number,
 * e.g. "CHG0000123"). Returns `{ ok: false, reason }` instead of throwing on
 * any failure (network, non-2xx, unparseable record) — the caller decides
 * whether to fall back to a stub or fail closed.
 */
export async function buildChangeRequestFromApi(
  creds: ServiceNowCredentials,
  meta: Omit<ChangeMetadata, "org"> & { instance: string },
  mapping: FieldMapping = DEFAULT_SERVICENOW_CHANGE_MAPPING,
): Promise<{ ok: true; plan: ServiceNowChangeRequestPlan } | { ok: false; reason: string }> {
  const result = await fetchChangeRequest(creds, meta.changeRequest);
  if (!result.ok) return { ok: false, reason: result.reason ?? "ServiceNow API call failed" };
  let fields: Record<string, string>;
  try {
    fields = extractRecordFields(result.json, mapping);
  } catch (err) {
    return { ok: false, reason: (err as Error).message };
  }
  return {
    ok: true,
    plan: {
      system: "servicenow",
      changeKind: "change_request",
      instance: meta.instance,
      environment: meta.environment,
      requestedBy: meta.requestedBy,
      changeRequest: meta.changeRequest,
      approvals: meta.approvals,
      changeWindow: meta.changeWindow,
      record: {
        number: fields.number,
        short_description: fields.short_description,
        cmdb_ci: fields.cmdb_ci,
        state: fields.state,
        planned_start_date: fields.planned_start_date,
        planned_end_date: fields.planned_end_date,
      },
    },
  };
}

export interface NetSuiteSdfDeployPlan {
  system: "netsuite";
  changeKind: "sdf_deploy";
  account: string;
  environment: "production" | "sandbox";
  requestedBy: string;
  changeRequest: string;
  approvals: number;
  changeWindow: boolean;
  project: {
    projectName: string;
    objects: Array<{ scriptId: string; type: string }>;
  };
}

/** Builds a NetSuiteSdfDeployPlan from a SuiteCloud `project:deploy --json` dry-run result. */
export function buildSdfDeployFromCli(
  invocation: CliInvocation,
  meta: Omit<ChangeMetadata, "org"> & { account: string },
  projectName: string,
  mapping: ComponentMapping = DEFAULT_SDF_MAPPING,
): { ok: true; plan: NetSuiteSdfDeployPlan } | { ok: false; reason: string } {
  const run = runDeployCli(invocation);
  if (!run.ok) return { ok: false, reason: run.reason ?? "CLI run failed" };
  let components: Array<{ type: string; member: string }>;
  try {
    components = extractComponents(run.json, mapping);
  } catch (err) {
    return { ok: false, reason: (err as Error).message };
  }
  if (components.length === 0) {
    return { ok: false, reason: "deploy plan has zero objects — refusing an empty deploy plan" };
  }
  return {
    ok: true,
    plan: {
      system: "netsuite",
      changeKind: "sdf_deploy",
      account: meta.account,
      environment: meta.environment,
      requestedBy: meta.requestedBy,
      changeRequest: meta.changeRequest,
      approvals: meta.approvals,
      changeWindow: meta.changeWindow,
      project: {
        projectName,
        objects: components.map((c) => ({ scriptId: c.member, type: c.type })),
      },
    },
  };
}

// ---------------------------------------------------------------------------
// Jira — real REST API GET (not a CLI; Jira has no official deploy-plan CLI)
// ---------------------------------------------------------------------------

/** One field to read out of a Jira issue's REST API response. */
export interface JiraFieldSpec {
  /** Output key name. */
  name: string;
  /** Path from the response root to the value, e.g. ["fields", "summary"]
   *  or ["fields", "status", "name"] — Jira issue fields are commonly nested
   *  reference objects (`status.name`, `assignee.displayName`), unlike
   *  ServiceNow's flatter (and optionally `{value,display_value}`-wrapped)
   *  Table API rows, so each field carries its own path rather than sharing
   *  one flat field list. */
  path: string[];
}

export interface JiraFieldMapping {
  fields: JiraFieldSpec[];
}

/** `GET /rest/api/3/issue/{issueIdOrKey}` — the stock fields a CAB-tracked
 *  change/incident issue type typically carries. */
export const DEFAULT_JIRA_ISSUE_MAPPING: JiraFieldMapping = {
  fields: [
    { name: "summary", path: ["fields", "summary"] },
    { name: "status", path: ["fields", "status", "name"] },
    { name: "issuetype", path: ["fields", "issuetype", "name"] },
    { name: "duedate", path: ["fields", "duedate"] },
    { name: "assignee", path: ["fields", "assignee", "displayName"] },
  ],
};

/**
 * Extracts `{ key, ...mapped fields }` from a Jira issue REST API response
 * using the given mapping. Pure — no I/O, safe to unit test with fixture
 * JSON. Throws (does not silently drop) if the response has no string `key`
 * at its root, or if any configured field path doesn't resolve to a
 * non-empty string — an issue with an unparseable field is refused, not
 * silently treated as absent.
 */
export function extractJiraFields(json: unknown, mapping: JiraFieldMapping): Record<string, string> {
  if (json === null || typeof json !== "object") {
    throw new Error(`extractJiraFields: expected an object at the response root, got ${typeof json}`);
  }
  const key = (json as Record<string, unknown>).key;
  if (typeof key !== "string" || key.length === 0) {
    throw new Error(`extractJiraFields: missing string field "key" at the response root`);
  }
  const out: Record<string, string> = { key };
  for (const spec of mapping.fields) {
    const v = walkAnyPath(json, spec.path);
    if (typeof v !== "string" || v.length === 0) {
      throw new Error(`extractJiraFields: field "${spec.name}" (path ${spec.path.join(".")}) is missing or not a non-empty string`);
    }
    out[spec.name] = v;
  }
  return out;
}

export interface JiraCredentials {
  /** Site name, e.g. "acmecorp" -> https://acmecorp.atlassian.net */
  site: string;
  /** Atlassian account email — API tokens authenticate as `email:token` Basic Auth. */
  email: string;
  apiToken: string;
}

/**
 * Fetches a Jira issue by key/id from the REST API. Real HTTPS GET via the
 * global `fetch`, Basic Auth (`email:api_token` — Atlassian Cloud's
 * documented API-token auth scheme; no OAuth app required). Never throws — a
 * network failure, non-2xx response, or unparseable body all resolve to
 * `{ ok: false, reason }` so the caller can fall back to a stub rather than
 * throw mid-run.
 */
export async function fetchJiraIssue(
  creds: JiraCredentials,
  issueKey: string,
): Promise<HttpFetchResult> {
  const url = `https://${creds.site}.atlassian.net/rest/api/3/issue/${encodeURIComponent(issueKey)}`;
  const auth = Buffer.from(`${creds.email}:${creds.apiToken}`).toString("base64");
  let res: Response;
  try {
    res = await fetch(url, {
      method: "GET",
      headers: { authorization: `Basic ${auth}`, accept: "application/json" },
    });
  } catch (err) {
    return { ok: false, reason: `Jira REST API request failed: ${(err as Error).message}` };
  }
  if (!res.ok) {
    return { ok: false, reason: `Jira REST API returned HTTP ${res.status}` };
  }
  try {
    return { ok: true, json: await res.json() };
  } catch {
    return { ok: false, reason: "Jira REST API did not return valid JSON" };
  }
}

export interface JiraIssuePlan {
  system: "jira";
  changeKind: "issue";
  site: string;
  environment: "production" | "sandbox";
  requestedBy: string;
  changeRequest: string;
  approvals: number;
  changeWindow: boolean;
  issue: {
    key: string;
    summary: string;
    status: string;
    issuetype: string;
    duedate: string;
    assignee: string;
  };
}

/**
 * Builds a JiraIssuePlan from a real REST API GET of the issue identified by
 * `meta.changeRequest` (the issue key, e.g. "CHG-123"). Returns
 * `{ ok: false, reason }` instead of throwing on any failure (network,
 * non-2xx, unparseable issue) — the caller decides whether to fall back to a
 * stub or fail closed.
 */
export async function buildJiraIssueFromApi(
  creds: JiraCredentials,
  meta: Omit<ChangeMetadata, "org"> & { site: string },
  mapping: JiraFieldMapping = DEFAULT_JIRA_ISSUE_MAPPING,
): Promise<{ ok: true; plan: JiraIssuePlan } | { ok: false; reason: string }> {
  const result = await fetchJiraIssue(creds, meta.changeRequest);
  if (!result.ok) return { ok: false, reason: result.reason ?? "Jira API call failed" };
  let fields: Record<string, string>;
  try {
    fields = extractJiraFields(result.json, mapping);
  } catch (err) {
    return { ok: false, reason: (err as Error).message };
  }
  return {
    ok: true,
    plan: {
      system: "jira",
      changeKind: "issue",
      site: meta.site,
      environment: meta.environment,
      requestedBy: meta.requestedBy,
      changeRequest: meta.changeRequest,
      approvals: meta.approvals,
      changeWindow: meta.changeWindow,
      issue: {
        key: fields.key,
        summary: fields.summary,
        status: fields.status,
        issuetype: fields.issuetype,
        duedate: fields.duedate,
        assignee: fields.assignee,
      },
    },
  };
}

// ---------------------------------------------------------------------------
// AWS (via Terraform) — real `terraform show -json <planfile>` shellout.
//
// AWS has no single official "deploy CLI" the way Salesforce/NetSuite do —
// infrastructure changes against AWS are typically driven by Terraform (or
// CloudFormation). `target_system: "aws"`/`plan_format: "terraform-plan"` are
// both already-documented example values in atlasent's
// CHANGE_PLAN_EXECUTION_CONVENTIONS.md (target_system examples include
// "kubernetes"/"terraform-cloud"; plan_format examples include
// "terraform-plan"), so this reads on the already-ratified vocabulary rather
// than inventing new terms.
//
// CALLER PRECONDITION: this shells out to `terraform show -json <planfile>`
// only — it does NOT run `terraform plan` itself. The caller's own pipeline
// must have already run `terraform plan -out=<planfile>` (the step that
// reads real provider state and needs real AWS credentials) before this
// connector is invoked; `terraform show -json` is a pure, read-only
// re-serialization of an already-produced plan file and needs no AWS
// credentials of its own. This mirrors the sf/suitecloud connectors' "your
// release pipeline already owns auth" boundary exactly.
// ---------------------------------------------------------------------------

export interface TerraformPlanDeployPlan {
  system: "aws";
  changeKind: "terraform_plan";
  account: string;
  environment: "production" | "sandbox";
  requestedBy: string;
  changeRequest: string;
  approvals: number;
  changeWindow: boolean;
  plan: {
    workspace: string;
    resources: Array<{ type: string; member: string }>;
  };
}

/**
 * Builds a TerraformPlanDeployPlan from a `terraform show -json <planfile>`
 * result. Returns `{ ok: false, reason }` instead of throwing on any failure
 * (CLI absent, non-JSON, unparseable resource_changes list, or an empty plan)
 * — the caller decides whether to fall back to a stub or fail closed. Reuses
 * `runDeployCli`/`extractComponents` verbatim — see the module header on why
 * a Terraform resource change and a Salesforce metadata component share one
 * extraction shape.
 */
export function buildTerraformPlanFromCli(
  invocation: CliInvocation,
  meta: Omit<ChangeMetadata, "org"> & { account: string },
  workspace: string,
  mapping: ComponentMapping = DEFAULT_TERRAFORM_MAPPING,
): { ok: true; plan: TerraformPlanDeployPlan } | { ok: false; reason: string } {
  const run = runDeployCli(invocation);
  if (!run.ok) return { ok: false, reason: run.reason ?? "CLI run failed" };
  let resources: Array<{ type: string; member: string }>;
  try {
    resources = extractComponents(run.json, mapping);
  } catch (err) {
    return { ok: false, reason: (err as Error).message };
  }
  if (resources.length === 0) {
    return { ok: false, reason: "terraform plan has zero resource changes — refusing an empty plan" };
  }
  return {
    ok: true,
    plan: {
      system: "aws",
      changeKind: "terraform_plan",
      account: meta.account,
      environment: meta.environment,
      requestedBy: meta.requestedBy,
      changeRequest: meta.changeRequest,
      approvals: meta.approvals,
      changeWindow: meta.changeWindow,
      plan: { workspace, resources },
    },
  };
}
