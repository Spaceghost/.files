"""The desktop breath: what the keyboard publishes and what the scene does with it.

Everything here runs on synthetic LED files, a synthetic clock and temporary
runtime directories. No display, no real hardware and no session are touched.
"""

import json
import math
import os
from pathlib import Path
import runpy
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / 'desktop/.local/lib/oldbook'
KEYBOARD = ROOT / 'desktop/.local/bin/oldbook-keyboard-backlight'
SCREENSAVER = ROOT / 'desktop/.local/bin/oldbook-screensaver'

import sys
sys.path.insert(0, str(LIB))
import air  # noqa: E402
import background_fade as fade  # noqa: E402


def load_keyboard():
    return runpy.run_path(str(KEYBOARD), run_name='keyboard_air_test')['KeyboardBacklight']


class AirRecordTests(unittest.TestCase):
    def record(self, **overrides):
        record = {'mode': 'breathe-air', 'volume': 0.5, 'phase': 0.25, 'breath': 0.75,
                  'tempo_seconds': 5.0, 'updated': 1000.0}
        record.update(overrides)
        return json.dumps(record)

    def test_reads_a_fresh_breathing_record(self):
        parsed = air.parse_air(self.record(), 1000.2)
        self.assertEqual(parsed['mode'], 'breathe-air')
        self.assertAlmostEqual(parsed['breath'], 0.75)
        self.assertAlmostEqual(parsed['tempo_seconds'], 5.0)

    def test_a_stale_record_is_no_breath_at_all(self):
        self.assertIsNone(air.parse_air(self.record(), 1000.0 + air.FRESH_SECONDS + 0.01))

    def test_a_record_from_the_future_is_refused(self):
        self.assertIsNone(air.parse_air(self.record(), 1000.0 - air.FRESH_SECONDS - 0.01))

    def test_the_closing_record_stops_the_scene(self):
        self.assertIsNone(air.parse_air(self.record(mode='off', volume=0.0), 1000.0))

    def test_broken_records_are_ignored(self):
        for data in ('', 'not json', '[]', '{}', json.dumps({'mode': 'breathing'}),
                     self.record(breath='high'), self.record(updated=float('nan')),
                     self.record(mode='typing')):
            self.assertIsNone(air.parse_air(data, 1000.0), data[:40])

    def test_values_outside_their_range_are_clamped(self):
        parsed = air.parse_air(self.record(volume=3.0, breath=-1.0, phase=9.5), 1000.0)
        self.assertEqual((parsed['volume'], parsed['breath'], parsed['phase']), (1.0, 0.0, 1.0))


class BreathMathsTests(unittest.TestCase):
    def air(self, **overrides):
        record = {'mode': 'breathe-air', 'volume': air.BASELINE_VOLUME, 'phase': 0.0,
                  'breath': 1.0, 'tempo_seconds': 7.0, 'updated': 0.0}
        record.update(overrides)
        return record

    def test_no_air_leaves_the_painting_alone(self):
        self.assertEqual(air.wallpaper_scale(None), 1.0)
        self.assertEqual(air.caption_alpha(None), air.CAPTION_LOW)

    def test_resting_lungs_swell_the_painting_slightly(self):
        scale = air.wallpaper_scale(self.air())
        self.assertAlmostEqual(scale, 1.0 + air.REST_AMPLITUDE, places=6)

    def test_full_lungs_swell_it_further(self):
        scale = air.wallpaper_scale(self.air(volume=1.0))
        self.assertAlmostEqual(scale, 1.0 + air.FULL_AMPLITUDE, places=6)

    def test_the_bottom_of_every_breath_is_the_untouched_painting(self):
        for volume in (air.BASELINE_VOLUME, 0.6, 1.0):
            self.assertEqual(air.wallpaper_scale(self.air(volume=volume, breath=0.0)), 1.0)

    def test_the_swell_never_exceeds_the_documented_ceiling(self):
        for volume in (0.0, 0.25, 0.5, 1.0):
            for breath in (0.0, 0.5, 1.0):
                scale = air.wallpaper_scale(self.air(volume=volume, breath=breath))
                self.assertGreaterEqual(scale, 1.0)
                self.assertLessEqual(scale, 1.0 + air.FULL_AMPLITUDE + 1e-9)

    def test_only_the_keystroke_breath_moves_the_caption(self):
        self.assertGreater(air.caption_alpha(self.air(breath=1.0)), air.CAPTION_LOW)
        for mode in ('breathing', 'last-breath'):
            self.assertEqual(air.caption_alpha(self.air(mode=mode, breath=1.0)), air.CAPTION_LOW)

    def test_the_caption_stays_inside_its_band(self):
        for breath in (0.0, 0.3, 1.0):
            value = air.caption_alpha(self.air(breath=breath))
            self.assertGreaterEqual(value, air.CAPTION_LOW)
            self.assertLessEqual(value, air.CAPTION_HIGH)

    def test_quantising_keeps_stylesheet_rewrites_rare(self):
        values = {air.quantise(index / 300) for index in range(300)}
        self.assertLessEqual(len(values), air.CAPTION_STEPS + 1)
        with self.assertRaises(ValueError):
            air.quantise(0.5, steps=0)


