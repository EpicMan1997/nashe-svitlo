/* Read-only EcoFlow transport. No credentials, serial numbers or commands in this file.
 * Expected gateway: a secure backend transforms EcoFlow MQTT/HTTP into the
 * minimal, public-safe canonical contract described in docs/ECOFLOW-LIVE.md.
 */
(function (host) {
  'use strict';
  const DEVICE_KEYS = Object.freeze([
    'dacha:dp3', 'dacha:dp3eb', 'dacha:d3p', 'dacha:d2', 'dacha:r3pw',
    'home:po', 'solovky:d2', 'solovky:d2eb', 'solovky:r2', 'naumenky:d2'
  ]);
  const KNOWN = new Set(DEVICE_KEYS);
  const VALID_OPERATIONS = new Set(['charging', 'discharging', 'holding', 'unknown']);
  const MAX_AGE_MS = 30000;
  const RECONNECT_CHECK_MS = 3000;
  let status = 'preview';
  let telemetry = new Map();
  let eventSource = null;
  let snapshotUrl = null;
  let streamUrl = null;
  let enabled = false;
  let newestEmittedMs = 0;
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
      operation: VALID_OPERATIONS.has(raw.operation) ? raw.operation : 'unknown',
      moduleSocPercent: null
    };
    if (Array.isArray(raw.moduleSocPercent) && raw.moduleSocPercent.length <= 10) {
      const modules = raw.moduleSocPercent.map(pct => number(pct, 0, 100));
      if (modules.every(pct => pct !== null)) result.moduleSocPercent = modules;
    }
    return result;
  }
  function isFresh(reading) {
    return Boolean(reading && Date.now() - reading.updatedMs <= MAX_AGE_MS &&
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
    return !value ? 'waiting' : isFresh(value) ? 'live' : 'stale';
  }
  function summary() {
    const present = DEVICE_KEYS.filter(key => statusFor(key) === 'live').length;
    return { status, lastError, present, total: DEVICE_KEYS.length, lastFrameMs: newestEmittedMs };
  }
  function refreshStatus() {
    if (!enabled) return;
    const freshCount = DEVICE_KEYS.filter(key => statusFor(key) === 'live').length;
    const next = freshCount ? 'live' : newestEmittedMs ? 'stale' : 'connecting';
    if (status !== next) { status = next; notify(); }
    // Update device tiles when an individual reading turns stale even if others remain fresh.
    else notify();
  }
  function acceptFrame(raw) {
    if (!enabled || !raw || raw.version !== 1 ||
        !raw.devices || typeof raw.devices !== 'object' || Array.isArray(raw.devices)) return false;
    const emittedMs = isoTime(raw.emittedAt);
    if (emittedMs === null || Date.now() - emittedMs > MAX_AGE_MS ||
        emittedMs < newestEmittedMs) return false;
    let changed = false;
    const next = new Map(telemetry);
    for (const [key, entry] of Object.entries(raw.devices)) {
      if (!KNOWN.has(key)) continue; // Unknown devices cannot contaminate another location.
      const value = normaliseReading(entry, emittedMs);
      if (!value || (next.has(key) && next.get(key).updatedMs > value.updatedMs)) continue;
      next.set(key, value);
      changed = true;
    }
    if (!changed) return false;
    telemetry = next;
    newestEmittedMs = emittedMs;
    lastError = null;
    refreshStatus();
    return true;
  }
  async function getSnapshot() {
    if (!enabled || !snapshotUrl) return;
    try {
      const response = await fetch(snapshotUrl, { cache: 'no-store', credentials: 'omit' });
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
      if (!validUrl(config.snapshotUrl) || !validUrl(config.streamUrl))
        throw new Error('Invalid read-only gateway URLs');
      enabled = true;
      snapshotUrl = new URL(config.snapshotUrl, host.location.href).href;
      streamUrl = new URL(config.streamUrl, host.location.href).href;
      status = 'connecting';
      notify();
      await getSnapshot();
      connectStream();
      // Backup snapshot: transport freshness is evaluated every 3 seconds.
      setInterval(refreshStatus, RECONNECT_CHECK_MS);
      setInterval(getSnapshot, 30000);
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
    // For deterministic tests only; never exposed as a control to the UI.
    acceptFrame, deviceKeys: DEVICE_KEYS
  });
})(window);
