// Demonstrates: configuring SIEM export to Splunk HEC, verifying connectivity,
// fetching the saved config, and managing the Dead Letter Queue (DLQ).
//
// Flow:
//   upsertSiemConfig (splunk_hec, bearer auth)
//   -> testSiemDelivery
//   -> getSiemConfig
//   -> listDlqEntries  (batches that failed all retries)
//   -> replayDlqEntry  (retry a failed batch)
//   -> dismissDlqEntry (discard a stale entry)
//
// Requires: ATLASENT_API_KEY, ATLASENT_BASE_URL, ATLASENT_ORG_ID,
//           SPLUNK_HEC_URL, SPLUNK_HEC_TOKEN env vars.
//
// Note: SIEM export requires an enterprise plan. The API returns HTTP 402
// when the plan gate blocks access.

import {
  AtlaSentClient,
  type SiemConfigInput,
  type SiemDlqEntry,
} from "@atlasent/sdk";

const apiKey = process.env["ATLASENT_API_KEY"];
const baseUrl = process.env["ATLASENT_BASE_URL"];
const orgId = process.env["ATLASENT_ORG_ID"];
const splunkHecUrl = process.env["SPLUNK_HEC_URL"];
const splunkHecToken = process.env["SPLUNK_HEC_TOKEN"];

if (!apiKey || !baseUrl || !orgId || !splunkHecUrl || !splunkHecToken) {
  console.error(
    "ATLASENT_API_KEY, ATLASENT_BASE_URL, ATLASENT_ORG_ID, SPLUNK_HEC_URL, " +
      "and SPLUNK_HEC_TOKEN are all required.",
  );
  process.exit(1);
}

const client = new AtlaSentClient({ apiKey, baseUrl });

async function main() {
  // ── Step 1: configure SIEM export to Splunk HEC ──────────────────────────
  const siemInput: SiemConfigInput = {
    destinationUrl: splunkHecUrl,
    format: "splunk_hec",
    authType: "bearer",
    credential: splunkHecToken,
    enabled: true,
    includedEventTypes: ["permit", "deny", "override", "governance"],
    batchSize: 100,
    retryCount: 3,
  };

  console.log("Configuring SIEM export...");
  console.log("  destination:", splunkHecUrl);
  console.log("  format:     splunk_hec");
  console.log("  auth_type:  bearer");

  const savedConfig = await client.upsertSiemConfig(orgId, siemInput);
  console.log("  Saved config updated_at:", savedConfig.updatedAt);
  console.log("  enabled:", savedConfig.enabled);

  // ── Step 2: verify connectivity with a test delivery ─────────────────────
  console.log("Testing SIEM delivery...");
  const testResult = await client.testSiemDelivery(orgId);

  if (testResult.success) {
    const latency =
      testResult.latencyMs != null ? `${testResult.latencyMs}ms` : "n/a";
    console.log("  Delivery succeeded. Latency:", latency);
  } else {
    // Connectivity failure is not a fatal error for this example — print it
    // and continue to show the saved config fetch below.
    console.warn("  Delivery test failed:", testResult.error ?? "unknown error");
  }

  // ── Step 3: fetch the saved config ───────────────────────────────────────
  // The credential field is never returned by the server (write-only).
  console.log("Fetching saved SIEM config...");
  const fetchedConfig = await client.getSiemConfig(orgId);
  console.log("  org_id:          ", fetchedConfig.orgId);
  console.log("  destination_url: ", fetchedConfig.destinationUrl);
  console.log("  format:          ", fetchedConfig.format);
  console.log("  auth_type:       ", fetchedConfig.authType);
  console.log("  event_types:     ", fetchedConfig.includedEventTypes.join(", "));
  console.log("  batch_size:      ", fetchedConfig.batchSize);
  console.log("  retry_count:     ", fetchedConfig.retryCount);

  // ── Step 4: inspect the Dead Letter Queue ─────────────────────────────────
  //
  // Batches that exhaust all retries land in the DLQ. The DLQ lets you replay
  // failed deliveries once the underlying issue (e.g. expired token, network
  // outage) is resolved, or dismiss entries that are no longer relevant.
  //
  // Entries are retained in the DLQ for 30 days, then automatically purged.
  console.log("Listing DLQ entries (failed batches)...");
  const dlqPage = await client.listSiemDlqEntries(orgId, { limit: 5 });

  if (dlqPage.entries.length === 0) {
    console.log("  No DLQ entries — all batches delivered successfully.");
  } else {
    console.log(`  ${dlqPage.entries.length} of ${dlqPage.total} entry/entries:`);
    for (const entry of dlqPage.entries) {
      console.log(
        `    [${entry.dlq_entry_id}]  ${entry.failed_at}  events: ${entry.event_count}  error: ${entry.last_error ?? "unknown"}`,
      );
    }

    // ── Step 5: replay the oldest failed batch ─────────────────────────────
    // In a real ops runbook you would replay after fixing the delivery issue
    // (e.g. rotating the Splunk HEC token and updating the SIEM config).
    const oldest: SiemDlqEntry = dlqPage.entries[dlqPage.entries.length - 1]!;
    console.log(`\nReplaying DLQ entry ${oldest.dlq_entry_id}...`);
    const replayResult = await client.replaySiemDlqEntry(orgId, oldest.dlq_entry_id);

    if (replayResult.success) {
      console.log(
        `  Replayed successfully. Latency: ${replayResult.latencyMs ?? "n/a"}ms`,
      );
    } else {
      // Still failing — leave in the DLQ or dismiss if the events are stale.
      console.warn(
        `  Replay failed: ${replayResult.error ?? "unknown error"}`,
      );

      // ── Step 6: dismiss a stale entry ─────────────────────────────────────
      // Dismiss entries whose events are outside your retention window or that
      // can be sourced from the AtlaSent audit chain export instead.
      console.log(`  Dismissing stale entry ${oldest.dlq_entry_id}...`);
      await client.dismissSiemDlqEntry(orgId, oldest.dlq_entry_id);
      console.log("  Entry dismissed.");
    }
  }
}

main().catch((err) => {
  console.error("Error:", err instanceof Error ? err.message : String(err));
  process.exit(1);
});