class SmootherTests(unittest.TestCase):
    def test_it_settles_exactly_and_stops(self):
        smoother = air.Smoother(1.0)
        settled = False
        for _ in range(600):
            value, settled = smoother.advance(1.018, 1 / 60)
            if settled:
                break
        self.assertTrue(settled)
        self.assertEqual(value, 1.018)

    def test_it_never_overshoots(self):
        smoother = air.Smoother(1.0)
        for _ in range(200):
            value, _ = smoother.advance(1.02, 1 / 60)
            self.assertLessEqual(value, 1.02)
            self.assertGreaterEqual(value, 1.0)

    def test_a_long_stall_does_not_jump_the_value(self):
        smoother = air.Smoother(1.0)
        value, _ = smoother.advance(2.0, 10.0)
        self.assertLess(value, 2.0)

    def test_a_zero_frame_changes_nothing(self):
        smoother = air.Smoother(1.0)
        self.assertEqual(smoother.advance(1.5, 0.0), (1.0, False))

    def test_bad_settings_are_refused(self):
        with self.assertRaises(ValueError):
            air.Smoother(1.0, response=0)


class WatcherTests(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix='oldbook-air-'))
        self.addCleanup(lambda: [path.unlink() for path in self.base.glob('*')]
                        and None or self.base.rmdir())
        self.path = self.base / 'air.json'

    def test_a_missing_file_reads_as_nothing(self):
        watcher = air.Watcher(self.path, parse=lambda data, _now: data)
        self.assertIsNone(watcher.poll())

    def test_it_parses_only_when_the_file_moves_on(self):
        reads = []
        self.path.write_text('one')
        watcher = air.Watcher(self.path, parse=lambda data, _now: reads.append(data) or data)
        self.assertEqual(watcher.poll(), 'one')
        self.assertEqual(watcher.poll(), 'one')
        self.assertEqual(reads, ['one'])
        os.utime(self.path, (1, 1))
        self.path.write_text('two!!')
        self.assertEqual(watcher.poll(), 'two!!')
        self.assertEqual(reads, ['one', 'two!!'])

    def test_a_vanished_file_clears_the_cache(self):
        self.path.write_text('one')
        watcher = air.Watcher(self.path, parse=lambda data, _now: data)
        watcher.poll()
        self.path.unlink()
        self.assertIsNone(watcher.poll())
        self.assertIsNone(watcher.signature)

    def test_the_air_watcher_re_checks_staleness_without_a_new_file(self):
        record = {'mode': 'breathing', 'volume': 1.0, 'phase': 0.0, 'breath': 0.5,
                  'tempo_seconds': 6.0, 'updated': time.time()}
        self.path.write_text(json.dumps(record))
        watcher = air.AirWatcher(self.path)
        self.assertIsNotNone(watcher.poll())
        self.assertIsNone(watcher.poll(now=record['updated'] + 5))


