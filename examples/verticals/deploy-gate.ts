/**
 * Example: Deploy Gate vertical — GitHub Actions context
 *
 * Drop this script into your GitHub Actions workflow as the authorization step.
 * It reads CI environment variables automatically (GITHUB_SHA, GITHUB_ACTOR, etc.)
 * and routes production deploys through HITL approval.
 *
 * Usage in .github/workflows/deploy.yml:
 *   - run: npx tsx examples/verticals/deploy-gate.ts
 *     env:
 *       ATLASENT_API_KEY: ${{ secrets.ATLASENT_API_KEY }}
 */
import { protectDeploy, configure } from "@atlasent/sdk";
import { EscalationDeniedError, EscalationTimeoutError } from "@atlasent/sdk";

// The SDK's built-in default base URL is the bare host; the AtlaSent API is
// served under /functions/v1, so set it explicitly.
configure({ baseUrl: process.env.ATLASENT_API_URL ?? "https://api.atlasent.io/functions/v1" });

try {
  const permit = await protectDeploy({
    service: process.env["SERVICE_NAME"] ?? "my-service",
    environment: "production",
    description: `Release ${process.env["GITHUB_SHA"]?.slice(0, 8)} via ${process.env["GITHUB_WORKFLOW"]}`,
    assignedToRole: "release-manager",
    waitMs: 30 * 60 * 1000,
    onEscalationCreated: (handle) => {
      console.log(`::notice title=AtlaSent::Escalation ${handle.escalationId} created — awaiting release manager approval`);
    },
  });
  console.log(`::notice title=AtlaSent::Deploy authorized — permit ${permit.permitId}`);
} catch (err) {
  if (err instanceof EscalationDeniedError) {
    console.error(`::error title=AtlaSent::Deploy rejected by ${err.outcome.resolvedBy ?? "reviewer"}`);
    process.exit(1);
  }
  if (err instanceof EscalationTimeoutError) {
    console.error("::error title=AtlaSent::Deploy approval timed out");
    process.exit(1);
  }
  throw err;
}
