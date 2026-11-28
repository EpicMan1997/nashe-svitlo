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
  const socket = [], intervals = [], snapshotCalls = [], documentEvents = {};
  let snapshotResponder = null;
  const FakeDate = class extends Date { static now() { return time; } };
  class FakeEvents {
    constructor(url, options) { this.url = url; this.options = options; this.handlers = {}; socket.push(this); }
    addEventListener(name, handler) { this.handlers[name] = handler; }
    close() {}
  }
  const window = {
    location: { href: 'https://epicman1997.github.io/nashe-svitlo/', origin:'https://epicman1997.github.io' },
    document: { addEventListener(name,fn) { documentEvents[name] = fn; }, visibilityState: 'visible' }
  };
  const context = {
    window, Date: FakeDate, URL, EventSource: FakeEvents, console,
    setInterval(fn,ms) { intervals.push({fn,ms}); },
    async fetch(url) {
      if (url === './ecoflow-live-config.json') return {
        ok: true, async json() { return config; }
      };
      snapshotCalls.push(url);
      if (snapshotResponder) return snapshotResponder(url);
      return { ok: true, async json() {
        return { version: 1, emittedAt: new Date(time).toISOString(), devices: {} };
      } };
    }
  };
  vm.runInNewContext(script, context);
  return {
    api: window.NasheSvitloEcoFlowLive,
    socket, now: () => time, advance: value => { time += value; },
    configure: value => { config = value; },
    intervals, snapshotCalls, document: window.document, documentEvents,
    setSnapshotResponder: fn => { snapshotResponder = fn; }
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
    'dacha:dp3': { socPercent: 0, inputW: 0, outputW: 1024, runtimeMinutes: 145, operation: 'discharging' },
    'home:po': { moduleSocPercent: [56, 57], inputW: 200, outputW: 451, operation: 'discharging' }
  } });
  assert.equal(received, true);
  assert.equal(f.api.reading('dacha:dp3').socPercent, 0);
  assert.equal(f.api.reading('dacha:dp3').runtimeMinutes, 145);
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
    assert.match(key, /^(dacha|home|solovky|naumenky|unassigned):[a-z0-9-]+$/);
  }
  assert.equal(f.api.deviceKeys.length, 13);
});

test('scheduled EcoFlow snapshot is never called live and expires after 25 min', async () => {
  const f = fixture();
  f.configure({ enabled: true, mode: 'published', snapshotUrl: './ecoflow-snapshot.json', streamUrl: '' });
  await f.api.start();
  assert.equal(f.socket.length, 0);
  f.advance(10 * 60000);
  const at = new Date(f.now() - 10 * 60000).toISOString();
  const read = f.api.acceptFrame({
    version: 1, mode: 'scheduled', emittedAt: at,
    availability: { 'dacha:d3p': 'unsupported', 'dacha:d2': 'unassigned' },
    unassigned: ['unassigned:delta2-1'],
    devices: {
      'dacha:dp3': { updatedAt: at, socPercent: 45, inputW: 0, outputW: 150 },
      'unassigned:delta2-1': { updatedAt: at, socPercent: 80, inputW: 90, outputW: 0 }
    }
  });
  assert.equal(read, true);
  assert.equal(f.api.summary().status, 'published');
  assert.equal(f.api.statusFor('dacha:dp3'), 'published');
  assert.equal(f.api.availabilityFor('dacha:d3p'), 'unsupported');
  assert.equal(f.api.reading('unassigned:delta2-1').socPercent, 80);
  assert.equal(f.api.reading('dacha:d2'), null);
  f.advance(16 * 60000);
  assert.equal(f.api.reading('dacha:dp3'), null);
  assert.equal(f.api.statusFor('dacha:dp3'), 'stale');
});

test('repeated published snapshot is idempotent but corrections remain accepted', async () => {
  const f=fixture();
  f.configure({enabled:true,mode:'published',snapshotUrl:'./ecoflow-snapshot.json',streamUrl:''});
  await f.api.start();
  let count=0;f.api.subscribe(()=>count++);
  f.advance(60000);
  const frame={version:1,emittedAt:new Date(f.now()).toISOString(),
    devices:{'dacha:dp3':{socPercent:42,inputW:0,outputW:200,operation:'discharging'}}};
  assert.equal(f.api.acceptFrame(frame),true);
  const prior=count;
  assert.equal(f.api.acceptFrame(frame),false);
  assert.equal(count,prior);
  const corrected={...frame,devices:{'dacha:dp3':{...frame.devices['dacha:dp3'],socPercent:41}}};
  assert.equal(f.api.acceptFrame(corrected),true);
  assert.equal(f.api.reading('dacha:dp3').socPercent,41);
});

