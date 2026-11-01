/* Run: node --test tests/ecoflow-live.test.cjs */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');

const script = fs.readFileSync('site/ecoflow-live.js', 'utf8');
function fixture() {
  let time = Date.now();
  let config = { enabled: true,
    snapshotUrl: 'https://read-only.example.test/api/ecoflow/snapshot',
    streamUrl: 'https://read-only.example.test/api/ecoflow/events' };
  const socket = [];
  const FakeDate = class extends Date { static now() { return time; } };
  class FakeEvents {
    constructor(url, options) { this.url = url; this.options = options; this.handlers = {}; socket.push(this); }
    addEventListener(name, handler) { this.handlers[name] = handler; }
    close() {}
  }
  const window = {
    location: { href: 'https://epicman1997.github.io/nashe-svitlo/' },
    document: { addEventListener() {}, visibilityState: 'visible' }
  };
  const context = {
    window, Date: FakeDate, URL, EventSource: FakeEvents, console,
    setInterval() {},
    async fetch(url) {
      if (url === './ecoflow-live-config.json') return {
        ok: true, async json() { return config; }
      };
      return { ok: true, async json() {
        return { version: 1, emittedAt: new Date(time).toISOString(), devices: {} };
      } };
    }
  };
  vm.runInNewContext(script, context);
  return {
    api: window.NasheSvitloEcoFlowLive,
    socket, now: () => time, advance: value => { time += value; },
    configure: value => { config = value; }
  };
}
test('disabled config never accepts live frames or exposes credentials', async () => {
  const f = fixture();
  f.configure({ enabled: false, snapshotUrl: '', streamUrl: '' });
  await f.api.start();
  assert.equal(f.api.summary().status, 'preview');
  assert.equal(f.api.acceptFrame({ version: 1, emittedAt: new Date(f.now()).toISOString(),
    devices: { 'dacha:dp3': { socPercent: 83 } } }), false);
  assert.equal(f.api.reading('dacha:dp3'), null);
  assert.equal(f.socket.length, 0);
});
test('live stream accepts valid zero values without swapping locations', async () => {
  const f = fixture();
  await f.api.start();
  assert.equal(f.socket.length, 1);
  assert.equal(f.socket[0].options.withCredentials, false);
  const at = new Date(f.now()).toISOString();
  const received = f.api.acceptFrame({ version: 1, emittedAt: at, devices: {
    'dacha:dp3': { socPercent: 0, inputW: 0, outputW: 1024, operation: 'discharging' },
    'home:po': { moduleSocPercent: [56, 57], inputW: 200, outputW: 451, operation: 'discharging' }
  } });
  assert.equal(received, true);
  assert.equal(f.api.reading('dacha:dp3').socPercent, 0);
  assert.equal(f.api.reading('dacha:dp3').outputW, 1024);
  assert.equal(f.api.reading('home:po').moduleSocPercent.length, 2);
  assert.equal(f.api.reading('solovky:d2'), null);
  assert.equal(f.api.statusFor('home:po'), 'live');
});
test('unrecognised devices, invalid SOC and old frames cannot pollute data', async () => {
  const f = fixture();
  await f.api.start();
  const at = new Date(f.now()).toISOString();
  const frame = { version: 1, emittedAt: at, devices: {
    'dacha:dp3': { socPercent: 189, inputW: -5, outputW: null },
    'other:dp3': { socPercent: 50 }
  } };
  assert.equal(f.api.acceptFrame(frame), true);
  assert.equal(f.api.reading('dacha:dp3').socPercent, null);
  assert.equal(f.api.reading('dacha:dp3').inputW, null);
  assert.equal(f.api.reading('other:dp3'), null);
  f.advance(31000);
  assert.equal(f.api.reading('dacha:dp3'), null);
  assert.equal(f.api.statusFor('dacha:dp3'), 'stale');
  assert.equal(f.api.acceptFrame(frame), false);
});
test('empty or malformed frames never invent a charge', async () => {
  const f = fixture();
  await f.api.start();
  const at = new Date(f.now()).toISOString();
  assert.equal(f.api.acceptFrame({ version: 2, emittedAt: at, devices: {
    'dacha:dp3': { socPercent: 80 }
  } }), false);
  assert.equal(f.api.acceptFrame({ version: 1, emittedAt: at, devices: {
    'dacha:dp3': { socPercent: 80, updatedAt: 'yesterday' }
  } }), false);
  assert.equal(f.api.reading('dacha:dp3'), null);
});
test('no secret or serial number appears in the public device contract', async () => {
  const f = fixture();
  for (const key of f.api.deviceKeys) {
    assert.match(key, /^(dacha|home|solovky|naumenky):[a-z0-9]+$/);
  }
  assert.equal(f.api.deviceKeys.length, 10);
});
