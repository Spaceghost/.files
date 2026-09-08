"""Offline sun and moon arithmetic, the masthead line, and nocturne weighting."""
import datetime as dt
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[2]
LIB = REPO / 'alpine/desktop/.local/lib/oldbook'
BIN = REPO / 'alpine/desktop/.local/bin'
sys.path.insert(0, str(LIB))
import astro
import nocturne

UTC = dt.timezone.utc
LOS_ANGELES = astro.Location('Los Angeles', 34.05, -118.24, 'America/Los_Angeles')
PACIFIC = ZoneInfo('America/Los_Angeles')


def minutes_apart(first, second):
    return abs((first - second).total_seconds()) / 60


class SolarTests(unittest.TestCase):
    def test_los_angeles_summer_solstice_matches_published_times(self):
        day = astro.solar_day(dt.date(2024, 6, 21), LOS_ANGELES)
        self.assertLessEqual(minutes_apart(day['sunrise'], dt.datetime(2024, 6, 21, 5, 42, tzinfo=PACIFIC)), 4)
        self.assertLessEqual(minutes_apart(day['sunset'], dt.datetime(2024, 6, 21, 20, 8, tzinfo=PACIFIC)), 4)
        self.assertEqual(day['sunrise'].tzinfo.key, 'America/Los_Angeles')

    def test_los_angeles_winter_solstice_matches_published_times(self):
        day = astro.solar_day(dt.date(2024, 12, 21), LOS_ANGELES)
        self.assertLessEqual(minutes_apart(day['sunrise'], dt.datetime(2024, 12, 21, 6, 54, tzinfo=PACIFIC)), 4)
        self.assertLessEqual(minutes_apart(day['sunset'], dt.datetime(2024, 12, 21, 16, 48, tzinfo=PACIFIC)), 4)

    def test_events_are_ordered_and_twilight_brackets_the_day(self):
        for month in range(1, 13):
            day = astro.solar_day(dt.date(2025, month, 15), LOS_ANGELES)
            with self.subTest(month=month):
                self.assertLess(day['dawn'], day['sunrise'])
                self.assertLess(day['sunrise'], day['noon'])
                self.assertLess(day['noon'], day['sunset'])
                self.assertLess(day['sunset'], day['dusk'])

    def test_equinox_day_is_near_twelve_hours_and_symmetric(self):
        equinox = astro.solar_day(dt.date(2024, 3, 20), LOS_ANGELES)
        length = equinox['sunset'] - equinox['sunrise']
        self.assertLess(abs(length - dt.timedelta(hours=12)), dt.timedelta(minutes=20))
        before = astro.solar_day(dt.date(2024, 3, 5), LOS_ANGELES)
        after = astro.solar_day(dt.date(2024, 4, 4), LOS_ANGELES)
        combined = (before['sunset'] - before['sunrise']) + (after['sunset'] - after['sunrise'])
        self.assertLess(abs(combined - dt.timedelta(hours=24)), dt.timedelta(minutes=20))

    def test_far_east_and_southern_locations_stay_on_the_right_calendar_day(self):
        auckland = astro.Location('Auckland', -36.85, 174.76, 'Pacific/Auckland')
        day = astro.solar_day(dt.date(2024, 12, 21), auckland)
        self.assertEqual(day['sunrise'].date(), dt.date(2024, 12, 21))
        self.assertLessEqual(minutes_apart(day['sunrise'], dt.datetime(2024, 12, 21, 5, 58, tzinfo=ZoneInfo('Pacific/Auckland'))), 5)
        self.assertLessEqual(minutes_apart(day['sunset'], dt.datetime(2024, 12, 21, 20, 39, tzinfo=ZoneInfo('Pacific/Auckland'))), 5)

    def test_midnight_sun_reports_no_crossing_and_counts_as_day(self):
        tromso = astro.Location('Tromsø', 69.65, 18.96, 'Europe/Oslo')
        day = astro.solar_day(dt.date(2024, 6, 21), tromso)
        self.assertIsNone(day['sunrise'])
        self.assertIsNone(day['sunset'])
        self.assertFalse(astro.is_night(dt.datetime(2024, 6, 21, 1, tzinfo=ZoneInfo('Europe/Oslo')), tromso))
        self.assertTrue(astro.is_night(dt.datetime(2024, 12, 21, 12, tzinfo=ZoneInfo('Europe/Oslo')), tromso))

    def test_night_is_between_sunset_and_sunrise(self):
        self.assertTrue(astro.is_night(dt.datetime(2026, 9, 8, 3, tzinfo=PACIFIC), LOS_ANGELES))
        self.assertFalse(astro.is_night(dt.datetime(2026, 9, 8, 12, tzinfo=PACIFIC), LOS_ANGELES))
        self.assertTrue(astro.is_night(dt.datetime(2026, 9, 8, 21, tzinfo=PACIFIC), LOS_ANGELES))


