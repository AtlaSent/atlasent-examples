/**
 * Example: enterprise control surface — health check, org summary, action registry
 *
 * Shows:
 * - checkIntegrationHealth(): probe API reachability and auth
 * - reportProtectedAction(): idempotent registration of action classes
 * - getOrgSummary(): org-level enforcement overview
 */
import {
  checkIntegrationHealth,
  reportProtectedAction,
  getOrgSummary,
  configureControlSurface,
} from "@atlasent/sdk";

configureControlSurface({
  apiKey: process.env["ATLASENT_API_KEY"],
  baseUrl: process.env["ATLASENT_BASE_URL"],
});

console.log("=== Integration Health Check ===");
const health = await checkIntegrationHealth();
console.log(`Healthy: ${health.healthy}`);
console.log(`API reachable: ${health.apiReachable}`);
console.log(`Authenticated: ${health.authenticated}`);
console.log(`Latency: ${health.latencyMs}ms`);
console.log(`API version: ${health.apiVersion ?? "unknown"}`);
if (health.errors.length > 0) {
  console.error(`Errors: ${health.errors.join(", ")}`);
}

if (!health.healthy) {
  console.error("Integration unhealthy — check ATLASENT_API_KEY and network access");
  process.exit(1);
}

console.log("\n=== Registering Protected Actions ===");
const actions = [
  { actionClass: "production.deploy",  enforcementMode: "enforce" as const, tags: ["ci", "devops"] },
  { actionClass: "payment.release",    enforcementMode: "enforce" as const, tags: ["finance"] },
  { actionClass: "data.export",        enforcementMode: "warn"    as const, tags: ["data", "compliance"] },
  { actionClass: "user.offboard",      enforcementMode: "observe" as const, tags: ["iam"] },
];

for (const action of actions) {
  const entry = await reportProtectedAction(action);
  console.log(`  ${entry.actionClass}: ${entry.enforcementMode} (registered ${entry.firstRegisteredAt})`);
}

console.log("\n=== Org Summary ===");
try {
  const summary = await getOrgSummary();
  console.log(`Active policies: ${summary.activePolicies} / ${summary.totalPolicies}`);
  console.log(`Pending escalations: ${summary.pendingEscalations}`);
  console.log(`Active overrides: ${summary.activeOverrides}`);
  console.log(`Enforced actions: ${summary.enforcedActions}`);
  console.log(`Shadow mode actions: ${summary.shadowModeActions}`);
  console.log(`Evidence signing: ${summary.evidenceSigningEnabled ? "enabled" : "disabled"}`);
} catch {
  console.log("(org summary endpoint not available in this environment)");
}
