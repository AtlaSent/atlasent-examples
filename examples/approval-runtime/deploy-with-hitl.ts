/**
 * Example: production deploy with HITL approval and override fallback
 *
 * Shows the full protectOrEscalate() flow:
 * 1. Attempt protect() for production.deploy
 * 2. On hold/escalate decision, route to HITL queue
 * 3. Poll for human approval with exponential backoff
 * 4. Handle approval, rejection, and timeout branches
 * 5. Request an override if rejected (out-of-band emergency path)
 */
import {
  protectOrEscalate,
  EscalationDeniedError,
  EscalationTimeoutError,
  requestOverride,
  type EscalationHandle,
  configure,
  configureApprovalRuntime,
} from "@atlasent/sdk";

// The SDK's built-in default base URL is the bare host; the AtlaSent API is
// served under /functions/v1, so set it explicitly.
configure({ baseUrl: process.env.ATLASENT_API_URL ?? "https://api.atlasent.io/functions/v1" });
configureApprovalRuntime({ baseUrl: process.env.ATLASENT_API_URL ?? "https://api.atlasent.io/functions/v1" });

async function deployToProduction(serviceName: string, sha: string) {
  console.log(`Requesting authorization to deploy ${serviceName}@${sha.slice(0, 8)}...`);

  let escalationHandle: EscalationHandle | null = null;

  try {
    const permit = await protectOrEscalate(
      {
        action: "production.deploy",
        resourceId: serviceName,
        agentId: process.env["GITHUB_ACTOR"] ?? "ci-system",
        context: {
          environment: "production",
          sha,
          service: serviceName,
        },
      },
      {
        escalationReason: `Production deploy of ${serviceName} requires release manager approval`,
        assignedToRole: "release-manager",
        waitMs: 30 * 60 * 1000,
        pollIntervalMs: 15_000,
        onEscalationCreated: (handle) => {
          escalationHandle = handle;
          console.log(`Escalation created: ${handle.escalationId}`);
          console.log(`Waiting for approval (timeout: ${handle.timeoutAt ?? "none"})...`);
        },
      },
    );

    console.log(`AUTHORIZED — permit ${permit.permitId}, basis: ${permit.approvalBasis}`);
    if (permit.resolvedBy) {
      console.log(`Approved by: ${permit.resolvedBy}`);
      if (permit.resolutionNote) console.log(`Note: ${permit.resolutionNote}`);
    }
    return permit;
  } catch (err) {
    if (err instanceof EscalationDeniedError) {
      console.error(`REJECTED by ${err.outcome.resolvedBy ?? "reviewer"}`);
      if (err.outcome.resolutionNote) {
        console.error(`Reason: ${err.outcome.resolutionNote}`);
      }

      // In a P0 emergency, request an override (requires a senior approver to grant it out-of-band)
      if (process.env["EMERGENCY_OVERRIDE"] === "true" && escalationHandle) {
        console.warn("Emergency override path requested — submitting override request...");
        const override = await requestOverride({
          reason: `P0 emergency deploy of ${serviceName} — business-critical fix`,
          evaluationId: err.outcome.escalation.evaluation_id ?? "",
          ttlSeconds: 3600,
        });
        console.warn(`Override ${override.id} pending. Have a senior approver grant it.`);
      }
      process.exit(1);
    }

    if (err instanceof EscalationTimeoutError) {
      console.error(`TIMED OUT waiting for approval after ${30}m`);
      process.exit(1);
    }

    throw err;
  }
}

await deployToProduction("payments-api", process.env["GITHUB_SHA"] ?? "abc123");
