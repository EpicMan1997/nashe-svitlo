"""Regression cases for the three-source collector and building-specific evidence."""
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from refresh import (parse_bude_queue, parse_powercut_city, active_source_reports,
                     choose, apply_home_report, bude_read, change)

D=date(2026,11,25)
R=(('14:00','18:30'),)
OTHER=(('12:30','17:00'),)

class ActiveSourceTests(unittest.TestCase):
    def test_bude_dated_heading_and_exact_queue(self):
        page='Графік на сьогодні, 25 листопада, по чергах ДТЕК. Черга 3.1: 12:30–17:00 Черга 4.1: 14:00–18:30 Черга 14.1: 12:00–16:30 Графік по чергах на завтра Черга 4.1: 05:00–08:00'
        self.assertEqual(parse_bude_queue(page,D,D,'4.1'),R)
        self.assertEqual(parse_bude_queue(page,D,D,'3.1'),OTHER)
        self.assertIsNone(parse_bude_queue(page,D+timedelta(days=1),D,'4.1'))
        self.assertIsNone(parse_bude_queue(page,D+timedelta(days=1),D+timedelta(days=1),'4.1'))

    def test_bude_tomorrow_explicit_and_zero(self):
        page='Сьогодні, 25 листопада 2026 Черга 4.1: 14:00–18:30 Завтра, 26 листопада 2026 Черга 4.1: Без відключень Черга 10.1: 09:30–14:00, 18:30–23:00'
        self.assertEqual(parse_bude_queue(page,D+timedelta(days=1),D,'4.1'),())
        self.assertEqual(parse_bude_queue(page,D+timedelta(days=1),D,'10.1'),(('09:30','14:00'),('18:30','23:00')))

    def test_bude_alternate_page_never_adds_second_vote(self):
        v,p,u=bude_read('Сьогодні, 24 листопада','Сьогодні, 25 листопада Черга 4.1: 14:00–18:30',D,D,'4.1','https://kolybude.com/kyiv')
        self.assertEqual(v,R)
        self.assertTrue(u.endswith('?group=4.1'))

    def test_powercut_exact_date_operator_and_group(self):
        page='Графік на сьогодні середа, 25 листопада. ДТЕК Київські електромережі, за даними Yasno. Зараз без світла: 3.1, 4.1, 14.1. 3.1 12:30–17:00 без світла до 17:00 4.1 14:00–18:30 без світла до 18:30 14.1 12:00–16:30 світло є до 12:00 Графік на завтра четвер, 26 листопада. ДТЕК Київські електромережі. Оператор ще не оприлюднив графік.'
        self.assertEqual(parse_powercut_city(page,D,D,'4.1'),R)
        self.assertEqual(parse_powercut_city(page,D,D,'3.1'),OTHER)
        self.assertIsNone(parse_powercut_city(page,D+timedelta(days=1),D,'4.1'))
        self.assertIsNone(parse_powercut_city(page.replace('ДТЕК Київські електромережі','Інший оператор'),D,D,'4.1'))

    def test_fresh_single_is_not_stale_and_cache_is_not_a_vote(self):
        prior={'date':D.isoformat(),'status':'normal','outages':[list(x) for x in R],
               'sources':['Карта світла','КолиБуде'],'source_reports':{'КолиБуде':{'outages':[list(x) for x in R]}}}
        bez={'candidates':[R],'updated':'','unpublished':False}
        entry=choose(D,bez,None,None,prior,{'Powercut':None},primary_source='Карта світла',allow_early=True)
        self.assertEqual(entry['status'],'preliminary')
        self.assertTrue(entry['previously_confirmed'])
        reports=active_source_reports(entry,{'Карта світла':(R,'map'),'КолиБуде':(None,'bude'),'Powercut':(None,'powercut')},prior)
        self.assertEqual(reports['Карта світла']['status'],'preliminary')
        self.assertEqual(reports['КолиБуде']['status'],'old')
        self.assertEqual(len(reports),3)
        confirmed=choose(D,bez,None,R,entry,{'Powercut':None},primary_source='Карта світла',allow_early=True)
        self.assertEqual(confirmed['status'],'normal')
        self.assertIsNone(change(entry,confirmed))

    def test_building_override_only_for_home_and_supplied_day(self):
        entry={'date':D.isoformat(),'status':'normal','outages':[list(x) for x in R],'sources':['Карта світла','КолиБуде']}
        manual=apply_home_report(entry,'home',D,D)
        self.assertEqual(manual['outages'],[list(x) for x in OTHER])
        self.assertEqual(manual['status'],'preliminary')
        self.assertEqual(manual['local_report']['observed_off_at'],'12:38')
        self.assertEqual(apply_home_report(entry,'solovky',D,D),entry)
        self.assertEqual(apply_home_report(entry,'home',D+timedelta(days=1),D+timedelta(days=1)),entry)
