/**
 * Example: Close Governance vertical — accounting period close
 *
 * Demonstrates:
 * - Dual-approval quorum for period.close (CFO + Controller)
 * - Single approval for data.export
 * - period.reopen treated as critical (requires same quorum)
 */
import { protectCloseAction, configure } from "@atlasent/sdk";
import { EscalationDeniedError, EscalationTimeoutError } from "@atlasent/sdk";

// The SDK's built-in default base URL is the bare host; the AtlaSent API is
// served under /functions/v1, so set it explicitly.
configure({ baseUrl: process.env.ATLASENT_API_URL ?? "https://api.atlasent.io/functions/v1" });

async function runCloseProcess(periodLabel: string, entityId: string) {
  console.log(`\n=== Close Process: ${periodLabel} for entity ${entityId} ===`);

  // Step 1: Lock reconciliations (single approval)
  console.log("\n[1/3] Locking reconciliations...");
  try {
    const lock = await protectCloseAction({
      action: "reconciliation.lock",
      periodLabel,
      closedBy: "u_controller_1",
      entityId,
      assignedToRole: "controller",
      waitMs: 60 * 60 * 1000,
    });
    console.log(`  Locked — permit ${lock.permitId}`);
  } catch (err) {
    handleCloseError(err, "reconciliation.lock");
    return;
  }

  // Step 2: Close the period (dual approval: controller + CFO)
  console.log("\n[2/3] Closing period (requires dual approval)...");
  try {
    const close = await protectCloseAction({
      action: "period.close",
      periodLabel,
      closedBy: "u_controller_1",
      entityId,
      requireDualApproval: true,
      assignedToRole: "cfo",
      waitMs: 24 * 60 * 60 * 1000,
      onEscalationCreated: (h) => console.log(`  Waiting for CFO approval: ${h.escalationId}`),
    });
    console.log(`  Period closed — basis: ${close.approvalBasis}`);
  } catch (err) {
    handleCloseError(err, "period.close");
    return;
  }

  // Step 3: Export trial balance (single approval, confidential data)
  console.log("\n[3/3] Exporting trial balance...");
  try {
    const exp = await protectCloseAction({
      action: "data.export",
      periodLabel,
      closedBy: "u_controller_1",
      entityId,
      dataClassification: "confidential",
      assignedToRole: "controller",
      waitMs: 2 * 60 * 60 * 1000,
    });
    console.log(`  Export authorized — permit ${exp.permitId}`);
  } catch (err) {
    handleCloseError(err, "data.export");
  }
}

function handleCloseError(err: unknown, action: string) {
  if (err instanceof EscalationDeniedError) {
    console.error(`  ${action} REJECTED: ${err.outcome.resolutionNote ?? "no reason given"}`);
  } else if (err instanceof EscalationTimeoutError) {
    console.error(`  ${action} TIMED OUT — close process halted`);
  } else {
    throw err;
  }
}

await runCloseProcess("April 2024", "entity_acme_us");
