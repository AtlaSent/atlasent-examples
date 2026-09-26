/**
 * Example: shadow mode — observe → warn → enforce migration ladder
 *
 * Demonstrates:
 * - protectShadow() in 'observe' mode: never blocks, records would-have-blocked
 * - Simulating 50 evaluations to build up shadow event history
 * - Auto-advancing to 'warn' mode when block rate drops below threshold
 * - Switching to full protect() in 'enforce' mode
 */
import {
  protectShadow,
  configureShadow,
  type ShadowOutcome,
  configure,
} from "@atlasent/sdk";
import { InMemoryShadowEventStore, MigrationTracker } from "@atlasent/shadow-mode";

// The SDK's built-in default base URL is the bare host; the AtlaSent API is
// served under /functions/v1, so set it explicitly.
configure({ baseUrl: process.env.ATLASENT_API_URL ?? "https://api.atlasent.io/functions/v1" });

const store = new InMemoryShadowEventStore();
const tracker = new MigrationTracker({ autoAdvanceThreshold: 0.1 });

tracker.register("production.deploy", { stage: "observe" });

configureShadow({
  baseUrl: process.env.ATLASENT_API_URL ?? "https://api.atlasent.io/functions/v1",
  mode: "observe",
  onOutcome: async (outcome: ShadowOutcome) => {
    await store.record({
      action: outcome.request.action,
      resourceId: outcome.request.resourceId,
      agentId: outcome.request.agentId ?? null,
      decision: outcome.decision,
      would_have_blocked: outcome.would_have_blocked,
      latencyMs: outcome.latencyMs,
      evaluationId: outcome.evaluationId,
      mode: outcome.mode,
      deniedReason: outcome.error?.message ?? null,
      timestamp: new Date().toISOString(),
      metadata: null,
    });
  },
});

console.log("Simulating 50 shadow evaluations in observe mode...");
for (let i = 0; i < 50; i++) {
  await protectShadow({
    action: "production.deploy",
    resourceId: "svc-api",
    agentId: `agent_${i % 3}`,
    context: { environment: "production" },
  });
}

const all = await store.listAll();
const blocked = await store.listBlocked();
console.log(`\nRecorded ${all.length} events, ${blocked.length} would have been blocked`);
console.log(`Block rate: ${((blocked.length / all.length) * 100).toFixed(1)}%`);

const promoted = await tracker.evaluateAutoAdvance(store);
if (promoted.length > 0) {
  console.log(`\nAuto-advanced to '${promoted[0]!.stage}' mode for: ${promoted.map((e) => e.actionClass).join(", ")}`);
} else {
  console.log("\nBlock rate above threshold — staying in observe mode");
}

console.log("\nCurrent migration state:");
const snapshot = tracker.snapshot();
for (const [cls, entry] of snapshot.entries) {
  console.log(`  ${cls}: ${entry.stage} (threshold: ${entry.autoAdvanceThreshold})`);
}
