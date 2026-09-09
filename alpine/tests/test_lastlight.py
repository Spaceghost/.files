"""The dying-battery warning: its curve, its glide and its promise to put things back.

The point of testing this against a table of charges rather than a laptop is that
the interesting states are the ones you cannot ask for. Nobody can run the suite
at two percent on demand, and the one behaviour that must never regress -- the
panel brightness being restored however the daemon ends -- is exactly the one
whose failure mode is somebody's screen left dim.
"""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
LIB = REPO / 'alpine/desktop/.local/lib/oldbook'
BIN = REPO / 'alpine/desktop/.local/bin'
sys.path.insert(0, str(LIB))

import lastlight  # noqa: E402


def load_script(name):
    """Import an extensionless helper as a module."""
    loader = importlib.machinery.SourceFileLoader(name.replace('-', '_'), str(BIN / name))
    specification = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(specification)
    loader.exec_module(module)
    return module


class CurveTests(unittest.TestCase):
    def test_mains_and_a_healthy_charge_ask_for_nothing(self):
        self.assertEqual(lastlight.urgency(100, mains=False), 0.0)
        self.assertEqual(lastlight.urgency(26, mains=False), 0.0)
        # Exactly at the warning the effect has not begun; it ramps in below it.
        self.assertEqual(lastlight.urgency(lastlight.WARNING, mains=False), 0.0)
        self.assertEqual(lastlight.urgency(2, mains=True), 0.0,
                         'plugged in is plugged in, however empty the cell is')
        self.assertEqual(lastlight.urgency(None, mains=False), 0.0,
                         'a machine with no battery must not be told it is dying')

    def test_stages_use_the_bands_the_rest_of_the_desktop_uses(self):
        self.assertEqual(lastlight.stage(100), 'clear')
        self.assertEqual(lastlight.stage(lastlight.WARNING), 'warning')
        self.assertEqual(lastlight.stage(lastlight.WARNING + 1), 'clear')
        self.assertEqual(lastlight.stage(lastlight.CRITICAL), 'critical')
        self.assertEqual(lastlight.stage(lastlight.TERMINAL), 'terminal')
        self.assertEqual(lastlight.stage(0), 'terminal')

    def test_every_channel_grows_as_the_charge_falls(self):
        charges = [24, 20, 15, 10, 7, 4, 2, 0]
        urgencies = [lastlight.urgency(c, False) for c in charges]
        self.assertEqual(urgencies, sorted(urgencies),
                         'urgency must never fall as the battery does')
        periods = [lastlight.breath_period(u) for u in urgencies]
        self.assertEqual(periods, sorted(periods, reverse=True),
                         'the keys must only ever breathe faster')
        alphas = [lastlight.vignette(u)['alpha'] for u in urgencies]
        reaches = [lastlight.vignette(u)['reach'] for u in urgencies]
        self.assertEqual(alphas, sorted(alphas))
        self.assertEqual(reaches, sorted(reaches, reverse=True),
                         'the darkness closes inward, it does not retreat')

    def test_the_effect_stays_readable_through_and_the_wave_stays_slight(self):
        worst = lastlight.vignette(1.0)
        self.assertLess(worst['alpha'], 0.7, 'the screen must never black out entirely')
        self.assertLessEqual(lastlight.wave(1.0)['amplitude'], 0.05,
                             'a backlight swing past a few percent reads as a fault')
        self.assertGreater(lastlight.wave(1.0)['period'],
                           lastlight.breath_period(1.0),
                           'the panel rides slower than the keys, so they read as two things')

    def test_the_breath_never_outruns_what_the_keyboard_will_accept(self):
        keyboard = load_script('oldbook-keyboard-backlight')
        self.assertGreaterEqual(lastlight.breath_period(1.0), keyboard.LASTLIGHT_MIN_PERIOD)
        self.assertLessEqual(lastlight.breath_period(0.0), keyboard.PERIOD)


class GlideTests(unittest.TestCase):
    def test_it_arrives_faster_than_it_leaves(self):
        rising = lastlight.glide(0.0, 1.0, 1.0)
        falling = lastlight.glide(1.0, 0.0, 1.0)
        self.assertGreater(rising, 1.0 - falling,
                           'dying should be noticed sooner than recovery is forgotten')

    def test_it_never_overshoots_or_oscillates(self):
        level = 0.0
        for _ in range(200):
            level = lastlight.glide(level, 0.42, 0.1)
        self.assertAlmostEqual(level, 0.42, places=6)
        for _ in range(200):
            level = lastlight.glide(level, 0.0, 0.1)
        self.assertEqual(level, 0.0)

    def test_charging_runs_the_same_code_backwards(self):
        """No special case for the cord: the target falls and the glide follows."""
        dying = lastlight.urgency(5, mains=False)
        plugged = lastlight.urgency(5, mains=True)
        self.assertGreater(dying, 0.5)
        self.assertEqual(plugged, 0.0)
        level = dying
        steps = 0
        while level > 0.0 and steps < 10000:
            level = lastlight.glide(level, plugged, 0.05)
            steps += 1
        self.assertEqual(level, 0.0)
        self.assertLess(steps * 0.05, lastlight.GLIDE_OUT + 1)


class PanelTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        device = self.root / 'gmux_backlight'
        device.mkdir()
        (device / 'max_brightness').write_text('1023\n')
        (device / 'brightness').write_text('800\n')
        self.device = device
        os.environ['OLDBOOK_BACKLIGHT_ROOT'] = str(self.root)
        self.module = load_script('oldbook-lastlight')

    def level(self):
        return int((self.device / 'brightness').read_text().strip())

    def test_the_wave_only_ever_dims_and_never_below_the_floor(self):
        panel = self.module.Panel(self.root)
        self.assertTrue(panel.available)
        seen = []
        for step in range(60):
            panel.apply(lastlight.WAVE_MAX, step / 60)
            seen.append(self.level())
        self.assertLessEqual(max(seen), 800, 'it must never brighten past his level')
        self.assertGreaterEqual(min(seen), 800 * self.module.BRIGHTNESS_FLOOR)
        self.assertLess(min(seen), 800, 'a wave that never moves is not a wave')

    def test_restore_puts_the_panel_back(self):
        panel = self.module.Panel(self.root)
        panel.apply(lastlight.WAVE_MAX, 0.5)
        self.assertNotEqual(self.level(), 800)
        panel.restore()
        self.assertEqual(self.level(), 800)

    def test_reaching_for_the_brightness_keys_rebases_instead_of_fighting(self):
        panel = self.module.Panel(self.root)
        panel.apply(lastlight.WAVE_MAX, 0.5)
        (self.device / 'brightness').write_text('400\n')   # he pressed F1
        panel.rebase_if_touched()
        self.assertEqual(panel.base, 400)
        panel.restore()
        self.assertEqual(self.level(), 400, 'restoring must not undo his own change')

    def test_a_machine_with_no_backlight_is_simply_quiet(self):
        panel = self.module.Panel(self.root / 'absent')
        self.assertFalse(panel.available)
        panel.apply(0.03, 0.5)
        panel.restore()


class DaemonTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.power = self.root / 'power'
        (self.power / 'BAT0').mkdir(parents=True)
        (self.power / 'ADP1').mkdir(parents=True)
        (self.power / 'BAT0' / 'type').write_text('Battery\n')
        (self.power / 'BAT0' / 'capacity').write_text('3\n')
        (self.power / 'BAT0' / 'status').write_text('Discharging\n')
        (self.power / 'ADP1' / 'type').write_text('Mains\n')
        (self.power / 'ADP1' / 'online').write_text('0\n')
        self.runtime = self.root / 'runtime'
        self.runtime.mkdir()

    def environment(self):
        return dict(os.environ, OLDBOOK_POWER_ROOT=str(self.power),
                    OLDBOOK_BACKLIGHT_ROOT=str(self.root / 'absent'),
                    XDG_RUNTIME_DIR=str(self.runtime))

    def test_one_pass_publishes_a_record_the_keyboard_can_read(self):
        result = subprocess.run(
            [sys.executable, str(BIN / 'oldbook-lastlight'), 'run', '--once', '--no-surface'],
            env=self.environment(), capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        # The daemon clears its record on the way out; capture it by reading the
        # same numbers the run would have written.
        show = subprocess.run(
            [sys.executable, str(BIN / 'oldbook-lastlight'), 'status'],
            env=self.environment(), capture_output=True, text=True, timeout=60)
        self.assertIn('terminal', show.stdout)
        self.assertIn('3%', show.stdout)

    def test_status_on_a_healthy_charge_asks_for_nothing(self):
        (self.power / 'BAT0' / 'capacity').write_text('80\n')
        show = subprocess.run(
            [sys.executable, str(BIN / 'oldbook-lastlight'), 'status'],
            env=self.environment(), capture_output=True, text=True, timeout=60)
        self.assertEqual(show.returncode, 0, show.stderr)
        self.assertIn('clear', show.stdout)
        self.assertIn('0.000', show.stdout)


class KeyboardHandshakeTests(unittest.TestCase):
    """The keyboard reads the published period defensively, or not at all."""

    def setUp(self):
        self.keyboard = load_script('oldbook-keyboard-backlight')
        self.runtime = Path(tempfile.mkdtemp())

    def period(self, cache=None, now=1000.0):
        return self.keyboard._breath_period(cache if cache is not None else {},
                                            self.runtime, now)

    def test_no_file_means_the_resting_breath(self):
        self.assertEqual(self.period(), self.keyboard.PERIOD)

    def test_rubbish_in_the_file_means_the_resting_breath(self):
        (self.runtime / self.keyboard.LASTLIGHT_FILENAME).write_text('not json at all')
        self.assertEqual(self.period(), self.keyboard.PERIOD)
        (self.runtime / self.keyboard.LASTLIGHT_FILENAME).write_text('{"breath_period": "soon"}')
        self.assertEqual(self.period(), self.keyboard.PERIOD)

    def test_a_published_period_is_honoured_and_clamped(self):
        path = self.runtime / self.keyboard.LASTLIGHT_FILENAME
        path.write_text(json.dumps({'breath_period': 2.0}))
        self.assertEqual(self.period(), 2.0)
        path.write_text(json.dumps({'breath_period': 0.001}))
        self.assertEqual(self.period(now=2000.0), self.keyboard.LASTLIGHT_MIN_PERIOD)
        path.write_text(json.dumps({'breath_period': 99.0}))
        self.assertEqual(self.period(now=3000.0), self.keyboard.PERIOD,
                         'nothing may slow the breath below its resting tempo')

    def test_the_file_is_not_read_every_frame(self):
        path = self.runtime / self.keyboard.LASTLIGHT_FILENAME
        path.write_text(json.dumps({'breath_period': 2.0}))
        cache = {}
        self.assertEqual(self.period(cache, now=1000.0), 2.0)
        path.write_text(json.dumps({'breath_period': 5.0}))
        self.assertEqual(self.period(cache, now=1000.1), 2.0, 'still cached')
        self.assertEqual(self.period(cache, now=1000.0 + self.keyboard.LASTLIGHT_REREAD + 0.01), 5.0)


if __name__ == '__main__':
    unittest.main()
