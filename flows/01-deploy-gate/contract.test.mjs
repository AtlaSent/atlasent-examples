import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createServer } from 'node:http';
import { once } from 'node:events';
import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const flowDirectory = dirname(fileURLToPath(import.meta.url));
const apiKey = 'api-key-sentinel-not-secret';
const permitToken = 'permit-token-sentinel-not-secret';
const executionHash = 'a'.repeat(64);

async function runFlow(respond) {
  const requests = [];
  const server = createServer(async (request, response) => {
    let rawBody = '';
    request.setEncoding('utf8');
    for await (const chunk of request) rawBody += chunk;
    const recorded = {
      path: request.url,
      authorization: request.headers.authorization,
      body: rawBody ? JSON.parse(rawBody) : {},
    };
    requests.push(recorded);
    const result = respond(recorded, requests.length);
    response.writeHead(result.status ?? 200, { 'content-type': 'application/json' });
    response.end(JSON.stringify(result.body));
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const address = server.address();
  assert(address && typeof address === 'object');

  const child = spawn(process.execPath, ['--import', 'tsx', 'index.ts'], {
    cwd: flowDirectory,
    env: {
      ...process.env,
      ATLASENT_API_KEY: apiKey,
      ATLASENT_API_URL: `http://127.0.0.1:${address.port}`,
      SERVICE: 'payments-api',
      TARGET_ENV: 'production',
      ACTOR: 'ci-bot@Atlasent/atlasent-examples',
      GITHUB_REPOSITORY: 'Atlasent/atlasent-examples',
      GITHUB_REF: 'refs/heads/contract-test',
      GITHUB_SHA: 'abc123def456',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let stdout = '';
  let stderr = '';
  child.stdout.setEncoding('utf8');
  child.stderr.setEncoding('utf8');
  child.stdout.on('data', (chunk) => { stdout += chunk; });
  child.stderr.on('data', (chunk) => { stderr += chunk; });
  const [code] = await once(child, 'close');
  server.close();
  await once(server, 'close');
  return { code, stdout, stderr, requests };
}

test('uses the canonical evaluate and verify contracts without logging credentials', async () => {
  const result = await runFlow(({ path }) => {
    if (path === '/v1-evaluate') {
      return {
        body: {
          decision: 'allow',
          permit_token: permitToken,
          execution_hash_expected: executionHash,
          audit_entry_hash: 'audit-entry-123',
        },
      };
    }
    if (path === '/v1-verify-permit') {
      return { body: { valid: true, consumed: true, outcome: 'allow' } };
    }
    return { status: 404, body: { error: 'not found' } };
  });

  assert.equal(result.code, 0, result.stderr);
  assert.equal(result.requests.length, 2);
  assert.equal(result.requests[0].authorization, `Bearer ${apiKey}`);
  assert.deepEqual(result.requests[0].body, {
    action_type: 'production.deploy',
    actor_id: 'ci-bot@Atlasent/atlasent-examples',
    resource_id: 'payments-api',
    change_plan: { operation: 'deploy', revision: 'abc123def456' },
    context: {
      service: 'payments-api',
      target_id: 'payments-api',
      target: { id: 'payments-api' },
      environment: 'production',
      repo: 'Atlasent/atlasent-examples',
      ref: 'refs/heads/contract-test',
      commit_sha: 'abc123def456',
    },
  });
  assert.equal(result.requests[1].authorization, `Bearer ${apiKey}`);
  assert.deepEqual(result.requests[1].body, {
    permit_token: permitToken,
    action_type: 'production.deploy',
    actor_id: 'ci-bot@Atlasent/atlasent-examples',
    environment: 'production',
    target_id: 'payments-api',
    payload_hash: executionHash,
    context: result.requests[0].body.context,
  });
  assert.doesNotMatch(`${result.stdout}${result.stderr}`, new RegExp(apiKey));
  assert.doesNotMatch(`${result.stdout}${result.stderr}`, new RegExp(permitToken.replaceAll('.', '\\.')));
  assert.match(result.stdout, /Deploy complete/);
});

test('fails closed when an allow response has no execution binding', async () => {
  const result = await runFlow(({ path }) => {
    assert.equal(path, '/v1-evaluate');
    return { body: { decision: 'allow', permit_token: permitToken } };
  });

  assert.equal(result.code, 3);
  assert.equal(result.requests.length, 1);
  assert.doesNotMatch(`${result.stdout}${result.stderr}`, new RegExp(permitToken.replaceAll('.', '\\.')));
  assert.doesNotMatch(result.stdout, /Deploy complete/);
});

test('blocks without verifying or executing when evaluation denies', async () => {
  const result = await runFlow(({ path }) => {
    assert.equal(path, '/v1-evaluate');
    return { body: { decision: 'deny', deny_reason: 'approval_required' } };
  });

  assert.equal(result.code, 2);
  assert.equal(result.requests.length, 1);
  assert.match(result.stdout, /gate rejected/i);
  assert.doesNotMatch(result.stdout, /Deploy complete/);
});

test('fails closed on an unknown evaluate decision', async () => {
  const result = await runFlow(() => ({ body: { decision: 'maybe' } }));

  assert.equal(result.code, 1);
  assert.equal(result.requests.length, 1);
  assert.doesNotMatch(result.stdout, /Deploy complete/);
});

test('fails closed when verification did not consume the permit', async () => {
  const result = await runFlow(({ path }) => path === '/v1-evaluate'
    ? {
        body: {
          decision: 'allow',
          permit_token: permitToken,
          execution_hash_expected: executionHash,
        },
      }
    : { body: { valid: true, consumed: false, outcome: 'allow' } });

  assert.equal(result.code, 3);
  assert.equal(result.requests.length, 2);
  assert.doesNotMatch(`${result.stdout}${result.stderr}`, new RegExp(permitToken.replaceAll('.', '\\.')));
  assert.doesNotMatch(result.stdout, /Deploy complete/);
});

test('does not print a reflected secret from an HTTP error', async () => {
  const result = await runFlow(() => ({
    status: 500,
    body: { debug: `${apiKey} ${permitToken}` },
  }));

  assert.equal(result.code, 1);
  assert.doesNotMatch(`${result.stdout}${result.stderr}`, new RegExp(apiKey));
  assert.doesNotMatch(`${result.stdout}${result.stderr}`, new RegExp(permitToken.replaceAll('.', '\\.')));
  assert.doesNotMatch(result.stdout, /Deploy complete/);
});
