from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT.joinpath("site/index.html").read_text(encoding="utf-8")


class VisualStatusContract(unittest.TestCase):
    """Source agreement and time since GitHub checked are distinct concepts."""

    def test_recent_source_consensus_does_not_require_fresh_github_job(self):
        self.assertIn("function currentStatus(e){return e?.status||'unknown'}", HTML)
        self.assertNotIn("if(s==='normal'&&(age>35||age< -5))s='delayed'", HTML)

    def test_four_matching_sources_are_still_verified(self):
        self.assertIn("const healthy=status==='normal'&&allMatch>=2", HTML)
        self.assertIn("healthy?'Графік підтверджено'", HTML)

    def test_old_source_is_independently_reported(self):
        self.assertIn("old:'Не оновлено'", HTML)
        self.assertIn("e.source_reports||{}", HTML)

    def test_age_only_colours_freshness_ring(self):
        self.assertIn("function updateRefreshRing(){", HTML)
        self.assertIn("ageLimit=10*60", HTML)
        self.assertNotIn("status==='delayed'", HTML)
        self.assertIn("age>=15*60", HTML)

    def test_freshness_does_not_expose_github_implementation_details(self):
        self.assertIn("function events(){", HTML)
        self.assertIn("changeDailyCount", HTML)
        self.assertIn("if(Number.isFinite(age)&&age>=15*60)message+=' · перевірка запізнюється';", HTML)
        self.assertNotIn("checkGithubRuns", HTML)
        self.assertNotIn("githubCheckedAt", HTML)
        self.assertNotIn("GitHub:", HTML)

    def test_obolon_is_clean_and_city_dtek_is_manual_only(self):
        self.assertNotIn("Група 4.1 попередня — потрібна адресна перевірка ДТЕК", HTML)
        self.assertIn("locationId!=='home'&&!activeLocation()?.address_verified", HTML)
        self.assertIn("ДТЕК</a><span class=\"source-verdict source-manual-verdict\">За адресою", HTML)
        self.assertIn("Перевірити вручну на сайті ДТЕК", HTML)
        self.assertIn("Object.keys(urls).filter(name=>rows[name]?.status==='match')", HTML)
        self.assertNotIn("'ДТЕК':'https://www.dtek-kem.com.ua/ua/shutdowns'", HTML)

    def test_source_palette_is_shared(self):
        self.assertIn("const palette=sourcePalette", HTML)
        self.assertIn("colors=sourcePalette", HTML)
        self.assertIn("const sourcePalette={", HTML)

    def test_five_current_source_colors_are_distinct(self):
        import re
        palette = re.search(r"const sourcePalette=\{(.*?)\};", HTML, re.S)
        self.assertIsNotNone(palette)
        colors = dict(re.findall(r"'([^']+)':'(#[0-9a-fA-F]{6})'", palette.group(1)))
        names = ['Карта світла', 'КолиСвітло', 'КолиБуде', 'Київщина.info', 'Alerts Energy']
        self.assertEqual(len(set(colors[name] for name in names)), 5)
        self.assertEqual(colors['ДТЕК'], colors['Київщина.info'])

    def test_current_outage_has_a_live_countdown_until_scheduled_restoration(self):
        self.assertIn('class="power-remaining" id="powerRemaining"', HTML)
        self.assertNotIn('id="powerRemainingNote"', HTML)
        self.assertIn('function currentOutageEnd(outages,minuteNow){', HTML)
        self.assertIn('function remainingOutageLabel(seconds){', HTML)
        self.assertIn('const outageEnd=canPredict?currentOutageEnd(outages,minuteNow):null;', HTML)
        self.assertIn("remaining.textContent=(emergencyOn?'За планом ще ':'Ще ')+remainingOutageLabel(seconds);", HTML)
        self.assertNotIn("remaining.textContent='Ще без світла: '", HTML)
        self.assertNotIn("'За графіком до '+String(Math.floor(outageEnd/60))", HTML)
        self.assertNotIn("'До кінця доби за графіком'", HTML)
        self.assertIn('remaining.hidden=!isOut;', HTML)
        self.assertIn("currentStatus(selectedEntry)==='normal'", HTML)
        self.assertIn('&&isFresh;', HTML)
        self.assertIn("if(!chip||tab!=='today')return;", HTML)
        self.assertIn('setInterval(tick,1000)', HTML)
        self.assertIn('updateCurrentPower(n)}', HTML)
        self.assertIn('.power-remaining[hidden]{display:none!important}', HTML)

    def test_yesterday_archive_and_comparison(self):
        refresh = ROOT.joinpath("scripts/refresh.py").read_text(encoding="utf-8")
        self.assertIn("'days':visible_days", refresh)
        self.assertIn("'days':visible_days,'logs':logs,'emergency':dacha_emergency,'operator':", refresh)
        self.assertIn("if k>=(today-timedelta(days=2)).isoformat()", refresh)
        self.assertIn("function changeComparison(parts){", HTML)
        self.assertIn("hoursAndMinutes(yMinutes)+' без світла'", HTML)
        self.assertIn("yesterday-count.zero", HTML)
        self.assertIn("yesterday-count.few", HTML)
        self.assertIn("yesterday-count.many", HTML)
        self.assertIn("item.date===yesterday&&eventKind(item)==='changed'", HTML)

    def test_yesterday_compact_and_unknown_archive(self):
        self.assertIn("$('previousTitle').textContent='Зміни і графік вчора'", HTML)
        self.assertIn("hoursAndMinutes(yMinutes)+' без світла'", HTML)
        self.assertIn(".yesterday-count.zero{color:#94a3b8}", HTML)
        self.assertIn("['normal','stale','suspended'].includes(saved.status)", HTML)
        self.assertNotIn("Графік за цей день не збережений", HTML)
        self.assertNotIn("Зміни графіка: '+count", HTML)

    def test_open_tomorrow_tab_marks_every_new_version_as_seen(self):
        self.assertIn("if(tab==='tomorrow'&&tomorrowFingerprint()){markTomorrowSeen();updateTomorrowTab()}", HTML)
        self.assertIn("setInterval(reload,15000)", HTML)

    def test_public_location_aliases_do_not_disclose_private_addresses(self):
        for key, label in [('dacha','Дача'),('home','Дім'),('solovky','Соловки'),('naumenky','Науменки')]:
            self.assertIn(f'data-location="{key}">{label} <small class="location-group-hint" hidden></small></button>', HTML)
        self.assertIn("const names={dacha:'Дача',home:'Дім',solovky:'Соловки',naumenky:'Науменки'}", HTML)
        self.assertIn("remember('dubechnya-selected-location',key)", HTML)
        self.assertNotIn('Квіткова 251', HTML)
        self.assertNotIn('Оболонський проспект 54', HTML)
        refresh=ROOT.joinpath("scripts/refresh.py").read_text(encoding="utf-8")
        self.assertNotIn("'street':", refresh)
        self.assertIn("'home': {'name':'Дім'", refresh)
        self.assertIn("'solovky': {'name':'Соловки'", refresh)
        self.assertIn("'naumenky': {'name':'Науменки'", refresh)
        state=__import__('json').loads(ROOT.joinpath('state/state.json').read_text(encoding='utf-8'))
        self.assertEqual(set(state['locations']),{'home','solovky','naumenky'})
        for key, label in [('home','Дім'),('solovky','Соловки'),('naumenky','Науменки')]:
            self.assertEqual(state['locations'][key]['name'],label)
            self.assertTrue(state['locations'][key]['logs'])
            self.assertTrue(state['locations'][key]['days'])

    def test_main_group_number_only_inside_location_menu(self):
        # Main heading stays clean; menu labels show 3, 4, 4, 10 without .1.
        self.assertIn('<span id="locationLabel">Дача</span><span class="location-chevron"', HTML)
        self.assertNotIn('id="locationGroup"', HTML)
        self.assertNotIn(".location-button #locationGroup{", HTML)
        self.assertIn("(group?'Група '+String(group).split('.')[0]:'')+(alert?.level==='active'?' · Екстрені відключення'", HTML)
        self.assertIn("hint.hidden=!group", HTML)
        refresh = ROOT.joinpath("scripts/refresh.py").read_text(encoding="utf-8")
        self.assertIn("'group':'4.1'", refresh)
        self.assertIn("'group':'10.1'", refresh)
        self.assertIn("parse_mapasvitla(city_map_pages[config['group']]", refresh)

    def test_previous_daily_changes_are_collapsed_but_available(self):
        self.assertIn("const previousEdits=logs.filter(item=>eventKind(item)==='changed'&&item!==logs[0]);", HTML)
        self.assertIn("previousEdits.map(compactYesterdayCard).join('')", HTML)
        self.assertIn("previousEdits.length?'<details id=\"earlierChanges\"", HTML)
        self.assertIn("const earlierOpen=$('earlierChanges')?.dataset.scope===earlierScope&&$('earlierChanges').open;", HTML)
        self.assertIn("data-scope=", HTML)
        self.assertIn("eventCard(logs[0])", HTML)
        self.assertIn(".earlier-changes>summary", HTML)

    def test_short_outage_boundaries_merge_without_losing_original_times(self):
        self.assertIn("function prepareBoundaryLabels(out){", HTML)
        self.assertIn("prepareBoundaryLabels(out);const city=", HTML)
        self.assertIn("merged.textContent=from+'–'+to", HTML)
        self.assertIn("a.hidden=true;b.hidden=true", HTML)
        self.assertIn("getBoundingClientRect().width", HTML)
        self.assertIn(".axis.outage-boundary[hidden]{display:none!important}", HTML)
        self.assertIn("Math.abs(first-currentMinute)<=30||Math.abs(last-currentMinute)<=30", HTML)

    def test_mobile_time_labels_use_measured_nonoverlapping_lanes(self):
        self.assertIn("function updateBoundaryLanes(n){", HTML)
        self.assertIn("graph.getBoundingClientRect()", HTML)
        self.assertIn("label.getBoundingClientRect().width", HTML)
        self.assertIn("const lanes=[", HTML)
        self.assertIn("{top:5,occupied:[]}", HTML)
        self.assertIn("{top:28,occupied:[]}", HTML)
        self.assertIn("{top:94,occupied:[]}", HTML)
        self.assertIn("{top:117,occupied:[]}", HTML)
        self.assertIn("lane.occupied.some(([left,right])=>x1<right+padding&&x2>left-padding)", HTML)
        self.assertIn("label.style.visibility='hidden'", HTML)
        self.assertIn("label.style.visibility='visible'", HTML)
        self.assertIn("label.style.left=center+'px'", HTML)
        self.assertIn("graph.querySelectorAll('.axis.start,.axis.end')", HTML)
        self.assertIn("window.addEventListener('resize',()=>{updateBoundaryLanes(now())})", HTML)

    def test_mobile_location_dropdown_expands_in_normal_document_flow(self):
        css = ROOT.joinpath("site/ecoflow.css").read_text(encoding="utf-8")
        self.assertIn("classList.toggle('location-menu-expanded',expanded)", HTML)
        self.assertIn("classList.remove('location-menu-expanded')", HTML)
        self.assertIn("if(expanded)closeViewMenu()", HTML)
        self.assertIn("@media(max-width:650px)", css)
        self.assertIn("main > header.location-menu-expanded #locationMenu:not([hidden])", css)
        self.assertIn("position:static;", css)
        self.assertIn("grid-template-columns:repeat(2,minmax(0,1fr))", css)
        self.assertIn("main > header.location-menu-expanded .clock-view", css)
        self.assertIn("main > header.location-menu-expanded .header-time", css)
        self.assertIn("@media(max-width:380px)", css)

    def test_emergency_warning_is_compact_and_keeps_schedule(self):
        self.assertIn("const emergency=tab==='today'?data?.locations?.[locationId]?.emergency:null;", HTML)
        self.assertIn("class=\"emergency-banner", HTML)
        self.assertIn("role=\"alert", HTML)
        self.assertIn("Екстрені в окремих районах", HTML)
        self.assertIn("Екстрені відключення", HTML)
        self.assertIn("Графік орієнтовний", HTML)
        self.assertIn("Перевірте свою адресу", HTML)
        self.assertIn("class=\"emergency-primary", HTML)
        self.assertIn("class=\"emergency-secondary", HTML)
        self.assertIn("class=\"emergency-link", HTML)
        self.assertIn("aria-label=\"Відкрити повідомлення ДТЕК\"", HTML)
        self.assertNotIn("Погодинний графік нижче збережено для орієнтиру, але", HTML)
        self.assertNotIn("ДТЕК повідомив про екстрені обмеження у вашому регіоні.", HTML)
        self.assertIn("emergencyOn?'Плановий графік'", HTML)
        self.assertIn("За планом: без світла", HTML)
        self.assertIn("За планом: зі світлом", HTML)
        self.assertIn("За планом ще ", HTML)
        self.assertIn("'<div class=\"graph\"><div class=\"bar", HTML)
        self.assertIn("out.forEach(x=>", HTML)
        css = ROOT.joinpath("site/ecoflow.css").read_text(encoding="utf-8")
        self.assertIn(".emergency-banner{", css)
        self.assertIn(".emergency-message{", css)
        self.assertIn(".emergency-unverified .emergency-symbol", css)
        self.assertIn("@media(max-width:700px){", css)
        self.assertIn("@media(max-width:350px){", css)


    def test_daily_change_badge_high_contrast_and_color_thresholds(self):
        self.assertIn("min-width:32px;height:32px", HTML)
        self.assertIn("font-size:18px;font-weight:850", HTML)
        self.assertIn(".change-count.zero{border-color:#53657b;background:#263449;color:#cbd5e1}", HTML)
        self.assertIn(".change-count.few{border-color:#eab308;background:#503b13;color:#fef08a}", HTML)
        self.assertIn(".change-count.many{border-color:#fb7185;background:#54202f;color:#ffe4e6}", HTML)
        self.assertIn("changeCount.classList.remove('zero','few','many');", HTML)
        self.assertIn("changeCount.classList.add(edits===0?'zero':edits<=2?'few':'many');", HTML)

    def test_historic_event_does_not_claim_unverified_first_signal(self):
        self.assertIn("Одне з джерел, що підтвердили зміну:", HTML)
        self.assertIn("const name=first||confirmed;", HTML)
        self.assertIn("item.sources_confirmed.find(x=>sourcePalette[x])", HTML)
        self.assertIn("info.first?'Перший сигнал':'Підтвердив'", HTML)
        self.assertIn("change-source-name", HTML)


if __name__ == '__main__':
    unittest.main()
