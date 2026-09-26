/**
 * access-certification/cert-revoke — TypeScript API shape example
 *
 * Shows the generic protect() call for access.cert.revoke with certId and
 * revocationReason in context. Concise reference for the API surface.
 *
 * Full runnable scenario: see main.ts
 * Docs: governance-kits/access-certification-kit.md
 */

import atlasent, { AtlaSentDeniedError } from "@atlasent/sdk";

// The SDK's built-in default base URL is the bare host; the AtlaSent API is
// served under /functions/v1, so set it explicitly.
atlasent.configure({ baseUrl: process.env.ATLASENT_API_URL ?? "https://api.atlasent.io/functions/v1" });

async function revokeCert(certId: string, revocationReason: string) {
  try {
    const permit = await atlasent.protect({
      agent: "iam:security-admin",
      action: "access.cert.revoke",
      context: {
        certId,
        revocationReason,
        authorizedBy: "iam:security-admin",
      },
    });

    // Permit verified — proceed with certificate revocation
    console.log(`Access cert revocation permit: ${permit.permitId}`);
    await pkiStore.revoke(certId, permit);
    await crlManager.update(certId);
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      console.error(`Cert revocation BLOCKED: ${err.reason}`);
      // evaluationId links to the denial record in the audit chain
      console.error(`Evaluation ID: ${err.evaluationId}`);
    } else {
      throw err;
    }
  }
}

// Usage
revokeCert(
  "cert:2026-Q2-ENG-42",
  "access no longer required — engineer offboarded 2026-05-28",
);

// Stub references — replace with real implementations
declare const pkiStore: { revoke(certId: string, permit: unknown): Promise<void> };
declare const crlManager: { update(certId: string): Promise<void> };
