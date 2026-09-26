// Demonstrates: pulling usage metering data from AtlaSent.
//
// Flow:
//   1. GET /v1-usage-metering/summary?period=month  -> high-level counters
//   2. GET /v1-usage-metering?limit=10              -> detailed evaluation list
//
// Usage metering tracks every governed action evaluation. Billable events are
// "allow" decisions (a permit was issued) and, depending on plan, "deny"
// decisions. The summary endpoint also shows % of the license limit consumed.
//
// Requires: ATLASENT_API_KEY, ATLASENT_BASE_URL, ATLASENT_ORG_ID env vars.

const apiKey = process.env["ATLASENT_API_KEY"];
const baseUrl = process.env["ATLASENT_BASE_URL"] ?? "https://api.atlasent.io/functions/v1";
const orgId = process.env["ATLASENT_ORG_ID"];

if (!apiKey || !orgId) {
  console.error("ATLASENT_API_KEY and ATLASENT_ORG_ID are required.");
  process.exit(1);
}

const headers = {
  Authorization: `Bearer ${apiKey}`,
  "Content-Type": "application/json",
};

// ── Types ─────────────────────────────────────────────────────────────────────

interface UsageSummary {
  org_id: string;
  period: "day" | "week" | "month" | "custom";
  period_start: string; // ISO-8601
  period_end: string;   // ISO-8601
  total_evaluations: number;
  billable_allows: number;
  billable_denies: number;
  holds: number;
  escalations: number;
  limit: number | null;       // null = unlimited (enterprise custom)
  limit_pct_used: number | null; // null when limit is null
  overage: boolean;
}

interface UsageRecord {
  evaluation_id: string;
  actor_id: string;
  action_type: string;
  decision: "allow" | "deny" | "hold" | "escalate";
  billable: boolean;
  evaluated_at: string; // ISO-8601
  latency_ms: number;
  request_id: string;
}

interface UsageListResponse {
  records: UsageRecord[];
  total: number;
  next_cursor?: string;
}

// ── API helpers ───────────────────────────────────────────────────────────────

async function getUsageSummary(
  period: "day" | "week" | "month" = "month",
): Promise<UsageSummary> {
  const url = new URL(`${baseUrl}/v1-usage-metering/summary`);
  url.searchParams.set("org_id", orgId!);
  url.searchParams.set("period", period);

  const res = await fetch(url.toString(), {
    headers,
    signal: AbortSignal.timeout(10_000),
  });
  if (!res.ok) {
    throw new Error(
      `/v1-usage-metering/summary returned ${res.status}: ${await res.text()}`,
    );
  }
  return res.json() as Promise<UsageSummary>;
}

async function getUsageList(opts: {
  limit?: number;
  decision?: "allow" | "deny" | "hold" | "escalate";
  cursor?: string;
}): Promise<UsageListResponse> {
  const url = new URL(`${baseUrl}/v1-usage-metering`);
  url.searchParams.set("org_id", orgId!);
  if (opts.limit != null) url.searchParams.set("limit", String(opts.limit));
  if (opts.decision) url.searchParams.set("decision", opts.decision);
  if (opts.cursor) url.searchParams.set("cursor", opts.cursor);

  const res = await fetch(url.toString(), {
    headers,
    signal: AbortSignal.timeout(10_000),
  });
  if (!res.ok) {
    throw new Error(
      `/v1-usage-metering returned ${res.status}: ${await res.text()}`,
    );
  }
  return res.json() as Promise<UsageListResponse>;
}

// ── Formatting helpers ────────────────────────────────────────────────────────

function formatPct(pct: number | null): string {
  if (pct == null) return "unlimited";
  return `${pct.toFixed(1)}%`;
}

function formatLimit(limit: number | null): string {
  if (limit == null) return "unlimited";
  return limit.toLocaleString();
}

