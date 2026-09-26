import type { ComplianceEvidenceRun } from '@atlasent/sdk';
import { evidenceRunPasses, nonPassingControls } from '@atlasent/sdk';

const API_KEY = process.env['ATLASENT_API_KEY']!;
const API_URL = (process.env['ATLASENT_API_URL'] ?? 'https://api.atlasent.io/functions/v1').replace(/\/$/, '');

if (!API_KEY) {
  console.error('ATLASENT_API_KEY environment variable is required');
  process.exit(1);
}

// Parse optional --start / --end args
const args = process.argv.slice(2);
const startIdx = args.indexOf('--start');
const endIdx = args.indexOf('--end');
const periodStart = startIdx !== -1 ? args[startIdx + 1] : undefined;
const periodEnd = endIdx !== -1 ? args[endIdx + 1] : undefined;

async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const resp = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${API_KEY}`,
      ...(init?.headers ?? {}),
    },
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`API error ${resp.status}: ${body}`);
  }
  return resp;
}

async function triggerRun(): Promise<ComplianceEvidenceRun> {
  const body: Record<string, string> = { framework: 'soc2' };
  if (periodStart) body['period_start'] = periodStart;
  if (periodEnd) body['period_end'] = periodEnd;

  const resp = await apiFetch('/v1/compliance-evidence', {
    method: 'POST',
    body: JSON.stringify(body),
  });
  return resp.json() as Promise<ComplianceEvidenceRun>;
}

async function pollUntilDone(runId: string): Promise<ComplianceEvidenceRun> {
  while (true) {
    const resp = await apiFetch(`/v1/compliance-evidence/${runId}`);
    const run = (await resp.json()) as ComplianceEvidenceRun;
    if (run.status !== 'running' && run.status !== 'pending') return run;
    process.stdout.write('.');
    await new Promise((r) => setTimeout(r, 2000));
  }
}

function statusEmoji(status: string): string {
  if (status === 'pass') return '✅';
  if (status === 'gap') return '⚠️ ';
  return '❌';
}

async function main() {
  console.log('Triggering SOC 2 evidence run...');
  const run = await triggerRun();
  console.log(`Run ID: ${run.id}  Status: ${run.status}`);

  if (run.status === 'running' || run.status === 'pending') {
    process.stdout.write('Polling');
    const done = await pollUntilDone(run.id);
    console.log('\nRun complete.\n');

    if (done.status === 'failed') {
      console.error('Evidence run failed. Check the AtlaSent console for details.');
      process.exit(1);
    }

    // Print controls
    for (const control of done.controls) {
      console.log(
        `${statusEmoji(control.status)} ${control.control_id} — ${control.title} (${control.status})`,
      );
      for (const item of control.evidence) {
        console.log(`   • ${item}`);
      }
      console.log();
    }

    // Summary
    const summary = done.summary;
    if (summary) {
      console.log(
        `Summary: ${summary.pass} pass, ${summary.gap} gap, ${summary.finding} finding`,
      );
    }

    const allPass = evidenceRunPasses(done);
    console.log(`All controls pass: ${allPass}`);

    if (!allPass) {
      const issues = nonPassingControls(done);
      console.log(
        `\nControls needing attention: ${issues.map((c) => c.control_id).join(', ')}`,
      );
      process.exit(1);
    }
  }
}

main().catch((err) => {
  console.error('Error:', err instanceof Error ? err.message : String(err));
  process.exit(1);
});
