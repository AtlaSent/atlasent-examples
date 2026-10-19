const { test } = require('node:test');
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const { createHmac } = require('node:crypto');

test('Express 5 verifies original webhook bytes and rejects invalid signatures', async (t) => {
  const secret = 'local-webhook-regression-secret';
  const child = spawn(process.execPath, ['dist/index.js'], {
    cwd: require('node:path').resolve(__dirname, '..'),
    env: { ...process.env, PORT: '0', ATLASENT_WEBHOOK_SECRET: secret },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  t.after(() => child.kill());
  const url = await new Promise((resolve, reject) => {
    let output = '';
    const timer = setTimeout(() => reject(new Error('Receiver did not start')), 10000);
    child.once('error', reject);
    child.once('exit', code => { clearTimeout(timer); reject(new Error(`Receiver exited: ${code}`)); });
    child.stdout.on('data', data => {
      output += data;
      const match = output.match(/http:\/\/localhost:(\d+)\/webhooks\/atlasent/);
      if (match) { clearTimeout(timer); resolve(`http://127.0.0.1:${match[1]}/webhooks/atlasent`); }
    });
  });
  const sign = body => 'sha256=' + createHmac('sha256', secret).update(body).digest('hex');
  const post = async (body, signature) => {
    const headers = { 'Content-Type': 'application/json' };
    if (signature !== undefined) headers['X-AtlaSent-Signature'] = signature;
    const response = await fetch(url, { method: 'POST', headers, body });
    await response.text();
    return response.status;
  };
  const body = '{ "id": "local-1", "event_type": "test", "data": {"text":"café ☕"} }';
  assert.equal(await post(body), 401);
  assert.equal(await post(body, 'sha256=' + '0'.repeat(64)), 401);
  assert.equal(await post(body, sign(body)), 200);
  assert.equal(await post(body + ' ', sign(body)), 401, 'changed original bytes must fail');
  assert.equal(await post('{broken', sign('{broken')), 400);
  const invalidUtf8 = Buffer.from([0x7b, 0xff, 0x7d]);
  assert.equal(await post(invalidUtf8, sign(invalidUtf8)), 400);
});
