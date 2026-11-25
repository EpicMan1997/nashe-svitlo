import sys
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from refresh import parse_gpv, safe_read, annotate_source_health, choose

D=date(2026,11,25)
NOW=datetime(2026,11,25,16,0,tzinfo=ZoneInfo('Europe/Kyiv'))
CITY='Графік відключень у Києві на сьогодні, 25 листопада 3.1 12:30–17:00 · 4 год 30 хв є до 12:30 4.1 14:00–18:30 · 4 год 30 хв є до 14:00 10.1 09:30–14:00, 18:30–23:00 · 9 год є до 09:30 14.1 12:00–16:30 · 4 год 30 хв Графік відключень у Києві на завтра, 26 листопада Графік на 26 листопада ще не опубліковано Останні зміни 4.1 01:00–09:00 · 8 год'
REGION='Графік відключень у Київській області на сьогодні, 25 листопада 3.1 08:00–11:00, 17:30–20:30 · 6 год є до 08:00 3.2 06:00–11:00, 17:30–20:30 · 8 год є до 06:00'

class GPVTests(unittest.TestCase):
    def test_all_city_queues_and_scope(self):
        self.assertEqual(parse_gpv(CITY,D,D,'4.1',True),(('14:00','18:30'),))
        self.assertEqual(parse_gpv(CITY,D,D,'10.1',True),(('09:30','14:00'),('18:30','23:00')))
        self.assertEqual(parse_gpv(CITY,D,D,'3.1',True),(('12:30','17:00'),))
        self.assertIsNone(parse_gpv(CITY,D,D,'4.1',False))
        self.assertIsNone(parse_gpv(CITY,D+timedelta(days=1),D,'4.1',True))
        self.assertIsNone(parse_gpv(CITY,D+timedelta(days=1),D+timedelta(days=1),'4.1',True))
    def test_region_duration_and_ambiguity(self):
        self.assertEqual(parse_gpv(REGION,D,D,'3.1',False),(('08:00','11:00'),('17:30','20:30')))
        self.assertIsNone(parse_gpv(REGION.replace('· 6 год','· 7 год'),D,D,'3.1',False))
        self.assertIsNone(parse_gpv(REGION+' 3.1 10:00–12:00 · 2 год',D,D,'3.1',False))
    def test_parser_failure_isolated(self):
        errors=[]
        def fail():raise ValueError('bad markup')
        self.assertIsNone(safe_read(fail,None,errors,'source'))
        self.assertEqual(errors,['source: parse ValueError'])
    def test_recent_checks_and_unpublished_are_distinct(self):
        reports={'GPV':{'status':'match','outages':[['14:00','18:30']]}}
        annotate_source_health(reports,{'GPV':CITY},D,D,now=NOW)
        self.assertEqual(reports['GPV']['recent_checks'],['parsed'])
        previous=reports
        reports={'GPV':{'status':'old','outages':[['14:00','18:30']]}}
        annotate_source_health(reports,{'GPV':None},D,D,now=NOW+timedelta(minutes=10),previous=previous)
        self.assertEqual(reports['GPV']['recent_checks'],['parsed','network'])
        tomorrow={'GPV':{'status':'unavailable','outages':None}}
        annotate_source_health(tomorrow,{'GPV':CITY},D+timedelta(days=1),D,now=NOW)
        self.assertEqual(tomorrow['GPV']['status'],'unpublished')
    def test_no_sources_keep_same_day_nonzero_provisional_as_stale(self):
        old={'date':D.isoformat(),'status':'preliminary','outages':[['14:00','18:30']],'sources':['GPV']}
        empty={'candidates':[],'updated':'','unpublished':False}
        result=choose(D,empty,None,None,old,allow_early=True)
        self.assertEqual(result['status'],'stale')
        self.assertEqual(result['outages'],old['outages'])
        self.assertEqual(choose(D+timedelta(days=1),empty,None,None,old,allow_early=True)['status'],'unknown')
