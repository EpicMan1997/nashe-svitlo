import sys,unittest,json
from zoneinfo import ZoneInfo
from datetime import date,datetime,timezone,timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from refresh import normalize,pairs,parse_bez,parse_kolysvitlo,parse_kolybude,parse_kyivshchyna,parse_svitlolive,source_reports,parse_alerts,parse_mapasvitla,choose,change,make_log_event,record_source_observations,earliest_observed_source,parse_city_bez,parse_city_koly,parse_city_bude,city_sources,CITY_LOCATIONS,parse_dtek_notice,parse_dtek_telegram,select_emergency
D=date(2026,10,24)
E=(('08:00','12:00'),('18:30','22:30'))
B='<h1>Вища Дубечня на 24.10.2026</h1><h3>Графік Черга 3.1</h3>00:00 – 08:00 08:00 – 12:00 12:00 – 18:30 18:30 – 22:30 22:30 – 24:00 Зберегти підчергу'
K='Сьогодні, 24 жовтня 2026 р. 3.1 Немає світла: 08:00–12:00, 18:30–22:30 3.2 Немає світла: 08:00–12:00'
KB='Сьогодні, 24 жовтня 2026. Черга 3.1: 08:00–12:00, 18:30–22:30 Черга 3.2: 08:00–12:00'
class DtekEmergencyTests(unittest.TestCase):
 def setup_now(self):
  return datetime(2026,11,1,13,15,tzinfo=ZoneInfo('Europe/Kyiv'))
 def post(self, number, time, body):
  return ('<div class="tgme_widget_message" data-post="dtek_ua/'+str(number)+'">'
    '<div class="tgme_widget_message_text">'+body+'</div>'
    '<a class="tgme_widget_message_date"><time datetime="'+time+'">13:15</time></a></div>')
 def test_city_emergency_without_mutating_schedules(self):
  page=self.post(4901,'2026-11-01T08:14:00+02:00',
    '‼️Київ: через обстріли застосовані екстрені відключення. Графіки не діють.')
  result=parse_dtek_telegram(page,self.setup_now())
  self.assertEqual(result['city']['level'],'active')
  self.assertEqual(result['city']['url'],'https://t.me/dtek_ua/4901')
  self.assertNotIn('dacha',result)
 def test_dacha_only_when_oblast_or_vyshhorod_is_affected(self):
  page=self.post(4902,'2026-11-01T08:00:00+02:00',
    'Київщина: в Обухівському та Бучанському районах аварія, графіки не діють.')
  self.assertIsNone(parse_dtek_telegram(page,self.setup_now()).get('dacha'))
  page=self.post(4903,'2026-11-01T08:10:00+02:00',
    '‼️Київщина: у Вишгородському районі екстрені відключення.')
  self.assertEqual(parse_dtek_telegram(page,self.setup_now())['dacha']['level'],'partial')
 def test_city_partial_is_never_reported_as_citywide(self):
  page=self.post(4904,'2026-11-01T07:30:00+02:00',
    '‼️Правий берег Києва: аварія на обладнанні, графіки тимчасово не діють.')
  self.assertEqual(parse_dtek_telegram(page,self.setup_now())['city']['level'],'partial')
 def test_explicit_cancellation_wins_over_older_emergency(self):
  page=(self.post(4901,'2026-11-01T07:30:00+02:00',
    '‼️Київ: застосовані екстрені відключення')+
    self.post(4902,'2026-11-01T09:30:00+02:00',
      '💡Київ: повертаємось до графіків, екстрені відключення скасовано'))
  self.assertIsNone(parse_dtek_telegram(page,self.setup_now())['city'])
 def test_stale_and_future_posts_are_rejected(self):
  page=self.post(4901,'2026-10-29T08:00:00+02:00',
    '‼️Київ: екстрені відключення')
  self.assertFalse(parse_dtek_telegram(page,self.setup_now()))
  page=self.post(4902,'2026-11-02T08:00:00+02:00',
    '‼️Київ: екстрені відключення')
  self.assertFalse(parse_dtek_telegram(page,self.setup_now()))
 def test_generic_article_and_other_city_do_not_trigger(self):
  self.assertIsNone(parse_dtek_notice('Київ: графік відключень на завтра.'))
  self.assertIsNone(parse_dtek_notice('Дніпро: екстрені відключення.'))
  self.assertIsNone(parse_dtek_notice('Обережно: шахраї в Києві.'))
 def test_failed_feed_keeps_recent_warning_without_claiming_verification(self):
  now=self.setup_now()
  recent={'level':'active','published_at':'2026-11-01T09:00:00+02:00','source_checked':True}
  old={'level':'active','published_at':'2026-10-30T09:00:00+02:00','source_checked':True}
  self.assertFalse(select_emergency({},'city',recent,now,False)['source_checked'])
  self.assertIsNone(select_emergency({},'city',old,now,False))
  self.assertFalse(select_emergency({},'city',recent,now,True)['source_checked'])
  self.assertIsNone(select_emergency({'city':None},'city',recent,now,True))

