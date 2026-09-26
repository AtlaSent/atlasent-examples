/**
 * financial-close/period-certify — TypeScript API shape example
 *
 * Shows the generic protect() call for period.close.certify with periodId,
 * certifiedBy, and financialController in context. Concise reference for
 * the API surface.
 *
 * Full runnable scenario: see main.ts
 * Docs: governance-kits/financial-close-kit.md / close-governance-kit.md
 */

import atlasent, { AtlaSentDeniedError } from "@atlasent/sdk";

// The SDK's built-in default base URL is the bare host; the AtlaSent API is
// served under /functions/v1, so set it explicitly.
atlasent.configure({ baseUrl: process.env.ATLASENT_API_URL ?? "https://api.atlasent.io/functions/v1" });

async function certifyPeriodClose(
  periodId: string,
  certifiedBy: string,
  financialController: string,
) {
  try {
    const permit = await atlasent.protect({
      agent: certifiedBy,
      action: "period.close.certify",
      context: {
        periodId,
        certifiedBy,
        financialController,
      },
    });

    // Permit verified — proceed with period close certification
    console.log(`Period close permit: ${permit.permitId}`);
    await erp.closePeriod(periodId, permit);
    await evidenceStore.seal(periodId, permit);
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      console.error(`Period close BLOCKED: ${err.reason}`);
      // evaluationId links to the denial record in the audit chain
      console.error(`Evaluation ID: ${err.evaluationId}`);
    } else {
      throw err;
    }
  }
}

// Usage
certifyPeriodClose("2026-Q1", "controller:jane", "fc:bob");

// Stub references — replace with real implementations
declare const erp: { closePeriod(periodId: string, permit: unknown): Promise<void> };
declare const evidenceStore: { seal(periodId: string, permit: unknown): Promise<void> };
