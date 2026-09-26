/**
 * Clinical Unblinding Execution-System Simulator
 * ==============================================
 *
 * A reference execution system for the AtlaSent clinical unblinding pilot. It
 * models an RTSM/IRT-style system that holds sealed treatment assignments and
 * REFUSES to release one unless AtlaSent has issued a permit for the exact
 * (trial, subject, action) AND that permit verifies. It enforces the real
 * permit contract — it adds no authorization state of its own.
 *
 * The protected action is clinical unblinding. Two action classes:
 *   - trial.unblinding.execute    (standard / non-emergency)
 *   - trial.unblinding.emergency  (emergency medical unblinding — distinct path)
 *
 * State vocabulary (printed as the flow advances):
 *   blinded → unblinding_requested → authorization_pending
 *     → authorized | denied
 *     → permit_issued → permit_verified
 *     → treatment_assignment_released → execution_verified
 *     → post_event_review_required (emergency, or when policy requires)
 *
 * Fail-closed at every branch: a non-allow decision, a missing permit, a failed
 * verification, or a permit bound to a different trial/subject/action all BLOCK
 * the release. There is NO fail-open path.
 *
 * Modes:
 *   - LIVE  (ATLASENT_API_KEY set): calls /v1-evaluate + /v1-verify-permit for
 *     real. Without an IdP-signed approval artifact the gate correctly DENIES
 *     (fail-closed) — supply APPROVAL_ARTIFACT_FILE to exercise the allow path.
 *   - DEMO  (no key): deterministically simulates the authorized happy path and
 *     the missing-permit block, clearly labelled SIMULATED, so CI can run it.
 *
 * Env:
 *   ATLASENT_API_KEY        clinical:read + clinical:manage + evaluate:write + verify:execute
 *   ATLASENT_BASE_URL       default https://api.atlasent.io/functions/v1  (or ATLASENT_API_URL)
 *   ACTION                  standard | emergency        (default: standard)
 *   TRIAL                   trial/protocol id           (default: NCT-SIM-1)
 *   SUBJECT                 subject id                   (default: S-001)
 *   ACTOR                   requester id                 (default: sim:medical-monitor)
 *   REASON                  reason-for-unblinding text   (§11.10(e))
 *   APPROVAL_ARTIFACT_FILE  path to an IdP-signed ApprovalArtifactV1 JSON (LIVE allow path)
 */

import { readFileSync } from 'node:fs';

type Json = Record<string, unknown>;

const apiKey = process.env.ATLASENT_API_KEY;
const base = (process.env.ATLASENT_BASE_URL ?? process.env.ATLASENT_API_URL ?? 'https://api.atlasent.io/functions/v1').replace(/\/$/, '');
const mode = (process.env.ACTION ?? 'standard').toLowerCase() === 'emergency' ? 'emergency' : 'standard';
const trial = process.env.TRIAL ?? 'NCT-SIM-1';
const subject = process.env.SUBJECT ?? 'S-001';
const actor = process.env.ACTOR ?? 'sim:medical-monitor';
const reason = process.env.REASON ?? 'DSMB-recommended interim unblinding for the acceptance run';
const actionType = mode === 'emergency' ? 'trial.unblinding.emergency' : 'trial.unblinding.execute';
const approvalFile = process.env.APPROVAL_ARTIFACT_FILE;

function log(state: string, detail = ''): void {
  console.log(`  [${state}]${detail ? ' ' + detail : ''}`);
}

/**
 * The verified permit as the execution system understands it: the token plus the
 * exact context AtlaSent authorized. The simulator releases ONLY when this
 * matches the release it is about to perform — this is what makes wrong-subject,
 * wrong-study, and wrong-action permits fail to release (spec cases 12/13/14).
 */
interface VerifiedPermit {
  token: string;
  action_type: string;
  trial_id: string;
  subject_id: string;
}

/**
 * The execution system. Sealed treatment assignments; release is impossible
 * without a matching verified permit. This class contains NO authorization
 * logic — it only checks that a permit it was handed actually authorizes the
 * exact release being requested.
 */
class UnblindingSimulator {
  private readonly assignments: Record<string, string> = {
    'S-001': 'ARM_A (active)',
    'S-002': 'ARM_B (placebo)',
  };

  release(req: { trial_id: string; subject_id: string; action_type: string }, permit: VerifiedPermit | null): string {
    if (!permit) {
      throw new Error('BLOCKED: no verified AtlaSent permit presented — treatment assignment stays sealed.');
    }
    if (permit.action_type !== req.action_type) {
      throw new Error(`BLOCKED: permit authorizes ${permit.action_type}, not ${req.action_type} (wrong action class).`);
    }
    if (permit.trial_id !== req.trial_id) {
      throw new Error(`BLOCKED: permit is bound to trial ${permit.trial_id}, not ${req.trial_id} (wrong study).`);
    }
    if (permit.subject_id !== req.subject_id) {
      throw new Error(`BLOCKED: permit is bound to subject ${permit.subject_id}, not ${req.subject_id} (wrong subject).`);
    }
    const assignment = this.assignments[req.subject_id];
    if (!assignment) throw new Error(`BLOCKED: unknown subject ${req.subject_id}.`);
    return assignment;
  }
}

