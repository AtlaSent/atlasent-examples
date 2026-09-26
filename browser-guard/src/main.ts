/**
 * AtlaSent Browser Guard — Vite + TypeScript (no framework)
 *
 * WHY import.meta.env AND NOT process.env?
 * ─────────────────────────────────────────
 * In a browser or edge runtime (Cloudflare Workers, Deno Deploy, etc.)
 * `process` is not defined. Accessing `process.env.ATLASENT_API_KEY` would
 * throw a ReferenceError at runtime and crash the page.
 *
 * Vite replaces `import.meta.env.VITE_*` variables at build time with their
 * literal values from the `.env` file, so they are safe to use in browser
 * bundles. Only variables prefixed with `VITE_` are exposed — this prevents
 * accidentally leaking server-only secrets into the bundle.
 *
 * WHY @atlasent/enforce AND NOT @atlasent/sdk?
 * ───────────────────────────────────────────────
 * @atlasent/sdk is the full Node SDK — it imports node:crypto's webcrypto
 * at the top level and does not bundle for the browser (Vite's rollup build
 * fails on it). @atlasent/enforce is the lightweight, fetch-only package
 * meant for exactly this use case: a browser/edge runtime evaluate() call
 * with no Node-only dependencies.
 *
 * Required .env variables (create a .env file from .env.example):
 *   VITE_ATLASENT_API_KEY   — your AtlaSent API key
 *   VITE_ATLASENT_API_URL   — base URL, e.g. https://api.atlasent.io/functions/v1
 *   VITE_ATLASENT_ORG_ID    — your organisation ID
 */

import { evaluate, EnforceError, type Decision } from '@atlasent/enforce';

// ── Read env vars via import.meta.env (Vite's browser-safe mechanism) ──────
// Never use process.env here — it does not exist in a browser and will crash.
const apiKey = import.meta.env.VITE_ATLASENT_API_KEY as string | undefined;
const apiUrl = import.meta.env.VITE_ATLASENT_API_URL as string | undefined
  ?? 'https://api.atlasent.io/functions/v1';
const orgId  = import.meta.env.VITE_ATLASENT_ORG_ID  as string | undefined;

// ── DOM helpers ────────────────────────────────────────────────────────────
const statusEl = document.getElementById('status') as HTMLDivElement;

function renderResult(decision: string, detail: string): void {
  // Decision values are canonical lowercase: "allow" | "deny" | "hold" | "escalate"
  // Always compare with === "allow", never === "ALLOW".
  const cls = ['allow', 'deny', 'hold', 'escalate'].includes(decision)
    ? decision
    : 'error';
  statusEl.className = cls;
  statusEl.innerHTML = `<strong>Decision: ${decision}</strong><br>${detail}`;
}

function renderError(message: string): void {
  statusEl.className = 'error';
  statusEl.innerHTML = `<strong>Error</strong><br>${message}`;
}

// ── Guard ──────────────────────────────────────────────────────────────────
async function runGuard(): Promise<void> {
  if (!apiKey) {
    renderError(
      'VITE_ATLASENT_API_KEY is not set. ' +
      'Add it to your <code>.env</code> file and restart <code>vite dev</code>.'
    );
    return;
  }
  if (!orgId) {
    renderError(
      'VITE_ATLASENT_ORG_ID is not set. ' +
      'Add it to your <code>.env</code> file and restart <code>vite dev</code>.'
    );
    return;
  }

  let result: Decision;

  try {
    // orgId is not part of EnforceConfig — the org is resolved from the
    // API key server-side; VITE_ATLASENT_ORG_ID is validated above only
    // as a config sanity check for callers that scope context by org.
    result = await evaluate({
      apiKey,
      apiUrl,
      actor: 'browser-user',
      action: 'ui.view_dashboard',
      context: {
        page:      'main-dashboard',
        userAgent: navigator.userAgent.slice(0, 80),
      },
    });
  } catch (err: unknown) {
    if (err instanceof EnforceError) {
      renderError(`[${err.phase}] ${err.message}`);
      return;
    }

    const status = (err as { status?: number })?.status;

    if (status === 401) {
      renderError(
        'Got 401 &mdash; your <code>VITE_ATLASENT_API_KEY</code> may be wrong or expired. ' +
        'Regenerate it in the AtlaSent console under <strong>Settings &rarr; API Keys</strong>.'
      );
      return;
    }
    if (status === 429) {
      renderError(
        'Got 429 &mdash; rate limited (100 req/min per org). ' +
        'Back off and retry after the <code>Retry-After</code> header duration.'
      );
      return;
    }

    renderError(`Unexpected error: ${(err as Error)?.message ?? String(err)}`);
    return;
  }

  // Canonical lowercase decision comparison
  const decision = result.decision;
  const permit   = result.permitToken ?? '';

  if (decision === 'allow') {
    renderResult('allow', `Access granted. Permit: <code>${permit || 'n/a'}</code>`);
    return;
  }

  if (decision === 'deny') {
    renderResult('deny', `Access denied. ${result.denyReason ?? ''}`);
    return;
  }

  if (decision === 'hold') {
    renderResult('hold',
      `Action is on hold — pending manual approval.<br>` +
      `${result.holdReason ? result.holdReason + '<br>' : ''}` +
      `Escalation ID: <code>${result.escalation_id ?? 'n/a'}</code>`);
    return;
  }

  if (decision === 'escalate') {
    renderResult('escalate',
      `Action requires escalation. Contact your compliance team.<br>` +
      `Escalation ID: <code>${result.escalation_id ?? 'n/a'}</code>`);
    return;
  }

  renderResult('error', `Unrecognised decision: "${decision}". Failing closed.`);
}

runGuard();
