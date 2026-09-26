/**
 * src/consume.ts — AtlaSent permit consumer
 *
 * Called in the `if: always()` step so that permits are consumed even if
 * the execute step fails. Consuming a permit closes the audit record:
 * AtlaSent records whether the permit was used (execute succeeded),
 * not used (execute skipped — DENY), or used-but-failed (execute errored).
 *
 * If PERMIT_ID is empty (DENY outcome), this is a no-op — there is no
 * permit to consume.
 */
import atlasent, { AtlaSentError } from "@atlasent/sdk";

// The SDK's built-in default base URL is the bare host; the AtlaSent API is
// served under /functions/v1, so set it explicitly.
atlasent.configure({ baseUrl: process.env.ATLASENT_API_URL ?? "https://api.atlasent.io/functions/v1" });

const PERMIT_ID = process.env.PERMIT_ID ?? "";
const DECISION  = process.env.DECISION ?? "DENY";

if (!PERMIT_ID || DECISION !== "ALLOW") {
  // No permit to consume — DENY outcome or evaluate step failed
  console.log(`[consume] no permit to consume (decision=${DECISION})`);
  process.exit(0);
}

console.log(`[consume] consuming permit ${PERMIT_ID}`);

async function main(): Promise<void> {
  try {
    // verifyAndConsume() verifies the permit has not been tampered with and
    // marks it as consumed in the AtlaSent audit chain.
    // The permit cannot be reused after consumption (single-use enforcement).
    await atlasent.verifyAndConsume(PERMIT_ID);
    console.log(`[consume] permit ${PERMIT_ID} consumed — audit record closed`);
  } catch (err) {
    if (err instanceof AtlaSentError) {
      // Log but do not fail the CI job — the decision and execution are already
      // recorded in the audit chain. A consume failure is surfaced in the AtlaSent
      // console as an "unconsumed permit" alert.
      console.error(`[consume] AtlaSent unavailable (code=${err.code}): ${err.message}`);
      console.error(`[consume] permit ${PERMIT_ID} will appear as unconsumed in the audit chain`);
      process.exit(0); // non-fatal
    }
    throw err;
  }
}

main().catch((err) => {
  console.error("[consume] unexpected error:", err);
  process.exit(1);
});