class PreferenceTests(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix='oldbook-breath-'))
        self.path = self.base / 'breath.json'

    def tearDown(self):
        for path in sorted(self.base.rglob('*'), reverse=True):
            path.unlink() if path.is_file() else path.rmdir()
        self.base.rmdir()

    def test_both_halves_breathe_by_default(self):
        self.assertEqual(air.read_preferences(self.path), {'wallpaper': True, 'caption': True})

    def test_an_unreadable_file_keeps_breathing(self):
        self.path.write_text('{ not json')
        self.assertEqual(air.read_preferences(self.path), {'wallpaper': True, 'caption': True})

    def test_switches_round_trip(self):
        air.write_preferences({'wallpaper': False, 'caption': True}, self.path)
        self.assertEqual(air.read_preferences(self.path), {'wallpaper': False, 'caption': True})

    def test_a_partial_file_fills_in_the_defaults(self):
        self.path.write_text(json.dumps({'wallpaper': False}))
        self.assertEqual(air.read_preferences(self.path), {'wallpaper': False, 'caption': True})


class DriftTests(unittest.TestCase):
    def test_a_segment_begins_on_the_untouched_painting(self):
        self.assertEqual(fade.ken_burns(0.0, 1.06, (1.0, 0.35), 1440, 900),
                         (1.0, 0.0, 0.0))

    def test_the_pan_always_stays_inside_the_room_the_zoom_opens(self):
        for step in range(0, 101):
            scale, dx, dy = fade.ken_burns(step / 100, 1.06, (1.0, -1.0), 1440, 900)
            self.assertGreaterEqual(scale, 1.0)
            self.assertLessEqual(abs(dx), (scale - 1.0) / 2 * 1440 + 1e-9)
            self.assertLessEqual(abs(dy), (scale - 1.0) / 2 * 900 + 1e-9)

    def test_the_drift_reaches_its_zoom_and_stops_there(self):
        scale, _, _ = fade.ken_burns(1.0, 1.06, (1.0, 0.0), 1440, 900)
        self.assertAlmostEqual(scale, 1.06)

    def test_zooming_out_is_refused_because_it_would_show_an_edge(self):
        with self.assertRaises(ValueError):
            fade.ken_burns(0.5, 0.9, (1.0, 0.0), 1440, 900)

    def test_directions_alternate_so_two_paintings_never_move_alike(self):
        self.assertGreaterEqual(len(fade.DRIFT_DIRECTIONS), 2)
        first, second = fade.DRIFT_DIRECTIONS[0], fade.DRIFT_DIRECTIONS[1]
        self.assertLess(first[0] * second[0], 0)

    def test_the_glide_back_lands_exactly_at_rest(self):
        self.assertEqual(fade.blend_transform((1.06, 40.0, 9.0), (1.0, 0.0, 0.0), 1.0),
                         (1.0, 0.0, 0.0))
        middle = fade.blend_transform((1.06, 40.0, 9.0), (1.0, 0.0, 0.0), 0.5)
        self.assertLess(middle[0], 1.06)
        self.assertGreater(middle[0], 1.0)