test('edge 09 parallel published snapshot triggers share one HTTP request', async () => {
  const f=fixture();
  f.configure({enabled:true,mode:'published',snapshotUrl:'./ecoflow-snapshot.json',streamUrl:''});
  await f.api.start();
  const poll=f.intervals.find(x=>x.ms===20000)?.fn;
  assert.ok(poll);
  assert.equal(f.snapshotCalls.length,1);
  let resolveSnapshot;
  f.setSnapshotResponder(()=>new Promise(resolve=>{resolveSnapshot=resolve;}));
  const first=poll(),second=poll();
  assert.equal(f.snapshotCalls.length,2,'only one in-flight HTTP call allowed');
  resolveSnapshot({ok:true,async json(){
    return {version:1,emittedAt:new Date(f.now()).toISOString(),
      devices:{'dacha:dp3':{socPercent:67,outputW:100,operation:'discharging'}}};
  }});
  await Promise.all([first,second]);
  assert.equal(f.api.reading('dacha:dp3').socPercent,67);
  assert.equal(f.snapshotCalls.length,2);
});

test('edge 10 hidden published PWA pauses polls and refreshes when visible',async()=>{
  const f=fixture();
  f.configure({enabled:true,mode:'published',snapshotUrl:'./ecoflow-snapshot.json',streamUrl:''});
  await f.api.start();
  const poll=f.intervals.find(x=>x.ms===20000)?.fn;
  assert.ok(poll);
  const initial=f.snapshotCalls.length;
  f.document.visibilityState='hidden';
  await poll();
  assert.equal(f.snapshotCalls.length,initial);
  f.advance(60000);
  f.document.visibilityState='visible';
  f.documentEvents.visibilitychange();
  await new Promise(setImmediate);
  assert.equal(f.snapshotCalls.length,initial+1);
  assert.equal(f.api.summary().mode,'published');
});

test('published mode checks snapshots every 20 seconds with a fresh cache key',async()=>{
  const f=fixture();
  f.configure({enabled:true,mode:'published',snapshotUrl:'./ecoflow-snapshot.json',streamUrl:''});
  await f.api.start();
  const poll=f.intervals.find(x=>x.ms===20000)?.fn;
  assert.ok(poll,'fast published polling');
  const initial=f.snapshotCalls[0];
  await poll();
  assert.equal(f.snapshotCalls.length,2);
  assert.equal(f.snapshotCalls[1],initial);
  f.advance(20000);
  await poll();
  assert.equal(f.snapshotCalls.length,3);
  assert.notEqual(f.snapshotCalls[2],initial);
  assert.equal(f.socket.length,0);
});

test('private API quota interruptions have explicit sanitized availability states',async()=>{
  const f=fixture();
  f.configure({enabled:true,mode:'published',snapshotUrl:'./ecoflow-snapshot.json',streamUrl:''});
  await f.api.start();
  const accepted=f.api.acceptFrame({
    version:1,emittedAt:new Date(f.now()).toISOString(),
    devices:{'dacha:dp3':{socPercent:64,inputW:0,outputW:200,operation:'discharging'}},
    availability:{
      'dacha:dp3':'readable','dacha:d2':'rate_limited',
      'solovky:d2':'not_listed','naumenky:d2':'api_error',
      'dacha:d3p':'unsupported','home:po':'unsupported',
      'dacha:r3pw':'invalid_data'
    },unassigned:[]
  });
  assert.equal(accepted,true);
  for(const [key,reason] of Object.entries({
    'dacha:d2':'rate_limited','solovky:d2':'not_listed',
    'naumenky:d2':'api_error','dacha:d3p':'unsupported',
    'dacha:r3pw':'invalid_data'}))
    assert.equal(f.api.availabilityFor(key),reason);
  assert.equal(f.api.reading('dacha:d2'),null);
  assert.equal(f.api.reading('dacha:dp3').socPercent,64);
});

