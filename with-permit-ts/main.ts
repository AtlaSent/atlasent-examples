/**
 * AtlaSent TypeScript SDK — `withPermit()` lexically-scoped form.
 *
 * `withPermit()` is the lexically-scoped peer of `protect()`. Same wire
 * contract (evaluate + verifyPermit), same fail-closed matrix, same
 * audit-chain entry — but binds the action body to the permit's lifetime
 * via a callback. The body runs only on a verified permit; on deny, hold,
 * escalate, verification failure, or transport error it is never invoked.
 *
 * Use `withPermit()` when the action body is a single lexical scope.
 * Use `protect()` (../typescript-sdk-quickstart/) when you need the
 * verified Permit as a value to pass across a boundary or interleave
 * with non-trivial control flow.
 */

import atlasent, {
  AtlaSentDeniedError,
  AtlaSentError,
  type Permit,
} from "@atlasent/sdk";

// The SDK's built-in default base URL is the bare host; the AtlaSent API is
// served under /functions/v1, so set it explicitly.
atlasent.configure({ baseUrl: process.env.ATLASENT_API_URL ?? "https://api.atlasent.io/functions/v1" });

interface PatientRecord {
  patientId: string;
  payload: Record<string, unknown>;
  writtenAt: string;
  atlasentPermitId: string;
}

async function writePatientRecord(
  permit: Permit,
  patientId: string,
  payload: Record<string, unknown>,
): Promise<PatientRecord> {
  // Stand-in for the EHR write. In production this would POST to the EHR.
  return {
    patientId,
    payload,
    writtenAt: new Date().toISOString(),
    // The audit-chain link: the Permit ID is what makes the AtlaSent
    // decision and your system-of-record row two-way navigable.
    atlasentPermitId: permit.permitId,
  };
}

async function main(): Promise<void> {
  if (!process.env.ATLASENT_API_KEY) {
    console.error("ATLASENT_API_KEY is required.");
    process.exit(1);
  }

  try {
    // The action body executes only on a verified permit. The Permit
    // is visible inside the callback for audit-chain linkage; outside
    // the callback, `withPermit` resolves to whatever the body returned.
    const record = await atlasent.withPermit(
      {
        agent: "agent-001",
        action: "ehr.write",
        context: { environment: "production", patient_id: "patient-42" },
      },
      async (permit) => {
        return writePatientRecord(permit, "patient-42", {
          medication: "metformin",
          dose_mg: 500,
        });
      },
    );
    console.log("Record:", record);
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      console.error("Denied:", err.reason || err.message);
    } else if (err instanceof AtlaSentError) {
      console.error("Fail-closed:", err.message);
    } else {
      throw err;
    }
  }
}

main();
