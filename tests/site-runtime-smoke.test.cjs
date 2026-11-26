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
  contains() { return true; }
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

test('legacy EcoFlow Admin controls are absent and generator is a static guide', () => {
  assert.doesNotMatch(index, /id="ecoAdminToggle"|id="eco-admin-bulk"/);
  assert.doesNotMatch(eco, /setAdminMode|adminControls\(|powerOceanAdmin\(|renderBulkPanel\(/);
  assert.match(index, /GRETOR GRT-IG5500IE/);
  assert.match(index, /5 <small>кВт<\/small>/);
  assert.match(index, /32 <small>А<\/small>/);
  assert.match(index, /Ввід через АВР · заплановано/);
  assert.doesNotMatch(index, /Ручний; електро та пульт/);
  assert.match(index, /id="eco-generator-guide"/);
  assert.doesNotMatch(index, /id="eco-gen-|data-eco-gen-target|eco-generator-planner/);
  assert.doesNotMatch(eco, /renderGeneratorPlanner|generatorPlan/);
});

test('inline main page JS syntax is valid', () => {
  const blocks = [...index.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)]
    .filter(match => !/\bsrc\s*=/.test(match[1]));
  assert.ok(blocks.length >= 1);
  for(const block of blocks) assert.doesNotThrow(() => new vm.Script(block[2]));
});

test('all four locations render without a gateway and never show demo readings', () => {
  const m = mount();
  assert.equal(m.root.dataset.location, 'dacha');
  assert.match(m.get('eco-devices').innerHTML, /DELTA Pro 3/);
  assert.doesNotMatch(m.get('eco-devices').innerHTML, /DELTA 3 Plus|RIVER 3|84%/);
  assert.match(m.get('eco-status').innerHTML, /очікуємо дані/);
  assert.equal(m.get('eco-count').textContent, '3');
  assert.match(m.get('eco-capacity').textContent, /9[\s\u00a0\u202f]216/);
  m.events['svitlo:location-change']({detail:{id:'home'}});
  assert.match(m.get('eco-devices').innerHTML, /Немає станцій, доступних через API/);
  assert.equal(m.get('eco-count').textContent, '0');
  m.events['svitlo:location-change']({detail:{id:'solovky'}});
  assert.match(m.get('eco-devices').innerHTML, /DELTA 2/);
  assert.doesNotMatch(m.get('eco-devices').innerHTML, /RIVER 2/);
  assert.equal(m.get('eco-count').textContent, '2');
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
  assert.equal(m.get('eco-demo-total').textContent, '40%');
  assert.equal(m.get('eco-location-charge-label').textContent, 'Середній заряд підключених');
  assert.match(m.get('eco-devices').innerHTML, /500 W/);
  assert.match(m.get('eco-status').innerHTML, /1\/2/);
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
  assert.match(detail.innerHTML, /67%/);
  reading = {'home:po': {
    socPercent:50,moduleSocPercent:[40,60], inputW:120,outputW:600,operation:'charging'
  }};
  notify();
  assert.equal(detail.hidden,false);
  assert.match(detail.innerHTML, /50%/);
  assert.doesNotMatch(detail.innerHTML, /40%|60%|74%/);
  assert.doesNotMatch(detail.innerHTML, /NaN|undefined|null/);
});

test('scheduled API snapshot excludes unsupported devices and shows 3 unassigned DELTA 2', () => {
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
  assert.match(m.get('eco-status').innerHTML, /API · 1\/2/);
  assert.match(m.get('eco-devices').innerHTML, /62%/);
  assert.match(m.get('eco-devices').innerHTML, /eco-api-unavailable/);
  assert.doesNotMatch(m.get('eco-devices').innerHTML, /DELTA 3 Plus|RIVER 3/);
  assert.match(m.get('eco-devices').innerHTML, /Локації не підтверджено/);
  assert.match(m.get('eco-devices').innerHTML, /DELTA 2 №3/);
  assert.match(m.get('eco-devices').innerHTML, /Заряд <b>0%<\/b>/);
  assert.equal(m.get('eco-demo-total').textContent, '62%');
  m.events['svitlo:location-change']({detail:{id:'home'}});
  assert.match(m.get('eco-devices').innerHTML, /Немає станцій, доступних через API/);
  assert.equal(m.get('eco-demo-total').textContent, '—');
});

test('expanded batteries have one rounded provider SOC and clearly doubled capacities', () => {
  const readings = {
    'dacha:dp3': { socPercent: 90.37937, inputW: 0, outputW: 171, runtimeMinutes: 1245, operation: 'discharging' },
    'dacha:d2': { socPercent: 98, inputW: 0, outputW: 0, operation: 'holding' },
    'solovky:d2': { socPercent: 80.46, inputW: 0, outputW: 30, operation: 'discharging' }
  };
  const live = {
    summary: () => ({status: 'published', lastFrameMs: Date.now(), unassigned: []}),
    reading: key => readings[key] ?? null,
    statusFor: key => readings[key] ? 'published' : 'waiting',
    availabilityFor: key => readings[key] ? 'readable' : 'unsupported',
    subscribe() {}, start() {}
  };
  const m = mount(live);
  let markup = m.get('eco-devices').innerHTML;
  assert.match(markup, /Заряд усієї системи/);
  assert.match(markup, /90,4%/);
  assert.match(markup, /Залишок: ≈/);
  assert.match(markup, /7[\s\u00a0\u202f]404 Wh/);
  assert.match(markup, /20 год 45 хв/);
  assert.doesNotMatch(markup, /За графіком/); // no outage context in this fixture
  assert.match(markup, /class="eco-operation eco-operation-discharging"/);
  assert.match(markup, /Розряджається/);
  assert.match(markup, /8[\s\u00a0\u202f]192 Wh/);
  assert.match(markup, /4[\s\u00a0\u202f]096 Wh/);
  assert.equal((markup.match(/class="eco-system-combined-percent"/g) || []).length, 1);
  assert.doesNotMatch(markup, /88,2%|bmsBattSoc/);
  m.events['svitlo:location-change']({detail:{id:'solovky'}});
  markup = m.get('eco-devices').innerHTML;
  assert.match(markup, /80,5%/);
  assert.match(markup, /class="eco-operation eco-operation-discharging"/);
  assert.match(markup, /2[\s\u00a0\u202f]048 Wh/);
  assert.match(markup, /1[\s\u00a0\u202f]024 Wh/);
  assert.equal((markup.match(/class="eco-system-combined-percent"/g) || []).length, 1);
  assert.doesNotMatch(markup, /70%|60%/);
  m.events['svitlo:location-change']({detail:{id:'dacha'}});
  const text = m.get('eco-devices').innerHTML;
  assert.match(text, /DELTA 2/);
  assert.match(text, /1[\s\u00a0\u202f]024 Wh/);
  assert.match(text, /98%/);
});


test('partial monitor keeps physical capacity and pending devices grouped',()=>{
 const live={summary:()=>({status:'published',lastFrameMs:Date.now()}),
  statusFor:key=>key==='dacha:dp3'?'published':'waiting',
  reading:key=>key==='dacha:dp3'?{socPercent:83,inputW:0,outputW:123,operation:'discharging'}:null,
  availabilityFor:()=> 'unsupported',subscribe(){},start(){}};
 const m=mount(live);
 assert.match(m.get('eco-devices').innerHTML,/class="eco-pending"/);
 assert.match(m.get('eco-devices').innerHTML,/Немає свіжих даних/);
 assert.doesNotMatch(m.get('eco-devices').innerHTML,/eco-autonomy-unknown|DELTA 3 Plus|RIVER 3/);
 assert.match(m.get('eco-data-coverage').textContent,/1\/2 станцій/);
});

test('Delta 2 router load of 0 W is not incorrectly called maintaining charge',()=>{
 const readings={'dacha:d2':{socPercent:77,inputW:0,outputW:0,
   runtimeMinutes:320,operation:'holding',updatedMs:Date.now()}};
 const live={summary:()=>({status:'published',lastFrameMs:Date.now(),unassigned:[]}),
  reading:key=>readings[key]??null,
  statusFor:key=>readings[key]?'published':'waiting',
  availabilityFor:key=>readings[key]?'readable':'unsupported',
  subscribe(){},start(){}};
 const m=mount(live);
 const html=m.get('eco-devices').innerHTML;
 assert.match(html,/Низьке навантаження/);
 assert.match(html,/5 год 20 хв/);
 assert.doesNotMatch(html,/Підтримує заряд/);
});

test('no-op EcoFlow outage update does not replace stable station markup', () => {
  const m=mount();
  const el=m.get('eco-devices');
  const original=el.innerHTML;
  let writes=0,markup=original;
  Object.defineProperty(el,'innerHTML',{configurable:true,
    get(){return markup;},set(v){markup=v;writes++;}});
  m.events['svitlo:outage-update']({});
  assert.equal(writes,0);
  assert.equal(el.innerHTML,original);
  m.events['svitlo:location-change']({detail:{id:'home'}});
  assert.equal(writes,1);
  assert.match(el.innerHTML,/Немає станцій, доступних через API/);
});

test('paired battery details start collapsed, can expand and survive location switches',()=>{
  const readings={'dacha:dp3':{socPercent:84,inputW:0,outputW:200,operation:'discharging'}};
  const m=mount({summary:()=>({status:'published'}),reading:key=>readings[key]??null,statusFor:key=>readings[key]?'published':'waiting',subscribe(){},start(){}});
  const html=m.get('eco-devices').innerHTML;
  assert.match(html,/class="eco-card-details"/);
  assert.match(html,/data-eco-card="dacha:dp3"/);
  assert.match(html,/<summary>Склад системи/);
  assert.doesNotMatch(html,/data-eco-card="dacha:dp3" open/);
  const onToggle=m.root.listeners.toggle;
  assert.equal(typeof onToggle,'function');
  onToggle({target:{matches:selector=>selector==='details.eco-card-details',
    dataset:{ecoCard:'dacha:dp3'},open:true}});
  m.events['svitlo:location-change']({detail:{id:'home'}});
  m.events['svitlo:location-change']({detail:{id:'dacha'}});
  assert.match(m.get('eco-devices').innerHTML,/data-eco-card="dacha:dp3" open/);
  onToggle({target:{matches:selector=>selector==='details.eco-card-details',
    dataset:{ecoCard:'dacha:dp3'},open:false}});
  m.events['svitlo:location-change']({detail:{id:'home'}});
  m.events['svitlo:location-change']({detail:{id:'dacha'}});
  assert.doesNotMatch(m.get('eco-devices').innerHTML,/data-eco-card="dacha:dp3" open/);
});

test('static generator tab stays available only for dacha and has no calculator controls', () => {
  const m=mount();
  assert.equal(m.get('eco-select-generator').hidden,false);
  m.get('eco-select-generator').listeners.click();
  assert.equal(m.get('eco-tab-generator').hidden,false);
  assert.equal(m.get('eco-tab-ecoflow').hidden,true);
  m.events['svitlo:location-change']({detail:{id:'home'}});
  assert.equal(m.get('eco-select-generator').hidden,true);
  assert.equal(m.get('eco-tab-generator').hidden,true);
  assert.equal(m.get('eco-tab-ecoflow').hidden,false);
});

test('charging without output hides capped runtime while preserving measured zero watts',()=>{
 const readings={'dacha:dp3':{socPercent:89.4,inputW:1493,outputW:0,runtimeMinutes:5939,operation:'charging'}};
 const m=mount({summary:()=>({status:'published'}),reading:key=>readings[key]??null,statusFor:key=>readings[key]?'published':'waiting',subscribe(){},start(){}});
 const html=m.get('eco-devices').innerHTML;
 assert.match(html,/89,4%/);
 assert.match(html,/1493 W/);
 assert.match(html,/>0 W</);
 assert.doesNotMatch(html,/98 год|eco-autonomy-runtime|eco-autonomy-unknown/);
 assert.equal(m.get('eco-overview-details').hidden,true);
});
