/* EcoFlow static data model until cloud telemetry is connected; no remote commands. */
(function () {
  'use strict';

  // Initial numeric UI values are static until EcoFlow telemetry is connected; never claim they are live.
  // capacityWh contains nominal manufacturer capacity, never inverter output.
  const demoInventory = Object.freeze({
    dacha: {
      name: 'Дача', space: 'Дача',
      devices: [
        // DELTA Pro 3 + one compatible 4096 Wh Smart Extra Battery; solar input rating is separate from capacity.
        { name: 'DELTA Pro 3', capacityWh: 4096, pct: 84, inputW: 0, outputW: 620, type: 'station', id: 'dp3', operation: 'discharging',
          solar: { maxW: 2600, highMaxW: 1600, lowMaxW: 1000, currentW: 1240, highW: 820, lowW: 420, todayWh: 4800, connected: false } },
        // Same stationary backup system, but a distinct physical battery for location-level totals.
        // Percentage mirrors the main station as a placeholder until real EcoFlow telemetry exists.
        { name: 'Smart Extra Battery DELTA Pro 3', capacityWh: 4096, pct: 84, type: 'battery',
          parent: 'DELTA Pro 3', parentId: 'dp3', id: 'dp3eb', operation: 'discharging' },
        { name: 'DELTA 3 Plus', capacityWh: 1024, pct: 92, inputW: 120, outputW: 38, type: 'station', id: 'd3p', operation: 'charging' },
        { name: 'DELTA 2', capacityWh: 1024, pct: 64, inputW: 0, outputW: 75, type: 'station', id: 'd2', operation: 'discharging' },
        { name: 'RIVER 3 Plus Wireless', capacityWh: 286, pct: 29, inputW: 0, outputW: 12, type: 'station', id: 'r3pw', operation: 'discharging' }
      ]
    },
    home: {
      name: 'Дім', space: 'Квартира',
      devices: [
        { name: 'PowerOcean', capacityWh: 5000, inverterKw: 6, systemPowerKw: 6, batteryCount: 1, pct: 67, inputW: 300, outputW: 760, type: 'system', id: 'po', operation: 'discharging' }
      ]
    },
    solovky: {
      name: 'Соловки', space: 'Соловки',
      devices: [
        { name: 'DELTA 2', capacityWh: 1024, pct: 54, inputW: 0, outputW: 125, type: 'station', id: 'd2', operation: 'discharging' },
        { name: 'Додаткова батарея DELTA 2', capacityWh: 1024, pct: 49, type: 'battery', parent: 'DELTA 2', parentId: 'd2', id: 'd2eb', operation: 'discharging' },
        { name: 'RIVER 2', capacityWh: 256, pct: 18, inputW: 0, outputW: 26, type: 'station', id: 'r2', operation: 'discharging' }
      ]
    },
    naumenky: {
      name: 'Науменки', space: 'Науменки',
      devices: [
        { name: 'DELTA 2', capacityWh: 1024, pct: 71, inputW: 93, outputW: 93, type: 'station', id: 'd2', operation: 'holding' }
      ]
    }
  });

  // Specifications are local. Dynamic values are supplied only by a read-only
  // gateway with validated, freshness-checked, location-scoped telemetry.
  const live = window.NasheSvitloEcoFlowLive || null;
  let inventory = demoInventory;
  let liveMode = false;
  const fmtSoc = new Intl.NumberFormat('uk-UA', { maximumFractionDigits: 1 });
  const pctLabel = value => Number.isFinite(value) ? fmtSoc.format(value) + '%' : '—';
  const wattsLabel = value => Number.isFinite(value) ? value + ' W' : '—';
  // Local-only SOC trend survives page refreshes; it never invents an output wattage.
  const socBaseline = new Map();
  const socMemoryKey = key => 'nashe-svitlo-ecoflow-soc-v1:' + key;
  function readSocBaseline(key) {
    if (socBaseline.has(key)) return socBaseline.get(key);
    try {
      const saved = JSON.parse(window.localStorage?.getItem(socMemoryKey(key)) || 'null');
      if (saved && Number.isFinite(saved.soc) && Number.isFinite(saved.at) &&
          Date.now()>=saved.at && Date.now()-saved.at<=3*3600000) {
        socBaseline.set(key,saved);
        return saved;
      }
    } catch (_) {}
    return null;
  }
  function rememberSoc(key,reading) {
    socBaseline.set(key,reading);
    try { window.localStorage?.setItem(socMemoryKey(key),JSON.stringify(reading)); } catch (_) {}
  }
  function operationFromReading(key,value) {
    if (!value) return {state:'unknown',inferred:false};
    const state=value.operation||'unknown',at=value.updatedMs||Date.parse(value.updatedAt||'')||Date.now();
    const soc=value.socPercent;
    if (!Number.isFinite(soc)||!Number.isFinite(at)) return {state,inferred:false};
    const prev=readSocBaseline(key),idleWatts=value.inputW===0&&value.outputW===0;
    const falling=idleWatts&&prev&&at>prev.at+5*60000&&at-prev.at<=3*3600000&&prev.soc-soc>=0.5;
    if (!prev||at>prev.at&&(soc>prev.soc+0.1||!idleWatts||at-prev.at>3*3600000))
      rememberSoc(key,{soc,at});
    if (falling&&['holding','unknown'].includes(state))
      return {state:'discharging',inferred:true};
    // The known Dacha DELTA 2 feeds a router and converter. 0 W alone
    // is insufficient evidence that its charge is actually holding steady.
    if (key==='dacha:d2'&&idleWatts&&state==='holding')
      return {state:'unknown',inferred:false,lowLoad:true};
    return {state,inferred:false};
  }
  function applyReadings() {
    const state = live?.summary()?.status || 'preview';
    liveMode = state !== 'preview';
    if (!liveMode) {
      inventory = demoInventory;
      return;
    }
    inventory = Object.fromEntries(Object.entries(demoInventory).map(([key, place]) => [
      key, { ...place, devices: place.devices.map(device => {
        const value = live.reading(key + ':' + device.id);
        const flow = operationFromReading(key + ':' + device.id, value);
        return {
          ...device,
          pct: value?.socPercent ?? (device.type === 'system' &&
            Array.isArray(value?.moduleSocPercent) && value.moduleSocPercent.length === device.batteryCount ?
            value.moduleSocPercent.reduce((sum, p) => sum + p, 0) / device.batteryCount : null),
          inputW: value?.inputW ?? null,
          outputW: value?.outputW ?? null,
          runtimeMinutes: value?.runtimeMinutes ?? null,
          operation: flow.state,
          inferredOperation: flow.inferred,
          lowLoad: flow.lowLoad===true,
          estimated: value?.estimated === true,
          availability: live.availabilityFor?.(key + ':' + device.id) || 'unavailable',
          // Unknown module SOC is never invented from a primary BMS value.
          modulePercentages: device.type === 'system' ? (value?.moduleSocPercent ?? []) : undefined
        };
      }) }
    ]));
  }
  function renderConnection() {
    const element = root.querySelector('.eco-status');
    if (!element) return;
    const mode = live?.summary()?.status || 'preview';
    const labels = {
      preview: 'Демо · API не підключено',
      connecting: 'Підключення…',
      live: 'Live · EcoFlow',
      published: 'EcoFlow API · за розкладом',
      stale: 'Дані застаріли',
      error: 'Налаштування відсутнє'
    };
    const devicesHere = batterySystems(demoInventory[activeEcoLocation]?.devices || []);
    const liveHere = devicesHere.filter(device =>
      ['live','published'].includes(live?.statusFor(activeEcoLocation + ':' + device.id))).length;
    const stateHere = ['live','published'].includes(mode) && liveHere === 0 ? 'stale' : mode;
    element.classList.toggle('is-live', stateHere === 'live');
    element.classList.toggle('is-published', stateHere === 'published');
    element.classList.toggle('is-stale', stateHere === 'stale');
    element.title = mode === 'preview' ?
      'Тестові показники, не реальна телеметрія EcoFlow' :
      mode === 'live' ? 'Дані зі шлюзу EcoFlow; стан перевіряється окремо для кожної станції' :
      mode === 'published' ? 'Реальні показники з EcoFlow API, GitHub Actions оновлює приблизно кожні 10 хвилин. Не миттєві.' :
      'Немає свіжих даних. Показники приховано.';
    const at = live?.summary()?.lastFrameMs;
    const hhmm = Number.isFinite(at) && at > 0 ? new Date(at).toLocaleTimeString('uk-UA', {hour:'2-digit',minute:'2-digit'}) : '—';
    element.innerHTML = '<i aria-hidden="true"></i>' + (mode === 'published'
      ? ('API · ' + liveHere + '/' + devicesHere.length + ' · ' + hhmm + ' · ≈10 хв')
      : mode === 'live' ? ('Live · ' + liveHere + '/' + devicesHere.length + ' станцій')
      : labels[mode] || 'Немає зв’язку');
    root.dataset.telemetryState = stateHere;
  }

  // Physical battery inventory for overview metrics (PowerOcean has one 5000 Wh module).
  function physicalDevices(devices) {
    return devices.flatMap(device => {
      if (device.type !== 'system' || device.batteryCount <= 1) return [device];
      const perModule = device.capacityWh / device.batteryCount;
      return Array.from({ length: device.batteryCount }, (_, i) => ({
        ...device,
        id: device.id + '-module-' + (i + 1),
        name: device.name + ' · акумулятор ' + (i + 1),
        type: 'battery',
        capacityWh: perModule,
        pct: Array.isArray(device.modulePercentages) && Number.isFinite(device.modulePercentages[i])
          ? device.modulePercentages[i] : (liveMode ? null : device.pct)
      }));
    });
  }

  // A station with an extra battery is ONE energy system with ONE provider SOC.
  // Sum physical capacities, but never manufacture per-module percentages.
  function batterySystems(devices) {
    const addons = new Map(devices.filter(d => d.type === 'battery' && d.parentId)
      .map(d => [d.parentId, d]));
    const ids = new Set(devices.map(d => d.id));
    return devices.filter(d => !(d.type === 'battery' && ids.has(d.parentId))).map(d => {
      const addon = addons.get(d.id);
      return addon ? {
        ...d, name: d.name + ' + ' + (d.id === 'dp3' ? 'Smart Extra Battery' : 'додаткова батарея'),
        capacityWh: d.capacityWh + addon.capacityWh,
        batteryCount: 2, hasAddon: true, addonName: addon.name
      } : d;
    });
  }

  const root = document.getElementById('ecoflow');
  if (!root) return;

  const $ = id => document.getElementById(id);
  // Power uses W; battery capacity and energy use Wh. Internal capacityWh values stay in watt-hours.
  // Never scale values to kilowatts; capacityWh always stores physical watt-hours.
  const uk = new Intl.NumberFormat('uk-UA', { maximumFractionDigits: 2 });
  function niceWh(wh) {
    return Number.isFinite(wh) ? uk.format(wh) + ' Wh' : '—';
  }
  function capClass(wh) {
    if (wh === null) return 'size-unknown';
    if (wh >= 3500) return 'size-large';
    if (wh >= 800) return 'size-medium';
    return 'size-small';
  }
  function level(pct) {
    if (!Number.isFinite(pct)) return 'unknown';
    if (pct >= 80) return 'high';
    if (pct >= 55) return 'good';
    if (pct >= 35) return 'medium';
    if (pct >= 20) return 'low';
    return 'critical';
  }

  const operationMeta = {
    charging: { label: 'Заряджається', sign: '↑' },
    discharging: { label: 'Розряджається', sign: '↓' },
    holding: { label: 'Підтримує заряд', sign: '•' },
    unknown: { label: 'Статус невідомий', sign: '?' }
  };
  function operationBadge(device) {
    const status = Object.prototype.hasOwnProperty.call(operationMeta, device.operation)
      ? device.operation : 'unknown';
    const { label, sign } = device.lowLoad
      ? {label:'Низьке навантаження',sign:'~'} : operationMeta[status];
    return '<span class="eco-operation eco-operation-' + status + '"' +
      (device.inferredOperation ? ' title="Розряджання визначено за зменшенням заряду"' : '') + '>' +
      '<span class="eco-operation-icon" aria-hidden="true">' + sign + '</span>' +
      label + '</span>';
  }

  function formatAutonomy(capacityWh, chargePct, outputW) {
    if (!Number.isFinite(outputW)||outputW<=0||!Number.isFinite(chargePct)) return '—';
    // Fallback only; EcoFlow's own time-to-empty is preferred when available.
    const estimatedMinutes=Math.round(capacityWh*chargePct/100*0.85/outputW*60/5)*5;
    return timeText(estimatedMinutes);
  }
  function timeText(minutes) {
    if (!Number.isFinite(minutes)||minutes<0) return '—';
    const value=Math.round(minutes),hours=Math.floor(value/60),mins=value%60;
    return (hours?hours+' год':'')+(mins?(hours?' ':'')+mins+' хв':'')||'0 хв';
  }
  function remainingEnergy(capacityWh,pct) {
    return Number.isFinite(pct)&&Number.isFinite(capacityWh)
      ? '≈ '+niceWh(Math.round(capacityWh*pct/100))+' із '+niceWh(capacityWh)
      : 'Заряд невідомий';
  }
  function runtimeReading(d,capWh,pct) {
    if (Number.isFinite(d.runtimeMinutes)&&d.runtimeMinutes>0)
      return {minutes:d.runtimeMinutes,source:'Прогноз EcoFlow'};
    const estimate=Number.isFinite(d.outputW)&&d.outputW>0&&Number.isFinite(pct)
      ? Math.round(capWh*pct/100*0.85/d.outputW*60/5)*5:null;
    return {minutes:estimate,source:estimate===null?'Немає прогнозу':'Оцінка за потужністю'};
  }
  function autonomyComparison(runtime) {
    const outage=window.NasheSvitloOutageContext?.(activeEcoLocation);
    if (!outage||!Number.isFinite(outage.minutes)||outage.minutes<=0)
      return {color:'unknown',value:'—',hint:'Немає підтвердженого графіка'};
    const label=(outage.current?'До відновлення: ':'Наступне відключення: ')+timeText(outage.minutes);
    if (!Number.isFinite(runtime.minutes))
      return {color:'unknown',value:'—',hint:label+' · прогноз недоступний'};
    const diff=runtime.minutes-outage.minutes;
    return {color:diff<0?'danger':diff<outage.minutes*0.25?'warning':'safe',
      value:diff<0?'Не вистачить':'Вистачить',
      hint:label+' · '+(diff<0?'бракує ':'запас ')+timeText(Math.abs(diff))};
  }
  function autonomyCards(d,capWh,pct) {
    const runtime=runtimeReading(d,capWh,pct),comp=autonomyComparison(runtime);
    return '<div class="eco-device-stat eco-autonomy-runtime"><span>За навантаженням</span>' +
      '<strong>'+timeText(runtime.minutes)+'</strong><small>'+runtime.source+'</small></div>' +
      '<div class="eco-device-stat eco-autonomy eco-autonomy-'+comp.color+'"><span>За графіком</span>' +
      '<strong>'+comp.value+'</strong><small>'+comp.hint+'</small></div>';
  }
  const powerSeen = new Map();
  function powerReading(d,kind) {
    const value = kind==='in'?d.inputW:d.outputW;
    const key=activeEcoLocation+':'+d.id+':'+kind,old=powerSeen.get(key);
    const changed=liveMode && Number.isFinite(value) && Number.isFinite(old) && value!==old;
    powerSeen.set(key,value);
    return '<strong class="eco-power-reading' + (changed?' eco-power-changed':'') + '">' + wattsLabel(value) + '</strong>';
  }
  function chargeTrack(pct, name) {
    return '<div class="eco-charge-track" role="progressbar" aria-label="Заряд ' + name +
      '" aria-valuemin="0" aria-valuemax="100"' +
      (Number.isFinite(pct) ? ' aria-valuenow="' + pct + '"' : ' aria-valuetext="Заряд невідомий"') + '>' +
      '<i style="width:' + (Number.isFinite(pct) ? pct : 0) + '%"></i></div>';
  }

  function energyStats(d, capWh, pct) {
    const output = d.outputW;
    return '<div class="eco-device-stats eco-common-stats">' +
      '<div class="eco-device-stat"><span>Вхід</span>' + powerReading(d,'in') + '</div>' +
      '<div class="eco-device-stat"><span>Вихід</span>' + powerReading(d,'out') + '</div>' +
      autonomyCards(d,capWh,pct) + '</div>';
  }

  // The solar component is retained for later, but hidden until panels actually exist.
  const solarUiEnabled = false;
  const solarPowerLabel = watt => Number.isFinite(watt)
    ? uk.format(watt) + ' W' : '—';

  function solarDisclosure(device) {
    if (!solarUiEnabled || !device.solar) return '';
    const source = $('eco-solar-template');
    if (!source) return '';
    return '<details class="eco-solar-disclosure">' +
      '<summary><span class="eco-solar-summary-label"><span class="eco-solar-summary-sun" aria-hidden="true">☀</span>' +
      'Сонячна генерація</span><span class="eco-solar-summary-end">' + solarPowerLabel(device.solar.currentW) +
      ' / ' + solarPowerLabel(device.solar.maxW) +
      '<span class="eco-solar-chevron" aria-hidden="true"></span></span></summary>' +
      source.innerHTML + '</details>';
  }

  function availabilityNote(d) {
    if (!liveMode || Number.isFinite(d.pct)) return '';
    const explanation = d.availability === 'unsupported'
      ? 'EcoFlow API повертає 1006'
      : d.availability === 'unassigned'
        ? 'Дані є, але станцію ще не прив’язано до локації'
        : d.type === 'battery'
          ? 'Окремих даних батареї поки немає'
          : 'Немає актуальних даних';
    return '<div class="eco-api-note"><span class="eco-api-dot" aria-hidden="true"></span>' +
      explanation + '</div>';
  }
  function unassignedSection() {
    if (!liveMode) return '';
    const keys = live?.summary()?.unassigned || [];
    if (!keys.length) return '';
    const rows = keys.map((key, i) => {
      const reading = live.reading(key);
      const soc = reading?.socPercent;
      return '<div class="eco-unassigned-row' + (reading ? '' : ' is-unavailable') + '">' +
        '<strong>DELTA 2 №' + (i + 1) + '</strong>' +
        '<span>Заряд <b>' + pctLabel(soc) + '</b></span>' +
        '<span>Вхід <b>' + wattsLabel(reading?.inputW) + '</b></span>' +
        '<span>Вихід <b>' + wattsLabel(reading?.outputW) + '</b></span></div>';
    }).join('');
    return '<section class="eco-unassigned" aria-label="DELTA 2 без прив’язки">' +
      '<div class="eco-unassigned-header"><strong>Доступні через API · DELTA 2</strong>' +
      '<span>Локації не підтверджено</span></div><p>Ці три станції передають реальні дані, але поки не зіставлені з локаціями. До середнього заряду локацій не включені.</p>' +
      '<div class="eco-unassigned-list">' + rows + '</div></section>';
  }

  function deviceView(d) {
    const size = capClass(d.capacityWh);
    const charge = level(d.pct);
    const capacity = niceWh(d.capacityWh);
    const titleNote = 'Зарядна станція';
    return '<article class="eco-device eco-standalone ' + size + ' charge-' + charge +
      (liveMode && !Number.isFinite(d.pct) ? ' eco-api-unavailable' : '') +
      '" aria-label="' + d.name + ', заряд ' + pctLabel(d.pct) + '">' +
      '<div class="eco-device-head"><div class="eco-device-ident">' +
      '<strong class="eco-device-name">' + d.name + '</strong>' +
      '<span class="eco-device-model">' + titleNote + '</span></div>' + operationBadge(d) + '</div>' +
      '<div class="eco-battery"><span class="eco-battery-percent">' + pctLabel(d.pct) +
      '</span><span class="eco-battery-art" aria-hidden="true"><i style="width:' +
      (Number.isFinite(d.pct) ? d.pct : 0) + '%"></i></span></div>' +
      chargeTrack(d.pct, d.name) +
      '<div class="eco-capacity-line"><strong>' + capacity + '</strong><small class="eco-remaining-energy">Залишок: ' + remainingEnergy(d.capacityWh,d.pct) + '</small></div>' +
      energyStats(d, d.capacityWh, d.pct) +
      solarDisclosure(d) +
      availabilityNote(d) +
      '</article>';
  }

  function powerOceanView(d) {
    const cap = niceWh(d.capacityWh);
    return '<article class="eco-powerocean charge-' + level(d.pct) + (liveMode && !Number.isFinite(d.pct) ? ' eco-api-unavailable' : '') + '" aria-label="PowerOcean, домашня система, заряд ' + pctLabel(d.pct) + '">' +
      '<div class="eco-ocean-top"><div><span class="eco-ocean-overline">Домашня енергосистема</span>' +
      '<h3>PowerOcean</h3><span class="eco-ocean-cap">' + d.batteryCount + (d.batteryCount === 1 ? ' акумулятор' : ' акумулятори') + ' · ' + cap + ' · інвертор ' + uk.format(d.inverterKw * 1000) + ' W' +
      '</span></div>' + operationBadge(d) + '</div>' +
      '<div class="eco-ocean-body"><div class="eco-ocean-battery"><span class="eco-ocean-label">Акумулятор</span>' +
      '<div class="eco-battery"><span class="eco-battery-percent">' + pctLabel(d.pct) + '</span></div>' +
      chargeTrack(d.pct, d.name) + '<span>' + cap + '</span><small class="eco-remaining-energy">Залишок: ' + remainingEnergy(d.capacityWh,d.pct) + '</small></div>' +
      '<div class="eco-ocean-energy"><div><span>Мережа / заряд</span>' + powerReading(d,'in') + '</div>' +
      '<div class="eco-ocean-flow" aria-hidden="true">→</div><div><span>Будинок</span>' +
      powerReading(d,'out') + '</div></div></div>' +
      '<div class="eco-ocean-autonomy eco-ocean-autonomy-split">' + autonomyCards(d,d.capacityWh,d.pct) + '</div>' +
      availabilityNote(d) +
      '</article>';
  }

  function systemView(main, addon) {
    const capacityWh = main.capacityWh + addon.capacityWh;
    const soc = main.pct; // Single provider-reported SOC for the complete battery system.
    const label = main.id === 'dp3' ? 'Smart Extra Battery' : 'Додаткова батарея';
    const charge = level(soc);
    return '<article class="eco-system eco-system-paired eco-system-combined charge-' + charge +
      (liveMode && !Number.isFinite(soc) ? ' eco-api-unavailable' : '') +
      '" aria-label="' + main.name + ' із додатковою батареєю, ємність ' + niceWh(capacityWh) +
      ', загальний заряд ' + pctLabel(soc) + '">' +
      '<div class="eco-system-head"><div class="eco-system-title"><strong>' + main.name +
      '</strong><span class="eco-system-tag">+ ' + label + '</span></div>' +
      '<div class="eco-system-total"><strong>' + niceWh(capacityWh) + '</strong>' + operationBadge(main) + '</div></div>' +
      '<div class="eco-system-combined-charge"><div class="eco-system-combined-heading">' +
      '<span>Заряд усієї системи</span><strong class="eco-system-combined-percent">' +
      pctLabel(soc) + '</strong></div>' + chargeTrack(soc, main.name + ' разом із батареєю') +
      '<small class="eco-remaining-energy">Залишок: ' + remainingEnergy(capacityWh,soc) + '</small>' +
      '</div>' +
      '<div class="eco-system-modules" aria-label="Склад системи">' +
      '<div class="eco-system-module"><span>Основна станція</span><strong>' +
      niceWh(main.capacityWh) + '</strong></div>' +
      '<div class="eco-system-module"><span>' + label + '</span><strong>' +
      niceWh(addon.capacityWh) + '</strong></div></div>' +
      (liveMode && !Number.isFinite(soc) ? availabilityNote(main) : '') +
      energyStats(main, capacityWh, soc) +
      solarDisclosure(main) +
      '</article>';
  }

  // Keep total capacity accurate while putting unsupported stations in one disclosure.
  const pendingExpanded = new Set();
  function renderDeviceGrid(devices) {
    const addons = new Map(devices.filter(d => d.type === 'battery' && d.parentId).map(d => [d.parentId, d]));
    const ids = new Set(devices.map(d => d.id));
    const active=[], pending=[];
    for (const d of devices) {
      if (d.type==='battery' && d.parentId && ids.has(d.parentId)) continue;
      const addon=addons.get(d.id);
      if (liveMode && !Number.isFinite(d.pct)) {
        pending.push('<div class="eco-pending-device eco-api-unavailable"><strong>' + textEscape(d.name) +
          '</strong><span>' + niceWh(d.capacityWh+(addon?.capacityWh||0)) + '</span><small>' +
          (d.availability==='unsupported'?'EcoFlow API повертає 1006':'Очікуємо даних') +
          ' · Підключення в процесі</small></div>');
      } else active.push(addon?systemView(d,addon):d.type==='system'?powerOceanView(d):deviceView(d));
    }
    return active.join('') + (pending.length ?
      '<details class="eco-pending"' + (pendingExpanded.has(activeEcoLocation)?' open':'') +
      ' data-eco-pending="' + activeEcoLocation + '"><summary><span><strong>Підключення в процесі</strong>' +
      '<small>' + pending.length + ' станцій поки без моніторингу</small></span>' +
      '<span class="eco-pending-chevron" aria-hidden="true">⌄</span></summary>' +
      '<div class="eco-pending-list">' + pending.join('') + '</div></details>' : '');
  }

  let activeEcoLocation = 'dacha';

  // Location metrics use all physical battery packs, including expansion batteries.
  const detailArea = $('eco-metrics-area');
  const detailPanel = $('eco-metric-detail');
  const preciseWh = new Intl.NumberFormat('uk-UA', { maximumFractionDigits: 3 });
  const percentValue = new Intl.NumberFormat('uk-UA', { maximumFractionDigits: 1 });
  const textEscape = value => String(value).replace(/[&<>"']/g, char =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
  const exactCapacity = wh => Number.isFinite(wh)
    ? preciseWh.format(wh) + ' Wh' : '—';
  let metricOpen = null;

  function metricBreakdown(kind) {
    const devices = batterySystems(inventory[activeEcoLocation].devices);
    const total = devices.reduce((sum, item) => sum + item.capacityWh, 0);
    const known = devices.filter(d => Number.isFinite(d.pct));
    const knownWh = known.reduce((sum,d) => sum+d.capacityWh, 0);
    const stored = knownWh ? known.reduce((sum,d) => sum+d.capacityWh*d.pct/100, 0) : null;
    const weighted = stored !== null && knownWh ? stored/knownWh*100 : null;
    const fmtPercent = value => percentValue.format(value) + '%';
    const deviceShare = device => total ? device.capacityWh / total * 100 : 0;
    // Percent contribution to the location-wide weighted charge, not device SOC.
    const chargeContribution = device => knownWh && Number.isFinite(device.pct) ? device.capacityWh * device.pct / knownWh : null;
    const storedEnergyWh = device => Number.isFinite(device.pct) ? device.capacityWh * device.pct / 100 : null;
    const title = kind === 'capacity' ? 'Розподіл ємності локації'
      : kind === 'charge' ? (knownWh < total ? 'Внесок підключених станцій у середній заряд' : 'Внесок станцій у середній заряд')
      : 'Станції та акумулятори локації';

    const rows = devices.map((device, i) => {
      const name = textEscape(device.name);
      const capacity = exactCapacity(device.capacityWh);
      const share = deviceShare(device);
      const contribution = chargeContribution(device);
      const savedEnergy = storedEnergyWh(device);
      if (kind === 'count') {
        const type = device.type === 'battery' ? (device.parent
          ? 'Додаткова батарея до ' + textEscape(device.parent) : 'Акумуляторний модуль')
          : device.type === 'system' ? 'Домашня система' : 'Портативна зарядна станція';
        const operation = operationMeta[device.operation] || operationMeta.unknown;
        const powerLine = device.type === 'station' && Number.isFinite(device.inputW) && Number.isFinite(device.outputW)
          ? '<span>Вхід ' + device.inputW + ' W · вихід ' + device.outputW + ' W</span>'
          : '';
        return '<div class="eco-detail-device eco-detail-inventory">' +
          '<div class="eco-detail-item-heading"><span class="eco-detail-index">' + (i + 1) +
          '</span><span class="eco-detail-device-name">' + name + '<small>' + type + '</small></span></div>' +
          '<div class="eco-detail-inventory-stats"><span><b>' + capacity + '</b> ємність</span>' +
          '<span><b class="eco-detail-percent" data-level="' + level(device.pct) + '">' +
          (device.estimated ? '≈ ' : '') + pctLabel(device.pct) + '</b> заряд</span>' +
          '<span>' + textEscape(operation.label) + '</span>' + powerLine + '</div></div>';
      }
      if (kind === 'capacity') {
        return '<div class="eco-detail-device eco-detail-capacity">' +
          '<span class="eco-detail-device-name">' + name + '</span>' +
          '<strong>' + fmtPercent(share) + ' від локації</strong>' +
          '<div class="eco-detail-track"><i style="width:' + share + '%"></i></div>' +
          '<small>' + capacity + ' із ' + exactCapacity(total) + '</small></div>';
      }
      return '<div class="eco-detail-device eco-detail-charge">' +
        '<span class="eco-detail-device-name">' + name + '</span>' +
        '<strong class="eco-detail-contribution">' + (contribution === null ? '—' : '+' + fmtPercent(contribution)) + '</strong>' +
        '<div class="eco-detail-track"><i style="width:' + (contribution ?? 0) +
        '%" data-level="' + level(device.pct) + '"></i></div>' +
        '<small>Заряд ' + pctLabel(device.pct) + ' · частка ємності ' + fmtPercent(share) +
        '</small><small><strong class="eco-detail-stored">' + (savedEnergy === null ? 'Дані недоступні' : '≈ ' + niceWh(Math.round(savedEnergy)) + ' запасено') + '</strong></small>' +
        '<small>' + (contribution === null ? 'Внесок невідомий' :
        fmtPercent(share) + ' × ' + pctLabel(device.pct) + ' = +' +
        fmtPercent(contribution) + ' загального заряду') + '</small></div>';
    }).join('');

    const capacityDistribution = kind === 'capacity' && total
      ? '<div class="eco-detail-distribution" role="img" aria-label="Частки загальної ємності">' +
        devices.map(device => '<i style="width:' + deviceShare(device) +
          '%" title="' + textEscape(device.name) + ': ' + fmtPercent(deviceShare(device)) + '"></i>').join('') +
        '</div>' : '';
    const chargeDistribution = kind === 'charge' && total
      ? '<div class="eco-detail-contribution-bar" role="img" aria-label="Внески станцій у середній заряд ' +
        (weighted === null ? 'невідомий' : fmtPercent(weighted)) + '">' + devices.map(device =>
          '<i data-level="' + level(device.pct) + '" style="width:' +
          (chargeContribution(device) ?? 0) + '%" title="' + textEscape(device.name) + ': +' +
          (chargeContribution(device) === null ? 'невідомо' : fmtPercent(chargeContribution(device))) + ' середнього заряду"></i>').join('') + '</div>' : '';
    const formula = kind === 'capacity'
      ? '<div class="eco-detail-total"><span>Загальна ємність</span><strong>' +
        exactCapacity(total) + ' = 100%</strong></div>'
      : kind === 'charge'
        ? '<div class="eco-detail-formula"><span>Внески в середній заряд</span>' +
          '<strong>' + (weighted === null ? 'Поки немає даних про заряд' :
          known.map(device => fmtPercent(chargeContribution(device))).join(' + ') +
          ' = ' + fmtPercent(weighted) +
          (knownWh < total ? ' · тільки ' + known.length + ' із ' + devices.length + ' систем' : '')) + '</strong></div>'
        : '<div class="eco-detail-total"><span>Усього акумуляторів і станцій</span><strong>' +
          physicalDevices(inventory[activeEcoLocation].devices).length + '</strong></div>';

    const note = kind === 'capacity'
      ? 'Частка від загальної номінальної ємності, незалежно від поточного заряду'
      : kind === 'charge'
        ? (weighted === null ? 'Заряд ще недоступний' : knownWh < total
          ? 'Розрахунок лише для систем із доступним зарядом. Інші не вважаємо розрядженими.'
          : 'Внесок у загальні ' + Math.round(weighted) + '%: враховано і ємність, і заряд')
        : 'Перелік пристроїв, їхній заряд, ємність та стан';
    return '<div class="eco-detail-heading"><strong>' + title +
      '</strong><span>' + textEscape(note) + '</span></div>' +
      capacityDistribution + chargeDistribution +
      '<div class="eco-detail-grid">' + rows + '</div>' + formula;
  }

  function displayMetric(kind) {
    if (!detailArea || !detailPanel || !['capacity', 'charge', 'count'].includes(kind)) return;
    if (metricOpen !== kind) {
      detailPanel.innerHTML = metricBreakdown(kind);
      detailPanel.scrollTop = 0;
      metricOpen = kind;
    }
    detailPanel.hidden = false;
    detailArea.querySelectorAll('[data-eco-metric]').forEach(button => {
      const selected = button.dataset.ecoMetric === kind;
      button.classList.toggle('is-selected', selected);
      button.setAttribute('aria-expanded', String(selected));
    });
  }
  function clearMetric() {
    if (!detailArea || !detailPanel) return;
    metricOpen = null;
    detailPanel.hidden = true;
    detailArea.querySelectorAll('[data-eco-metric]').forEach(button => {
      button.classList.remove('is-selected');
      button.setAttribute('aria-expanded', 'false');
    });
  }
  // Keep the battery overview visible. Switch breakdowns only on explicit tap/click.
  // Automatic hover or outside-click dismissal caused the section to jump on iPhone/desktop.
  if (detailArea && detailPanel) {
    detailArea.addEventListener('click', event => {
      const trigger = event.target.closest('button[data-eco-metric]');
      if (!trigger) return;
      const kind = trigger.dataset.ecoMetric;
      if (metricOpen === kind && !detailPanel.hidden) clearMetric();
      else displayMetric(kind);
    });
  }

  let backupTab = 'ecoflow';
  function selectBackupTab(name) {
    const generatorAvailable = activeEcoLocation === 'dacha';
    backupTab = generatorAvailable && name === 'generator' ? 'generator' : 'ecoflow';
    root.classList.toggle('is-generator-tab', backupTab === 'generator');
    $('eco-section-title').textContent = backupTab === 'generator' ? 'Генератор' : 'EcoFlow';
    $('eco-tab-ecoflow').hidden = backupTab !== 'ecoflow';
    $('eco-tab-generator').hidden = backupTab !== 'generator';
    ['ecoflow', 'generator'].forEach(tab => {
      const button = $('eco-select-' + tab);
      button.setAttribute('aria-selected', String(backupTab === tab));
      button.classList.toggle('is-active', backupTab === tab);
    });
  }
  ['ecoflow', 'generator'].forEach(tab => {
    $('eco-select-' + tab).addEventListener('click', () => selectBackupTab(tab));
  });

  function renderSolar(place) {
    const section = $('eco-solar');
    const station = place.devices.find(d => d.id === 'dp3' && d.solar);
    if (!section || !station) return;
    const pv = station.solar;
    const solarPower = Number.isFinite(pv.currentW) ? pv.currentW
      : Number.isFinite(pv.highW) && Number.isFinite(pv.lowW) ? pv.highW + pv.lowW : null;
    const formatPower = solarPowerLabel;
    const percentOf = (current, max) =>
      Number.isFinite(current) ? Math.max(0, Math.min(100, current / max * 100)) + '%' : '0%';
    const updateChannel = (kind, power, maximum) => {
      $('eco-solar-' + kind).textContent = formatPower(power) + ' / ' + formatPower(maximum);
      $('eco-solar-' + kind + '-fill').style.width = percentOf(power, maximum);
    };
    $('eco-solar-max').textContent = formatPower(pv.maxW);
    $('eco-solar-current').textContent = formatPower(solarPower);
    $('eco-solar-today').textContent = niceWh(pv.todayWh);
    $('eco-solar-fill').style.width = percentOf(solarPower, pv.maxW);
    const progress = $('eco-solar-track');
    progress.setAttribute('aria-valuemax', String(pv.maxW));
    if (solarPower === null) {
      progress.removeAttribute('aria-valuenow');
      progress.setAttribute('aria-valuetext', 'Дані недоступні');
    } else {
      progress.setAttribute('aria-valuenow', String(solarPower));
      progress.setAttribute('aria-valuetext', formatPower(solarPower));
    }
    $('eco-solar-availability').textContent = pv.connected === true
      ? 'Сонячний вхід DELTA Pro 3' : 'Очікується підключення EcoFlow';
    updateChannel('high', pv.highW, pv.highMaxW);
    updateChannel('low', pv.lowW, pv.lowMaxW);
  }

  // Generator planning is local-only and never sends any control commands.
  // The initial SOC values are sample EcoFlow inventory numbers, NOT live readings.
  const generatorPlan = {
    chargeW: 2500, otherLoadW: 150, targetPct: 100, fuelLph: null,
    soc: new Map()
  };
  const generatorRatedW = 5000;
  const generatorCurrentInputLimitW = 16 * 230; // Existing Schuko cable, NOT the generator's 32 A outlet.
  const generatorSuggestedFraction = 0.8; // conservative planning headroom, not a manufacturer operating limit
  const generatorChargeEfficiency = 0.85; // illustrative average, charging tapers near 100%
  const generatorNum = new Intl.NumberFormat('uk-UA', { maximumFractionDigits: 1 });

  function generatorBatteryPacks() {
    return batterySystems(inventory.dacha.devices).filter(device => device.type === 'station');
  }
  function generatorSOC(device) {
    const stored = generatorPlan.soc.get(device.id);
    return Number.isFinite(stored) ? Math.max(0, Math.min(100, stored)) :
      Number.isFinite(device.pct) ? device.pct : null;
  }
  function generatorMissingWh(devices) {
    if (devices.some(d => generatorSOC(d) === null)) return null;
    return devices.reduce((total, d) =>
      total + d.capacityWh * Math.max(0, generatorPlan.targetPct - generatorSOC(d)) / 100, 0);
  }
  function generatorDuration(energyWh, availableW) {
    if (energyWh === null) return NaN;
    return energyWh <= 0 ? 0 :
      availableW > 0 ? energyWh / (availableW * generatorChargeEfficiency) : Infinity;
  }
  function generatorTime(hours) {
    if (Number.isNaN(hours)) return 'Немає даних';
    if (!Number.isFinite(hours)) return 'Недостатньо W';
    if (hours <= 0) return 'Заряджено до цілі';
    const minutes = Math.max(1, Math.ceil(hours * 60));
    const wholeHours = Math.floor(minutes / 60);
    const rem = minutes % 60;
    return wholeHours ? wholeHours + ' год' + (rem ? ' ' + rem + ' хв' : '') : rem + ' хв';
  }
  function renderGeneratorPlanner() {
    const area = $('eco-generator-planner');
    if (!area) return;
    const packs = generatorBatteryPacks();
    const dp3 = packs.filter(d => d.id === 'dp3');
    if (!area.dataset.initialized) {
      $('eco-gen-soc-fields').innerHTML = packs.map(device =>
        '<label class="eco-generator-soc-item"><span>' + textEscape(device.name) +
        '<small>' + niceWh(device.capacityWh) + '</small></span>' +
        '<span class="eco-generator-soc-input"><input type="number" min="0" max="100" step="1" ' +
        'data-eco-gen-soc="' + textEscape(device.id) + '" value="' + (generatorSOC(device) ?? '') +
        '" placeholder="—" aria-label="Заряд ' + textEscape(device.name) + '"><span>%</span></span></label>'
      ).join('');
      area.dataset.initialized = 'true';
    }
    // Update fields from latest telemetry unless the user explicitly entered an override.
    area.querySelectorAll('[data-eco-gen-soc]').forEach(field => {
      if (!generatorPlan.soc.has(field.dataset.ecoGenSoc)) {
        const pack = packs.find(d => d.id === field.dataset.ecoGenSoc);
        if (pack && document.activeElement !== field) field.value = generatorSOC(pack) ?? '';
      }
    });
    const allowedW = Math.max(0, Math.min(Math.floor(generatorRatedW * generatorSuggestedFraction),
      generatorCurrentInputLimitW) - generatorPlan.otherLoadW);
    const actualW = Math.min(generatorPlan.chargeW, allowedW);
    const dp3Missing = generatorMissingWh(dp3);
    const allMissing = generatorMissingWh(packs);
    const dp3Hours = generatorDuration(dp3Missing, actualW);
    const allHours = generatorDuration(allMissing, actualW);
    $('eco-gen-dp3-time').textContent = '≈ ' + generatorTime(dp3Hours);
    $('eco-gen-all-time').textContent = '≈ ' + generatorTime(allHours);
    $('eco-gen-dp3-energy').textContent = 'Дозарядити ' + (dp3Missing === null ? '—' : niceWh(Math.ceil(dp3Missing))) + ' із ' +
      niceWh(dp3.reduce((sum, d) => sum + d.capacityWh, 0));
    $('eco-gen-all-energy').textContent = 'Дозарядити ' + (allMissing === null ? '—' : niceWh(Math.ceil(allMissing))) + ' із ' +
      niceWh(packs.reduce((sum, d) => sum + d.capacityWh, 0));
    $('eco-gen-charge-value').textContent = generatorNum.format(generatorPlan.chargeW) + ' W';
    $('eco-gen-house-value').textContent = generatorNum.format(generatorPlan.otherLoadW) + ' W';
    area.querySelectorAll('[data-eco-gen-target]').forEach(button => {
      const active = Number(button.dataset.ecoGenTarget) === generatorPlan.targetPct;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-pressed', String(active));
    });
    const limited = actualW < generatorPlan.chargeW;
    $('eco-gen-budget').textContent =
      'Доступно на заряджання: ' + generatorNum.format(actualW) + ' W · інші прилади: ' +
      generatorNum.format(generatorPlan.otherLoadW) + ' W · резерв потужності: ' +
      generatorNum.format(generatorRatedW * (1 - generatorSuggestedFraction)) + ' W · ввід 16 A: максимум ' +
      generatorNum.format(generatorCurrentInputLimitW) + ' W разом з іншими приладами' +
      (limited ? '. Потужність заряджання обмежена з урахуванням інших приладів.' : '.');
    $('eco-gen-budget').classList.toggle('is-limited', limited);
    const rate = generatorPlan.fuelLph;
    const fuelDisplay = $('eco-gen-fuel-result');
    fuelDisplay.hidden = !(Number.isFinite(rate) && rate > 0);
    if (!fuelDisplay.hidden) {
      const fuelDp3 = Number.isFinite(dp3Hours) ? generatorNum.format(dp3Hours * rate) + ' л' : '—';
      const fuelAll = Number.isFinite(allHours) ? generatorNum.format(allHours * rate) + ' л' : '—';
      fuelDisplay.textContent = 'Орієнтир пального: ' + fuelDp3 +
        ' для DELTA Pro 3 · ' + fuelAll + ' для всіх EcoFlow. Розраховано з введеної витрати.';
    }
  }
  root.addEventListener('click', event => {
    const target = event.target.closest('button[data-eco-gen-target]');
    if (!target || !root.contains(target)) return;
    const value = Number(target.dataset.ecoGenTarget);
    if (![80, 90, 100].includes(value)) return;
    generatorPlan.targetPct = value;
    renderGeneratorPlanner();
  });
  root.addEventListener('input', event => {
    const input = event.target;
    if (input.id === 'eco-gen-charge-w') {
      generatorPlan.chargeW = Math.min(4000, Math.max(400, Number(input.value) || 2500));
    } else if (input.id === 'eco-gen-house-w') {
      generatorPlan.otherLoadW = Math.min(3000, Math.max(0, Number(input.value) || 0));
    } else if (input.id === 'eco-gen-fuel') {
      const rate = Number(input.value);
      generatorPlan.fuelLph = input.value.trim() && rate > 0 ? rate : null;
    } else if (input.matches?.('[data-eco-gen-soc]')) {
      const pack = generatorBatteryPacks().find(d => d.id === input.dataset.ecoGenSoc);
      if (!pack || input.value === '') return;
      const value = Number(input.value);
      if (!Number.isFinite(value)) return;
      generatorPlan.soc.set(pack.id, Math.max(0, Math.min(100, value)));
    } else return;
    renderGeneratorPlanner();
  });

  function updateLocation(id, refreshOnly = false) {
    if (!Object.prototype.hasOwnProperty.call(inventory, id)) return;
    const place = inventory[id];
    const packs = physicalDevices(place.devices);
    const systems = batterySystems(place.devices);
    const totalWh = systems.reduce((v, d) => v + (d.capacityWh || 0), 0);
    const allKnown = systems.every(d => Number.isFinite(d.capacityWh));
    const knownSystems = systems.filter(d=>Number.isFinite(d.pct));
    const knownCapacityWh = knownSystems.reduce((sum,d)=>sum+d.capacityWh,0);
    const allChargesKnown = knownSystems.length === systems.length;
    const weighted = knownCapacityWh
      ? Math.round(knownSystems.reduce((sum,d)=>sum+d.capacityWh*d.pct,0)/knownCapacityWh*10)/10
      : null;
     activeEcoLocation = id;
    renderConnection();
    if (!refreshOnly) clearMetric();
    root.dataset.location = id;
    const empty = place.devices.length === 0;
    $('eco-select-generator').hidden = id !== 'dacha';
    $('eco-location-summary').hidden = empty;
    $('eco-overview-details').hidden = empty;
    // Dacha has EcoFlow stations again; keep Generator as a separate selectable tab.
    if (!refreshOnly) selectBackupTab('ecoflow');
    $('eco-selected-location').textContent = place.name;
    $('eco-space-name').textContent = place.space;
    $('eco-count').textContent = String(packs.length);
    $('eco-capacity').textContent = !packs.length ? '—' : allKnown ? niceWh(totalWh) : 'Уточнюється';
    const available=systems.filter(d=>Number.isFinite(d.pct));
    const coverage=$('eco-data-coverage');
    if (coverage) coverage.textContent=liveMode && available.length<systems.length
      ? 'Моніторинг ' + available.length + '/' + systems.length + ' систем · ' +
        niceWh(available.reduce((sum,d)=>sum+d.capacityWh,0)) + ' із ' + niceWh(totalWh) +
        '. Заряд решти невідомий.'
      : 'Моніторинг усіх систем';
    const partial = liveMode && !allChargesKnown;
    const averageLabel = partial ? 'Середній заряд підключених' : 'Середній заряд локації';
    if ($('eco-location-charge-label')) $('eco-location-charge-label').textContent = averageLabel;
    if ($('eco-metric-charge-label')) $('eco-metric-charge-label').textContent = averageLabel;
    const hasEstimates = knownSystems.some(d => d.estimated === true);
    $('eco-demo-total').textContent = weighted === null ? '—' : (hasEstimates ? '≈ ' : '') + pctLabel(weighted);
    $('eco-demo-total').dataset.level = weighted === null ? 'unknown' : level(weighted);
    // One bar represents the capacity-weighted average charge across physical batteries.
    const overallTrack = $('eco-location-charge-track');
    $('eco-location-charge-value').textContent = weighted === null ? '—' : (hasEstimates ? '≈ ' : '') + pctLabel(weighted);
    overallTrack.dataset.level = weighted === null ? 'unknown' : level(weighted);
    overallTrack.setAttribute('aria-label', averageLabel);
    $('eco-location-charge-fill').style.width = weighted === null ? '0%' : weighted + '%';
    if (weighted === null) {
      overallTrack.removeAttribute('aria-valuenow');
      overallTrack.setAttribute('aria-valuetext', 'Заряд невідомий');
    } else {
      overallTrack.setAttribute('aria-valuenow', String(weighted));
      overallTrack.setAttribute('aria-valuetext', weighted + ' відсотків');
    }
    $('eco-devices').innerHTML = (place.devices.length ? renderDeviceGrid(place.devices) : '<div class="eco-empty-state"><strong>У цій локації немає EcoFlow</strong><span>Резервне живлення дачі забезпечує генератор. Його характеристики є в сусідній вкладці.</span></div>') +
      (id === 'dacha' ? unassignedSection() : '');
    renderSolar(place);
    if (id === 'dacha') renderGeneratorPlanner();
    if (refreshOnly && metricOpen && detailPanel && !detailPanel.hidden) {
      detailPanel.innerHTML = metricBreakdown(metricOpen);
    }
  }

  root.addEventListener('toggle', event => {
    const item=event.target;
    if (!item?.matches?.('details.eco-pending')) return;
    const key=item.dataset.ecoPending;
    if (item.open) pendingExpanded.add(key); else pendingExpanded.delete(key);
  },true);
  const selectedButton = document.querySelector('[data-location].selected');
  const restored = selectedButton?.dataset.location || 'dacha';
  applyReadings();
  renderConnection();
  updateLocation(restored);
  live?.subscribe(() => {
    applyReadings();
    renderConnection();
    updateLocation(activeEcoLocation, true);
  });
  live?.start();
  window.addEventListener('svitlo:location-change', e => updateLocation(e.detail?.id));
  window.addEventListener('svitlo:outage-update', () => updateLocation(activeEcoLocation,true));
})();
