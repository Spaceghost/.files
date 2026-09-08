"""Ambient display brightness: the room curve, the learned offset and the pauses."""
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'alpine/desktop/.local/lib/oldbook'))
import ambient_light as al  # noqa: E402

loader = importlib.machinery.SourceFileLoader(
    'oldbook_ambient_display', str(REPO / 'alpine/desktop/.local/bin/oldbook-ambient-display'))
spec = importlib.util.spec_from_loader(loader.name, loader)
module = importlib.util.module_from_spec(spec)
loader.exec_module(module)


class SensorTests(unittest.TestCase):
    def test_parses_the_two_value_form(self):
        self.assertEqual(al.parse_reading('(11,0)\n'), 11)
        self.assertEqual(al.parse_reading('(0,240)\n'), 240)

    def test_parses_a_bare_value(self):
        self.assertEqual(al.parse_reading('37\n'), 37)

    def test_rejects_anything_else(self):
        for text in ('', 'nonsense', '(a,b)', None):
            self.assertIsNone(al.parse_reading(text))

    def test_reads_the_first_sensor_that_answers(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / 'broken').write_text('nonsense')
            (base / 'good').write_text('(64,0)')
            self.assertEqual(al.read_sensor([str(base / 'missing'), str(base / 'broken'),
                                             str(base / 'good')]), 64)

    def test_returns_none_without_a_sensor(self):
        self.assertIsNone(al.read_sensor([]))


class CurveTests(unittest.TestCase):
    def test_a_dark_room_settles_at_the_floor(self):
        self.assertAlmostEqual(al.display_fraction(al.log_sample(0)), al.FLOOR)
        self.assertAlmostEqual(al.display_fraction(al.log_sample(2)), al.FLOOR)

    def test_a_bright_room_reaches_full(self):
        self.assertAlmostEqual(al.display_fraction(al.log_sample(240)), 1.0)
        self.assertAlmostEqual(al.display_fraction(al.log_sample(4000)), 1.0)

    def test_the_curve_rises_with_the_room(self):
        values = [al.display_fraction(al.log_sample(reading)) for reading in (0, 8, 30, 90, 240)]
        self.assertEqual(values, sorted(values))
        self.assertTrue(all(al.FLOOR <= value <= 1.0 for value in values))

    def test_is_logarithmic_rather_than_linear(self):
        # Half way in readings is well past half way in brightness.
        midpoint = al.display_fraction(al.log_sample(120))
        linear = al.FLOOR + (1 - al.FLOOR) * 0.5
        self.assertGreater(midpoint, linear)

    def test_an_offset_shifts_the_curve_but_respects_the_floor(self):
        dark = al.display_fraction(al.log_sample(0), offset=-0.5)
        self.assertAlmostEqual(dark, al.FLOOR)
        lifted = al.display_fraction(al.log_sample(30), offset=0.2)
        self.assertAlmostEqual(lifted, al.display_fraction(al.log_sample(30)) + 0.2, places=6)

    def test_smoothing_moves_towards_the_sample(self):
        self.assertEqual(al.smooth(None, 4.0), 4.0)
        self.assertAlmostEqual(al.smooth(2.0, 4.0, 0.5), 3.0)

    def test_hysteresis_ignores_a_small_change(self):
        self.assertFalse(al.should_retarget(2.0, 2.05))
        self.assertTrue(al.should_retarget(2.0, 3.0))
        self.assertTrue(al.should_retarget(2.0, None))

    def test_the_fade_settles_exactly_without_overshoot(self):
        values = [al.fade_value(100, 400, step / 24) for step in range(25)]
        self.assertEqual(values[0], 100)
        self.assertEqual(values[-1], 400)
        self.assertEqual(values, sorted(values))
        self.assertTrue(all(100 <= value <= 400 for value in values))

    def test_a_learned_offset_is_clamped(self):
        self.assertAlmostEqual(al.learned_offset(0.0, 1.0, 0.2), al.OFFSET_LIMIT)
        self.assertAlmostEqual(al.learned_offset(0.0, 0.0, 0.9), -al.OFFSET_LIMIT)
        self.assertAlmostEqual(al.learned_offset(0.1, 0.6, 0.5), 0.2)


class DaemonTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        base = Path(self.directory.name)
        self.addCleanup(self.directory.cleanup)
        self.backlight = base / 'backlight/panel'
        self.backlight.mkdir(parents=True)
        (self.backlight / 'brightness').write_text('500\n')
        (self.backlight / 'max_brightness').write_text('1000\n')
        self.sensor = base / 'light'
        self.sensor.write_text('(11,0)')
        self.config = base / 'ambient-display.json'
        self.idle = base / 'idle.json'
        self.lock = base / 'lock.json'
        self.pills = []
        self.ambient = module.AmbientDisplay(
            config=self.config, runtime=base / 'runtime', backlight_root=base / 'backlight',
            sensors=[str(self.sensor)], idle_state=self.idle, lock_record=self.lock,
            notify=self.pills.append)

    def enable(self, offset=0.0):
        self.config.write_text(json.dumps({'enabled': True, 'offset': offset}))

    def brightness(self):
        return int((self.backlight / 'brightness').read_text())

    def test_does_nothing_while_disabled(self):
        self.config.write_text(json.dumps({'enabled': False, 'offset': 0.0}))
        self.assertEqual(self.ambient.tick(), 'disabled')
        self.assertEqual(self.brightness(), 500)

    def test_a_dark_room_takes_the_panel_towards_the_floor(self):
        self.enable()
        self.sensor.write_text('(1,0)')
        self.assertEqual(self.ambient.tick(), 'settled')
        self.assertEqual(self.brightness(), round(1000 * al.FLOOR))

    def test_a_bright_room_takes_the_panel_up(self):
        self.enable()
        self.sensor.write_text('(240,0)')
        self.assertEqual(self.ambient.tick(), 'settled')
        self.assertEqual(self.brightness(), 1000)

    def test_never_writes_below_the_floor(self):
        self.enable()
        self.sensor.write_text('(0,0)')
        self.ambient.tick()
        self.assertGreaterEqual(self.brightness(), round(1000 * al.FLOOR))

    def test_stands_down_while_the_idle_stage_holds_the_display(self):
        self.enable()
        self.idle.write_text('{"device": "panel"}')
        self.sensor.write_text('(240,0)')
        self.assertEqual(self.ambient.tick(), 'paused')
        self.assertEqual(self.brightness(), 500)

    def test_stands_down_while_the_session_is_locked(self):
        self.enable()
        import os
        self.lock.write_text(json.dumps({'process': {'pid': os.getpid()}}))
        self.sensor.write_text('(240,0)')
        self.assertEqual(self.ambient.tick(), 'paused')
        self.assertEqual(self.brightness(), 500)

    def test_a_dead_lock_record_does_not_pause_it(self):
        self.enable()
        self.lock.write_text(json.dumps({'process': {'pid': 2 ** 22}}))
        self.assertFalse(self.ambient.session_locked())

    def test_reports_no_sensor_when_none_answers(self):
        self.enable()
        self.sensor.write_text('nonsense')
        self.assertEqual(self.ambient.tick(), 'no-sensor')

    def test_reports_no_display_without_a_writable_backlight(self):
        self.enable()
        (self.backlight / 'brightness').unlink()
        self.assertEqual(self.ambient.tick(), 'no-display')

    def test_holds_still_while_the_room_barely_moves(self):
        self.enable()
        self.sensor.write_text('(60,0)')
        self.assertEqual(self.ambient.tick(), 'settled')
        settled = self.brightness()
        self.sensor.write_text('(61,0)')
        self.assertEqual(self.ambient.tick(), 'steady')
        self.assertEqual(self.brightness(), settled)

    def test_learns_the_offset_from_a_level_the_user_sets(self):
        self.enable()
        self.sensor.write_text('(60,0)')
        self.ambient.tick()
        automatic = self.brightness()
        # The user turns the panel down by hand.
        (self.backlight / 'brightness').write_text('200\n')
        self.assertEqual(self.ambient.tick(), 'learned')
        offset = json.loads(self.config.read_text())['offset']
        self.assertLess(offset, 0)
        self.assertEqual(self.brightness(), 200, 'the level the user chose is left alone')
        # The same room now settles near their choice rather than the old one.
        self.sensor.write_text('(200,0)')
        self.ambient.tick()
        self.sensor.write_text('(60,0)')
        self.ambient.tick()
        self.assertLess(self.brightness(), automatic)

    def test_a_saved_offset_shifts_the_whole_curve_including_its_ceiling(self):
        # Somebody who keeps turning the panel down wants a dimmer screen in
        # every room, so the offset lowers the bright end too rather than being
        # swallowed by the clamp.
        self.enable(offset=-0.2)
        self.assertAlmostEqual(self.ambient.read_config()['offset'], -0.2)
        self.sensor.write_text('(240,0)')
        self.ambient.tick()
        self.assertEqual(self.brightness(), 800)

    def test_status_describes_the_room_and_the_panel(self):
        self.enable()
        self.sensor.write_text('(120,0)')
        status = self.ambient.status()
        self.assertTrue(status['enabled'])
        self.assertEqual(status['light'], 120)
        self.assertEqual(status['percent'], 50)
        self.assertFalse(status['paused'])
        self.assertIn('target_percent', status)

    def test_off_writes_the_preference_and_shows_the_pill(self):
        self.enable()
        self.ambient.write_config(dict(self.ambient.read_config(), enabled=False))
        self.assertFalse(self.ambient.read_config()['enabled'])

    def test_a_missing_configuration_reads_as_off(self):
        self.assertEqual(self.ambient.read_config(), {'enabled': False, 'offset': 0.0})

    def test_a_corrupt_configuration_reads_as_off(self):
        self.config.write_text('{ not json')
        self.assertEqual(self.ambient.read_config()['enabled'], False)


if __name__ == '__main__':
    unittest.main()