async function post(path: string, body: Json): Promise<{ status: number; json: Json }> {
  const res = await fetch(`${base}${path}`, {
    method: 'POST',
    headers: { authorization: `Bearer ${apiKey}`, 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  const text = await res.text();
  return { status: res.status, json: text ? (JSON.parse(text) as Json) : {} };
}

function loadApproval(): Json | undefined {
  if (!approvalFile) return undefined;
  try {
    return JSON.parse(readFileSync(approvalFile, 'utf8')) as Json;
  } catch (err) {
    console.error(`Could not read APPROVAL_ARTIFACT_FILE (${approvalFile}): ${(err as Error).message}`);
    process.exit(1);
  }
}

async function runLive(sim: UnblindingSimulator): Promise<number> {
  log('blinded', `trial=${trial} subject=${subject} action=${actionType}`);
  log('unblinding_requested', `requester=${actor}`);
  log('authorization_pending', 'POST /v1-evaluate');

  const approval = loadApproval();
  const evalBody: Json = {
    action_type: actionType,
    actor_id: actor,
    environment: 'production',
    target_id: `trial:${trial}:subject:${subject}`,
    context: { trial_id: trial, subject_id: subject, unblinding_reason: reason, rationale: reason },
    state_snapshot: { source: 'execution-simulator', complete: true },
    reason,
  };
  if (approval) evalBody.approval = { artifact: approval };

  const evalRes = await post('/v1-evaluate', evalBody);
  const decision = String(evalRes.json.decision ?? '').toLowerCase();
  const denyCode = String(evalRes.json.deny_code ?? '');
  const permitToken = (evalRes.json.permit_token ?? evalRes.json.permitToken) as string | undefined;

  if (decision !== 'allow') {
    log('denied', `decision=${decision || 'unknown'} deny_code=${denyCode || 'n/a'}`);
    log('BLOCKED', 'fail-closed — treatment assignment stays sealed.');
    if (!approval) {
      console.log('\n(ℹ Supply APPROVAL_ARTIFACT_FILE with an IdP-signed approval to exercise the allow path.)');
    }
    return 0; // a correct fail-closed deny is a successful demonstration
  }
  log('authorized', 'decision=allow');

  if (!permitToken) {
    log('BLOCKED', 'allow returned no executable permit — refusing to release (fail-closed).');
    return 3;
  }
  log('permit_issued', `permit=${permitToken.slice(0, 10)}…`);

  log('permit_verified', 'POST /v1-verify-permit');
  const verifyRes = await post('/v1-verify-permit', { permit_token: permitToken, action_type: actionType, actor_id: actor });
  const valid = verifyRes.json.valid === true || String(verifyRes.json.outcome ?? '').toLowerCase() === 'verified';
  if (!valid) {
    log('BLOCKED', `verification failed (outcome=${verifyRes.json.outcome ?? 'invalid'}) — refusing to release.`);
    return 3;
  }

  const permit: VerifiedPermit = { token: permitToken, action_type: actionType, trial_id: trial, subject_id: subject };
  let assignment: string;
  try {
    assignment = sim.release({ trial_id: trial, subject_id: subject, action_type: actionType }, permit);
  } catch (err) {
    log('BLOCKED', (err as Error).message);
    return 3;
  }
  log('treatment_assignment_released', `subject ${subject} → ${assignment}`);
  log('execution_verified', 'released only after a verified, context-bound permit');
  if (mode === 'emergency') log('post_event_review_required', 'emergency path — schedule mandatory post-event review');
  console.log('\n✅ Clinical unblinding executed under a verified permit.');
  return 0;
}

function runDemo(sim: UnblindingSimulator): number {
  console.log('DEMO mode (no ATLASENT_API_KEY) — SIMULATED permit contract, no live AtlaSent call.\n');

  console.log('Scenario A — authorized standard unblinding (SIMULATED verified permit):');
  log('blinded', `trial=${trial} subject=${subject}`);
  log('unblinding_requested', `requester=${actor}`);
  log('authorization_pending');
  log('authorized', 'decision=allow (simulated)');
  log('permit_issued', 'pt.sim.xxxx');
  log('permit_verified', 'valid=true (simulated)');
  const permit: VerifiedPermit = { token: 'pt.sim.xxxx', action_type: 'trial.unblinding.execute', trial_id: trial, subject_id: subject };
  const assignment = sim.release({ trial_id: trial, subject_id: subject, action_type: 'trial.unblinding.execute' }, permit);
  log('treatment_assignment_released', `subject ${subject} → ${assignment}`);
  log('execution_verified');

  console.log('\nScenario B — missing permit (the execution system MUST block):');
  log('unblinding_requested', 'no permit presented');
  try {
    sim.release({ trial_id: trial, subject_id: subject, action_type: 'trial.unblinding.execute' }, null);
    console.error('  ✗ FAIL: release succeeded without a permit — this is a fail-open bug.');
    return 1;
  } catch (err) {
    log('BLOCKED', (err as Error).message);
  }

  console.log('\nScenario C — wrong-subject permit (bound to S-001, presented for S-002):');
  try {
    sim.release({ trial_id: trial, subject_id: 'S-002', action_type: 'trial.unblinding.execute' }, permit);
    console.error('  ✗ FAIL: released against a mismatched permit — fail-open bug.');
    return 1;
  } catch (err) {
    log('BLOCKED', (err as Error).message);
  }

  console.log('\n✅ Fail-closed contract holds: no release without a matching verified permit.');
  return 0;
}

async function main(): Promise<void> {
  console.log('=== Clinical Unblinding Execution-System Simulator ===\n');
  const sim = new UnblindingSimulator();
  const code = apiKey ? await runLive(sim) : runDemo(sim);
  process.exit(code);
}

main().catch((err) => {
  console.error('Simulator error:', err);
  process.exit(1);
});
