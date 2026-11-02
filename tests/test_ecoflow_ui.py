"""Contract checks for the unauthenticated, read-only EcoFlow prototype."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "site/index.html").read_text(encoding="utf-8")
JS = (ROOT / "site/ecoflow.js").read_text(encoding="utf-8")
CSS = (ROOT / "site/ecoflow.css").read_text(encoding="utf-8")
SW = (ROOT / "site/sw.js").read_text(encoding="utf-8")


class EcoFlowPreviewContract(unittest.TestCase):
    def test_all_four_locations_are_listed(self):
        for key in ("dacha:", "home:", "solovky:", "naumenky:"):
            self.assertIn(key, JS)
        for name in ("DELTA Pro 3", "DELTA 3 Plus", "RIVER 3 Plus Wireless",
                     "PowerOcean", "RIVER 2", "Додаткова батарея DELTA 2", "Smart Extra Battery DELTA Pro 3"):
            self.assertIn(name, JS)
        self.assertEqual(JS.count("capacityWh: 4096"), 2)
        self.assertEqual(JS.count("capacityWh: 1024"), 5)
        self.assertEqual(JS.count("capacityWh: 286"), 1)
        self.assertEqual(JS.count("capacityWh: 256"), 1)
        self.assertEqual(JS.count("capacityWh: 10000"), 1)

    def test_disconnected_device_values_are_not_claimed_as_live(self):
        self.assertIn("Демо · API не підключено", HTML)
        self.assertIn("Тестові показники, не реальна телеметрія EcoFlow", HTML)
        panel = HTML.split('<section class="eco-shell"', 1)[1].split('</section>', 1)[0]
        self.assertTrue(panel)
        self.assertIn("const demoInventory = Object.freeze({", JS)
        self.assertNotRegex(JS, r"\bfetch\s*\(|XMLHttpRequest|WebSocket")
        self.assertIn("disabled", JS)

    def test_admin_toggle_is_ui_only(self):
        self.assertIn('id="ecoAdminToggle"', HTML)
        self.assertIn('role="switch"', HTML)
        self.assertIn('aria-checked="false"', HTML)
        self.assertIn("setAdminMode(false)", JS)
        self.assertIn("toggle.addEventListener('click'", JS)
        self.assertNotIn('id="eco-admin-mode-hint"', HTML)
        self.assertNotIn("eco-admin-mode-hint", JS)
        self.assertIn(".eco-shell.is-admin-mode", CSS)

    def test_capacity_average_is_weighted_and_powerocean_is_known(self):
        self.assertIn("capacityWh: 10000, inverterKw: 6, systemPowerKw: 6, batteryCount: 2", JS)
        self.assertIn("function powerOceanView(d)", JS)
        self.assertIn("powerOceanAdmin(d)", JS)
        self.assertIn("const packs = physicalDevices(place.devices)", JS)
        self.assertIn("systems.reduce((v, d) => v + d.capacityWh * d.pct, 0)", JS)
        self.assertIn('id="eco-location-charge-track"', HTML)
        self.assertNotIn('id="eco-capacity-strip"', HTML)

    def test_location_changer_and_pwa_integration(self):
        self.assertIn("svitlo:location-change", JS)
        self.assertIn("new CustomEvent('svitlo:location-change'", HTML)
        self.assertNotIn('href="#ecoflow"', HTML)
        self.assertIn('<section class="eco-shell"', HTML)
        self.assertIn('"./ecoflow.css?v=51"', SW)
        self.assertIn('"./ecoflow.js?v=51"', SW)


    def test_device_section_first_and_header_rearranged(self):
        self.assertLess(HTML.index(">Станції та акумулятори<"),
                        HTML.index(">Огляд батарей<"))
        self.assertIn('class="site-clock" id="clock"', HTML)
        self.assertIn('</small></button></div></div><div class="clock-view">', HTML)
        self.assertIn('<div class="site-clock" id="clock"', HTML)
        self.assertLess(HTML.index('id="clock"'), HTML.index('id="viewMenuToggle"'))
        self.assertLess(HTML.index('id="locationMenu"'), HTML.index('id="clock"'))
        self.assertLess(HTML.index('id="clock"'), HTML.index('id="ecoAdminToggle"'))
        self.assertEqual(HTML.count('id="clock"'), 1)
        self.assertIn('<span class="eco-admin-toggle-label">Admin</span>', HTML)
        self.assertIn('class="eco-admin-shield"', HTML)
        self.assertNotIn('Admin <small>Preview</small>', HTML)
        self.assertIn('main > header #clock', CSS)
        self.assertIn('grid-template-columns:minmax(0,1fr) max-content minmax(0,1fr)', CSS)
        self.assertIn('main > .tabs .tomorrow-tab{margin-left:auto}', CSS)
        self.assertIn('width:calc(100% - 284px)', CSS)
        self.assertIn('main > .tabs{width:100%;padding-right:14px}', CSS)
        self.assertIn(".eco-admin-toggle[aria-checked=\"true\"]", CSS)

    def test_expansion_batteries_are_one_system_card(self):
        self.assertIn("parentId: 'dp3'", JS)
        self.assertIn("parentId: 'd2'", JS)
        self.assertIn("function renderDeviceGrid(devices)", JS)
        self.assertIn("const addons = new Map(", JS)
        self.assertIn("ids.has(d.parentId)", JS)
        self.assertIn("return addon ? systemView(d, addon) : d.type === 'system' ? powerOceanView(d) : deviceView(d);", JS)
        self.assertIn('class="eco-system eco-system-paired', JS)
        self.assertIn('class="eco-system-modules"', JS)
        self.assertIn("Заряд усієї системи", JS)
        self.assertIn("const soc = main.pct", JS)
        self.assertIn("niceWh(capacityWh)", JS)
        self.assertIn(".eco-system-modules{", CSS)
        self.assertIn("formatAutonomy(capacityWh, chargePct, outputW)", JS)
        self.assertIn("energyStats(main, capacityWh, soc)", JS)
        self.assertIn("solarDisclosure(main)", JS)
        self.assertIn("Smart Extra Battery", JS)

    def test_delta_pro_3_expansion_capacity_and_location_totals(self):
        # Exactly one physical 4096 Wh expansion attached to DELTA Pro 3.
        dacha = JS.split("dacha: {", 1)[1].split("home: {", 1)[0]
        self.assertEqual(dacha.count("parentId: 'dp3'"), 1)
        self.assertIn("id: 'dp3eb'", dacha)
        self.assertIn("name: 'Smart Extra Battery DELTA Pro 3'", dacha)
        self.assertEqual(dacha.count("capacityWh: 4096"), 2)
        capacities = [int(v) for v in re.findall(r"capacityWh:\s*(\d+)", dacha)]
        self.assertEqual(sum(capacities), 10526)  # 8.192 kWh DP3 system + other dacha stations
        self.assertEqual(len(capacities), 5)
        self.assertIn("const capacityWh = main.capacityWh + addon.capacityWh;", JS)
        self.assertIn("const packs = physicalDevices(place.devices);", JS)
        self.assertIn("renderDeviceGrid(place.devices)", JS)
        # PV controls must survive the change from standalone to paired system.
        self.assertIn("solarDisclosure(main)", JS)

    def test_header_alignment_and_tabs_reach_graph_end(self):
        self.assertIn("main > header .location-shell,\nmain > header #clock,\nmain > header .header-time{min-height:58px}", CSS)
        self.assertIn("main > nav.tabs{", CSS)
        self.assertIn("grid-template-columns:minmax(0,1fr) max-content", CSS)
        self.assertIn('main > nav.tabs > button[data-tab="tomorrow"]{justify-self:end;margin:0}', CSS)
        self.assertIn("main > nav.tabs{width:100%;padding-right:0}", CSS)

    def test_power_and_autonomy_are_shared_at_system_level(self):
        self.assertIn("function energyStats(d, capWh, pct)", JS)
        self.assertIn("Math.round(capacityWh * chargePct / 100 * 0.85 / outputW", JS)
        self.assertIn("Автономність", JS)
        self.assertNotIn("Автономність: —", JS)
        self.assertNotIn("Вхід / вихід контролює основна станція", JS)
        self.assertIn("disabled", JS)


    def test_compact_location_and_space_mapping(self):
        self.assertIn('id="eco-selected-location"', HTML)
        self.assertIn('id="eco-space-name"', HTML)
        self.assertIn("name: 'Дім', space: 'Квартира'", JS)
        self.assertIn("$('eco-space-name').textContent = place.space;", JS)
        self.assertIn("eco-context-arrow", HTML)
        self.assertEqual(HTML.count('class="eco-status"'), 1)
        self.assertIn(".eco-context-space strong{color:#a5e4db}", CSS)

    def test_admin_stays_accessible_while_scrolling(self):
        self.assertIn("function syncFloatingAdmin()", JS)
        self.assertIn("window.addEventListener('scroll', syncFloatingAdmin", JS)
        self.assertIn("adminHost.classList.toggle('is-floating'", JS)
        self.assertIn("main > header .header-time.is-floating", CSS)
        self.assertIn("position:fixed", CSS)
        self.assertIn("z-index:150", CSS)



    def test_device_reallocation_to_dacha_and_solar(self):
        dacha = JS.split("dacha: {", 1)[1].split("home: {", 1)[0]
        home = JS.split("home: {", 1)[1].split("solovky: {", 1)[0]
        solovky = JS.split("solovky: {", 1)[1].split("naumenky: {", 1)[0]
        for name in ("DELTA Pro 3", "DELTA 3 Plus", "DELTA 2", "RIVER 3 Plus Wireless"):
            self.assertIn("name: '" + name + "'", dacha)
        self.assertIn("parentId: 'dp3'", dacha)
        self.assertIn("space: 'Дача'", dacha)
        self.assertIn("solar: { maxW: 2600, highMaxW: 1600, lowMaxW: 1000", dacha)
        self.assertIn("currentW: 1240, highW: 820, lowW: 420, todayWh: 4800, connected: false", dacha)
        self.assertIn("pv.connected === true", JS)
        self.assertIn("Очікується підключення EcoFlow", JS)
        self.assertIn("name: 'PowerOcean'", home)
        self.assertNotIn("name: 'DELTA 3 Plus'", home)
        self.assertNotIn("name: 'RIVER 3 Plus Wireless'", home)
        self.assertNotIn("DELTA Pro 3", solovky)
        self.assertIn("name: 'DELTA 2'", solovky)
        self.assertIn("name: 'Додаткова батарея DELTA 2'", solovky)
        self.assertIn("name: 'RIVER 2'", solovky)
        self.assertNotIn("d2second", JS)
        self.assertEqual(solovky.count("capacityWh: 1024"), 2)
        self.assertIn("selectBackupTab('ecoflow')", JS)
        self.assertIn("function physicalDevices(devices)", JS)

    def test_full_width_chart_with_inline_change_history(self):
        self.assertIn('class="card schedule-card"', HTML)
        self.assertIn('class="history history-inline"', HTML)
        self.assertIn('id="scheduleDetailsHost"', HTML)
        self.assertLess(HTML.index('id="display"'), HTML.index('class="history history-inline"'))
        self.assertLess(HTML.index('class="history history-inline"'), HTML.index('id="scheduleDetailsHost"'))
        self.assertIn("const detailsAt=html.indexOf", HTML)
        self.assertIn("$('scheduleDetailsHost').innerHTML=html.slice(detailsAt)", HTML)
        self.assertIn("document.querySelector('#scheduleDetailsHost .schedule-details')", HTML)
        self.assertIn("main > .layout{display:block;grid-template-columns:none", CSS)
        self.assertIn(".history-inline .change-comparison", CSS)
        self.assertIn("grid-template-columns:repeat(2,minmax(0,1fr))", CSS)

    def test_speed_presets_show_per_model_watts_and_allow_overrides(self):
        self.assertIn("const chargingProfiles = {", JS)
        self.assertIn("d2: { quiet: 200, balanced: 500, fast: 1200 }", JS)
        self.assertIn("d3p: { quiet: 200, balanced: 500, fast: 1500 }", JS)
        self.assertIn("dp3: { quiet: 500, balanced: 1000, fast: 2900 }", JS)
        self.assertIn("Тиха", JS)
        self.assertIn("Оптимальна", JS)
        self.assertIn("Швидка", JS)
        self.assertIn("data-eco-preset", JS)
        self.assertIn("data-eco-speed", JS)
        self.assertIn("adminDraft.speeds.set(key, value)", JS)
        self.assertNotIn("['25', '50', '75', '100']", JS)
        self.assertIn(".eco-speed-preset{", CSS)

    def test_average_includes_all_physical_batteries(self):
        self.assertIn("function physicalDevices(devices)", JS)
        self.assertIn("device.capacityWh / device.batteryCount", JS)
        self.assertIn("const packs = physicalDevices(place.devices)", JS)
        self.assertIn("const totalWh = systems.reduce", JS)
        self.assertIn("d.capacityWh * d.pct", JS)
        self.assertNotIn("flex-grow:' + system.wh", JS)

    def test_admin_shared_actions_and_independent_targets(self):
        self.assertIn('id="eco-admin-bulk"', HTML)
        self.assertIn('id="eco-bulk-content"', HTML)
        self.assertIn("'eco-admin-bulk').hidden = !enabled", JS)
        for group in ("reserve", "ac", "speed"):
            self.assertIn("targetRows('" + group + "'", JS)
        for action in ("Застосувати резерв", "Увімкнути AC", "Вимкнути AC", "Застосувати швидкості"):
            self.assertIn(action, JS)
        self.assertIn("data-eco-target", JS)
        self.assertIn("data-eco-speed", JS)
        self.assertIn("data-eco-select", JS)
        self.assertIn("value=\"all\"", JS)
        self.assertIn("function renderBulkPanel()", JS)
        self.assertIn("new Set()", JS)
        self.assertIn("Object.keys(adminDraft.selected).forEach(group => adminDraft.selected[group].clear())", JS)
        self.assertIn(".eco-bulk-actions{display:grid", CSS)

    def test_no_unsecured_admin_commands_and_powerocean_is_separate(self):
        self.assertIn("PowerOcean requires separate verified commands", JS)
        self.assertIn(".filter(d => d.type === 'station')", JS)
        self.assertNotRegex(JS, r"\bfetch\s*\(|XMLHttpRequest|WebSocket")
        self.assertIn("type=\"button\" disabled>Увімкнути AC", JS)
        self.assertIn("type=\"button\" disabled>Вимкнути AC", JS)
        self.assertIn("type=\"button\" disabled>Застосувати швидкості", JS)
        self.assertNotIn("Доступ після захищеного підключення.", JS)



    def test_previous_changes_counter_and_yesterday_label(self):
        self.assertIn('Минулі зміни сьогодні <span class="past-change-count">', HTML)
        self.assertIn("previousEdits.length", HTML)
        self.assertNotIn("<summary>Ще '+previousEdits.length", HTML)
        self.assertIn("$('previousTitle').textContent='Зміни і графік вчора'", HTML)
        self.assertNotIn("$('previousTitle').textContent='Зміни і графік '+yDate", HTML)
        self.assertIn(".past-change-count{", CSS)

    def test_tomorrow_aligned_to_full_width_chart(self):
        self.assertIn("main > nav.tabs{width:100%;padding-left:0;padding-right:20px}", CSS)
        self.assertIn("@media(max-width:650px){main > nav.tabs{padding-right:14px}}", CSS)
        self.assertIn('main > nav.tabs > button[data-tab="tomorrow"]{justify-self:end;margin:0}', CSS)

    def test_overall_charge_replaces_capacity_distribution(self):
        self.assertNotIn("Розподіл ємності", HTML)
        self.assertNotIn('id="eco-capacity-tooltip"', HTML)
        self.assertNotIn("capacityStrip.addEventListener", JS)
        self.assertIn('id="eco-location-charge-value"', HTML)
        self.assertIn('id="eco-location-charge-fill"', HTML)
        self.assertIn("overallTrack.dataset.level = weighted === null ? 'unknown' : level(weighted)", JS)
        self.assertIn("overallTrack.setAttribute('aria-valuenow', String(weighted))", JS)
        self.assertIn("overallTrack.removeAttribute('aria-valuenow')", JS)
        self.assertIn("weighted === null ? '0%' : weighted + '%'", JS)
        self.assertIn('.eco-location-charge-track[data-level="good"]', CSS)

    def test_charge_arrows_and_home_layout(self):
        self.assertIn("charging: { label: 'Заряджається', sign: '↑' }", JS)
        self.assertIn("discharging: { label: 'Розряджається', sign: '↓' }", JS)
        self.assertIn('.eco-shell[data-location="home"] .eco-devices', CSS)
        self.assertIn(".eco-shell[data-location=\"home\"] .eco-devices>.eco-powerocean", CSS)
        self.assertIn("grid-template-columns:repeat(24,minmax(0,1fr))", CSS)
        self.assertIn("grid-column:span 12", CSS)

    def test_every_battery_has_explicit_operation_state(self):
        self.assertEqual(JS.count("operation: 'discharging'"), 8)
        self.assertEqual(JS.count("operation: 'charging'"), 1)
        self.assertEqual(JS.count("operation: 'holding'"), 1)
        self.assertIn("charging: { label: 'Заряджається'", JS)
        self.assertIn("discharging: { label: 'Розряджається'", JS)
        self.assertIn("holding: { label: 'Підтримує заряд'", JS)
        self.assertIn("unknown: { label: 'Статус невідомий'", JS)
        self.assertIn("function operationBadge(device)", JS)
        self.assertIn("operationBadge(d)", JS)
        for classname in ("charging", "discharging", "holding", "unknown"):
            self.assertIn(".eco-operation-" + classname, CSS)
        self.assertIn(".eco-system-part .eco-operation", CSS)

    def test_reserve_presets_replaced_charge_limit(self):
        self.assertIn("const reservePresets = [0, 5, 20, 50, 80, 100]", JS)
        self.assertIn("const individualReserves = new Map()", JS)
        self.assertIn("function adminControls(device)", JS)
        self.assertIn("adminControls(d)", JS)
        self.assertIn("adminControls(main)", JS)
        self.assertIn("data-eco-reserve", JS)
        self.assertIn("individualReserves.set(key, value)", JS)
        self.assertNotIn("Ліміт заряджання", JS)
        self.assertIn("Резерв заряду", JS)
        self.assertIn(".eco-reserve-presets", CSS)
        self.assertIn(".eco-reserve-option.is-active", CSS)

    def test_powerocean_wide_with_separate_energy_flow_and_controls(self):
        self.assertIn("function powerOceanView(d)", JS)
        self.assertIn('class="eco-powerocean charge-', JS)
        self.assertIn("eco-ocean-body", JS)
        self.assertIn("eco-ocean-energy", JS)
        self.assertIn("powerOceanAdmin(d)", JS)
        self.assertIn("powerOceanDraft = { reserve: 0, selfPowered: true, allDay: true", JS)
        self.assertIn("chargeW: 3000", JS)
        self.assertIn("data-eco-ocean-watts", JS)
        self.assertIn('min="100" max="3000" step="100"', JS)
        self.assertIn("data-eco-ocean-allday", JS)
        self.assertIn("data-eco-ocean-self-powered", JS)
        self.assertIn("data-eco-ocean-time", JS)
        self.assertIn(".eco-powerocean{", CSS)
        self.assertIn('grid-column:1/-1!important', CSS)
        self.assertIn(".eco-ocean-controls{", CSS)
        self.assertNotIn("Інвертор ' + d.inverterKw", JS)

    def test_river_three_plus_quiet_is_eighty_watts(self):
        self.assertIn("r3pw: { quiet: 80, balanced: 200, fast: 380 }", JS)
        self.assertIn("mode.key === 'quiet' ? 'до 80 W'", JS)
        self.assertIn("'</select>'", JS)


    def test_matching_archive_arrows_and_prominent_daily_counter(self):
        self.assertIn('class="past-change-label"', HTML)
        self.assertIn("Минулі зміни сьогодні", HTML)
        self.assertIn('class="archive-arrow" aria-hidden="true"', HTML)
        self.assertEqual(HTML.count('class="archive-arrow"'), 2)
        self.assertIn('class="yesterday-summary-label"', HTML)
        self.assertIn(".history-inline .archive-arrow::before", CSS)
        self.assertIn(".history-inline details[open]>summary>.archive-arrow::before", CSS)
        self.assertIn(".past-change-count{", CSS)
        self.assertIn("border:2px solid #fb7185", CSS)
        self.assertIn(".history-inline .earlier-changes>summary::after{content:none!important}", CSS)

    def test_tomorrow_flush_with_schedule_card_edge(self):
        self.assertIn("main > nav.tabs{", CSS)
        self.assertIn("box-sizing:border-box", CSS)
        self.assertIn("margin-inline:0", CSS)
        self.assertIn("padding:0", CSS)
        self.assertIn('main > nav.tabs > button[data-tab="tomorrow"]{justify-self:end;margin-right:0;margin-left:0}', CSS)
        self.assertIn("main > nav.tabs{padding:0}", CSS)


    def test_ecoflow_branding_and_fresh_pwa_assets(self):
        self.assertIn('eco-title-monogram', HTML)
        self.assertIn('<path d="M14 20H26" stroke="currentColor"', HTML)
        self.assertNotIn('stroke="#67E8F9"', HTML)
        self.assertIn('href="./ecoflow.css?v=51"', HTML)
        self.assertIn('src="./ecoflow.js?v=51"', HTML)
        self.assertIn("updateViaCache:'none'", HTML)
        self.assertIn('nashe-svitlo-static-v51', SW)
        self.assertIn('url.pathname.endsWith("/ecoflow.css")', SW)
        self.assertIn('url.pathname.endsWith("/ecoflow.js")', SW)
        self.assertIn('fetch(request, {cache: "no-store"})', SW)
        self.assertIn('caches.match(request)', SW)
        self.assertIn(".eco-title-monogram{", CSS)



    def test_expanded_overview_retains_per_battery_charge_and_capacity(self):
        self.assertIn('id="eco-overview-details"', HTML)
        self.assertIn("function metricBreakdown(kind)", JS)
        self.assertIn("device.capacityWh * device.pct / total", JS)
        self.assertIn('class="eco-detail-percent" data-level="', JS)
        self.assertIn("'<div class=\"eco-detail-grid\">' + rows", JS)
        self.assertNotIn("data-eco-tooltip=", JS)
        self.assertNotIn("eco-capacity-strip", JS)

    def test_mobile_eco_cards_full_width_and_admin_switch_within_track(self):
        self.assertIn('.eco-shell[data-location="home"] .eco-devices', CSS)
        self.assertIn("grid-template-columns:minmax(0,1fr)", CSS)
        self.assertIn("grid-column:1/-1!important", CSS)
        self.assertIn('main > header .eco-admin-toggle .eco-switch-track{', CSS)
        self.assertIn("overflow:hidden", CSS)
        self.assertIn("transform:translateX(18px)", CSS)
        self.assertIn("transform:translateX(16px)", CSS)
        self.assertIn("max-width:calc(100vw - 16px)", CSS)

    def test_long_outages_have_responsive_duration_labels(self):
        self.assertIn("function outageDurationText(minutes)", HTML)
        self.assertIn("function outageDurationCompact(minutes)", HTML)
        self.assertIn("length>120?", HTML)
        self.assertIn('class="outage-duration"', HTML)
        self.assertIn('duration-full', HTML)
        self.assertIn('duration-short', HTML)
        self.assertIn(".outage-duration .duration-short{display:none}", CSS)
        self.assertIn("@media(max-width:700px)", CSS)


    def test_zero_reserve_only_on_powerocean(self):
        self.assertIn("reservePresets.filter(percent => powerOcean || percent >= 5)", JS)
        self.assertIn("if (!device || (device.type !== 'system' && value < 5)) return;", JS)
        self.assertIn("powerOceanDraft = { reserve: 0", JS)
        self.assertIn("reserveOptions(device, key, powerOceanDraft.reserve, true)", JS)
        self.assertIn("    reserve: 5,", JS)
        self.assertIn('id="eco-bulk-reserve" min="5" max="100" step="5"', JS)
        self.assertIn("Math.max(5, Math.min(100", JS)

    def test_reserve_buttons_fit_small_river_card(self):
        self.assertIn(".eco-admin-controls .eco-reserve-presets > button.eco-reserve-option{", CSS)
        self.assertIn("min-width:0", CSS)
        self.assertIn("box-sizing:border-box", CSS)
        self.assertIn(".eco-device.size-small .eco-admin-controls{", CSS)
        self.assertIn("flex-direction:column", CSS)
        self.assertIn(".eco-device.size-small .eco-admin-controls > button[disabled]{", CSS)



    def test_header_clock_has_single_section_picker_and_no_top_level_tabs(self):
        self.assertIn('class="clock-view"', HTML)
        self.assertIn('id="clock" aria-label="Час у Києві"', HTML)
        self.assertIn('id="viewMenuToggle" type="button"', HTML)
        self.assertIn('id="viewMenuLabel">Графік</span>', HTML)
        self.assertIn('id="viewMenu" class="view-menu" role="menu"', HTML)
        self.assertIn('data-site-view="schedule"', HTML)
        self.assertIn('data-site-view="statistics"', HTML)
        self.assertNotIn('class="view-tabs"', HTML)
        self.assertNotIn('id="viewSchedule"', HTML)
        self.assertNotIn('id="viewStats"', HTML)
        self.assertIn('id="scheduleLayout" role="region"', HTML)
        self.assertIn('id="seasonPanel" class="season-panel" role="region"', HTML)
        self.assertIn('id="dayTabs"', HTML)
        self.assertLess(HTML.index('id="clock"'), HTML.index('id="viewMenuToggle"'))
        self.assertLess(HTML.index('id="viewMenuToggle"'), HTML.index('id="dayTabs"'))
        self.assertIn("function switchSiteView(next)", HTML)
        self.assertIn("$('dayTabs').hidden=stats;", HTML)
        self.assertIn("$('scheduleLayout').hidden=stats;", HTML)
        self.assertIn("$('ecoflow').hidden=stats;", HTML)
        self.assertIn("$('seasonPanel').hidden=!stats;", HTML)
        self.assertIn("$('viewMenuLabel').textContent=stats?'Статистика':'Графік'", HTML)
        self.assertIn("remembered('nashe-svitlo-active-view')==='statistics'", HTML)
        self.assertIn(".clock-view #viewMenuToggle", CSS)
        self.assertIn('main > header .clock-view{grid-column:2', CSS)
        self.assertIn('main > header .clock-view{grid-column:1/-1;grid-row:2', CSS)

    def test_season_detailed_metrics_respect_missing_data(self):
        self.assertIn('Днів із відключеннями', HTML)
        self.assertIn('Без планових відключень', HTML)
        self.assertIn('Змін графіка на день', HTML)
        self.assertIn('Найбільше змін за день', HTML)
        self.assertIn('Інтервалів відключення', HTML)
        self.assertIn('Середня довжина інтервалу', HTML)
        self.assertIn('Днів від першого запису', HTML)
        self.assertIn('loc.tracked_change_days', HTML)
        self.assertIn('class="season-extra-kpis"', HTML)
        self.assertIn('.season-extra-kpis', HTML)
        self.assertIn("function seasonCount(value){return Number.isFinite(value)?String(value).replace('.',','):'—'}", HTML)
        self.assertIn('Пропущені дні не вважаються днями без відключень', HTML)
        self.assertIn('seasonHelpDescriptions', HTML)
        self.assertIn('class="season-help-button"', HTML)
        self.assertIn('class="season-all-toggle"', HTML)
        self.assertIn('id="seasonAllMetrics"', HTML)
        self.assertIn('seasonAllExpanded=!seasonAllExpanded', HTML)
        self.assertIn('document.querySelectorAll(\'#seasonContent .season-extra-kpis\')', HTML)
        self.assertNotIn('<details class="season-extra">', HTML)

    def test_all_season_metrics_have_explanations_and_one_global_toggle(self):
        for label in ('longest','maxDaily','dailyAverage','total','outageDays','zeroDays',
                      'changesAverage','changesTotal','maxChanges','intervals',
                      'avgInterval','daysSince','coverage','method'):
            self.assertIn(label+':', HTML)
        self.assertIn("seasonHelpButton(id,title)", HTML)
        self.assertIn("seasonHelpButton('method','Методика підрахунку')", HTML)
        self.assertIn("seasonHelpButton('coverage','Підтверджені дні')", HTML)
        self.assertIn('id="seasonHelpPopover" class="season-help-popover" role="tooltip" hidden', HTML)
        self.assertIn("aria-controls=\"seasonHelpPopover\"", HTML)
        self.assertIn("String(report.season||'').replace(/^20(", HTML)
        self.assertIn("if(seasonHelpTrigger===trigger&&!pop.hidden)", HTML)
        self.assertIn("pop.style.left=Math.max(12", HTML)
        self.assertIn("closeSeasonHelp(true)", HTML)
        self.assertIn(".season-extra-kpis[hidden]{display:none!important}", HTML)
        self.assertNotIn('class="season-subtitle"', HTML)

    def test_season_extra_metrics_have_spacing_without_divider(self):
        self.assertIn('.season-extra-kpis{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;margin-top:14px}', HTML)
        self.assertNotIn('.season-extra-kpis{margin-top:12px;border-top:', HTML)
        self.assertNotIn('.season-extra-kpis{border-top:', HTML)

    def test_season_kpis_are_colored_by_daily_duration_not_total(self):
        self.assertIn("function seasonLevel(minutes)", HTML)
        self.assertIn("minutes<=240?'low':minutes<=480?'medium':'high'", HTML)
        self.assertIn("season-kpi level-", HTML)
        self.assertIn("metric('total','Разом без світла',loc.total_minutes,'За підтвердженими графіками',true)", HTML)
        self.assertIn('class="season-legend"', HTML)
        self.assertIn('.season-kpi.level-low', HTML)
        self.assertIn('.season-kpi.level-medium', HTML)
        self.assertIn('.season-kpi.level-high', HTML)
        self.assertIn('.season-kpi.level-total', HTML)

    def test_summary_bar_then_always_open_battery_overview(self):
        self.assertIn('class="eco-location-summary"', HTML)
        self.assertIn('<section class="eco-overview-details" id="eco-overview-details" aria-labelledby="eco-overview-heading">', HTML)
        self.assertNotIn('<summary>Детальніше про батареї', HTML)
        self.assertIn('class="eco-overview-content"', HTML)
        self.assertIn('role="progressbar" aria-label="Середній заряд локації"', HTML)
        self.assertLess(HTML.index('id="eco-location-summary"'), HTML.index('id="eco-overview-heading"'))
        self.assertIn('.eco-location-summary[hidden],.eco-overview-details[hidden]', CSS)
        self.assertNotIn("if (!empty) displayMetric('capacity');", JS)
        self.assertIn("if (!refreshOnly) clearMetric();", JS)
        self.assertNotIn("eco-overview-details').open", JS)
        self.assertNotIn('.eco-overview-details[open]', CSS)

    def test_location_metrics_have_compact_labels_and_accessible_details(self):
        self.assertIn('Ємність локації', HTML)
        self.assertIn('Середній заряд локації', HTML)
        self.assertIn('Кількість акумуляторів та станцій', HTML)
        self.assertNotIn('Сума номінальних ємностей батарей', HTML + JS)
        self.assertNotIn('Зважений за ємністю', HTML)
        self.assertNotIn('eco-capacity-note', HTML + JS)
        self.assertNotIn('eco-demo-note', HTML + JS)
        self.assertIn('id="eco-metrics-area"', HTML)
        self.assertIn('id="eco-metric-detail"', HTML)
        for kind in ('capacity', 'charge', 'count'):
            self.assertIn('data-eco-metric="' + kind + '"', HTML)
        self.assertIn('aria-controls="eco-metric-detail"', HTML)
        self.assertIn("function metricBreakdown(kind)", JS)
        self.assertIn("function displayMetric(kind)", JS)
        self.assertIn("function clearMetric()", JS)
        self.assertIn("kind === 'capacity'", JS)
        self.assertIn("kind === 'charge'", JS)
        self.assertIn("kind === 'count'", JS)
        self.assertIn("const stored = allSocKnown ?", JS)
        self.assertIn("const weighted = stored !== null && total", JS)
        self.assertIn("device.capacityWh * device.pct / total", JS)
        self.assertIn("Внески в середній заряд</span>", JS)
        self.assertIn("exactCapacity(total)", JS)
        self.assertIn("physicalDevices(inventory[activeEcoLocation].devices).length + '</strong></div>'", JS)

    def test_metric_explanations_change_only_on_explicit_click(self):
        self.assertIn("detailArea.addEventListener('click', event => {", JS)
        self.assertIn("if (!trigger) return;", JS)
        self.assertIn("if (metricOpen === kind && !detailPanel.hidden) clearMetric();", JS)
        self.assertIn("else displayMetric(kind);", JS)
        self.assertIn('id="eco-metric-detail" aria-live="polite" hidden', HTML)
        self.assertNotIn("detailArea.addEventListener('pointerover'", JS)
        self.assertNotIn("detailArea.addEventListener('pointerleave'", JS)
        self.assertNotIn("metricPinned", JS)
        self.assertIn("detailArea.querySelectorAll('[data-eco-metric]')", JS)
        self.assertIn("aria-expanded", JS)
        self.assertIn(".eco-metric-detail[hidden]{display:none!important}", CSS)
        self.assertIn(".eco-detail-grid{", CSS)
        self.assertIn(".eco-detail-track{", CSS)
        detail_style = CSS.split(".eco-metric-detail{", 1)[1].split("}", 1)[0]
        self.assertIn("position:static", detail_style)
        self.assertIn("display:block", detail_style)
        self.assertIn("width:100%", detail_style)
        self.assertIn("margin:12px 0 0", detail_style)
        self.assertNotIn("position:absolute", detail_style)
        self.assertNotIn("top:calc(100% + 8px)", detail_style)
        self.assertNotIn("position:relative;top:auto", CSS)
        self.assertIn(".eco-detail-grid{", CSS)
        self.assertIn("grid-template-columns:minmax(0,1fr)", CSS)



    def test_expanded_metric_detail_never_overlaps_capacity_strip(self):
        detail_style = CSS.split(".eco-metric-detail{", 1)[1].split("}", 1)[0]
        self.assertIn("position:static", detail_style)
        self.assertIn("box-sizing:border-box", detail_style)
        self.assertIn("max-width:100%", detail_style)
        self.assertIn("min-width:0", detail_style)
        self.assertIn("overflow-wrap:anywhere", detail_style)
        self.assertNotIn("position:absolute", detail_style)
        self.assertIn('id="eco-metric-detail"', HTML)
        self.assertLess(HTML.index('id="eco-location-summary"'), HTML.index('id="eco-overview-details"'))
        self.assertLess(HTML.index('id="eco-overview-details"'), HTML.index('id="eco-metric-detail"'))
        self.assertIn(".eco-metric-detail[hidden]{display:none!important}", CSS)
        self.assertIn(".eco-detail-formula strong{", CSS)


    def test_generator_tab_and_verified_specs(self):
        self.assertIn('id="eco-select-ecoflow"', HTML)
        self.assertIn('id="eco-select-generator"', HTML)
        self.assertIn('id="eco-tab-ecoflow"', HTML)
        self.assertIn('id="eco-tab-generator"', HTML)
        self.assertIn('EDON PT-3000', HTML)
        self.assertIn('2 800 W', HTML)
        self.assertIn('3 000 W', HTML)
        self.assertIn('15 л', HTML)
        self.assertIn('Ручний', HTML)
        self.assertIn('Планування заряджання', HTML)
        self.assertNotIn('Статус роботи, залишок пального та споживання не відстежуються автоматично.', HTML)
        self.assertIn('id="eco-generator-planner"', HTML)
        self.assertIn('id="eco-gen-dp3-time"', HTML)
        self.assertIn('id="eco-gen-all-time"', HTML)
        self.assertIn('id="eco-gen-dp3-energy"', HTML)
        self.assertIn('id="eco-gen-all-energy"', HTML)
        self.assertIn('id="eco-gen-soc-fields"', HTML)
        self.assertIn('id="eco-gen-charge-w"', HTML)
        self.assertIn('id="eco-gen-house-w"', HTML)
        self.assertIn('id="eco-gen-fuel"', HTML)
        self.assertIn('data-eco-gen-target="80"', HTML)
        self.assertIn('data-eco-gen-target="90"', HTML)
        self.assertIn('data-eco-gen-target="100"', HTML)
        self.assertIn('.eco-generator-plan-results', CSS)
        self.assertIn("selectBackupTab(name)", JS)
        self.assertIn("id !== 'dacha'", JS)
        self.assertIn(".eco-generator-specs", CSS)
        self.assertIn("#eco-tab-generator[hidden]", CSS)

    def test_generator_planner_is_linked_to_battery_inventory_not_hardcoded_energies(self):
        self.assertIn("const generatorPlan = {", JS)
        self.assertIn("generatorBatteryPacks()", JS)
        self.assertIn("batterySystems(inventory.dacha.devices)", JS)
        self.assertIn("d.id === 'dp3'", JS)
        self.assertIn("generatorPlan.soc.get(device.id)", JS)
        self.assertIn("d.capacityWh * Math.max(0, generatorPlan.targetPct - generatorSOC(d)) / 100", JS)
        self.assertIn("energyWh / (availableW * generatorChargeEfficiency)", JS)
        self.assertIn("const generatorChargeEfficiency = 0.85", JS)
        self.assertIn("const generatorSuggestedFraction = 0.8", JS)
        self.assertIn("generatorRatedW * generatorSuggestedFraction", JS)
        self.assertIn("Math.min(generatorPlan.chargeW, allowedW)", JS)
        self.assertIn("Math.ceil(dp3Missing)", JS)
        self.assertIn("Math.ceil(allMissing)", JS)
        self.assertIn("if (id === 'dacha') renderGeneratorPlanner();", JS)
        self.assertIn("[data-eco-gen-soc]", JS)
        self.assertIn("generatorPlan.fuelLph = input.value.trim()", JS)
        self.assertIn("let backupTab = 'ecoflow'", JS)
        self.assertIn(".eco-generator-soc-fields", CSS)
        self.assertIn(".eco-generator-target-options", CSS)
        self.assertNotRegex(JS, r"\bfetch\s*\(|XMLHttpRequest|WebSocket")

    def test_dacha_empty_state_and_physical_pack_counts(self):
        self.assertIn("physicalDevices(place.devices)", JS)
        self.assertIn("physicalDevices(inventory[activeEcoLocation].devices)", JS)
        self.assertIn("device.batteryCount <= 1", JS)
        self.assertIn("device.capacityWh / device.batteryCount", JS)
        self.assertIn('id="eco-overview-heading"', HTML)
        self.assertIn('id="eco-location-summary"', HTML)
        self.assertIn('id="eco-overview-details"', HTML)
        self.assertIn("$('eco-location-summary').hidden = empty", JS)
        self.assertIn("$('eco-overview-details').hidden = empty", JS)
        self.assertNotIn("if (!empty) displayMetric('capacity');", JS)
        self.assertIn("if (!refreshOnly) clearMetric();", JS)
        self.assertNotIn("eco-overview-details').open", JS)
        self.assertIn("У цій локації немає EcoFlow", JS)
        self.assertIn(".eco-empty-state", CSS)


    def test_consistent_w_display_units_without_mutating_capacity_calculations(self):
        self.assertIn("return Number.isFinite(wh) ? uk.format(wh) + ' Wh' : '—';", JS)
        self.assertIn("preciseWh.format(wh) + ' Wh'", JS)
        self.assertIn("uk.format(d.inverterKw * 1000) + ' W'", JS)
        self.assertIn("const solarUiEnabled = false;", JS)
        self.assertIn("wattsLabel(d.inputW)", JS)
        self.assertNotIn("кВт", JS)
        self.assertNotIn("кВт", HTML)
        self.assertNotIn("Вт", JS)
        self.assertNotIn("Вт", HTML)
        self.assertIn("4 800 Wh", HTML)
        self.assertIn("maximumFractionDigits: 2", JS)
        self.assertIn("device.capacityWh * device.pct / total", JS)
        self.assertIn("const weighted = stored !== null && total", JS)

    def test_solar_generation_is_read_only_and_dacha_only(self):
        self.assertIn('id="eco-solar"', HTML)
        self.assertIn('aria-label="Сонячна генерація DELTA Pro 3"', HTML)
        self.assertIn("Панелі ", HTML)
        self.assertIn('id="eco-solar-current"', HTML)
        self.assertIn('id="eco-solar-today"', HTML)
        self.assertIn('id="eco-solar-high"', HTML)
        self.assertIn('id="eco-solar-low"', HTML)
        self.assertIn('id="eco-solar-track"', HTML)
        self.assertIn("maxW: 2600", JS)
        self.assertIn("highMaxW: 1600", JS)
        self.assertIn("lowMaxW: 1000", JS)
        self.assertIn("function renderSolar(place)", JS)
        self.assertIn("if (!section || !station) return;", JS)
        self.assertIn("function solarDisclosure(device)", JS)
        self.assertIn("solarDisclosure(d)", JS)
        self.assertIn("source.innerHTML + '</details>'", JS)
        self.assertIn('<template id="eco-solar-template">', HTML)
        self.assertIn('<details class="eco-solar-disclosure">', JS)
        self.assertIn("Сонячна генерація", JS)
        self.assertIn("solarPowerLabel(device.solar.currentW)", JS)
        self.assertIn("solarPowerLabel(device.solar.maxW)", JS)
        self.assertIn("1 240 W", HTML)
        self.assertIn("820 W / 1 600 W", HTML)
        self.assertIn("420 W / 1 000 W", HTML)
        self.assertIn("4 800 Wh", HTML)
        self.assertNotIn("section.hidden = !station", JS)
        self.assertIn("renderSolar(place);", JS)
        self.assertIn("Очікується підключення EcoFlow", JS)
        self.assertIn(".eco-solar[hidden]{display:none!important}", CSS)
        self.assertIn(".eco-solar-overview{", CSS)
        self.assertIn(".eco-solar-channels{", CSS)
        self.assertIn(".eco-solar-disclosure > summary{", CSS)
        self.assertIn(".eco-solar-disclosure[open]>summary", CSS)
        self.assertIn(".eco-solar-disclosure .eco-solar{", CSS)
        self.assertIn(".eco-solar-disclosure .eco-solar-overview", CSS)
        self.assertIn("uk.format(watt) + ' W'", JS)
        self.assertIn(".eco-device.size-large{grid-column:span 24}", CSS)
        self.assertIn("role=\"progressbar\"", HTML)
        self.assertNotRegex(JS, r"\bfetch\s*\(|XMLHttpRequest|WebSocket")



    def test_solar_is_nested_in_station_and_no_longer_an_external_panel(self):
        template_open = HTML.index('<template id="eco-solar-template">')
        template_close = HTML.index('</template>', template_open)
        self.assertTrue(template_open < HTML.index('class="eco-devices" id="eco-devices"'))
        self.assertTrue(template_open < HTML.index('id="eco-solar"') < template_close)
        self.assertNotIn(' hidden>', HTML[template_open:template_close])
        device_fn = JS.split("function deviceView(d) {", 1)[1].split("function powerOceanView(d)", 1)[0]
        self.assertIn("solarDisclosure(d)", device_fn)
        self.assertIn("adminControls(d)", device_fn)
        self.assertLess(device_fn.index("solarDisclosure(d)"), device_fn.index("adminControls(d)"))
        loc = JS.split("function updateLocation(id, refreshOnly = false) {", 1)[1].split("// Read-only draft controls", 1)[0]
        self.assertLess(loc.index("renderDeviceGrid(place.devices)"), loc.index("renderSolar(place);"))
        self.assertIn("if (!solarUiEnabled || !device.solar) return '';", JS)
        self.assertIn("source.innerHTML", JS)


    def test_solar_values_are_preserved_but_panel_is_hidden(self):
        self.assertIn("currentW: 1240", JS)
        self.assertIn("highW: 820, lowW: 420", JS)
        self.assertIn("todayWh: 4800", JS)
        self.assertIn("connected: false", JS)
        self.assertIn("const solarUiEnabled = false;", JS)
        self.assertIn("if (!solarUiEnabled || !device.solar) return '';", JS)
        self.assertIn("solarPowerLabel(device.solar.currentW)", JS)
        self.assertIn("solarPowerLabel(device.solar.maxW)", JS)
        self.assertIn("progress.setAttribute('aria-valuenow'", JS)
        self.assertIn("Очікується підключення EcoFlow", JS)
        self.assertIn('Демо · API не підключено', HTML)


    def test_solar_footnote_removed_and_overview_details_closed_initially(self):
        self.assertNotIn('eco-solar-footnote', HTML)
        self.assertNotIn('не прогноз виробітку', HTML)
        self.assertIn('id="eco-metric-detail" aria-live="polite" hidden', HTML)
        self.assertNotIn("if (!empty) displayMetric('capacity');", JS)
        self.assertIn("metricOpen = null;", JS)
        self.assertIn("if (metricOpen === kind && !detailPanel.hidden) clearMetric();", JS)
        self.assertNotIn("detailArea.addEventListener('pointerover'", JS)
        self.assertNotIn("detailArea.addEventListener('focusin'", JS)



    def test_three_metric_chevrons_use_fixed_height_detail_panel(self):
        self.assertEqual(HTML.count('class="eco-metric-arrow"'), 3)
        self.assertNotIn('Детальніше <span>ⓘ</span>', HTML)
        self.assertIn(".eco-metrics .eco-metric-arrow{", CSS)
        self.assertIn(".eco-metrics .eco-metric.is-selected .eco-metric-arrow{", CSS)
        self.assertIn("transform:rotate(225deg)", CSS)
        self.assertIn("height:114px", CSS)
        self.assertIn("height:104px", CSS)
        self.assertIn("height:352px", CSS)
        self.assertIn("max-height:352px", CSS)
        self.assertIn("height:328px", CSS)
        self.assertIn("max-height:328px", CSS)
        self.assertIn("overflow-y:auto", CSS)
        self.assertIn("overscroll-behavior:contain", CSS)
        self.assertIn("detailPanel.scrollTop = 0;", JS)
        self.assertIn("if (metricOpen === kind && !detailPanel.hidden) clearMetric();", JS)



    def test_capacity_distribution_is_independent_of_state_of_charge(self):
        self.assertIn("Розподіл ємності локації", JS)
        self.assertIn("Частка від загальної номінальної ємності", JS)
        self.assertIn("const deviceShare = device => total ? device.capacityWh / total * 100 : 0;", JS)
        self.assertIn("fmtPercent(share) + ' від локації</strong>'", JS)
        self.assertIn("eco-detail-distribution", JS)
        self.assertIn("eco-detail-distribution i:nth-child", CSS)
        self.assertIn("Загальна ємність", JS)

    def test_average_charge_uses_percent_contributions_and_real_energy_units(self):
        self.assertIn("Внесок станцій у середній заряд", JS)
        self.assertIn("const chargeContribution = device => total && Number.isFinite(device.pct)", JS)
        self.assertIn("const storedEnergyWh = device => Number.isFinite(device.pct)", JS)
        self.assertIn("const savedEnergy = storedEnergyWh(device);", JS)
        self.assertIn("eco-detail-contribution", JS)
        self.assertIn("eco-detail-contribution-bar", JS)
        self.assertIn("eco-detail-stored", JS)
        self.assertIn("niceWh(Math.round(savedEnergy))", JS)
        self.assertIn("fmtPercent(contribution)) + '</strong>'", JS)
        self.assertIn("fmtPercent(contribution) + ' загального заряду", JS)
        self.assertIn("'<small>Заряд ' + pctLabel(device.pct)", JS)
        self.assertIn("Внески в середній заряд</span>", JS)
        self.assertIn("devices.map(device => fmtPercent(chargeContribution(device)))", JS)
        self.assertNotIn("в.п.", JS)
        self.assertIn(".eco-detail-charge .eco-detail-track i[data-level=", CSS)

    def test_physical_device_inventory_has_useful_station_details(self):
        self.assertIn("Станції та акумулятори локації", JS)
        self.assertIn("eco-detail-inventory", JS)
        self.assertIn("eco-detail-inventory-stats", JS)
        self.assertIn("Портативна зарядна станція", JS)
        self.assertIn("Акумуляторний модуль", JS)
        self.assertIn("Додаткова батарея до", JS)
        self.assertIn("operationMeta[device.operation]", JS)
        self.assertIn("Вхід ' + device.inputW + ' W · вихід ' + device.outputW", JS)
        self.assertIn(".eco-detail-inventory{", CSS)
        self.assertIn(".eco-detail-inventory-stats{", CSS)



if __name__ == "__main__":
    unittest.main()
