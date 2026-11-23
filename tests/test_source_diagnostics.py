"""Confirm source freshness and parser errors never masquerade as missing schedules."""
import sys
import unittest
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from refresh import annotate_source_health

class SourceDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.today = date(2026, 11, 23)
        self.now = datetime(2026, 11, 23, 20, 0, tzinfo=ZoneInfo('Europe/Kyiv'))

    def test_current_parsed_report_stamped_as_checked_and_seen(self):
        reports = {'Карта світла': {'status': 'match', 'outages': [['11:00', '18:00']]}}
        annotate_source_health(reports, {'Карта світла': '<html>ok</html>'},
                               self.today, self.today, now=self.now)
        report = reports['Карта світла']
        self.assertEqual(report['checked_at'], self.now.isoformat(timespec='minutes'))
        self.assertEqual(report['data_seen_at'], self.now.isoformat(timespec='minutes'))
        self.assertEqual(report['status'], 'match')

    def test_successful_fetch_without_parsed_hours_is_unreadable(self):
        reports = {'КолиСвітло': {'status': 'unavailable', 'outages': None}}
        annotate_source_health(reports, {'КолиСвітло': '<html>Dynamic chart</html>'},
                               self.today, self.today, now=self.now)
        self.assertEqual(reports['КолиСвітло']['status'], 'unreadable')
        self.assertIn('checked_at', reports['КолиСвітло'])
        self.assertNotIn('data_seen_at', reports['КолиСвітло'])

    def test_unreachable_source_is_not_fake_missing_hours(self):
        reports = {'КолиСвітло': {'status': 'unavailable', 'outages': None}}
        annotate_source_health(reports, {'КолиСвітло': None},
                               self.today, self.today, now=self.now)
        self.assertEqual(reports['КолиСвітло']['status'], 'fetch_error')
        self.assertTrue(reports['КолиСвітло']['fetch_failed'])

    def test_old_hours_retain_last_parse_timestamp_but_not_new_one(self):
        past = self.now.replace(hour=11).isoformat(timespec='minutes')
        reports = {'Alerts Energy': {'status': 'old', 'outages': [['11:00', '17:00']]}}
        annotate_source_health(reports, {'Alerts Energy': '<html>different format</html>'},
                               self.today, self.today, now=self.now,
                               previous={'Alerts Energy': {'data_seen_at': past}})
        self.assertEqual(reports['Alerts Energy']['status'], 'old')
        self.assertEqual(reports['Alerts Energy']['data_seen_at'], past)
        self.assertEqual(reports['Alerts Energy']['checked_at'],
                         self.now.isoformat(timespec='minutes'))

    def test_unpublished_tomorrow_not_a_parser_error(self):
        reports = {'Карта світла': {'status': 'unavailable', 'outages': None}}
        annotate_source_health(
            reports, {'Карта світла': 'Оператор ще не опублікував графік на завтра'},
            date(2026, 11, 24), self.today,
            unpublished={'Карта світла'}, now=self.now)
        self.assertEqual(reports['Карта світла']['status'], 'unpublished')

if __name__ == '__main__':
    unittest.main()
