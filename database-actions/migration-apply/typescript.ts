/**
 * database-actions/migration-apply — TypeScript API shape example
 *
 * Shows protectDatabaseMigration for production with rollbackPlan,
 * onPermitEvidence, and onDenialEvidence callbacks showing evidence recording.
 * Concise reference for the API surface.
 *
 * Docs: governance-kits/database-operations-kit.md
 */

import { protectDatabaseMigration, AtlaSentDeniedError, configure } from "@atlasent/sdk";

// The SDK's built-in default base URL is the bare host; the AtlaSent API is
// served under /functions/v1, so set it explicitly.
configure({ baseUrl: process.env.ATLASENT_API_URL ?? "https://api.atlasent.io/functions/v1" });

async function applyProductionMigration(
  migrationId: string,
  checksum: string,
) {
  try {
    const permit = await protectDatabaseMigration({
      migrationId,
      checksum,
      environment: "production",
      rollbackPlan: `rollback/${migrationId}.sql`,
      onPermitEvidence: async (evidence) => {
        // Write permit evidence before executing migration — append-only audit row
        await auditStore.append({
          action: "database.migration.apply",
          migrationId: evidence.migrationId,
          permitId: evidence.permitId,
          auditHash: evidence.auditHash,
          approvedBy: evidence.approvedBy,
          environment: evidence.environment,
          timestamp: evidence.issuedAt,
        });
      },
      onDenialEvidence: async (evidence) => {
        // Write denial evidence — migration blocked, record why
        await auditStore.append({
          action: "database.migration.apply",
          migrationId: evidence.migrationId,
          decision: "deny",
          reason: evidence.reason,
          evaluationId: evidence.evaluationId,
          timestamp: new Date().toISOString(),
        });
      },
    });

    // Permit verified — proceed with migration
    console.log(`Migration permit: ${permit.permitId}`);
    await migrationRunner.apply(migrationId, permit);
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      console.error(`Migration BLOCKED: ${err.reason}`);
      // evaluationId links to the denial record in the audit chain
      console.error(`Evaluation ID: ${err.evaluationId}`);
    } else {
      throw err;
    }
  }
}

// Usage
applyProductionMigration(
  "20260529_add_user_preferences_index",
  "sha256:a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
);

// Stub references — replace with real implementations
declare const auditStore: { append(record: Record<string, unknown>): Promise<void> };
declare const migrationRunner: { apply(migrationId: string, permit: unknown): Promise<void> };
