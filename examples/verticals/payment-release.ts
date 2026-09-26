/**
 * Example: Payment Release vertical — QBO-style payment gate
 *
 * Demonstrates:
 * - Auto-approval for payments under $10,000
 * - HITL escalation for payments $10,000–$100,000 (single approver)
 * - Dual-approval quorum for payments over $100,000
 * - ISO 4217 currency validation
 */
import { protectPaymentRelease, configure } from "@atlasent/sdk";
import { EscalationDeniedError } from "@atlasent/sdk";

// The SDK's built-in default base URL is the bare host; the AtlaSent API is
// served under /functions/v1, so set it explicitly.
configure({ baseUrl: process.env.ATLASENT_API_URL ?? "https://api.atlasent.io/functions/v1" });

const payments = [
  { amount: 500,     currency: "USD", vendorId: "vendor_office_supplies", description: "Office supplies" },
  { amount: 25_000,  currency: "USD", vendorId: "vendor_saas_tool",      description: "Annual SaaS license" },
  { amount: 150_000, currency: "USD", vendorId: "vendor_contractor",     description: "Q1 contractor invoice" },
];

for (const payment of payments) {
  console.log(`\nProcessing: ${payment.currency} ${payment.amount.toLocaleString()} → ${payment.vendorId}`);
  try {
    const permit = await protectPaymentRelease({
      ...payment,
      authorizedBy: "u_controller_99",
      autoEscalateAbove: 10_000,
      requireDualApprovalAbove: 100_000,
      assignedToRole: "finance-approver",
      waitMs: 4 * 60 * 60 * 1000,
      onEscalationCreated: (handle) => {
        console.log(`  Escalated: ${handle.escalationId} (assigned to finance-approver)`);
      },
    });
    const basis = "approvalBasis" in permit ? permit.approvalBasis : "direct_policy";
    console.log(`  AUTHORIZED — ${basis}`);
  } catch (err) {
    if (err instanceof EscalationDeniedError) {
      console.error(`  REJECTED by ${err.outcome.resolvedBy ?? "approver"}: ${err.outcome.resolutionNote ?? ""}`);
    } else {
      throw err;
    }
  }
}
