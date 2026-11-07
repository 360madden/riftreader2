const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const source = fs.readFileSync('scripts/lab2_tool_handoff.js', 'utf8');
const base = 'C:\\work\\riftreader2\\artifacts\\e2e-latency-20261106\\lab2-handoff-';
const sha = 'A'.repeat(64);

function fixture(response, previous) {
  const calls = [], shown = [], values = [], memory = {'lab2-handoff-previous': previous};
  const tools = {
    exec_command: async arg => { calls.push(arg); return response; },
    write_stdin: async arg => { calls.push(arg); return {exit_code: 0, output: ''}; },
    view_image: async arg => { calls.push(arg); return {image_url: 'pixels'}; }
  };
  const inspect = new Function('tools', 'image', 'text', 'store', 'load', source)(
    tools, x => shown.push(x), x => values.push(x), (k, v) => memory[k] = v, k => memory[k]);
  return {inspect, calls, shown, values, memory};
}
function delivery(tag, extra = {}) {
  const root = base + tag;
  return JSON.stringify({status: 'verified-awaiting-visual-review', image: root + '\\capture\\image.bmp',
    report: root + '\\report.json', imageSha256: sha, nativeVitals: {metrics: {health: 42}}, ...extra});
}
test('overview polls, displays current image, and suppresses native values', async () => {
  const f = fixture({session_id: 3, output: delivery('first')});
  await f.inspect('overview', {outputTag: 'first'});
  assert.equal(f.calls.length, 3);
  assert.deepEqual(f.shown, ['pixels']);
  assert.equal(JSON.stringify(f.values).includes('health'), false);
  assert.deepEqual(f.memory['lab2-handoff-previous'], {root: base + 'first', sha});
});
test('continuation uses reviewed metadata and exposes only selected metric', async () => {
  const f = fixture({exit_code: 0, output: delivery('second', {focus: 'energy', selectedMetric: 11, reviewedOutput: base + 'first', reviewedImageSha256: sha, qualification: 'candidate-only; semantics/passive-freshness/restart-unverified; UI review required', nativeSourceReportSha256: sha})}, {root: base + 'first', sha});
  await f.inspect('energy', {outputTag: 'second'});
  assert.match(f.calls[0].cmd, /--reviewed-output/);
  assert.equal(f.values[0].selectedMetric, 11);
  assert.equal(JSON.stringify(f.values).includes('health'), false);
  await assert.rejects(f.inspect('health', {outputTag: 'third'}));
  assert.equal(f.calls.length, 2);
});
test('bad input and invalid prior metadata never execute', async () => {
  const f = fixture({});
  await assert.rejects(f.inspect('bad'));
  await assert.rejects(f.inspect('overview', {outputTag: "x'"}));
  await assert.rejects(f.inspect('health', {outputTag: 'next'}));
  assert.equal(f.calls.length, 0);
});
test('failed or mismatched delivery shows no image or stored proof', async () => {
  for (const response of [{exit_code: 2, output: ''}, {exit_code: 0, output: delivery('other')}]) {
    const f = fixture(response);
    await assert.rejects(f.inspect('overview', {outputTag: 'first'}));
    assert.equal(f.shown.length, 0);
    assert.equal(f.memory['lab2-handoff-previous'], null);
  }
});
