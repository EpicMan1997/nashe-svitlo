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
  let mode = 'stream';
  let availability = {};
  let unassigned = [];
  const RECONNECT_CHECK_MS = 3000;
  let status = 'preview';
  let telemetry = new Map();
  let eventSource = null;
  let snapshotUrl = null;
  let streamUrl = null;
  let enabled = false;
  let newestEmittedMs = 0;
  let revision = 0;
  let publishedSignature = '';
  let lastError = null;
  const subscribers = new Set();

  const notify = () => subscribers.forEach(fn => {
    try { fn(); } catch (error) { console.warn('EcoFlow subscriber error', error); }
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
  function reading(key) {
    // Expiry is checked per device, not only by the health of the SSE socket.
    const value = telemetry.get(key);
    return isFresh(value) ? { ...value } : null;
  }
  function statusFor(key) {
    if (!enabled) return 'preview';
    const value = telemetry.get(key);
    return !value ? 'waiting' : isFresh(value) ? (mode === 'published' ? 'published' : 'live') : 'stale';
  }
  function summary() {
    const present = DEVICE_KEYS.filter(key => ['live','published'].includes(statusFor(key))).length;
    return { status, mode, lastError, present, total: DEVICE_KEYS.length, lastFrameMs: newestEmittedMs,
      unassigned: [...unassigned] };
  }
  function refreshStatus() {
    if (!enabled) return;
    const freshCount = DEVICE_KEYS.filter(key => ['live','published'].includes(statusFor(key))).length;
    const next = freshCount ? (mode === 'published' ? 'published' : 'live') : newestEmittedMs ? 'stale' : 'connecting';
    status = next;
    const signature = [status, revision, ...DEVICE_KEYS.map(key => statusFor(key))].join('|');
    if (signature !== publishedSignature) {
      publishedSignature = signature;
      notify();
    }
  }
  function acceptFrame(raw) {
    if (!enabled || !raw || raw.version !== 1 ||
        !raw.devices || typeof raw.devices !== 'object' || Array.isArray(raw.devices)) return false;
    const emittedMs = isoTime(raw.emittedAt);
    if (emittedMs === null || Date.now() - emittedMs > (mode === 'published' ? PUBLISHED_MAX_AGE_MS : MAX_AGE_MS) ||
        emittedMs < newestEmittedMs) return false;
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
      const allowed = new Set(['unavailable','unsupported','unassigned','readable']);
      availability = Object.fromEntries(Object.entries(raw.availability || {})
        .filter(([key,val]) => KNOWN.has(key) && allowed.has(val)));
      unassigned = Array.isArray(raw.unassigned)
        ? raw.unassigned.filter(key => KNOWN.has(key) && key.startsWith('unassigned:')) : [];
      changed = true;
    }
    if (!changed) return false;
    telemetry = next;
    newestEmittedMs = emittedMs;
    revision++;
    lastError = null;
    refreshStatus();
    return true;
  }
  async function getSnapshot() {
    if (!enabled || !snapshotUrl) return;
    try {
      const cacheBust = mode === 'published' ? ('?t=' + Math.floor(Date.now() / 60000)) : '';
      const response = await fetch(snapshotUrl + cacheBust, { cache: 'no-store', credentials: 'omit' });
      if (!response.ok) throw new Error('HTTP ' + response.status);
      acceptFrame(await response.json());
    } catch (error) {
      lastError = 'snapshot-unavailable';
      refreshStatus();
    }
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
    try {
      const response = await fetch('./ecoflow-live-config.json', { cache: 'no-store' });
      if (!response.ok) throw new Error('Configuration unavailable');
      const config = await response.json();
      if (config.enabled !== true) { status = 'preview'; notify(); return; }
      mode = config.mode === 'published' ? 'published' : 'stream';
      if (!validUrl(config.snapshotUrl) || (mode === 'stream' && !validUrl(config.streamUrl)))
        throw new Error('Invalid read-only gateway URLs');
      if (mode === 'published' && new URL(config.snapshotUrl, host.location.href).origin !== host.location.origin)
        throw new Error('Published snapshot must be same-origin');
      enabled = true;
      snapshotUrl = new URL(config.snapshotUrl, host.location.href).href;
      streamUrl = mode === 'stream' ? new URL(config.streamUrl, host.location.href).href : null;
      status = 'connecting';
      notify();
      await getSnapshot();
      if (mode === 'stream') connectStream();
      // Published GitHub Actions snapshots are NOT live. Re-fetch every minute.
      setInterval(refreshStatus, RECONNECT_CHECK_MS);
      setInterval(getSnapshot, mode === 'published' ? 60000 : 30000);
      host.document?.addEventListener?.('visibilitychange', () => {
        if (host.document.visibilityState === 'visible') getSnapshot();
      });
    } catch (error) {
      enabled = false; status = 'error'; lastError = 'configuration-error'; notify();
    }
  }
  function subscribe(fn) {
    subscribers.add(fn);
    return () => subscribers.delete(fn);
  }
  host.NasheSvitloEcoFlowLive = Object.freeze({
    start, subscribe, reading, statusFor, summary,
    availabilityFor: key => availability[key] || 'unavailable',
    // For deterministic tests only; never exposed as a control to the UI.
    acceptFrame, deviceKeys: DEVICE_KEYS
  });
})(window);