class ScreensaverProtocolTests(unittest.TestCase):
    def parse(self, **fields):
        message = {'action': 'screensaver', 'id': 'token'}
        message.update(fields)
        return fade.parse_request(json.dumps(message).encode())

    def test_defaults_fill_in(self):
        parsed = self.parse(enable=True, paths=['/a.png'])
        self.assertEqual(parsed['hold_ms'], fade.SCREENSAVER_HOLD_MS)
        self.assertEqual(parsed['fade_ms'], fade.SCREENSAVER_FADE_MS)
        self.assertEqual(parsed['zoom'], fade.SCREENSAVER_ZOOM)
        self.assertTrue(parsed['enable'])

    def test_stopping_needs_no_list(self):
        self.assertEqual(self.parse(enable=False)['paths'], [])

    def test_relative_paths_are_refused(self):
        with self.assertRaises(ValueError):
            self.parse(enable=True, paths=['gallery/one.png'])

    def test_an_unbounded_list_is_refused(self):
        with self.assertRaises(ValueError):
            self.parse(enable=True, paths=['/x.png'] * (fade.MAX_SCREENSAVER_PATHS + 1))

    def test_absurd_timings_are_clamped(self):
        parsed = self.parse(enable=True, paths=[], hold_ms=1, zoom=9.0)
        self.assertGreaterEqual(parsed['hold_ms'], 2000)
        self.assertLessEqual(parsed['zoom'], 1.5)

    def test_the_encoder_round_trips(self):
        parsed = fade.parse_request(fade.encode_screensaver(True, ['/a.png'], hold_ms=5000))
        self.assertEqual(parsed['paths'], ['/a.png'])
        self.assertEqual(parsed['hold_ms'], 5000)


class ScreensaverSelectionTests(unittest.TestCase):
    def setUp(self):
        self.module = runpy.run_path(str(SCREENSAVER), run_name='screensaver_test')

    def entries(self):
        return [{'id': 'a', 'path': '/gallery/a.png', 'rotate': True},
                {'id': 'b', 'path': '/gallery/b.png', 'rotate': True},
                {'id': 'c', 'path': '/gallery/c.png', 'rotate': False},
                {'id': 'd', 'path': '/gallery/d.png'}]

    def test_only_rotating_paintings_are_offered(self):
        paths = self.module['candidates'](self.entries(), rng=_FixedShuffle())
        self.assertEqual(sorted(paths), ['/gallery/a.png', '/gallery/b.png', '/gallery/d.png'])

    def test_the_painting_on_screen_is_not_repeated_first(self):
        paths = self.module['candidates'](self.entries(), current='/gallery/a.png',
                                          rng=_FixedShuffle())
        self.assertNotIn('/gallery/a.png', paths)

    def test_a_collection_with_nothing_rotating_still_drifts(self):
        entries = [dict(entry, rotate=False) for entry in self.entries()]
        self.assertTrue(self.module['candidates'](entries, rng=_FixedShuffle()))

    def test_the_list_stays_bounded(self):
        entries = [{'id': str(index), 'path': f'/gallery/{index}.png'} for index in range(200)]
        paths = self.module['candidates'](entries, rng=_FixedShuffle())
        self.assertLessEqual(len(paths), fade.MAX_SCREENSAVER_PATHS)


class _FixedShuffle:
    @staticmethod
    def shuffle(items):
        items.sort()


