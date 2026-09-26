/**
 * Example: build, validate, and redact a payment action context
 *
 * Demonstrates:
 * - buildActionContext() with nested sub-schemas and flat shorthands
 * - validateActionContext() with cross-field checks (amount→currency)
 * - redactContext() using DEFAULT_REDACTION_RULES (strips api_key, masks email/ip)
 * - flattenActionContext() for use with protect()
 */
import {
  buildActionContext,
  validateActionContext,
  redactContext,
  flattenActionContext,
  DEFAULT_REDACTION_RULES,
  protect,
  configure,
} from "@atlasent/sdk";

// The SDK's built-in default base URL is the bare host; the AtlaSent API is
// served under /functions/v1, so set it explicitly.
configure({ baseUrl: process.env.ATLASENT_API_URL ?? "https://api.atlasent.io/functions/v1" });

const ctx = buildActionContext({
  actor: {
    id: "u_finance_42",
    email: "controller@acme.com",
    ip: "10.0.1.55",
    type: "human",
    trust_level: "high",
    roles: ["controller", "finance-approver"],
  },
  resource: {
    id: "vendor_stripe_001",
    type: "vendor",
    name: "Stripe Inc.",
    sensitivity: "confidential",
  },
  environment: "production",
  action_meta: {
    estimated_amount: 250_000,
    currency: "USD",
    risk_level: "critical",
    reversibility: "irreversible",
    description: "Monthly platform fee payment",
  },
  extra: {
    api_key: "sk_live_XXXXXX",
    reference_po: "PO-2024-001",
  },
});

console.log("\n=== Raw Context ===");
console.log(JSON.stringify(ctx, null, 2));

const validation = validateActionContext(ctx, {
  requiredFields: ["actor.id"],
});
console.log("\n=== Validation ===");
console.log("valid:", validation.valid);
console.log("errors:", validation.errors);
console.log("warnings:", validation.warnings);

const redacted = redactContext(ctx, DEFAULT_REDACTION_RULES);
console.log("\n=== Redacted Context (for audit log) ===");
console.log(JSON.stringify(redacted, null, 2));

const flat = flattenActionContext(ctx);
console.log("\n=== Flat Context (for protect()) ===");
console.log(JSON.stringify(flat, null, 2));

console.log("\nCalling protect() with flat context...");
try {
  const permit = await protect({
    action: "payment.release",
    resourceId: "vendor_stripe_001",
    agentId: "u_finance_42",
    context: flat,
  });
  console.log("Permit issued:", permit.permitId);
} catch (err) {
  console.log("Denied (expected in sandbox):", (err as Error).message);
}