function bar(pct: number | null, width = 30): string {
  if (pct == null) return "─".repeat(width) + " (unlimited)";
  const filled = Math.round((Math.min(pct, 100) / 100) * width);
  const empty = width - filled;
  const indicator = pct >= 90 ? "!" : pct >= 75 ? "~" : "=";
  return `[${"=".repeat(filled - (filled > 0 ? 1 : 0))}${filled > 0 ? indicator : ""}${" ".repeat(empty)}] ${formatPct(pct)}`;
}

// ── Main ──────────────────────────────────────────────────────────────────────

async function main() {
  // ── Step 1: monthly summary ───────────────────────────────────────────────
  console.log("Fetching monthly usage summary...\n");
  const summary = await getUsageSummary("month");

  const periodStart = new Date(summary.period_start).toLocaleDateString();
  const periodEnd = new Date(summary.period_end).toLocaleDateString();

  console.log(`  Org:            ${summary.org_id}`);
  console.log(`  Period:         ${periodStart} → ${periodEnd}`);
  console.log(`  ─────────────────────────────────────────────`);
  console.log(
    `  Total evals:    ${summary.total_evaluations.toLocaleString()}`,
  );
  console.log(
    `  Billable allows:${summary.billable_allows.toLocaleString()}`,
  );
  console.log(
    `  Billable denies:${summary.billable_denies.toLocaleString()}`,
  );
  console.log(`  Holds:          ${summary.holds.toLocaleString()}`);
  console.log(`  Escalations:    ${summary.escalations.toLocaleString()}`);
  console.log(`  ─────────────────────────────────────────────`);
  console.log(`  License limit:  ${formatLimit(summary.limit)}`);
  console.log(`  Usage:          ${bar(summary.limit_pct_used)}`);

  if (summary.overage) {
    console.warn(
      "\n  WARNING: Org is over its license limit. Contact sales@atlasent.io.",
    );
  } else if (
    summary.limit_pct_used != null &&
    summary.limit_pct_used >= 80
  ) {
    console.warn(
      `\n  NOTICE: ${formatPct(summary.limit_pct_used)} of monthly limit consumed — consider upgrading.`,
    );
  }

  // ── Step 2: detailed list (most recent 10 billable allows) ────────────────
  console.log("\nFetching recent billable allow evaluations...\n");
  const list = await getUsageList({ limit: 10, decision: "allow" });

  if (list.records.length === 0) {
    console.log("  No allow evaluations found in this period.");
  } else {
    console.log(
      `  Showing ${list.records.length} of ${list.total.toLocaleString()} allow evaluations\n`,
    );
    console.log(
      `  ${"evaluation_id".padEnd(36)}  ${"actor_id".padEnd(30)}  ${"action_type".padEnd(36)}  latency`,
    );
    console.log(`  ${"─".repeat(36)}  ${"─".repeat(30)}  ${"─".repeat(36)}  ───────`);

    for (const rec of list.records) {
      console.log(
        `  ${rec.evaluation_id.padEnd(36)}  ${rec.actor_id.padEnd(30)}  ${rec.action_type.padEnd(36)}  ${rec.latency_ms}ms`,
      );
    }

    if (list.next_cursor) {
      console.log(
        `\n  More records available. Pass cursor="${list.next_cursor}" to fetch the next page.`,
      );
    }
  }

  // ── Step 3: show deny count and % ────────────────────────────────────────
  console.log("\nFetching deny count...\n");
  const denyList = await getUsageList({ limit: 1, decision: "deny" });
  const totalDenies = denyList.total;
  const totalEvals = summary.total_evaluations;
  const denyRate =
    totalEvals > 0 ? ((totalDenies / totalEvals) * 100).toFixed(1) : "0.0";

  console.log(
    `  Total denies this month: ${totalDenies.toLocaleString()} (${denyRate}% of evaluations)`,
  );
  if (Number(denyRate) > 20) {
    console.warn(
      "  High deny rate may indicate a policy misconfiguration or an ongoing probe.",
    );
  }
}

main().catch((err) => {
  console.error("Error:", err instanceof Error ? err.message : String(err));
  process.exit(1);
});
