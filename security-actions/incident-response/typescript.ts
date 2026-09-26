/**
 * security-actions/incident-response — TypeScript API shape example
 *
 * Shows the generic protect() call for security.incident.escalate with
 * incidentId and severity in context. Concise reference for the API
 * surface.
 *
 * Full runnable scenario: see main.ts
 * Docs: governance-kits/security-incident-response-kit.md
 */

import atlasent, { AtlaSentDeniedError } from "@atlasent/sdk";

// The SDK's built-in default base URL is the bare host; the AtlaSent API is
// served under /functions/v1, so set it explicitly.
atlasent.configure({ baseUrl: process.env.ATLASENT_API_URL ?? "https://api.atlasent.io/functions/v1" });

async function escalateIncident() {
  const incidentId = "INC-2026-CRIT-042";
  const severity = "critical";
  try {
    const permit = await atlasent.protect({
      agent: "soc:lead-alice",
      action: "security.incident.escalate",
      context: {
        environment: "production",
        incidentId,
        severity,
        authorizedBy: "soc:lead-alice",
      },
    });

    // Permit verified — proceed with incident escalation workflow
    console.log(`Incident escalation permit: ${permit.permitId}`);
    console.log(`Audit hash: ${permit.auditHash}`);
    await notifyPagerDuty(incidentId, severity);
    await incidentTracker.escalate(incidentId, permit);
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      console.error(`Escalation BLOCKED: ${err.reason}`);
      // evaluationId links to the denial record in the audit chain
      console.error(`Evaluation ID: ${err.evaluationId}`);
    } else {
      throw err;
    }
  }
}

// Stub references — replace with real implementations
declare function notifyPagerDuty(incidentId: string, severity: string): Promise<void>;
declare const incidentTracker: { escalate(id: string, permit: unknown): Promise<void> };