class MoonTests(unittest.TestCase):
    def test_january_2024_new_and_full_moons_within_a_day(self):
        new = astro.next_phase_crossing(dt.datetime(2024, 1, 1, tzinfo=UTC), 0)
        self.assertLess(abs(new - dt.datetime(2024, 1, 11, 11, 57, tzinfo=UTC)), dt.timedelta(days=1))
        full = astro.next_phase_crossing(dt.datetime(2024, 1, 12, tzinfo=UTC), 180)
        self.assertLess(abs(full - dt.datetime(2024, 1, 25, 17, 54, tzinfo=UTC)), dt.timedelta(days=1))

    def test_cycle_length_is_a_synodic_month(self):
        first = astro.next_phase_crossing(dt.datetime(2025, 3, 1, tzinfo=UTC), 0)
        second = astro.next_phase_crossing(first + dt.timedelta(days=1), 0)
        days = (second - first).total_seconds() / 86400
        self.assertGreater(days, 29.2)
        self.assertLess(days, 29.9)

    def test_phase_names_glyphs_and_illumination_follow_the_elongation(self):
        full = astro.moon_phase(dt.datetime(2024, 1, 25, 18, tzinfo=UTC))
        self.assertEqual(full['phase'], 'Full moon')
        self.assertGreater(full['illumination'], 0.97)
        new = astro.moon_phase(dt.datetime(2024, 1, 11, 12, tzinfo=UTC))
        self.assertEqual(new['phase'], 'New moon')
        self.assertLess(new['illumination'], 0.03)
        waxing = astro.moon_phase(dt.datetime(2024, 1, 15, tzinfo=UTC))
        self.assertTrue(waxing['waxing'])
        self.assertIn(waxing['phase'], ('Waxing crescent', 'First quarter'))
        self.assertEqual(len(astro.PHASE_GLYPHS), len(astro.PHASE_NAMES))
        self.assertEqual(len(set(astro.PHASE_GLYPHS)), 8)

    def test_southern_hemisphere_mirrors_the_lit_limb(self):
        when = dt.datetime(2024, 1, 15, tzinfo=UTC)
        north = astro.moon_phase(when, latitude=34.0)
        south = astro.moon_phase(when, latitude=-34.0)
        self.assertEqual(north['phase'], south['phase'])
        self.assertNotEqual(north['glyph'], south['glyph'])
        self.assertEqual(astro.moon_phase(when, latitude=-34.0)['glyph'],
                         astro.SOUTHERN_GLYPHS[astro.PHASE_GLYPHS.index(north['glyph'])])


