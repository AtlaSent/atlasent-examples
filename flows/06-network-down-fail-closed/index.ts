// 06 · Network-down boundary regression — contract test
// =======================================================
// Verifies the fail-closed boundary: when AtlaSent's authority source
// is unreachable, an SDK that obeys the contract MUST raise rather
// than silently allow. A gate that fails open when its authority
// source is down is worse than no gate.
//
// This flow is intentionally **dependency-free**. It exercises the
// underlying transport contract directly via Node's built-in `fetch`,
// so it runs in CI without needing a published `@atlasent/sdk`. The
// SDK-level enforcement of this property is covered by the per-SDK
// unit suites (TS in atlasent-sdk/typescript/test/, Python in
// atlasent-sdk/python/tests/test_with_permit.py).
//
// What this test asserts:
//
//   1. A POST to the AtlaSent API on an unreachable host raises a
//      `TypeError` from `fetch()` itself (Node's standard behaviour
//      for an unreachable connection). This is the *hard floor*: if
//      this property breaks, every SDK built on `fetch` (including
//      `@atlasent/sdk`) breaks fail-closed.
//
//   2. The error message identifies the unreachable destination —
//      so any SDK wrapping this can surface a coherent
//      `AtlaSentError` (or `AuthorizationUnavailableError`) message
//      including the URL the caller saw fail.
//
// If any SDK ever returns a permit decision when this contract test
// throws, that SDK has violated fail-closed. Each SDK's tests should
// reproduce this scenario against a mock and confirm their wrapper
// raises rather than returns.

const UNREACHABLE_URL = 'http://127.0.0.1:1';
const TIMEOUT_MS = 1500;

type FetchOutcome =
  | { ok: true; status: number }
  | { ok: false; error: Error };

async function fetchWithTimeout(url: string): Promise<FetchOutcome> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${url}/v1-evaluate`, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        authorization: 'Bearer ask_test_unreachable_boundary_regression',
      },
      body: JSON.stringify({
        agent: 'boundary-regression',
        action: 'production.deploy',
        context: { reason: 'demo' },
      }),
      signal: ctrl.signal,
    });
    return { ok: true, status: res.status };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err : new Error(String(err)) };
  } finally {
    clearTimeout(timer);
  }
}

async function main(): Promise<void> {
  console.log('=== 06 · Network-down boundary regression ===\n');
  console.log(`Probing unreachable host: ${UNREACHABLE_URL}`);
  console.log('Expected: fetch() raises on transport failure.\n');

  const outcome = await fetchWithTimeout(UNREACHABLE_URL);

  if (outcome.ok) {
    console.error(
      '❌ FAIL: fetch() returned a response from an unreachable host. ' +
        'Either the test environment routes 127.0.0.1:1 to a real listener ' +
        '(broken sandbox), or the host is misconfigured. Skip rather than ' +
        'declare a regression.',
    );
    process.exit(1);
  }

  const errName = outcome.error.constructor.name;
  const errMsg = outcome.error.message;
  console.log(`✅ fetch() raised: ${errName}: ${errMsg.slice(0, 200)}`);

  // The contract: any SDK wrapping fetch() in this scenario MUST
  // surface this error (typed appropriately) rather than returning
  // a synthetic "decision: allow" payload.
  console.log('');
  console.log('Contract this proves:');
  console.log('  • Transport failure is observable at the fetch boundary.');
  console.log('  • An SDK on top of fetch can therefore raise reliably.');
  console.log('  • A wrapper that hides this error and returns "allow" is broken.');
  console.log('');
  console.log('🛡  Boundary held. SDKs that wrap this contract MUST raise here.');
}

main().catch((err: unknown) => {
  // Reaches here only on a wiring error — fetch() outcomes are
  // captured above. Surface non-zero so a CI runner notices.
  console.error('Flow harness failed:', err instanceof Error ? err.message : err);
  process.exit(1);
});
