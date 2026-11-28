/* Read-only EcoFlow transport. No credentials, serial numbers or commands in this file.
 * Expected gateway: a secure backend transforms EcoFlow MQTT/HTTP into the
 * minimal, public-safe canonical contract described in docs/ECOFLOW-LIVE.md.
 */
(function (host) {
  'use strict';
  const DEVICE_KEYS = Object.freeze([
    'dacha:dp3', 'dacha:dp3eb', 'dacha:d3p', 'dacha:d2', 'dacha:r3pw',
    'home:po', 'solovky:d2', 'solovky:d2eb', 'solovky:r2', 'naumenky:d2',
    'unassigned:delta2-1', 'unassigned:delta2-2', 'unassigned:delta2-3'
  ]);
  const KNOWN = new Set(DEVICE_KEYS);
  const VALID_OPERATIONS = new Set(['charging', 'discharging', 'holding', 'unknown']);
  const MAX_AGE_MS = 30000;
  const PUBLISHED_MAX_AGE_MS = 25 * 60 * 1000;
  const WORKER_MAX_AGE_MS = 150000;
  const WORKER_KEYS = ['dacha:dp3','dacha:d2','solovky:d2','naumenky:d2'];
  const WORKER_URL = 'https://nashe-svitlo-ecoflow.ssolovko.workers.dev/snapshot';
  let fallbackUrl = null;
  let workerReadings = new Map(), fallbackReadings = new Map();
  let workerAvailability = {}, fallbackAvailability = {}, workerSignature = '', fallbackSignature = '';
  let workerFrameMs = 0, fallbackFrameMs = 0;
  let mode = 'stream';
  let availability = {};
  let unassigned = [];
  const RECONNECT_CHECK_MS = 15000;
  let status = 'preview';
  let telemetry = new Map();
  let eventSource = null;
  let snapshotUrl = null;
  let streamUrl = null;
  let enabled = false;
  let newestEmittedMs = 0;
  let revision = 0;
  let publishedSignature = '';
  let acceptedPublishedFrame = null;
  let snapshotInFlight = null;
  let nextCheckMs = null;
  const MIN_CHECK_MS=700, RESULT_MS=2200;
  let checkStartedMs=null,checkFinishedMs=null,checkResult=null,resultUntilMs=null,checkId=0;
  let pollTimer=null, pollActive=false, pendingNotify=false, started=false;
  const hidden=()=>host.document?.visibilityState==='hidden';
  const pollDelay=()=>mode==='stream'?30000:20000;
  function cancelPoll(){
    if(pollTimer!==null)clearTimeout(pollTimer);
    pollTimer=null;nextCheckMs=null;
  }
  function schedulePoll(){
    cancelPoll();
    if(!enabled||hidden())return;
    nextCheckMs=(resultUntilMs??Date.now())+pollDelay();
    pollTimer=setTimeout(()=>{pollTimer=null;return getSnapshot();},Math.max(0,nextCheckMs-Date.now()));
  }
  const pollSubscribers=new Set();
  const notifyPoll=()=>pollSubscribers.forEach(fn=>{try{fn();}catch(_){}});
  let lastError = null;
  const subscribers = new Set();

  const notify = event => subscribers.forEach(fn => {
    try { fn(event); } catch (error) { console.warn('EcoFlow subscriber error', error); }
  });
  const number = (value, min, max) =>
    typeof value === 'number' && Number.isFinite(value) && value >= min && value <= max ? value : null;
  const isoTime = value => {
    if (typeof value !== 'string' || !/^\d{4}-\d\d-\d\dT/.test(value)) return null;
    const ms = Date.parse(value);
    // Don't accept a future reading or data from a past outage as "live".
    return Number.isFinite(ms) && ms <= Date.now() + 60000 && ms > Date.now() - 86400000 ? ms : null;
  };
  function normaliseReading(raw, emittedMs) {
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null;
    const stamp = Object.prototype.hasOwnProperty.call(raw, 'updatedAt') ?
      isoTime(raw.updatedAt) : emittedMs;
    if (stamp === null) return null;
    const result = {
      updatedMs: stamp,
      socPercent: number(raw.socPercent, 0, 100),
      inputW: number(raw.inputW, 0, 20000),
      outputW: number(raw.outputW, 0, 20000),
      runtimeMinutes: number(raw.runtimeMinutes, 1, 10080),
      operation: VALID_OPERATIONS.has(raw.operation) ? raw.operation : 'unknown',
      estimated: raw.estimated === true,
      moduleSocPercent: null
    };
    if (Array.isArray(raw.moduleSocPercent) && raw.moduleSocPercent.length <= 10) {
      const modules = raw.moduleSocPercent.map(pct => number(pct, 0, 100));
      if (modules.every(pct => pct !== null)) result.moduleSocPercent = modules;
    }
    return result;
  }
  function isFresh(reading) {
    return Boolean(reading && Date.now() - reading.updatedMs <=
      (mode === 'published' ? PUBLISHED_MAX_AGE_MS : MAX_AGE_MS) &&
      Date.now() >= reading.updatedMs - 60000);
  }
  function workerFresh(value) {
    return Boolean(value && Date.now()-value.updatedMs<=WORKER_MAX_AGE_MS && Date.now()>=value.updatedMs-60000);
  }
  function fallbackFresh(value) {
    return Boolean(value && Date.now()-value.updatedMs<=PUBLISHED_MAX_AGE_MS && Date.now()>=value.updatedMs-60000);
  }
  function reading(key) {
    if(mode==='worker') {
      const primary=workerReadings.get(key), backup=fallbackReadings.get(key);
      return workerFresh(primary)?{...primary}:fallbackFresh(backup)?{...backup}:null;
    }
    // Expiry is checked per device, not only by the health of the SSE socket.
    const value = telemetry.get(key);
    return isFresh(value) ? { ...value } : null;
  }
  function statusFor(key) {
    if (!enabled) return 'preview';
    if(mode==='worker') {
      if(workerFresh(workerReadings.get(key))) return 'live';
      if(fallbackFresh(fallbackReadings.get(key))) return 'published';
      return workerReadings.has(key)||fallbackReadings.has(key)?'stale':'waiting';
    }
    const value = telemetry.get(key);
    return !value ? 'waiting' : isFresh(value) ? (mode === 'published' ? 'published' : 'live') : 'stale';
  }
  function summary() {
    const present = DEVICE_KEYS.filter(key => ['live','published'].includes(statusFor(key))).length;
    return { status, mode, lastError, present, total: DEVICE_KEYS.length, lastFrameMs: newestEmittedMs,
      unassigned: [...unassigned], checking: pollActive, nextCheckMs, checkStartedMs, checkFinishedMs, checkResult, checkId, resultUntilMs };
  }
  function refreshStatus() {
    if (!enabled) return;
    const freshCount = DEVICE_KEYS.filter(key => ['live','published'].includes(statusFor(key))).length;
    const next = freshCount ? (mode === 'worker' ? (DEVICE_KEYS.some(key=>statusFor(key)==='live')?'live':'published') : mode === 'published' ? 'published' : 'live') : newestEmittedMs ? 'stale' : 'connecting';
    status = next;
    const signature = [status, revision, ...DEVICE_KEYS.map(key => statusFor(key))].join('|');
    if (signature !== publishedSignature) {
      publishedSignature = signature;
      if(pollActive)pendingNotify=true;else notify();
    }
  }
  function acceptWorkerFrame(raw, source) {
    if(!enabled||!raw||raw.version!==1||raw.mode!==(source==='worker'?'worker-poll':'scheduled')||!raw.devices||typeof raw.devices!=='object'||Array.isArray(raw.devices))return false;
    const emitted=isoTime(raw.emittedAt), primary=source==='worker', maxAge=primary?WORKER_MAX_AGE_MS:PUBLISHED_MAX_AGE_MS;
    if(emitted===null||Date.now()-emitted>maxAge||emitted<(primary?workerFrameMs:fallbackFrameMs)||raw.connection==='unavailable')return false;
    const signature=JSON.stringify(raw);
    if(signature===(primary?workerSignature:fallbackSignature))return Object.entries(raw.devices).some(([key,value])=>(primary?WORKER_KEYS.includes(key):KNOWN.has(key))&&normaliseReading(value,emitted)?.socPercent!=null);
    const next=new Map(primary?workerReadings:fallbackReadings);
    let usable=0;
    for(const [key,entry] of Object.entries(raw.devices)){
      if(!(primary?WORKER_KEYS.includes(key):KNOWN.has(key)))continue;
      const value=normaliseReading(entry,emitted);
      if(!value||value.socPercent===null||Date.now()-value.updatedMs>maxAge||value.updatedMs>emitted+60000)continue;
      if(!next.has(key)||next.get(key).updatedMs<=value.updatedMs)next.set(key,value);
      usable++;
    }
    const allowed=new Set(['unavailable','unsupported','unassigned','readable','not_listed','api_error','invalid_data','rate_limited']);
    const avail=Object.fromEntries(Object.entries(raw.availability||{}).filter(([key,val])=>KNOWN.has(key)&&allowed.has(val)));
    if(primary){workerReadings=next;workerAvailability=avail;workerFrameMs=emitted;workerSignature=signature;}
    else{fallbackReadings=next;fallbackAvailability=avail;fallbackFrameMs=emitted;fallbackSignature=signature;unassigned=Array.isArray(raw.unassigned)?raw.unassigned.filter(key=>KNOWN.has(key)&&key.startsWith('unassigned:')):[];}
    newestEmittedMs=Math.max(workerFrameMs,fallbackFrameMs);
    revision++;refreshStatus();return usable>0;
  }
  function acceptFrame(raw) {
    if(mode==='worker')return acceptWorkerFrame(raw,raw?.mode==='worker-poll'?'worker':'fallback');
    if (!enabled || !raw || raw.version !== 1 ||
        !raw.devices || typeof raw.devices !== 'object' || Array.isArray(raw.devices)) return false;
    const emittedMs = isoTime(raw.emittedAt);
    if (emittedMs === null || Date.now() - emittedMs > (mode === 'published' ? PUBLISHED_MAX_AGE_MS : MAX_AGE_MS) ||
        emittedMs < newestEmittedMs) return false;
    // Skip duplicate published frames; keep live stream events independent.
    const frameSignature = mode === 'published' ? JSON.stringify(raw) : null;
    if (frameSignature !== null && frameSignature === acceptedPublishedFrame) return false;
    let changed = false;
    const next = mode === 'published' ? new Map() : new Map(telemetry);
    for (const [key, entry] of Object.entries(raw.devices)) {
      if (!KNOWN.has(key)) continue; // Unknown devices cannot contaminate another location.
      const value = normaliseReading(entry, emittedMs);
      if (!value || (next.has(key) && next.get(key).updatedMs > value.updatedMs)) continue;
      next.set(key, value);
      changed = true;
    }
    if (mode === 'published') {
      const allowed = new Set(['unavailable','unsupported','unassigned','readable',
          'not_listed','api_error','invalid_data','rate_limited']);
      availability = Object.fromEntries(Object.entries(raw.availability || {})
        .filter(([key,val]) => KNOWN.has(key) && allowed.has(val)));
      unassigned = Array.isArray(raw.unassigned)
        ? raw.unassigned.filter(key => KNOWN.has(key) && key.startsWith('unassigned:')) : [];
      changed = true;
    }
    if (!changed) return false;
    telemetry = next;
    newestEmittedMs = emittedMs;
    if (frameSignature !== null) acceptedPublishedFrame = frameSignature;
    revision++;
    lastError = null;
    refreshStatus();
    return true;
  }
  async function getWorkerSnapshot() {
    let primaryOk=false, fallbackOk=false;
    try{
      const options={cache:'no-store',credentials:'omit'};
      if(typeof AbortSignal!=='undefined'&&typeof AbortSignal.timeout==='function')options.signal=AbortSignal.timeout(25000);
      const response=await fetch(snapshotUrl,options);
      if(response.ok)primaryOk=acceptWorkerFrame(await response.json(),'worker');
    }catch(_){}
    lastError=primaryOk?null:'worker-unavailable';
    if(!primaryOk||WORKER_KEYS.some(key=>!workerFresh(workerReadings.get(key))||workerAvailability[key]!=='readable')){
      try{
        const options={cache:'no-store',credentials:'omit'};
        if(typeof AbortSignal!=='undefined'&&typeof AbortSignal.timeout==='function')options.signal=AbortSignal.timeout(10000);
        const response=await fetch(fallbackUrl+'?t='+Math.floor(Date.now()/20000),options);
        if(response.ok)fallbackOk=acceptWorkerFrame(await response.json(),'fallback');
      }catch(_){}
    }
    refreshStatus();
    return primaryOk||fallbackOk;
  }
  async function getSnapshot() {
    if(!enabled||!snapshotUrl||hidden())return;
    if(snapshotInFlight)return snapshotInFlight;
    cancelPoll();
    const id=++checkId;
    checkStartedMs=Date.now();checkFinishedMs=null;checkResult=null;resultUntilMs=null;
    pollActive=true;pendingNotify=false;
    // Publish primary and fallback together after the minimum visible check.
    snapshotInFlight=(async()=>{
      let ok=false;
      try {
        if(mode==='worker')ok=await getWorkerSnapshot();
        else {
          const cacheBust=mode==='published'?('?t='+Math.floor(Date.now()/20000)):'';
          const options={cache:'no-store',credentials:'omit'};
          if(typeof AbortSignal!=='undefined'&&typeof AbortSignal.timeout==='function')options.signal=AbortSignal.timeout(15000);
          const response=await fetch(snapshotUrl+cacheBust,options);
          if(!response.ok)throw new Error('HTTP '+response.status);
          const frame=await response.json();
          const accepted=acceptFrame(frame);
          const duplicate=mode==='published'&&JSON.stringify(frame)===acceptedPublishedFrame;
          ok=Boolean((accepted||duplicate)&&frame.connection!=='unavailable'&&Object.keys(frame.devices||{}).some(key=>KNOWN.has(key)&&normaliseReading(frame.devices[key],Date.parse(frame.emittedAt))?.socPercent!=null));
        }
      }catch(_){lastError='snapshot-unavailable';ok=false;}
      const remaining=MIN_CHECK_MS-(Date.now()-checkStartedMs);
      if(remaining>0&&!hidden())await new Promise(resolve=>setTimeout(resolve,remaining));
      checkFinishedMs=Date.now();checkResult=ok?'ok':'failed';resultUntilMs=checkFinishedMs+RESULT_MS;
      pollActive=false;snapshotInFlight=null;
      const changed=pendingNotify;pendingNotify=false;
      schedulePoll();
      if(changed)notify({kind:'poll',checkId:id});
      notifyPoll();
    })();
    notifyPoll();
    return snapshotInFlight;
  }
  function connectStream() {
    if (!enabled || !streamUrl || typeof EventSource === 'undefined') return;
    if (eventSource) eventSource.close();
    // SSE auto-reconnects; only an authenticated, read-only gateway may publish data.
    eventSource = new EventSource(streamUrl, { withCredentials: false });
    const consume = event => {
      try { acceptFrame(JSON.parse(event.data)); } catch (_) { lastError = 'invalid-frame'; }
    };
    eventSource.addEventListener('telemetry', consume);
    eventSource.onmessage = consume;
    eventSource.onerror = () => { lastError = 'stream-disconnected'; refreshStatus(); };
    eventSource.onopen = () => { lastError = null; refreshStatus(); getSnapshot(); };
  }
  function validUrl(value) {
    if (typeof value !== 'string' || !value.trim()) return false;
    try {
      const parsed = new URL(value, host.location.href);
      return parsed.protocol === 'https:' && !parsed.username && !parsed.password &&
        parsed.searchParams.toString() === '' && !parsed.hash;
    } catch (_) { return false; }
  }
  async function start() {
    if(started)return;started=true;
    try {
      const response = await fetch('./ecoflow-live-config.json', { cache: 'no-store' });
      if (!response.ok) throw new Error('Configuration unavailable');
      const config = await response.json();
      if (config.enabled !== true) { status = 'preview'; notify(); return; }
      mode = config.mode === 'worker' ? 'worker' : config.mode === 'published' ? 'published' : 'stream';
      if (!validUrl(config.snapshotUrl) || (mode === 'stream' && !validUrl(config.streamUrl)))
        throw new Error('Invalid read-only gateway URLs');
      if (mode === 'published' && new URL(config.snapshotUrl, host.location.href).origin !== host.location.origin)
        throw new Error('Published snapshot must be same-origin');
      if(mode==='worker'){
        if(config.snapshotUrl!==WORKER_URL||config.fallbackUrl!=='./ecoflow-snapshot.json'||config.streamUrl!=='')throw new Error('Invalid Worker configuration');
        fallbackUrl=new URL(config.fallbackUrl,host.location.href).href;
      }
      enabled = true;
      snapshotUrl = new URL(config.snapshotUrl, host.location.href).href;
      streamUrl = mode === 'stream' ? new URL(config.streamUrl, host.location.href).href : null;
      status = 'connecting';
      notify();
      await getSnapshot();
      if (mode === 'stream') connectStream();
      setInterval(refreshStatus, RECONNECT_CHECK_MS);
      host.document?.addEventListener?.('visibilitychange', () => {
        if(hidden()){cancelPoll();notifyPoll();}
        else {refreshStatus();getSnapshot();}
      });
      if(!snapshotInFlight&&pollTimer===null&&!hidden())schedulePoll();
    } catch (error) {
      cancelPoll();enabled = false; status = 'error'; lastError = 'configuration-error'; notify();
    }
  }
  function subscribe(fn) {
    subscribers.add(fn);
    return () => subscribers.delete(fn);
  }
  host.NasheSvitloEcoFlowLive = Object.freeze({
    start, subscribe, reading, statusFor, summary,
    subscribePoll(fn){pollSubscribers.add(fn);return ()=>pollSubscribers.delete(fn);},
    availabilityFor: key => mode==='worker'?(statusFor(key)==='published'?fallbackAvailability[key]||'readable':workerAvailability[key]||fallbackAvailability[key]||'unavailable'):availability[key] || 'unavailable',
    // For deterministic tests only; never exposed as a control to the UI.
    acceptFrame, deviceKeys: DEVICE_KEYS
  });
})(window);
