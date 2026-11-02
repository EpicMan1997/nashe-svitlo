/* Runtime smoke tests with a minimal DOM surface; no external packages needed.
 * Validate the actual EcoFlow script execution and event-driven rendering.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const vm = require('node:vm');

const eco = fs.readFileSync('site/ecoflow.js', 'utf8');
const index = fs.readFileSync('site/index.html', 'utf8');

class Element {
  constructor(id) {
    this.id = id;
    this.dataset = {};
    this.attributes = new Map();
    this.style = {};
    this.hidden = false;
    this.textContent = '';
    this.innerHTML = '';
    this.offsetTop = 0;
    this.offsetHeight = 100;
    this.scrollTop = 0;
    this.listeners = {};
    this.classList = {
      values: new Set(), add: (...args) => args.forEach(x => this.classList.values.add(x)),
      remove: (...args) => args.forEach(x => this.classList.values.delete(x)),
      toggle: (s, value) => {
        if (value === false || (value === undefined && this.classList.values.has(s))) {
          this.classList.values.delete(s); return false;
        }
        this.classList.values.add(s); return true;
      },
      contains: s => this.classList.values.has(s)
    };
  }
  addEventListener(name, handler) { this.listeners[name] = handler; }
  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  getAttribute(name) { return this.attributes.get(name) || null; }
  removeAttribute(name) { this.attributes.delete(name); }
  querySelectorAll() { return []; }
  querySelector() { return null; }
  closest() { return this; }
  focus() {}
}

function mount(live = null) {
  const nodes = new Map();
  const get = id => {
    if (!nodes.has(id)) nodes.set(id, new Element(id));
    return nodes.get(id);
  };
  const windowEvents = {};
  const doc = {
    getElementById: get, body: get('body'),
    querySelector: selector => selector === 'main > header' ? get('header') : null,
    querySelectorAll: selector => selector === '[data-location].selected'
      ? [{ dataset: { location: 'dacha' } }] : [],
    addEventListener: () => {}
  };
  const root = get('ecoflow');
  root.querySelector = selector => selector === '.eco-status' ? get('eco-status') : null;
  const window = {
    document: doc,
    scrollY: 0,
    addEventListener(name, callback) { windowEvents[name] = callback; },
    NasheSvitloEcoFlowLive: live
  };
  vm.runInNewContext(eco, {window, document:doc, console});
  return {get, events:windowEvents, root};
}

test('inline main page JS syntax is valid', () => {
  const blocks = [...index.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)]
    .filter(match => !/\bsrc\s*=/.test(match[1]));
  assert.ok(blocks.length >= 1);
  for(const block of blocks) assert.doesNotThrow(() => new vm.Script(block[2]));
});

test('all four locations render and switch without DOM exceptions', () => {
  const m = mount();
  assert.equal(m.root.dataset.location, 'dacha');
  assert.match(m.get('eco-devices').innerHTML, /DELTA Pro 3/);
  assert.match(m.get('eco-devices').innerHTML, /Smart Extra Battery/);
  assert.match(m.get('eco-status').innerHTML, /Демо/);
  assert.equal(m.get('eco-count').textContent, '5');
  assert.match(m.get('eco-capacity').textContent, /10.526|10 526|10 526|10 526/);
  m.events['svitlo:location-change']({detail:{id:'home'}});
  assert.match(m.get('eco-devices').innerHTML, /PowerOcean/);
  assert.equal(m.get('eco-count').textContent, '2');
  m.events['svitlo:location-change']({detail:{id:'solovky'}});
  assert.match(m.get('eco-devices').innerHTML, /\+ додаткова батарея/);
  assert.equal(m.get('eco-count').textContent, '3');
  m.events['svitlo:location-change']({detail:{id:'naumenky'}});
  assert.match(m.get('eco-devices').innerHTML, /DELTA 2/);
  assert.equal(m.get('eco-count').textContent, '1');
});

test('partially connected live location shows unknown data, not sample values', () => {
  let subscriber = () => {};
  let mode = 'live';
  let online = {
    'dacha:dp3': { socPercent: 40, inputW: 0, outputW: 500, operation: 'discharging' },
    'dacha:dp3eb': { socPercent: 36, inputW: null, outputW: null, operation: 'unknown' }
  };
  const live = {
    summary: () => ({status:mode}),
    statusFor: key => online[key] ? 'live' : 'waiting',
    reading: key => online[key] || null,
    subscribe: fn => {subscriber = fn;},
    start: () => {}
  };
  const m = mount(live);
  assert.match(m.get('eco-devices').innerHTML, /40%/);
  assert.doesNotMatch(m.get('eco-devices').innerHTML, /36%/);
  assert.doesNotMatch(m.get('eco-devices').innerHTML, />84%/);
  assert.equal(m.get('eco-demo-total').textContent, '—');
  assert.match(m.get('eco-devices').innerHTML, /500 W/);
  assert.match(m.get('eco-status').innerHTML, /2\/5/);
  // Simulate a disconnected gateway; stale numbers must never linger.
  mode = 'stale';
  online = {};
  subscriber();
  assert.doesNotMatch(m.get('eco-devices').innerHTML, /500 W/);
  assert.doesNotMatch(m.get('eco-devices').innerHTML, />40%/);
  assert.equal(m.get('eco-demo-total').textContent, '—');
  assert.match(m.get('eco-status').innerHTML, /застаріли/);
});

test('opened battery metric details are recalculated in place on new readings', () => {
  let notify = () => {};
  let reading = {'home:po': {
    socPercent: 67, moduleSocPercent:[60,74], inputW:0, outputW:450, operation:'discharging'
  }};
  const live = {summary:()=>({status:'live'}),statusFor:key=>reading[key]?'live':'waiting',
    reading:key=>reading[key]||null,subscribe:fn=>{notify=fn;},start:()=>{}};
  const m = mount(live);
  m.events['svitlo:location-change']({detail:{id:'home'}});
  const btn = {dataset:{ecoMetric:'charge'}};
  btn.closest = ()=>btn;
  m.get('eco-metrics-area').listeners.click({target:btn});
  const detail = m.get('eco-metric-detail');
  assert.equal(detail.hidden,false);
  assert.match(detail.innerHTML, /60%/);
  reading = {'home:po': {
    socPercent:50,moduleSocPercent:[40,60], inputW:120,outputW:600,operation:'charging'
  }};
  notify();
  assert.equal(detail.hidden,false);
  assert.match(detail.innerHTML, /40%/);
  assert.match(detail.innerHTML, /60%/);
  assert.doesNotMatch(detail.innerHTML, /74%/);
  assert.doesNotMatch(detail.innerHTML, /NaN|undefined|null/);
});

test('scheduled API snapshot keeps unsupported devices gray and shows 3 unassigned DELTA 2', () => {
  const map = {
    'dacha:dp3': { socPercent: 62, inputW: 0, outputW: 224, operation: 'discharging' },
    'unassigned:delta2-1': { socPercent: 23, inputW: 120, outputW: 0, operation: 'charging' },
    'unassigned:delta2-2': { socPercent: 52, inputW: 0, outputW: 52, operation: 'discharging' },
    'unassigned:delta2-3': { socPercent: 0, inputW: 0, outputW: 0, operation: 'holding' }
  };
  const live = {
    summary: () => ({ status: 'published', lastFrameMs: Date.now(),
      unassigned: ['unassigned:delta2-1', 'unassigned:delta2-2', 'unassigned:delta2-3'] }),
    reading: key => map[key] ?? null,
    statusFor: key => map[key] ? 'published' : 'waiting',
    availabilityFor: key => key === 'dacha:d2' ? 'unassigned' : 'unsupported',
    subscribe() {}, start() {}
  };
  const m = mount(live);
  assert.match(m.get('eco-status').innerHTML, /API · 1\/5/);
  assert.match(m.get('eco-devices').innerHTML, /62%/);
  assert.match(m.get('eco-devices').innerHTML, /eco-api-unavailable/);
  assert.match(m.get('eco-devices').innerHTML, /EcoFlow API повертає 1006/);
  assert.match(m.get('eco-devices').innerHTML, /Локації не підтверджено/);
  assert.match(m.get('eco-devices').innerHTML, /DELTA 2 №3/);
  assert.match(m.get('eco-devices').innerHTML, /Заряд <b>0%<\/b>/);
  assert.equal(m.get('eco-demo-total').textContent, '—');
  m.events['svitlo:location-change']({detail:{id:'home'}});
  assert.match(m.get('eco-devices').innerHTML, /eco-api-unavailable/);
  assert.match(m.get('eco-devices').innerHTML, /EcoFlow API повертає 1006/);
  assert.equal(m.get('eco-demo-total').textContent, '—');
});
