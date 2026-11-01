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
        { name: 'PowerOcean', capacityWh: 10000, inverterKw: 6, systemPowerKw: 6, batteryCount: 2, pct: 67, inputW: 300, outputW: 760, type: 'system', id: 'po', operation: 'discharging' }
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
  const pctLabel = value => Number.isFinite(value) ? value + '%' : '—';
  const wattsLabel = value => Number.isFinite(value) ? value + ' W' : '—';
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
        return {
          ...device,
          pct: value?.socPercent ?? (value?.moduleSocPercent?.length === device.batteryCount ?
            value.moduleSocPercent.reduce((sum, p) => sum + p, 0) / device.batteryCount : null),
          inputW: value?.inputW ?? null,
          outputW: value?.outputW ?? null,
          operation: value?.operation || 'unknown',
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
      stale: 'Дані застаріли',
      error: 'Налаштування відсутнє'
    };
    const devicesHere = demoInventory[activeEcoLocation]?.devices || [];
    const liveHere = devicesHere.filter(device =>
      live?.statusFor(activeEcoLocation + ':' + device.id) === 'live').length;
    const stateHere = mode === 'live' && liveHere === 0 ? 'stale' : mode;
    element.classList.toggle('is-live', stateHere === 'live');
    element.classList.toggle('is-stale', stateHere === 'stale');
    element.title = mode === 'preview' ?
      'Тестові показники, не реальна телеметрія EcoFlow' :
      mode === 'live' ? 'Дані зі шлюзу EcoFlow; стан перевіряється окремо для кожної станції' :
      'Немає свіжих даних. Показники приховано.';
    element.innerHTML = '<i aria-hidden="true"></i>' + (mode === 'live'
      ? ('Live · ' + liveHere + '/' + devicesHere.length + ' станцій')
      : labels[mode] || 'Немає зв’язку');
    root.dataset.telemetryState = stateHere;
  }

  // Physical battery inventory for overview metrics (PowerOcean has two 5000 Wh modules).
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

  const root = document.getElementById('ecoflow');
  const toggle = document.getElementById('ecoAdminToggle');
  if (!root || !toggle) return;

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
    const { label, sign } = operationMeta[status];
    return '<span class="eco-operation eco-operation-' + status + '">' +
      '<span class="eco-operation-icon" aria-hidden="true">' + sign + '</span>' +
      label + '</span>';
  }

  function formatAutonomy(capacityWh, chargePct, outputW) {
    if (!Number.isFinite(outputW) || outputW <= 0 || !Number.isFinite(chargePct)) return '—';
    // Approximation using an 85% available energy factor.
    const estimatedMinutes = Math.round(capacityWh * chargePct / 100 * 0.85 / outputW * 60 / 5) * 5;
    const hours = Math.floor(estimatedMinutes / 60);
    const mins = estimatedMinutes % 60;
    return (hours ? hours + ' год' : '') + (mins ? (hours ? ' ' : '') + mins + ' хв' : '');
  }

  function chargeTrack(pct, name) {
    return '<div class="eco-charge-track" role="progressbar" aria-label="Заряд ' + name +
      '" aria-valuemin="0" aria-valuemax="100"' +
      (Number.isFinite(pct) ? ' aria-valuenow="' + pct + '"' : ' aria-valuetext="Заряд невідомий"') + '>' +
      '<i style="width:' + (Number.isFinite(pct) ? pct : 0) + '%"></i></div>';
  }

  function energyStats(d, capWh, pct) {
    const output = d.outputW;
    const autonomy = formatAutonomy(capWh, pct, output);
    return '<div class="eco-device-stats eco-common-stats">' +
      '<div class="eco-device-stat"><span>Вхід</span><strong>' + wattsLabel(d.inputW) + '</strong></div>' +
      '<div class="eco-device-stat"><span>Вихід</span><strong>' + wattsLabel(output) + '</strong></div>' +
      '<div class="eco-device-stat eco-autonomy"><span>Автономність</span><strong>' + autonomy + '</strong></div>' +
      '</div>';
  }

  // Draft-only settings. No API writes, credentials, or actual device configuration.
  const reservePresets = [0, 5, 20, 50, 80, 100];
  const individualReserves = new Map();
  const powerOceanDraft = { reserve: 0, selfPowered: true, allDay: true, start: '00:00', end: '24:00', chargeW: 3000 };
  const timeSteps = Array.from({ length: 24 }, (_, hour) => String(hour).padStart(2, '0') + ':00');

  function reserveOptions(device, key, selected, powerOcean = false) {
    return '<div class="eco-reserve-presets" role="group" aria-label="Резерв заряду ' + device.name + '">' +
      reservePresets.filter(percent => powerOcean || percent >= 5).map(percent =>
        '<button type="button" class="eco-reserve-option' + (selected === percent ? ' is-active' : '') +
        '" data-eco-reserve="' + percent + '" data-eco-device="' + key +
        '" aria-pressed="' + String(selected === percent) + '">' + percent + '%</button>'
      ).join('') + '</div>';
  }

  function adminControls(device) {
    const key = activeEcoLocation + ':' + device.id;
    const selected = individualReserves.has(key) ? individualReserves.get(key) : null;
    return '<div class="eco-admin-only eco-device-admin"><strong>Керування</strong>' +
      '<div class="eco-admin-controls"><div class="eco-individual-limit">' +
      '<span class="eco-individual-label">Резерв заряду</span>' +
      reserveOptions(device, key, selected) + '</div>' +
      '<button type="button" disabled>AC-вихід</button></div></div>';
  }

  function powerOceanAdmin(device) {
    const key = activeEcoLocation + ':' + device.id;
    const dayLabel = powerOceanDraft.allDay ? '00:00–24:00' : powerOceanDraft.start + '–' + powerOceanDraft.end;
    const timeSelect = (field, value, list) => '<select data-eco-ocean-time="' + field + '" aria-label="' +
      (field === 'start' ? 'Початок заряджання' : 'Кінець заряджання') + '">' +
      list.map(time => '<option value="' + time + '"' + (value === time ? ' selected' : '') + '>' +
      time + '</option>').join('') + '</select>';
    return '<section class="eco-admin-only eco-ocean-admin eco-device-admin"><div class="eco-ocean-admin-heading"><strong>Керування PowerOcean</strong>' +
      '<span>Режим: ' + (powerOceanDraft.selfPowered ? 'Самозабезпечення' : 'Вимкнено') + '</span></div>' +
      '<label class="eco-ocean-selfpowered"><input type="checkbox" data-eco-ocean-self-powered' +
      (powerOceanDraft.selfPowered ? ' checked' : '') + '> Самозабезпечення</label>' +
      '<div class="eco-ocean-controls">' +
      '<div class="eco-ocean-setting"><span>Резерв заряду</span>' +
      reserveOptions(device, key, powerOceanDraft.reserve, true) + '</div>' +
      '<div class="eco-ocean-setting"><span>Потужність заряджання</span>' +
      '<div class="eco-ocean-watts"><input type="range" data-eco-ocean-watts min="100" max="3000" step="100" value="' +
      powerOceanDraft.chargeW + '" aria-label="Потужність заряджання PowerOcean"><output>' +
      powerOceanDraft.chargeW + ' W</output></div><small>100–3000 W</small></div>' +
      '<div class="eco-ocean-setting"><span>Час заряджання</span><label class="eco-ocean-allday">' +
      '<input type="checkbox" data-eco-ocean-allday' + (powerOceanDraft.allDay ? ' checked' : '') +
      '> Цілодобово</label><div class="eco-ocean-clock">' +
      (powerOceanDraft.allDay ? '<strong>' + dayLabel + '</strong>' :
        timeSelect('start', powerOceanDraft.start, timeSteps) +
        '<span>до</span>' + timeSelect('end', powerOceanDraft.end, [...timeSteps.slice(1), '24:00'])) +
      '</div></div></div>' +
      '</section>';
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

  function deviceView(d) {
    const size = capClass(d.capacityWh);
    const charge = level(d.pct);
    const capacity = niceWh(d.capacityWh);
    const titleNote = 'Зарядна станція';
    return '<article class="eco-device eco-standalone ' + size + ' charge-' + charge +
      '" aria-label="' + d.name + ', заряд ' + pctLabel(d.pct) + '">' +
      '<div class="eco-device-head"><div class="eco-device-ident">' +
      '<strong class="eco-device-name">' + d.name + '</strong>' +
      '<span class="eco-device-model">' + titleNote + '</span></div>' + operationBadge(d) + '</div>' +
      '<div class="eco-battery"><span class="eco-battery-percent">' + pctLabel(d.pct) +
      '</span><span class="eco-battery-art" aria-hidden="true"><i style="width:' +
      (Number.isFinite(d.pct) ? d.pct : 0) + '%"></i></span></div>' +
      chargeTrack(d.pct, d.name) +
      '<div class="eco-capacity-line"><strong>' + capacity + '</strong></div>' +
      energyStats(d, d.capacityWh, d.pct) +
      solarDisclosure(d) +
      adminControls(d) +
      '</article>';
  }

  function powerOceanView(d) {
    const cap = niceWh(d.capacityWh);
    return '<article class="eco-powerocean charge-' + level(d.pct) + '" aria-label="PowerOcean, домашня система, заряд ' + pctLabel(d.pct) + '">' +
      '<div class="eco-ocean-top"><div><span class="eco-ocean-overline">Домашня енергосистема</span>' +
      '<h3>PowerOcean</h3><span class="eco-ocean-cap">' + d.batteryCount + ' акумулятори · ' + cap + ' · інвертор ' + uk.format(d.inverterKw * 1000) + ' W' +
      '</span></div>' + operationBadge(d) + '</div>' +
      '<div class="eco-ocean-body"><div class="eco-ocean-battery"><span class="eco-ocean-label">Акумулятор</span>' +
      '<div class="eco-battery"><span class="eco-battery-percent">' + pctLabel(d.pct) + '</span></div>' +
      chargeTrack(d.pct, d.name) + '<span>' + cap + '</span></div>' +
      '<div class="eco-ocean-energy"><div><span>Мережа / заряд</span><strong>' + wattsLabel(d.inputW) + '</strong></div>' +
      '<div class="eco-ocean-flow" aria-hidden="true">→</div><div><span>Будинок</span><strong>' +
      wattsLabel(d.outputW) + '</strong></div></div></div>' +
      '<div class="eco-ocean-autonomy"><span>Орієнтовна автономність</span><strong>' +
      formatAutonomy(d.capacityWh, d.pct, d.outputW) + '</strong></div>' +
      powerOceanAdmin(d) + '</article>';
  }

  function systemView(main, addon) {
    const capacityWh = main.capacityWh + addon.capacityWh;
    const weighted = Number.isFinite(main.pct) && Number.isFinite(addon.pct) ?
      Math.round((main.capacityWh * main.pct + addon.capacityWh * addon.pct) / capacityWh) : null;
    const batteryPart = (d, role) => {
      const name = role === 'Основна' ? 'основної станції' : 'додаткової батареї';
      return '<div class="eco-system-part charge-' + level(d.pct) + '">' +
        '<div class="eco-system-part-top"><span class="eco-system-part-label">' + role + '</span>' +
        '<strong class="eco-system-percent">' + pctLabel(d.pct) + '</strong></div>' +
        (role === 'Додаткова' && main.id === 'dp3'
          ? '<span class="eco-system-part-model">Smart Extra Battery</span>' : '') +
        operationBadge(d) +
        chargeTrack(d.pct, name) +
        '<span class="eco-system-part-cap">' + niceWh(d.capacityWh) + '</span>' +
        '</div>';
    };
    return '<article class="eco-system eco-system-paired charge-' + level(weighted) +
      '" aria-label="' + main.name + ' із додатковою батареєю, загалом ' + niceWh(capacityWh) + '">' +
      '<div class="eco-system-head"><div class="eco-system-title"><strong>' + main.name +
      '</strong><span class="eco-system-tag">' + (main.id === 'dp3' ? '+ Smart Extra Battery' : '+ додаткова батарея') + '</span></div>' +
      '<div class="eco-system-total"><strong>' + niceWh(capacityWh) + '</strong>' +
      '<span>' + (Number.isFinite(weighted) ? weighted + '% загалом' : 'Заряд невідомий') + '</span></div></div>' +
      '<div class="eco-system-parts">' + batteryPart(main, 'Основна') + batteryPart(addon, 'Додаткова') + '</div>' +
      energyStats(main, capacityWh, weighted) +
      solarDisclosure(main) +
      adminControls(main) +
      '</article>';
  }

  // Each primary station and its expansion battery form ONE visual system.
  function renderDeviceGrid(devices) {
    const addons = new Map(devices.filter(d => d.type === 'battery' && d.parentId).map(d => [d.parentId, d]));
    const ids = new Set(devices.map(d => d.id));
    return devices.map(d => {
      if (d.type === 'battery' && d.parentId && ids.has(d.parentId)) return '';
      const addon = addons.get(d.id);
      return addon ? systemView(d, addon) : d.type === 'system' ? powerOceanView(d) : deviceView(d);
    }).join('');
  }

  // Drafts are session-local UI state. No device commands or authentication exist yet.
  const adminDraft = {
    scope: 'current',
    reserve: 5,
    selected: { reserve: new Set(), ac: new Set(), speed: new Set() },
    speeds: new Map(),
    speedPreset: 'balanced'
  };
  let activeEcoLocation = 'dacha';

  function selectableStations() {
    const locIds = adminDraft.scope === 'all'
      ? Object.keys(inventory) : [activeEcoLocation];
    // Expansion batteries belong to the primary; PowerOcean requires separate verified commands.
    return locIds.flatMap(loc => inventory[loc].devices
      .filter(d => d.type === 'station')
      .map(d => ({ key: loc + ':' + d.id, name: d.name, id: d.id, loc, place: inventory[loc].name })));
  }

  // Per-model AC input power targets in W. Values are illustrative until device API capabilities are verified.
  // DELTA 2 200/500/1200 W follows EcoFlow's documented quiet/optimized/max settings.
  const chargingProfiles = {
    dp3: { quiet: 500, balanced: 1000, fast: 2900 },
    d3p: { quiet: 200, balanced: 500, fast: 1500 },
    d2: { quiet: 200, balanced: 500, fast: 1200 },
    r3pw: { quiet: 80, balanced: 200, fast: 380 },
    r2: { quiet: 100, balanced: 200, fast: 360 }
  };
  const speedModes = [
    { key: 'quiet', label: 'Тиха' },
    { key: 'balanced', label: 'Оптимальна' },
    { key: 'fast', label: 'Швидка' }
  ];
  function speedOptions(station) {
    const profile = chargingProfiles[station.id];
    const selected = adminDraft.speeds.get(station.key) || adminDraft.speedPreset;
    return '<select class="eco-speed-select" data-eco-speed="' + station.key +
      '" aria-label="Режим заряджання ' + station.name + '">' +
      speedModes.map(mode => '<option value="' + mode.key + '"' +
        (selected === mode.key ? ' selected' : '') + '>' + mode.label +
        ' · ' + (station.id === 'r3pw' && mode.key === 'quiet' ? 'до 80 W' : profile[mode.key] + ' W') + '</option>').join('') + '</select>';
  }

  function targetRows(group, withSpeed) {
    const stations = selectableStations();
    const set = adminDraft.selected[group];
    const rows = stations.map(station => {
      const checked = set.has(station.key);
      const speedSelect = withSpeed ? speedOptions(station) : '';
      return '<div class="eco-target-row"><label class="eco-target-label">' +
        '<input type="checkbox" data-eco-group="' + group + '" data-eco-target="' +
        station.key + '"' + (checked ? ' checked' : '') + '>' +
        '<span>' + station.name + (adminDraft.scope === 'all' ?
          '<small>' + station.place + '</small>' : '') + '</span></label>' +
        speedSelect + '</div>';
    }).join('');
    return '<div class="eco-target-top"><span>Станції: ' +
      set.size + ' / ' + stations.length + '</span><span class="eco-target-actions">' +
      '<button type="button" data-eco-select="all" data-eco-group="' + group + '">Усі</button>' +
      '<button type="button" data-eco-select="none" data-eco-group="' + group + '">Жодної</button>' +
      '</span></div><div class="eco-target-list">' +
      (rows || '<p class="eco-target-empty">Немає сумісних переносних станцій у цій локації.</p>') +
      '</div>';
  }

  function renderBulkPanel() {
    const container = $('eco-bulk-content');
    if (!container) return;
    const selected = adminDraft.scope === 'all' ? 'Усі локації' : inventory[activeEcoLocation].name;
    const scopePicker = '<label class="eco-bulk-scope">Локації <select id="eco-admin-scope">' +
      '<option value="current"' + (adminDraft.scope === 'current' ? ' selected' : '') + '>Поточна: ' +
        inventory[activeEcoLocation].name + '</option>' +
      '<option value="all"' + (adminDraft.scope === 'all' ? ' selected' : '') + '>Усі локації</option></select></label>';
    container.innerHTML =
      '<div class="eco-bulk-toolbar">' + scopePicker +
      '<span class="eco-bulk-scope-note">' + selected + '</span></div>' +
      '<div class="eco-bulk-actions">' +
      '<section class="eco-bulk-card"><h4>Резерв заряду</h4>' +
      '<div class="eco-bulk-range"><input type="range" id="eco-bulk-reserve" min="5" max="100" step="5" value="' +
        adminDraft.reserve + '" aria-label="Спільний резерв заряду">' +
      '<output id="eco-bulk-reserve-value" for="eco-bulk-reserve">' + adminDraft.reserve + '%</output></div>' +
      targetRows('reserve', false) +
      '<button class="eco-bulk-apply" type="button" disabled>Застосувати резерв</button></section>' +
      '<section class="eco-bulk-card"><h4>AC-виходи</h4>' +
      targetRows('ac', false) +
      '<div class="eco-bulk-buttons"><button class="eco-bulk-apply" type="button" disabled>Увімкнути AC</button>' +
      '<button class="eco-bulk-apply eco-bulk-danger" type="button" disabled>Вимкнути AC</button></div>' +
      '</section>' +
      '<section class="eco-bulk-card"><h4>Швидкість заряджання</h4>' +
      '<div class="eco-speed-preset" role="group" aria-label="Режим заряджання для вибраних станцій">' +
      speedModes.map(mode => '<button type="button" data-eco-preset="' + mode.key +
        '" class="eco-speed-preset-button' + (adminDraft.speedPreset === mode.key ? ' active' : '') + '">' +
        mode.label + '</button>').join('') + '</div>' +
      '<p class="eco-bulk-subtitle">Потужність у ватах залежить від моделі. Можна змінити режим кожної станції окремо.</p>' +
      targetRows('speed', true) +
      '<button class="eco-bulk-apply" type="button" disabled>Застосувати швидкості</button></section></div>';
  }

  const bulkContent = $('eco-bulk-content');
  if (bulkContent) {
    bulkContent.addEventListener('click', event => {
      const presetButton = event.target.closest('button[data-eco-preset]');
      if (presetButton) {
        const mode = presetButton.dataset.ecoPreset;
        if (!speedModes.some(item => item.key === mode)) return;
        adminDraft.speedPreset = mode;
        const available = new Set(selectableStations().map(st => st.key));
        adminDraft.selected.speed.forEach(key => {
          if (available.has(key)) adminDraft.speeds.set(key, mode);
        });
        renderBulkPanel();
        return;
      }
      const button = event.target.closest('button[data-eco-select]');
      if (!button) return;
      const group = button.dataset.ecoGroup;
      if (!Object.prototype.hasOwnProperty.call(adminDraft.selected, group)) return;
      adminDraft.selected[group] = button.dataset.ecoSelect === 'all'
        ? new Set(selectableStations().map(x => x.key))
        : new Set();
      renderBulkPanel();
    });
    bulkContent.addEventListener('input', event => {
      const target = event.target;
      if (target.id === 'eco-bulk-reserve') {
        $('eco-bulk-reserve-value').textContent = target.value + '%';
      }
    });
    bulkContent.addEventListener('change', event => {
      const target = event.target;
      if (target.id === 'eco-admin-scope') {
        adminDraft.scope = target.value === 'all' ? 'all' : 'current';
        Object.keys(adminDraft.selected).forEach(group => adminDraft.selected[group].clear());
      } else if (target.id === 'eco-bulk-reserve') {
        adminDraft.reserve = Math.max(5, Math.min(100, Number(target.value) || 5));
      } else if (target.dataset.ecoTarget) {
        const group = target.dataset.ecoGroup;
        const key = target.dataset.ecoTarget;
        if (!adminDraft.selected[group] || !selectableStations().some(st => st.key === key)) return;
        if (target.checked) adminDraft.selected[group].add(key);
        else adminDraft.selected[group].delete(key);
      } else if (target.dataset.ecoSpeed) {
        const key = target.dataset.ecoSpeed;
        if (!selectableStations().some(st => st.key === key)) return;
        const value = speedModes.some(item => item.key === target.value) ? target.value : 'balanced';
        adminDraft.speeds.set(key, value);
        adminDraft.selected.speed.add(key);
      } else return;
      renderBulkPanel();
    });
  }


  // Location metrics use all physical battery packs, including expansion batteries.
  const detailArea = $('eco-metrics-area');
  const detailPanel = $('eco-metric-detail');
  const preciseWh = new Intl.NumberFormat('uk-UA', { maximumFractionDigits: 3 });
  const percentValue = new Intl.NumberFormat('uk-UA', { maximumFractionDigits: 2 });
  const textEscape = value => String(value).replace(/[&<>"']/g, char =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
  const exactCapacity = wh => Number.isFinite(wh)
    ? preciseWh.format(wh) + ' Wh' : '—';
  let metricOpen = null;

  function metricBreakdown(kind) {
    const devices = physicalDevices(inventory[activeEcoLocation].devices);
    const total = devices.reduce((sum, item) => sum + item.capacityWh, 0);
    const allSocKnown = devices.every(d => Number.isFinite(d.pct));
    const stored = allSocKnown ? devices.reduce((sum, item) => sum + item.capacityWh * item.pct / 100, 0) : null;
    const weighted = stored !== null && total ? stored / total * 100 : null;
    const fmtPercent = value => percentValue.format(value) + '%';
    const deviceShare = device => total ? device.capacityWh / total * 100 : 0;
    // Percent contribution to the location-wide weighted charge, not device SOC.
    const chargeContribution = device => total && Number.isFinite(device.pct) ? device.capacityWh * device.pct / total : null;
    const storedEnergyWh = device => Number.isFinite(device.pct) ? device.capacityWh * device.pct / 100 : null;
    const title = kind === 'capacity' ? 'Розподіл ємності локації'
      : kind === 'charge' ? 'Внесок станцій у середній заряд'
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
          pctLabel(device.pct) + '</b> заряд</span>' +
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
          '<strong>' + (weighted === null ? 'Очікуємо даних від усіх акумуляторів' :
          devices.map(device => fmtPercent(chargeContribution(device))).join(' + ') +
          ' = ' + fmtPercent(weighted) + ' ≈ ' + Math.round(weighted) + '%') + '</strong></div>'
        : '<div class="eco-detail-total"><span>Усього акумуляторів і станцій</span><strong>' +
          devices.length + '</strong></div>';

    const note = kind === 'capacity'
      ? 'Частка від загальної номінальної ємності, незалежно від поточного заряду'
      : kind === 'charge'
        ? (weighted === null ? 'Не всі акумулятори передали заряд' :
          'Внесок у загальні ' + Math.round(weighted) + '%: враховано і ємність, і заряд')
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
    chargeW: 1800, otherLoadW: 150, targetPct: 100, fuelLph: null,
    soc: new Map()
  };
  const generatorRatedW = 2800;
  const generatorSuggestedFraction = 0.8; // conservative planning headroom, not a manufacturer operating limit
  const generatorChargeEfficiency = 0.85; // illustrative average, charging tapers near 100%
  const generatorNum = new Intl.NumberFormat('uk-UA', { maximumFractionDigits: 1 });

  function generatorBatteryPacks() {
    return inventory.dacha.devices.filter(device =>
      device.type === 'station' || device.type === 'battery');
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
    const dp3 = packs.filter(d => d.id === 'dp3' || d.parentId === 'dp3');
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
    const allowedW = Math.max(0, Math.floor(generatorRatedW * generatorSuggestedFraction) - generatorPlan.otherLoadW);
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
      generatorNum.format(generatorRatedW * (1 - generatorSuggestedFraction)) + ' W' +
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
      generatorPlan.chargeW = Math.min(2200, Math.max(400, Number(input.value) || 1800));
    } else if (input.id === 'eco-gen-house-w') {
      generatorPlan.otherLoadW = Math.min(1200, Math.max(0, Number(input.value) || 0));
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
    const totalWh = packs.reduce((v, d) => v + (d.capacityWh || 0), 0);
    const allKnown = packs.every(d => Number.isFinite(d.capacityWh));
    const allChargesKnown = packs.every(d => Number.isFinite(d.pct));
    const weighted = allKnown && allChargesKnown && totalWh
      ? Math.round(packs.reduce((v, d) => v + d.capacityWh * d.pct, 0) / totalWh)
      : null;
    if (adminDraft.scope === 'current' && activeEcoLocation !== id) {
      Object.keys(adminDraft.selected).forEach(group => adminDraft.selected[group].clear());
    }
    activeEcoLocation = id;
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
    $('eco-demo-total').textContent = weighted === null ? '—' : weighted + '%';
    $('eco-demo-total').dataset.level = weighted === null ? 'unknown' : level(weighted);
    // One bar represents the capacity-weighted average charge across physical batteries.
    const overallTrack = $('eco-location-charge-track');
    $('eco-location-charge-value').textContent = weighted === null ? '—' : weighted + '%';
    overallTrack.dataset.level = weighted === null ? 'unknown' : level(weighted);
    $('eco-location-charge-fill').style.width = weighted === null ? '0%' : weighted + '%';
    if (weighted === null) {
      overallTrack.removeAttribute('aria-valuenow');
      overallTrack.setAttribute('aria-valuetext', 'Заряд невідомий');
    } else {
      overallTrack.setAttribute('aria-valuenow', String(weighted));
      overallTrack.setAttribute('aria-valuetext', weighted + ' відсотків');
    }
    $('eco-devices').innerHTML = place.devices.length ? renderDeviceGrid(place.devices) : '<div class="eco-empty-state"><strong>У цій локації немає EcoFlow</strong><span>Резервне живлення дачі забезпечує генератор. Його характеристики є в сусідній вкладці.</span></div>';
    renderSolar(place);
    renderBulkPanel();
    if (id === 'dacha') renderGeneratorPlanner();
    if (refreshOnly && metricOpen && detailPanel && !detailPanel.hidden) {
      detailPanel.innerHTML = metricBreakdown(metricOpen);
    }
  }

  // Read-only draft controls; no configuration reaches any EcoFlow device.
  root.addEventListener('click', event => {
    const button = event.target.closest('button[data-eco-reserve]');
    if (!button || !root.contains(button)) return;
    const value = Number(button.dataset.ecoReserve);
    const key = button.dataset.ecoDevice;
    if (!reservePresets.includes(value)) return;
    if (!key.startsWith(activeEcoLocation + ':')) return;
    const device = inventory[activeEcoLocation].devices.find(d =>
      d.type !== 'battery' && (activeEcoLocation + ':' + d.id) === key);
    if (!device || (device.type !== 'system' && value < 5)) return;
    if (device.type === 'system') powerOceanDraft.reserve = value;
    else individualReserves.set(key, value);
    const group = button.closest('.eco-reserve-presets');
    if (!group) return;
    group.querySelectorAll('button[data-eco-reserve]').forEach(option => {
      const active = Number(option.dataset.ecoReserve) === value;
      option.classList.toggle('is-active', active);
      option.setAttribute('aria-pressed', String(active));
    });
  });

  root.addEventListener('input', event => {
    const target = event.target;
    if (!target.matches?.('[data-eco-ocean-watts]')) return;
    const watts = Math.max(100, Math.min(3000, Math.round(Number(target.value) / 100) * 100 || 100));
    powerOceanDraft.chargeW = watts;
    const output = target.closest('.eco-ocean-watts')?.querySelector('output');
    if (output) output.textContent = watts + ' W';
  });
  root.addEventListener('change', event => {
    const target = event.target;
    if (target.matches?.('[data-eco-ocean-self-powered]')) {
      powerOceanDraft.selfPowered = target.checked;
    } else if (target.matches?.('[data-eco-ocean-allday]')) {
      powerOceanDraft.allDay = target.checked;
    } else if (target.matches?.('[data-eco-ocean-time]')) {
      const field = target.dataset.ecoOceanTime;
      if (field !== 'start' && field !== 'end') return;
      if (![...timeSteps, '24:00'].includes(target.value)) return;
      powerOceanDraft[field] = target.value;
      if (powerOceanDraft.end <= powerOceanDraft.start) powerOceanDraft.end = '24:00';
    } else return;
    $('eco-devices').innerHTML = renderDeviceGrid(inventory[activeEcoLocation].devices);
  });

  // Persistent, centered detail row. It does not reposition when the hovered bar changes.
  // Admin controls stay disabled pending authenticated server access.
  function setAdminMode(enabled) {
    root.classList.toggle('is-admin-mode', enabled);
    document.body.classList.toggle('eco-admin-visible', enabled);
    toggle.setAttribute('aria-checked', String(enabled));
    toggle.title = enabled ? 'Вимкнути Admin' : 'Увімкнути Admin';
    $('eco-admin-bulk').hidden = !enabled;
  }
  toggle.addEventListener('click', function () {
    setAdminMode(toggle.getAttribute('aria-checked') !== 'true');
  });
  setAdminMode(false);

  // Keep Admin reachable after the header scrolls out of view.
  const adminHost = toggle.closest('.header-time');
  const siteHeader = document.querySelector('main > header');
  function syncFloatingAdmin() {
    if (!adminHost || !siteHeader) return;
    const threshold = siteHeader.offsetTop + siteHeader.offsetHeight + 12;
    adminHost.classList.toggle('is-floating', window.scrollY > threshold);
  }
  window.addEventListener('scroll', syncFloatingAdmin, { passive: true });
  window.addEventListener('resize', syncFloatingAdmin);
  syncFloatingAdmin();

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
})();
