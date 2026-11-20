"""Ten-case reliability audit: schedule quorum, date boundaries and EcoFlow input."""
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from refresh import choose, source_reports
from validate_build import check_intervals
from ecoflow_live_normalize import StationReading


DAY = date(2026, 11, 20)
EMPTY_PRIMARY = {'candidates': [], 'updated': '', 'unpublished': False}
MORNING = (('07:00', '09:00'),)
AFTERNOON = (('14:00', '17:00'),)


class ScheduleAndTelemetryEdgeCases(unittest.TestCase):
    def test_edge_01_tied_source_quorums_never_confirm_either_schedule(self):
        result = choose(DAY, EMPTY_PRIMARY, MORNING, MORNING, {},
                        {'Київщина.info': AFTERNOON, 'Alerts Energy': AFTERNOON},
                        primary_source='Карта світла', allow_early=True)
        self.assertEqual(result['status'], 'preliminary')
        self.assertEqual(len(result['alternatives']), 1)
        self.assertEqual(set(result['sources']), {'Київщина.info', 'Alerts Energy'})

    def test_edge_02_single_new_cancellation_is_preliminary_not_confirmed(self):
        old = {'date': DAY.isoformat(), 'status': 'normal',
               'outages': [['14:00', '17:00']],
               'sources': ['КолиСвітло', 'КолиБуде']}
        result = choose(DAY, EMPTY_PRIMARY, None, None, old,
                        {'Київщина.info': ()}, allow_early=True)
        self.assertEqual(result['status'], 'preliminary')
        self.assertEqual(result['outages'], [])
        reports = source_reports(result, EMPTY_PRIMARY, None, None, (), None, old)
        self.assertEqual(reports['Київщина.info']['status'], 'preliminary')

    def test_edge_03_one_matching_source_does_not_reconfirm_stale_plan(self):
        old = {'date': DAY.isoformat(), 'status': 'normal',
               'outages': [list(x) for x in MORNING],
               'sources': ['КолиСвітло', 'КолиБуде']}
        result = choose(DAY, EMPTY_PRIMARY, MORNING, None, old, {},
                        allow_early=True)
        self.assertEqual(result['status'], 'stale')
        self.assertEqual(result['outages'], [list(x) for x in MORNING])
        reports = source_reports(result, EMPTY_PRIMARY, MORNING, None, None, None, old)
        self.assertEqual(reports['КолиСвітло']['status'], 'unconfirmed')

    def test_edge_04_yesterday_schedule_never_fills_new_day(self):
        old = {'date': (DAY - timedelta(days=1)).isoformat(),
               'status': 'normal', 'outages': [list(x) for x in MORNING]}
        result = choose(DAY, EMPTY_PRIMARY, None, None, old, {},
                        allow_early=True)
        self.assertEqual(result['status'], 'unknown')
        self.assertEqual(result['outages'], [])

    def test_edge_05_overlapping_or_invalid_midnight_ranges_fail_validation(self):
        with self.assertRaisesRegex(ValueError, 'overlapping'):
            check_intervals([['10:00', '12:00'], ['11:59', '13:00']], 'case5')
        with self.assertRaisesRegex(ValueError, 'Invalid time'):
            check_intervals([['23:00', '24:01']], 'case5')
        check_intervals([['22:30', '24:00']], 'case5')

    def test_edge_06_invalid_ecoflow_numbers_cannot_create_readable_battery(self):
        station = StationReading('dacha:dp3', 'delta_pro_3')
        self.assertFalse(station.update({
            'cmsBattSoc': False, 'powInSumW': -1, 'powOutSumW': 25001
        }, 100))
        self.assertIsNone(station.snapshot(100))
        self.assertTrue(station.update({'cmsBattSoc': 0}, 101))
        self.assertEqual(station.snapshot(101)['socPercent'], 0)
        self.assertIsNone(station.snapshot(140))


if __name__ == '__main__':
    unittest.main()
