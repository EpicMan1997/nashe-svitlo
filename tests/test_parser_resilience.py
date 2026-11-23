"""Regression cases from real 23.11.26 outages and provider layout changes."""
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from refresh import parse_mapasvitla, choose, parse_kyivshchyna

TODAY = date(2026, 11, 23)
EXPECTED = (('11:00', '18:00'), ('22:30', '24:00'))


def map_page(body, group='3.1', tagged=True):
    container = ('<section data-day="today">' + body + '</section>') if tagged else body
    return ('<html><head><title>Черга ' + group +
            ', ДТЕК Київські регіональні</title></head><body>' +
            '<h1>Черга ' + group + '</h1>' + container + '</body></html>')


class MapSourceResilience(unittest.TestCase):
    def test_current_2026_11_23_layout(self):
        body = ('План на сьогодні, пн 23.11 Час за київським часом. '
                '11:00–18:00 7 год 22:30–24:00 1,5 год '
                'Всього планових відключень 8,5 год '
                'Графік черги 3.1 на завтра ще не опубліковано. '
                'За останні 7 днів було 09:00–18:00')
        self.assertEqual(parse_mapasvitla(map_page(body), TODAY, TODAY, '3.1')['candidates'],
                         [EXPECTED])

    def test_can_recover_when_provider_removes_data_day(self):
        body = ('Планове відключення 22:30–24:00 '
                'План на сьогодні, пн 23.11 '
                '11:00–18:00 22:30–24:00 '
                'Всього планових відключень 8,5 год '
                'План на завтра, вт 24.11 08:00–18:00 '
                'Всього планових відключень 10 год')
        self.assertEqual(parse_mapasvitla(map_page(body, tagged=False), TODAY, TODAY, '3.1')['candidates'],
                         [EXPECTED])

    def test_legacy_summary_remains_supported(self):
        body = ('План на сьогодні, пн 23.11 '
                '11:00–18:00 22:30–24:00 Всього без світла 8,5 год')
        self.assertEqual(parse_mapasvitla(map_page(body), TODAY, TODAY, '3.1')['candidates'],
                         [EXPECTED])

    def test_wrong_group_and_wrong_day_never_leak(self):
        body = ('План на сьогодні, пн 23.11 '
                '11:00–18:00 22:30–24:00 Всього планових відключень 8,5 год')
        self.assertFalse(parse_mapasvitla(map_page(body, group='3.2'), TODAY, TODAY, '3.1')['candidates'])
        self.assertFalse(parse_mapasvitla(map_page(body), TODAY + timedelta(days=1),
                                          TODAY, '3.1')['candidates'])

    def test_inconsistent_total_is_not_mistaken_for_confirmed_data(self):
        body = ('План на сьогодні, пн 23.11 '
                '11:00–18:00 22:30–24:00 Всього планових відключень 7 год')
        self.assertFalse(parse_mapasvitla(map_page(body), TODAY, TODAY, '3.1')['candidates'])

    def test_valid_zero_hours_not_treated_as_missing(self):
        body = 'План на сьогодні, пн 23.11 Світло весь день Всього планових відключень 0 год'
        self.assertEqual(parse_mapasvitla(map_page(body), TODAY, TODAY, '3.1')['candidates'], [()])

    def test_tomorrow_placeholder_does_not_hide_today(self):
        body = ('<section data-day="today">План на сьогодні, пн 23.11 '
                '11:00–18:00 22:30–24:00 Всього планових відключень 8,5 год</section>'
                '<section data-day="tomorrow">Очікуємо графік. '
                'Оператор ще не опублікував графік на завтра.</section>')
        html = map_page(body, tagged=False)
        self.assertEqual(parse_mapasvitla(html, TODAY, TODAY, '3.1')['candidates'], [EXPECTED])
        self.assertTrue(parse_mapasvitla(html, TODAY + timedelta(days=1),
                                         TODAY, '3.1')['unpublished'])

    def test_independent_confirmation_with_kyivshchyna(self):
        html = ('<h2>Графік відключення світла в Київській області: '
                'сьогодні, 23 листопада</h2>'
                '<p>Черга 3.1 8,5 год без світла: '
                '11:00–18:00 22:30–24:00</p>'
                '<p>Черга 3.2 8 год без світла: 13:00–21:00</p>'
                '<h2>Новини про світло на Київщині</h2>')
        report = parse_kyivshchyna(html, TODAY, TODAY)
        self.assertEqual(report, EXPECTED)
        map_report = parse_mapasvitla(map_page(
            'План на сьогодні, пн 23.11 11:00–18:00 22:30–24:00 '
            'Всього планових відключень 8,5 год'), TODAY, TODAY, '3.1')
        result = choose(TODAY, map_report, None, None, {},
                        {'Київщина.info': report},
                        primary_source='Карта світла', allow_early=True)
        self.assertEqual(result['status'], 'normal')
        self.assertEqual(result['outages'], [list(x) for x in EXPECTED])

    def test_single_source_shown_without_false_confirmation(self):
        report = parse_mapasvitla(map_page(
            'План на сьогодні, пн 23.11 11:00–18:00 22:30–24:00 '
            'Всього планових відключень 8,5 год'), TODAY, TODAY, '3.1')
        result = choose(TODAY, report, None, None, {}, {},
                        primary_source='Карта світла', allow_early=True)
        self.assertEqual(result['status'], 'preliminary')
        self.assertEqual(result['outages'], [list(x) for x in EXPECTED])


if __name__ == '__main__':
    unittest.main()
