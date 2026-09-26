/**
 * database-actions/schema-drop — TypeScript API shape example
 *
 * Shows protectDatabaseSchemaDrop (critical, destructive) with
 * backupVerified: true and recoveryPointId. Concise reference for the
 * API surface.
 *
 * Docs: governance-kits/database-operations-kit.md
 */

import { protectDatabaseSchemaDrop, AtlaSentDeniedError, configure } from "@atlasent/sdk";

// The SDK's built-in default base URL is the bare host; the AtlaSent API is
// served under /functions/v1, so set it explicitly.
configure({ baseUrl: process.env.ATLASENT_API_URL ?? "https://api.atlasent.io/functions/v1" });

async function dropProductionSchema(
  targetSchema: string,
  recoveryPointId: string,
) {
  try {
    const permit = await protectDatabaseSchemaDrop({
      targetSchema,
      backupVerified: true,
      recoveryPointId,
      environment: "production",
      onPermitEvidence: async (evidence) => {
        // Write permit evidence before executing schema drop — append-only audit row
        await auditStore.append({
          action: "database.schema.drop",
          targetSchema: evidence.targetSchema,
          permitId: evidence.permitId,
          auditHash: evidence.auditHash,
          approvers: evidence.approvers,
          backupVerified: evidence.backupVerified,
          recoveryPointId: evidence.recoveryPointId,
          timestamp: evidence.issuedAt,
        });
      },
      onDenialEvidence: async (evidence) => {
        // Write denial evidence — schema NOT dropped, record why
        await auditStore.append({
          action: "database.schema.drop",
          targetSchema: evidence.targetSchema,
          decision: "deny",
          reason: evidence.reason,
          evaluationId: evidence.evaluationId,
          timestamp: new Date().toISOString(),
        });
      },
    });

    // Permit verified — proceed with schema drop (irreversible)
    console.log(`Schema drop permit: ${permit.permitId}`);
    await dbaTools.dropSchema(targetSchema, permit);
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      console.error(`Schema drop BLOCKED: ${err.reason}`);
      // evaluationId links to the denial record in the audit chain
      console.error(`Evaluation ID: ${err.evaluationId}`);
    } else {
      throw err;
    }
  }
}

// Usage
dropProductionSchema("legacy_billing_v1", "rp-2026-05-29-0300");

// Stub references — replace with real implementations
declare const auditStore: { append(record: Record<string, unknown>): Promise<void> };
declare const dbaTools: { dropSchema(schema: string, permit: unknown): Promise<void> };