class PublishedBreathTests(unittest.TestCase):
    """The worker's own output, on a synthetic clock and synthetic LED files."""

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix='oldbook-air-worker-'))
        self.led = self.base / 'smc::kbd_backlight'
        self.state = self.base / 'state'
        self.runtime = self.base / 'runtime'
        for folder in (self.led, self.state, self.runtime):
            folder.mkdir(parents=True)
        (self.led / 'max_brightness').write_text('255\n')
        (self.led / 'brightness').write_text('64\n')
        (self.led / 'trigger').write_text('[none] nand-disk\n')
        self.air = self.runtime / 'air.json'

    def tearDown(self):
        for path in sorted(self.base.rglob('*'), reverse=True):
            path.unlink() if path.is_file() else path.rmdir()
        self.base.rmdir()

    def run_worker(self, mode, stop_at, keystrokes=None):
        """Serve until `stop_at`, collecting every air record written."""
        now = [0.0]
        published = []
        presses = sorted(keystrokes or [], key=lambda item: item[0])

        class SyntheticPoller:
            def unregister(self, _fd):
                pass

        def open_devices():
            return SyntheticPoller(), {os.open(os.devnull, os.O_RDONLY): 'synthetic'}

        def consume(_poller, _handles, _deadline):
            count = 0
            while presses and presses[0][0] <= now[0]:
                count += presses.pop(0)[1]
            return count

        def advance(seconds):
            now[0] += max(float(seconds), 0.000001)

        class ControlledStop:
            def is_set(self):
                return now[0] >= stop_at

            def wait(self, seconds):
                advance(seconds)
                return self.is_set()

        helper_class = load_keyboard()
        with patch('time.monotonic', side_effect=lambda: now[0]), \
                patch('time.sleep', side_effect=advance):
            helper = helper_class(self.led, self.state, self.runtime)
            helper._open_key_devices = open_devices
            helper._consume_key_presses = consume
            original = helper.publish_air

            def record(*args):
                original(*args)
                published.append(json.loads(self.air.read_text()))

            helper.publish_air = record
            (self.state / 'keyboard-backlight').write_text('200\n')
            (self.state / 'keyboard-backlight-mode').write_text(mode + '\n')
            self.assertIs(helper.serve(ControlledStop()), True)
        return published

    def test_the_six_second_breath_is_published(self):
        published = self.run_worker('breathing', stop_at=7.0)
        self.assertTrue(published)
        self.assertTrue(all(record['mode'] in ('breathing', 'off') for record in published))
        breathing = [record for record in published if record['mode'] == 'breathing']
        self.assertAlmostEqual(breathing[0]['tempo_seconds'], 6.0)
        self.assertEqual({record['volume'] for record in breathing}, {1.0})
        self.assertGreater(max(record['breath'] for record in breathing), 0.9)
        self.assertLess(min(record['breath'] for record in breathing), 0.2)

    def test_the_publisher_keeps_to_its_own_rate(self):
        published = self.run_worker('breathing', stop_at=5.0)
        stamps = [record for record in published if record['mode'] == 'breathing']
        # Twenty a second across five seconds, never one per sixty-hertz frame.
        self.assertLess(len(stamps), 5 * 60)
        self.assertGreater(len(stamps), 5 * 10)

    def test_keystrokes_fill_the_lungs(self):
        published = self.run_worker('breathe-air', stop_at=12.0,
                                    keystrokes=[(4.0 + index * 0.05, 1) for index in range(40)])
        volumes = [record['volume'] for record in published if record['mode'] == 'breathe-air']
        self.assertLess(volumes[0], 0.3)
        self.assertGreater(max(volumes), volumes[0] + 0.2)

    def test_the_tempo_quickens_as_the_lungs_fill(self):
        published = self.run_worker('breathe-air', stop_at=12.0,
                                    keystrokes=[(4.0 + index * 0.05, 2) for index in range(40)])
        tempos = [record['tempo_seconds'] for record in published
                  if record['mode'] == 'breathe-air']
        self.assertGreater(tempos[0], min(tempos))
        self.assertLessEqual(min(tempos), 7.0)

    def test_the_phase_runs_forward_without_jumping(self):
        published = [record for record in self.run_worker('breathing', stop_at=6.0)
                     if record['mode'] == 'breathing']
        for before, after in zip(published, published[1:]):
            step = (after['phase'] - before['phase']) % 1.0
            self.assertLess(step, 0.2, 'the published phase jumped')

    def test_a_worker_that_stops_tells_the_scene_to_settle(self):
        published = self.run_worker('breathing', stop_at=3.0)
        self.assertEqual(published[-1]['mode'], 'off')
        self.assertEqual(published[-1]['volume'], 0.0)
        self.assertIsNone(air.parse_air(self.air.read_text(), time.time()))

    def test_the_typing_modes_leave_the_desktop_still(self):
        published = self.run_worker('typing', stop_at=3.0,
                                    keystrokes=[(1.0, 3), (1.5, 3)])
        self.assertEqual([record for record in published if record['mode'] != 'off'], [])

    def test_every_published_record_reads_back(self):
        for record in self.run_worker('breathe-air', stop_at=4.0):
            if record['mode'] == 'off':
                continue
            parsed = air.parse_air(json.dumps(record), record['updated'])
            self.assertIsNotNone(parsed)
            self.assertTrue(math.isfinite(air.wallpaper_scale(parsed)))


if __name__ == '__main__':
    unittest.main()