class Tests(unittest.TestCase):
 def test_bez(self):self.assertIn(E,parse_bez(B,D)['candidates'])
 def test_koly(self):self.assertEqual(parse_kolysvitlo(K,D,D),E)
 def test_koly_real_navigation(self):
  site='Графік відключень Київська область Сьогодні, 24 жовтня 2026 р. Моя черга Оберіть свою чергу Усі черги Сьогодні Завтра 0 6 12 18 24 1.1 6–8:30 Немає світла: 06:00–08:30 2.2 15–19 Немає світла: 15:00–19:00 3.1 8–12 18:30–22:30 Немає світла: 08:00–12:00, 18:30–22:30 3.2 8–12 Немає світла: 08:00–12:00 Графік на завтра ще не опубліковано'
  self.assertEqual(parse_kolysvitlo(site,D,D),E)
 def test_koly_tomorrow_if_date_published(self):
  site='Сьогодні, 24 жовтня 2026 р. 3.1 Немає світла: 08:00–12:00 3.2 Завтра, 25 жовтня 2026 р. 3.1 Немає світла: 09:30–11:00 3.2'
  self.assertEqual(parse_kolysvitlo(site,date(2026,10,25),D),(('09:30','11:00'),))
 def test_bude(self):self.assertEqual(parse_kolybude(KB,D,D),E)
 def test_concensus(self):self.assertEqual(choose(D,parse_bez(B,D),E,None,{})['status'],'normal')
 def test_conflict(self):self.assertEqual(choose(D,{'candidates':[E],'updated':'','unpublished':False},(('15:00','16:00'),),None,{})['status'],'unknown')
 def test_stale(self):self.assertEqual(choose(D,{'candidates':[],'updated':'','unpublished':False},None,None,{'date':D.isoformat(),'status':'normal','outages':[['08:00','12:00']]})['status'],'stale')
 def test_tomorrow(self):self.assertIsNone(parse_kolysvitlo(K,date(2026,10,25),D))
 def test_zero(self):self.assertEqual(parse_kolysvitlo('Сьогодні, 24 жовтня 2026 р. 3.1 Без відключень 3.2',D,D),())
 def test_merge(self):self.assertEqual(normalize([('12:00','13:00'),('13:00','14:00')]),(('12:00','14:00'),))
 def test_unpublished(self):self.assertTrue(parse_bez('На 25.10.2026 ще не опубліковано',date(2026,10,25))['unpublished'])
 def test_no_wrong_date(self):self.assertEqual(parse_bez(B,date(2026,10,25))['candidates'],[])
 def test_region_dated(self):
  page='Графік сьогодні 24.10.2026 Черга 3.1 8 год без світла без світла: 08:00–12:00 18:30–22:30 Черга 3.2'
  self.assertEqual(parse_kyivshchyna(page,D,D),E)
 def test_region_refuse_tomorrow(self):
  page='24.10.2026 Черга 3.1 без світла: 08:00–12:00 Черга 3.2'
  self.assertIsNone(parse_kyivshchyna(page,date(2026,10,25),D))
 def test_svitlolive_partial_not_exact(self):
  cells=['●']*24
  for i in range(8,12):cells[i]='✕'
  cells[18]='%'
  for i in range(19,22):cells[i]='✕'
  page='Графік на сьогодні - черга 3.1 24.10.2026 Черга 3.1 '+' '.join(cells)+' Графік на завтра - черга 3.1'
  report=parse_svitlolive(page,D,D)
  self.assertEqual(report['outages'],(('08:00','12:00'),('19:00','22:00')))
  self.assertEqual(report['partial'],['18:00–19:00'])
 def test_source_reports_not_faked(self):
  consensus={'date':D.isoformat(),'status':'normal','outages':[list(x) for x in E],'url':'https://example.com'}
  result=source_reports(consensus,{'candidates':[E],'updated':'','unpublished':False},E,E,(('08:00','12:00'),('18:30','22:00')),None,{})
  self.assertEqual(len(result),5)
  self.assertEqual(result['КолиСвітло']['status'],'match')
  self.assertEqual(result['Київщина.info']['status'],'diff')
  self.assertNotIn('Svitlo.live',result)

 def test_kyiv_address_groups(self):
  self.assertEqual(CITY_LOCATIONS['home']['group'],'4.1')
  self.assertEqual(CITY_LOCATIONS['solovky']['group'],'4.1')
  self.assertEqual(CITY_LOCATIONS['naumenky']['group'],'10.1')
 def test_kyiv_bez_queue(self):
  page='<h1>Графік у Києві на 24.10.2026</h1>Графік Черга 4.1 00:00 – 07:30 07:30 – 11:00 11:00 – 16:30 16:30 – 20:00 20:00 – 24:00 Зберегти підчергу'
  result=parse_city_bez(page,D,'4.1')
  self.assertIn((('07:30','11:00'),('16:30','20:00')),result['candidates'])
 def test_kyiv_colysvitlo(self):
  page='Графік Київ Сьогодні, 24 жовтня 2026 р. Усі групи Сьогодні Завтра 0 6 12 18 24 3.1 Немає світла: 06:00–07:00 4.1 7:30–11 16:30–20 Немає світла: 07:30–11:00, 16:30–20:00 4.2 Без відключень 10.1 0–3:30 12–15:30 Немає світла: 00:00–03:30, 12:00–15:30 11.1 Без відключень'
  self.assertEqual(parse_city_koly(page,D,D,'4.1'),(('07:30','11:00'),('16:30','20:00')))
  self.assertEqual(parse_city_koly(page,D,D,'10.1'),(('00:00','03:30'),('12:00','15:30')))
 def test_kyiv_kolybude_reject_old_day(self):
  page='Графік відключень світла у Києві на сьогодні, 17 жовтня, Черга 4.1: 22:00–24:00'
  self.assertIsNone(parse_city_bude(page,D,D,'4.1'))
 def test_city_source_dtek_not_faked(self):
  expected={'date':D.isoformat(),'status':'normal','outages':[['07:30','11:00']],'sources':['КолиСвітло','КолиБуде']}
  result=city_sources(expected,{'candidates':[]},(('07:30','11:00'),),(('07:30','11:00'),),'https://example.com',{})
  self.assertNotIn('ДТЕК',result)
  self.assertEqual(result['КолиСвітло']['status'],'match')
  self.assertEqual(len(result),4)
  script=Path(__file__).resolve().parents[1].joinpath('scripts/refresh.py').read_text(encoding='utf-8')
  self.assertNotIn("city_dtek=fetch(",script)
  self.assertNotIn("'ДТЕК':None",script)
 def test_alerts_region_half_hour_codes(self):
  slots=[0]*24
  for i in range(8,12):slots[i]=1
  slots[18]=3
  for i in range(19,22):slots[i]=1
  slots[22]=2
  payload={'someKey':{'rows':[{'queue':'3.1','initiator':'kyivska_oblast_oblenergo','todayDate':'2026-10-24','todayStatus':'ScheduleApplies','today':slots,'todayPossible':[0]*24}]}}
  page='<html><script id="ng-state" type="application/json">'+json.dumps(payload)+'</script></html>'
  self.assertEqual(parse_alerts(page,D,'3.1','kyivska_oblast_oblenergo'),E)
  self.assertIsNone(parse_alerts(page,D,'3.1','kyiv_oblenergo'))
  self.assertIsNone(parse_alerts(page,date(2026,10,25),'3.1','kyivska_oblast_oblenergo'))
 def test_alerts_city_half_hours(self):
  slots=[0]*24;slots[7]=3;slots[8:11]=[1,1,1];slots[16]=3;slots[17:20]=[1,1,1]
  page='<script id="ng-state" type="application/json">'+json.dumps({'wrapper':[{'initiator':'kyiv_oblenergo','queue':'4.1','today':slots,'todayDate':'2026-10-24','todayStatus':'ScheduleApplies'}]})+'</script>'
  self.assertEqual(parse_alerts(page,D,'4.1','kyiv_oblenergo'),(('07:30','11:00'),('16:30','20:00')))
 def test_alerts_reject_ambiguous_and_possible(self):
  slots=[0]*24;slots[8]=1
  row={'initiator':'kyivska_oblast_oblenergo','queue':'3.1','today':slots,'todayDate':'2026-10-24','todayStatus':'ScheduleApplies','todayPossible':[0]*24}
  ambiguous=dict(row,today=[0]*24)
  page='<script id="ng-state" type="application/json">'+json.dumps({'rows':[row,ambiguous]})+'</script>'
  self.assertIsNone(parse_alerts(page,D,'3.1','kyivska_oblast_oblenergo'))
  row['todayPossible'][8]=1
  page='<script id="ng-state" type="application/json">'+json.dumps([row])+'</script>'
  self.assertIsNone(parse_alerts(page,D,'3.1','kyivska_oblast_oblenergo'))
 def test_alerts_no_outage_is_valid(self):
  row={'initiator':'kyiv_oblenergo','queue':'10.1','today':[0]*24,'todayDate':'2026-10-24','todayStatus':'ScheduleApplies'}
  page='<script id="ng-state" type="application/json">'+json.dumps(row)+'</script>'
  self.assertEqual(parse_alerts(page,D,'10.1','kyiv_oblenergo'),())
 def test_tomorrow_two_sources_including_alerts(self):
  target=date(2026,10,25)
  ranges=(('09:00','12:00'),('18:00','21:30'))
  result=choose(target,{'candidates':[ranges,(('00:00','09:00'),('12:00','18:00'),('21:30','24:00'))],'unpublished':False,'updated':''},None,None,{}, {'Alerts Energy':ranges})
  self.assertEqual(result['status'],'normal')
  self.assertEqual(result['outages'],[list(x) for x in ranges])
  self.assertEqual(set(result['sources']),{'БезСвітла','Alerts Energy'})
 def test_tomorrow_two_fresh_aggregators_without_bez(self):
  target=date(2026,10,25)
  ranges=(('10:30','13:00'),)
  result=choose(target,{'candidates':[],'unpublished':True,'updated':''},None,None,{}, {'Alerts Energy':ranges,'Київщина.info':ranges})
  self.assertEqual(result['status'],'normal')
  self.assertEqual(result['outages'],[list(x) for x in ranges])
 def test_tomorrow_unverified_single_source_is_unknown(self):
  target=date(2026,10,25)
  ranges=(('10:30','13:00'),)
  result=choose(target,{'candidates':[],'unpublished':True,'updated':''},None,None,{}, {'Alerts Energy':ranges})
  self.assertEqual(result['status'],'unknown')
 def test_structured_change_event(self):
  moment=datetime(2026,10,25,8,16,tzinfo=timezone(timedelta(hours=2)))
  old={'status':'normal','outages':[['07:00','09:00'],['16:00','19:30']]}
  new={'status':'normal','outages':[['16:00','19:30']],'sources':['Alerts Energy','КолиСвітло']}
  event=make_log_event(moment,date(2026,10,25),old,new,'Змінено графік')
  self.assertEqual(event['kind'],'changed')
  self.assertEqual(event['before'],old['outages'])
  self.assertEqual(event['after'],new['outages'])
  self.assertEqual(event['at'],'2026-10-25T08:16+02:00')
  self.assertEqual(event['sources_confirmed'],new['sources'])
 def test_publication_does_not_count_as_change(self):
  moment=datetime(2026,10,24,20,24,tzinfo=timezone(timedelta(hours=3)))
  new={'status':'normal','outages':[['09:00','12:00']],'sources':['БезСвітла','Alerts Energy']}
  event=make_log_event(moment,date(2026,10,25),{},new,'Опубліковано графік')
  self.assertEqual(event['kind'],'published')
  self.assertIsNone(event['before'])
  self.assertEqual(event['date'],'2026-10-25')
 def test_bez_regional_fallback_parser(self):
  page='<h1>Київська область на 25.10.2026</h1>Оновлено: 25.10.2026 13:48 Графік Черга 3.1 00:00 – 16:00 16:00 – 19:30 19:30 – 24:00 Зберегти підчергу Історія змін 25.10.2026 06:14'
  parsed=parse_bez(page,date(2026,10,25))
  self.assertIn((('16:00','19:30'),),parsed['candidates'])
  self.assertTrue(parsed['updated'])
 def test_first_observed_source_only_when_unique(self):
  moment=datetime(2026,10,25,8,16,tzinfo=timezone(timedelta(hours=2)))
  intervals=[['16:00','19:30']]
  old={'source_observations':{'Alerts Energy':{'fingerprint':json.dumps(intervals,ensure_ascii=False,sort_keys=True),'first_seen':'2026-10-25T08:06+02:00'}}}
  new={'outages':intervals,'sources':['Alerts Energy','КолиСвітло'],'source_reports':{
   'Alerts Energy':{'status':'match','outages':intervals},
   'КолиСвітло':{'status':'match','outages':intervals}}}
  record_source_observations(moment,old,new)
  self.assertEqual(earliest_observed_source(new),'Alerts Energy')
  changed=make_log_event(moment,date(2026,10,25),{'status':'normal','outages':[['07:00','09:00']]},new,'Змінено графік')
  self.assertEqual(changed['first_observed_source'],'Alerts Energy')
 def test_first_observed_source_tie_is_not_guessed(self):
  now=datetime(2026,10,25,8,16,tzinfo=timezone(timedelta(hours=2)))
  new={'outages':[['16:00','19:30']],'sources':['Alerts Energy','КолиСвітло'],
       'source_reports':{'Alerts Energy':{'outages':[['16:00','19:30']],'status':'match'},
                         'КолиСвітло':{'outages':[['16:00','19:30']],'status':'match'}}}
  record_source_observations(now,{},new)
  self.assertIsNone(earliest_observed_source(new))
 def test_stale_source_not_assumed_new_signal(self):
  now=datetime(2026,10,25,8,16,tzinfo=timezone(timedelta(hours=2)))
  new={'outages':[['16:00','19:30']],'sources':['КолиСвітло'],
       'source_reports':{'БезСвітла':{'outages':[['16:00','19:30']],'status':'old'},
                         'КолиСвітло':{'outages':[['16:00','19:30']],'status':'match'}}}
  record_source_observations(now,{},new)
  self.assertNotIn('БезСвітла',new['source_observations'])
  self.assertEqual(earliest_observed_source(new),'КолиСвітло')
 def test_mapasvitla_today_and_tomorrow_scopes(self):
  html='<title>Черга 3.1, ДТЕК Київські регіональні — графік</title><div data-day="today">План на сьогодні, нд 25.10 0 1 2 3 4 світло є немає світла 16:00 – 19:30 3,5 год Всього без світла 3,5 год</div><div data-day="tomorrow">Очікуємо графік Оператор ще не опублікував графік на завтра.</div>'
  parsed=parse_mapasvitla(html,date(2026,10,25),date(2026,10,25),'3.1')
  self.assertEqual(parsed['candidates'],[(('16:00','19:30'),)])
  self.assertTrue(parse_mapasvitla(html,date(2026,10,26),date(2026,10,25),'3.1')['unpublished'])
  self.assertFalse(parse_mapasvitla(html,date(2026,10,24),date(2026,10,25),'3.1')['candidates'])
 def test_mapasvitla_city_exact_group_and_date(self):
  html='<title>Черга 4.1, ДТЕК Київські електромережі — графік</title><div data-day="today">План на сьогодні, нд 25.10 09:00 – 12:30 22:00 – 24:00 Всього без світла 5,5 год</div>'
  result=parse_mapasvitla(html,date(2026,10,25),date(2026,10,25),'4.1')
  self.assertEqual(result['candidates'],[(('09:00','12:30'),('22:00','24:00'))])
  self.assertFalse(parse_mapasvitla(html,date(2026,10,25),date(2026,10,25),'10.1')['candidates'])
  self.assertFalse(parse_mapasvitla(html,date(2026,10,26),date(2026,10,26),'4.1')['candidates'])
 def test_mapasvitla_no_outages_not_unknown(self):
  html='<title>Черга 3.1</title><div data-day="today">План на сьогодні, нд 25.10 Світло весь день Всього без світла 0 год</div>'
  result=parse_mapasvitla(html,date(2026,10,25),date(2026,10,25),'3.1')
  self.assertEqual(result['candidates'],[()])
 def test_consensus_map_source_label(self):
  intervals=(('16:00','19:30'),)
  primary={'candidates':[intervals],'unpublished':False,'updated':'','url':'https://mapasvitla.com.ua/kyivska-oblast/dtek-krem/3.1'}
  result=choose(date(2026,10,25),primary,intervals,None,{},primary_source='Карта світла')
  self.assertEqual(result['status'],'normal')
  self.assertEqual(set(result['sources']),{'Карта світла','КолиСвітло'})
 def test_early_tomorrow_single_source_is_visible_but_unconfirmed(self):
  date_next=date(2026,10,31)
  ranges=(('08:00','12:00'),('18:30','22:30'))
  result=choose(date_next,{'candidates':[],'unpublished':True,'updated':''},None,None,{}, {'Alerts Energy':ranges},allow_early=True)
  self.assertEqual(result['status'],'preliminary')
  self.assertEqual(result['outages'],[list(r) for r in ranges])
  self.assertEqual(result['sources'],['Alerts Energy'])
  self.assertFalse(result['alternatives'])
  self.assertIsNone(change({},result))
 def test_early_conflicting_providers_are_visible_as_alternatives(self):
  date_next=date(2026,10,31)
  alerts=(('08:00','12:00'),('18:30','22:30'))
  map_schedule=(('08:00','11:30'),('18:30','22:00'))
  result=choose(date_next,{'candidates':[map_schedule],'unpublished':False,'updated':''},None,None,{}, {'Alerts Energy':alerts},primary_source='Карта світла',allow_early=True)
  self.assertEqual(result['status'],'preliminary')
  self.assertEqual(result['outages'],[list(r) for r in alerts])
  self.assertEqual(result['alternatives'][0]['outages'],[list(r) for r in map_schedule])
 def test_early_ambiguous_map_is_not_a_trusted_single_source(self):
  future=date(2026,10,31)
  a=(('08:00','12:00'),)
  b=(('12:00','18:00'),)
  result=choose(future,{'candidates':[a,b],'unpublished':False,'updated':''},None,None,{},allow_early=True,primary_source='Карта світла')
  self.assertEqual(result['status'],'unknown')
 def test_no_repeat(self):self.assertIsNone(change({'status':'normal','outages':[['08:00','12:00']]},{'status':'normal','outages':[['08:00','12:00']]}))