test('worker mode prefers fresh primary per station and uses scheduled fallback independently', async()=>{
 const f=fixture();
 const url='https://nashe-svitlo-ecoflow.ssolovko.workers.dev/snapshot';
 f.configure({enabled:true,mode:'worker',snapshotUrl:url,fallbackUrl:'./ecoflow-snapshot.json',streamUrl:''});
 let primary=true;
 const frame=(mode,devices,age=0)=>({version:1,mode,emittedAt:new Date(f.now()-age).toISOString(),devices,
   availability:Object.fromEntries(Object.keys(devices).map(k=>[k,'readable'])),connection:'ok'});
 f.setSnapshotResponder(async u=>u===url?{ok:primary,json:async()=>frame('worker-poll',{'dacha:dp3':{socPercent:55,inputW:0,outputW:200}})}:
  {ok:true,json:async()=>frame('scheduled',{'dacha:dp3':{socPercent:50},'dacha:d2':{socPercent:80}},60000)});
 await f.api.start();
 assert.equal(f.api.statusFor('dacha:dp3'),'live');
 assert.equal(f.api.reading('dacha:dp3').socPercent,55);
 assert.equal(f.api.statusFor('dacha:d2'),'published');
 assert.equal(f.api.reading('dacha:d2').socPercent,80);
 assert.equal(f.socket.length,0);
 primary=false;f.advance(151000);
 await f.intervals.find(x=>x.ms===20000).fn();
 assert.equal(f.api.statusFor('dacha:dp3'),'published');
 assert.equal(f.api.reading('dacha:dp3').socPercent,50);
 primary=true;f.advance(60000);
 await f.intervals.find(x=>x.ms===20000).fn();
 assert.equal(f.api.statusFor('dacha:dp3'),'live');
 assert.equal(f.api.reading('dacha:dp3').socPercent,55);
 f.document.visibilityState='hidden';
 const count=f.snapshotCalls.length;
 await f.intervals.find(x=>x.ms===20000).fn();
 assert.equal(f.snapshotCalls.length,count);
});
test('worker mode rejects unexpected gateway host',async()=>{
 const f=fixture();
 f.configure({enabled:true,mode:'worker',snapshotUrl:'https://other.test/snapshot',fallbackUrl:'./ecoflow-snapshot.json',streamUrl:''});
 await f.api.start();
 assert.equal(f.api.summary().status,'error');
 assert.equal(f.snapshotCalls.length,0);
});

test('poll timing is the actual browser check interval, not a claimed upstream refresh',async()=>{
 const f=fixture();f.configure({enabled:true,mode:'published',snapshotUrl:'./ecoflow-snapshot.json',streamUrl:''});
 await f.api.start();
 assert.equal(f.api.summary().nextCheckMs,f.now()+20000);
 const poll=f.intervals.find(x=>x.ms===20000).fn;
 f.advance(20000);
 let resolve;f.setSnapshotResponder(()=>new Promise(r=>{resolve=r;}));
 const pending=poll();assert.equal(f.api.summary().checking,true);assert.equal(f.api.summary().nextCheckMs,f.now()+20000);
 resolve({ok:true,json:async()=>({version:1,emittedAt:new Date(f.now()).toISOString(),devices:{}})});
 await pending;assert.equal(f.api.summary().checking,false);
});

test('poll subscribers see start and end even for unchanged fast snapshot',async()=>{
 const f=fixture();f.configure({enabled:true,mode:'published',snapshotUrl:'./ecoflow-snapshot.json',streamUrl:''});
 const raw={version:1,emittedAt:new Date(f.now()).toISOString(),devices:{'dacha:dp3':{socPercent:50}}};
 f.setSnapshotResponder(async()=>({ok:true,json:async()=>raw}));
 await f.api.start();
 let changes=0;const events=[];
 f.api.subscribe(()=>changes++);
 f.api.subscribePoll(()=>{const info=f.api.summary();events.push([info.checking,info.checkResult]);});
 f.advance(20000);
 await f.intervals.find(x=>x.ms===20000).fn();
 assert.deepEqual(events,[[true,null],[false,'ok']]);
 assert.equal(changes,0);
 assert.equal(f.api.summary().checkStartedMs,f.now());
 assert.equal(f.api.summary().checkFinishedMs,f.now());
});
