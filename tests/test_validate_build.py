"""Build validation must accept each source verdict emitted by the parser."""
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from validate_build import check_payload

KYIV = ZoneInfo('Europe/Kyiv')


class BuildValidationTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 20, 10, 0, tzinfo=KYIV)
        today = self.now.date()
        self.days = [today.isoformat(), (today + timedelta(days=1)).isoformat()]
        self.config = {'enabled': False, 'snapshotUrl': '', 'streamUrl': ''}
        self.season = {'basis': 'confirmed_schedules_not_actual_outages',
                       'locations': {key: {'recorded_days': 1}
                                     for key in ('dacha', 'home', 'solovky', 'naumenky')}}
        self.payload = {
            'updated_at': self.now.isoformat(),
            'today_date': self.days[0],
            'tomorrow_date': self.days[1],
            'days': {}, 'logs': [], 'source_health': {'issues': []},
            'locations': {}
        }
        for loc, group in {'dacha': '3.1', 'home': '4.1',
                           'solovky': '4.1', 'naumenky': '10.1'}.items():
            days = {}
            for date in self.days:
                days[date] = {
                    'date': date, 'status': 'stale',
                    'outages': [['14:00', '17:30']], 'sources': ['КолиБуде'],
                    'source_reports': {
                        'КолиБуде': {'status': 'unconfirmed', 'outages': [['14:00','17:30']]},
                        'КолиСвітло': {'status': 'old', 'outages': [['14:00','17:30']]},
                        'Alerts Energy': {'status': 'unavailable', 'outages': None}
                    }
                }
            self.payload['locations'][loc] = {
                'group': group, 'days': days, 'logs': [], 'emergency': None
            }

    def test_stale_matching_report_does_not_block_all_publication(self):
        counts = check_payload(self.payload, self.season, self.config,
                               ROOT / 'site', self.now)
        self.assertEqual(counts['dacha'][self.days[0]]['status'], 'stale')

    def test_all_real_diagnostic_states_are_valid(self):
        for verdict in ('unreadable', 'fetch_error', 'unpublished'):
            with self.subTest(verdict=verdict):
                self.payload['locations']['dacha']['days'][self.days[0]][
                    'source_reports']['Alerts Energy']['status'] = verdict
                check_payload(self.payload, self.season, self.config,
                              ROOT / 'site', self.now)

    def test_invalid_unknown_source_verdict_still_fails(self):
        self.payload['locations']['dacha']['days'][self.days[0]][
            'source_reports']['КолиБуде']['status'] = 'invented'
        with self.assertRaisesRegex(ValueError, 'invalid source'):
            check_payload(self.payload, self.season, self.config,
                          ROOT / 'site', self.now)

    def test_unverified_normal_still_cannot_be_published(self):
        self.payload['locations']['dacha']['days'][self.days[0]]['status'] = 'normal'
        with self.assertRaisesRegex(ValueError, 'unverified confirmed schedule'):
            check_payload(self.payload, self.season, self.config,
                          ROOT / 'site', self.now)


if __name__ == '__main__':
    unittest.main()
