import atlasent, {
  AtlaSentError,
  AtlaSentDeniedError,
} from "@atlasent/sdk";

// The SDK's built-in default base URL is the bare host; the AtlaSent API is
// served under /functions/v1, so set it explicitly.
atlasent.configure({ baseUrl: process.env.ATLASENT_BASE_URL ?? "https://api.atlasent.io/functions/v1" });

// The SDK's category primitive. Fail-closed: on deny or transport
// error it throws — if we reach the line after protect(), the
// action is authorized end-to-end (evaluate + verifyPermitById).
async function generateReport(reportId: string): Promise<string> {
  await atlasent.protect({
    agent: "assistant",
    action: "report.generate",
    context: { environment: "production", report_id: reportId },
  });
  return `Report ${reportId} generated at ${new Date().toISOString()}`;
}

async function exportData(
  dataset: string,
): Promise<{ dataset: string; rows: number }> {
  await atlasent.protect({
    agent: "assistant",
    action: "data.export",
    context: { environment: "production", dataset, format: "csv" },
  });
  return { dataset, rows: 42 };
}

async function main() {
  try {
    const report = await generateReport("Q1-2026");
    console.log("Report:", report);
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      console.error("Denied:", err.reason || err.message);
    } else if (err instanceof AtlaSentError) {
      console.error("Error:", err.message);
    } else {
      throw err;
    }
  }

  try {
    const data = await exportData("sales");
    console.log("Export:", data);
  } catch (err) {
    if (err instanceof AtlaSentDeniedError) {
      console.error("Denied:", err.reason || err.message);
    } else if (err instanceof AtlaSentError) {
      console.error("Error:", err.message);
    } else {
      throw err;
    }
  }
}

main();
