"""The desktop's one power posture, and the ladder its effects shed by."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

REPO = Path(__file__).resolve().parents[2]
SERVICE = REPO / 'alpine/desktop/.local/bin/oldbook-power-mode'
LIBRARY = REPO / 'alpine/desktop/.local/lib/oldbook'


def load():
    import importlib.util
    spec = importlib.util.spec_from_file_location('power_source', LIBRARY / 'power_source.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def supplies(root, mains=None, battery=None, status='Discharging'):
    """A synthetic /sys/class/power_supply with the parts under test."""
    root.mkdir(parents=True, exist_ok=True)
    if mains is not None:
        adapter = root / 'ADP1'
        adapter.mkdir()
        (adapter / 'type').write_text('Mains\n')
        (adapter / 'online').write_text(f'{1 if mains else 0}\n')
    if battery is not None:
        cell = root / 'BAT0'
        cell.mkdir()
        (cell / 'type').write_text('Battery\n')
        (cell / 'capacity').write_text(f'{battery}\n')
        (cell / 'status').write_text(f'{status}\n')
    return root


class PostureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.power = load()

    def posture(self, **keywords):
        return self.power.measured_posture(supplies(self.root / 'sys', **keywords))

    def test_the_cord_outranks_the_charge(self):
        self.assertEqual(self.posture(mains=True, battery=4), 'mains')

    def test_the_charge_names_the_rung_once_the_cord_is_out(self):
        self.assertEqual(self.posture(mains=False, battery=76), 'battery')
        self.tmp.cleanup()
        for charge, expected in ((26, 'battery'), (25, 'battery-low'),
                                 (11, 'battery-low'), (10, 'battery-critical'),
                                 (1, 'battery-critical')):
            with self.subTest(charge=charge):
                with tempfile.TemporaryDirectory() as fresh:
                    self.assertEqual(
                        self.power.measured_posture(
                            supplies(Path(fresh) / 'sys', mains=False, battery=charge)),
                        expected)

    def test_a_machine_that_cannot_run_out_sheds_nothing(self):
        """A desktop has no battery; it must not be treated as an empty one."""
        self.assertEqual(self.posture(mains=True), 'mains')
        with tempfile.TemporaryDirectory() as fresh:
            self.assertEqual(self.power.measured_posture(Path(fresh) / 'absent'), 'mains')

    def test_a_charging_battery_proves_the_cord_without_a_mains_supply(self):
        self.assertEqual(self.posture(battery=40, status='Charging'), 'mains')

    def test_an_unreadable_supply_is_skipped_rather_than_guessed(self):
        root = supplies(self.root / 'sys', mains=False, battery=50)
        broken = root / 'BAT1'
        broken.mkdir()
        (broken / 'type').write_text('Battery\n')
        (broken / 'capacity').write_text('not a number\n')
        (broken / 'status').write_text('Discharging\n')
        self.assertEqual(self.power.measured_posture(root), 'battery')

    def test_an_effect_missing_from_the_ladder_is_never_switched_off(self):
        for posture in self.power.POSTURES:
            with self.subTest(posture=posture):
                self.assertTrue(self.power.allows('a-helper-added-tomorrow', posture))

    def test_each_rung_shed_is_a_superset_of_the_one_above(self):
        previous = set()
        for posture in self.power.POSTURES:
            shed = set(self.power.shed(posture))
            self.assertTrue(previous <= shed, f'{posture} un-sheds {previous - shed}')
            previous = shed
        self.assertEqual(previous, set(self.power.LADDER))


class OverrideTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.environment = dict(
            os.environ,
            OLDBOOK_POWER_ROOT=str(supplies(self.root / 'sys', mains=True, battery=80)),
            XDG_STATE_HOME=str(self.root / 'state'),
            XDG_RUNTIME_DIR=str(self.root / 'run'),
            XDG_CONFIG_HOME=str(self.root / 'config'))
        (self.root / 'run').mkdir(mode=0o700)

    def service(self, *arguments):
        return subprocess.run([str(SERVICE), *arguments], env=self.environment,
                              capture_output=True, text=True, timeout=20)

    def test_an_override_can_only_make_the_desktop_quieter(self):
        """Being plugged in is not permission to override a flat battery back up."""
        held = self.service('override', 'battery-low')
        self.assertEqual(held.returncode, 0, held.stderr)
        self.assertIn('battery-low', held.stdout)
        supplies(self.root / 'empty', mains=False, battery=3)
        louder = subprocess.run(
            [str(SERVICE), 'show'],
            env=dict(self.environment, OLDBOOK_POWER_ROOT=str(self.root / 'empty')),
            capture_output=True, text=True, timeout=20)
        self.assertIn('posture   battery-critical', louder.stdout)

    def test_auto_returns_the_desktop_to_the_hardware(self):
        self.service('override', 'battery-critical')
        released = self.service('override', 'auto')
        self.assertEqual(released.returncode, 0, released.stderr)
        self.assertIn('posture   mains', released.stdout)
        self.assertNotIn('override', released.stdout)

    def test_allows_answers_by_exit_status_for_shell_callers(self):
        self.assertEqual(self.service('allows', 'shaders').returncode, 0)
        self.service('override', 'battery')
        self.assertEqual(self.service('allows', 'shaders').returncode, 1)
        self.assertEqual(self.service('allows', 'sound-cues').returncode, 0)

    def test_the_service_publishes_a_record_and_announces_the_change(self):
        hooks = self.root / 'config/oldbook/power.d'
        hooks.mkdir(parents=True)
        witness = self.root / 'witness'
        (hooks / '10-broken').write_text('#!/bin/sh\nexit 9\n')
        (hooks / '20-record').write_text(f'#!/bin/sh\nprintf "%s" "$1" > {witness}\n')
        for hook in hooks.iterdir():
            hook.chmod(0o755)
        published = self.service('run', '--once')
        self.assertEqual(published.returncode, 0, published.stderr)
        record = json.loads((self.root / 'run/oldbook/power.json').read_text())
        self.assertEqual(record['posture'], 'mains')
        self.assertEqual(record['capacity'], 80)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not witness.exists():
            time.sleep(.05)
        # A hook that fails must not silence the hooks after it.
        self.assertEqual(witness.read_text(), 'mains')

    def test_a_subscriber_reads_a_true_posture_with_no_service_running(self):
        power = load()
        self.assertEqual(
            power.published(str(self.root / 'empty-runtime'))['posture'],
            power.measured_posture())


if __name__ == '__main__':
    unittest.main()