class LocationAndPanelTests(unittest.TestCase):
    def write(self, directory, document):
        path = Path(directory) / 'location.json'
        path.write_text(json.dumps(document) if not isinstance(document, str) else document)
        return path

    def test_missing_invalid_or_out_of_range_files_yield_no_location(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(astro.load_location(Path(directory) / 'absent.json'))
            self.assertIsNone(astro.load_location(self.write(directory, 'not json')))
            self.assertIsNone(astro.load_location(self.write(directory, {'latitude': 1, 'longitude': 2})))
            self.assertIsNone(astro.load_location(self.write(directory, {
                'latitude': 91, 'longitude': 2, 'timezone': 'UTC'})))
            self.assertIsNone(astro.load_location(self.write(directory, {
                'latitude': 1, 'longitude': 2, 'timezone': 'Mars/Olympus_Mons'})))
            location = astro.load_location(self.write(directory, {
                'name': 'Somewhere', 'latitude': 34.05, 'longitude': -118.24,
                'timezone': 'America/Los_Angeles'}))
            self.assertEqual((location.name, location.timezone), ('Somewhere', 'America/Los_Angeles'))

    def test_panel_line_is_one_quiet_row_with_glyphs_and_times(self):
        report = astro.status(dt.datetime(2026, 9, 8, 12, tzinfo=PACIFIC), LOS_ANGELES)
        line = astro.panel_line(report)
        self.assertNotIn('\n', line)
        self.assertIn(astro.SUNRISE_GLYPH, line)
        self.assertIn(astro.SUNSET_GLYPH, line)
        self.assertIn(report['moon']['glyph'], line)
        self.assertIn(report['sunrise'].strftime('%H:%M'), line)
        self.assertIn(report['sunset'].strftime('%H:%M'), line)
        self.assertRegex(line, r'\d+%$')
        for forbidden in ('cpu', 'mem', 'uptime', 'downspeed'):
            self.assertNotIn(forbidden, line.lower())

    def test_serializable_report_is_json(self):
        report = astro.status(dt.datetime(2026, 9, 8, 12, tzinfo=PACIFIC), LOS_ANGELES)
        document = json.loads(json.dumps(astro.serializable(report)))
        self.assertEqual(document['sunrise'][:10], '2026-09-08')
        self.assertIsInstance(document['day_length'], int)

    def test_cli_is_silent_without_a_location_and_prints_the_line_with_one(self):
        with tempfile.TemporaryDirectory() as directory:
            env = dict(os.environ, XDG_CONFIG_HOME=directory, HOME=directory)
            silent = subprocess.run([str(BIN / 'oldbook-astro'), 'panel'], env=env,
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual((silent.returncode, silent.stdout), (0, ''))
            status = subprocess.run([str(BIN / 'oldbook-astro'), 'status'], env=env,
                                    capture_output=True, text=True, timeout=20)
            self.assertFalse(json.loads(status.stdout)['configured'])
            path = self.write(directory, {'name': 'Los Angeles', 'latitude': 34.05,
                                          'longitude': -118.24, 'timezone': 'America/Los_Angeles'})
            shown = subprocess.run([str(BIN / 'oldbook-astro'), 'panel', '--location', str(path),
                                    '--at', '2024-06-21T19:00:00+00:00'],
                                   env=env, capture_output=True, text=True, timeout=20)
            self.assertEqual(shown.returncode, 0, shown.stderr)
            self.assertIn('05:42', shown.stdout)
            self.assertIn('20:07', shown.stdout)
            light = subprocess.run([str(BIN / 'oldbook-sun-light'), 'status'], env=env,
                                   capture_output=True, text=True, timeout=20)
            self.assertEqual(light.stdout.strip(), 'unconfigured')


class NocturneTests(unittest.TestCase):
    NIGHT = dt.datetime(2026, 9, 8, 23, 30, tzinfo=PACIFIC)
    DAY = dt.datetime(2026, 9, 8, 13, 0, tzinfo=PACIFIC)
    ENTRIES = [
        {'id': 'harbour', 'title': 'Harbour Dawn', 'description': 'A luminous morning harbour.'},
        {'id': 'diner', 'title': 'Coast to Coast, Last Orders',
         'description': 'A loving parody of the luminous midnight diner painting Nighthawks.'},
        {'id': 'orchard', 'title': 'Orchard Harvest', 'description': 'Apples in the afternoon.'},
        {'id': 'tagged', 'title': 'Bright Noon', 'description': 'Nothing nocturnal here.',
         'time_of_day': 'night'},
    ]

    def test_explicit_tag_wins_and_keywords_are_whole_words(self):
        self.assertTrue(nocturne.is_nocturne(self.ENTRIES[1]))
        self.assertTrue(nocturne.is_nocturne(self.ENTRIES[3]))
        self.assertFalse(nocturne.is_nocturne(self.ENTRIES[0]))
        self.assertFalse(nocturne.is_nocturne({'id': 'x', 'description': 'Nighthawks only, no other cue',
                                               'time_of_day': 'day'}))
        self.assertFalse(nocturne.is_nocturne({'id': 'x', 'description': 'A knight in daylight'}))
        self.assertTrue(nocturne.is_nocturne({'id': 'x', 'description': 'Lanterns along the quay'}))

    def test_daytime_no_location_or_no_nocturnes_defer_to_the_ordinary_order(self):
        rng = random.Random(1)
        self.assertIsNone(nocturne.nocturne_preference(self.ENTRIES, 'harbour', now=self.DAY,
                                                       location=LOS_ANGELES, rng=rng))
        with mock.patch.object(astro, 'load_location', return_value=None):
            self.assertIsNone(nocturne.nocturne_preference(self.ENTRIES, 'harbour', now=self.NIGHT,
                                                           location=None, rng=rng))
        daylight_only = [self.ENTRIES[0], self.ENTRIES[2]]
        self.assertIsNone(nocturne.nocturne_preference(daylight_only, 'harbour', now=self.NIGHT,
                                                       location=LOS_ANGELES, rng=rng))
        self.assertIsNone(nocturne.nocturne_preference([self.ENTRIES[1]], 'diner', now=self.NIGHT,
                                                       location=LOS_ANGELES, rng=rng))

    def test_night_weights_nocturnes_three_to_one_without_excluding_anything(self):
        rng = random.Random(2026)
        counts = {}
        for _ in range(4000):
            chosen = nocturne.nocturne_preference(self.ENTRIES, 'harbour', now=self.NIGHT,
                                                  location=LOS_ANGELES, rng=rng)
            counts[chosen] = counts.get(chosen, 0) + 1
        self.assertNotIn('harbour', counts)
        self.assertEqual(set(counts), {'diner', 'orchard', 'tagged'})
        self.assertGreater(counts['orchard'], 0)
        ratio = (counts['diner'] + counts['tagged']) / 2 / counts['orchard']
        self.assertGreater(ratio, 2.4)
        self.assertLess(ratio, 3.7)


if __name__ == '__main__':
    unittest.main()
