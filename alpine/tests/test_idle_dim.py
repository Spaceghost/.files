"""oldbook-idle dims a synthetic backlight and drives a fake keyboard helper."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest


HELPER = Path(__file__).resolve().parents[1] / 'desktop/.local/bin/oldbook-idle'


class IdleDimTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='oldbook-idle-test-')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / 'backlight'
        self.panel = self.root / 'panel'
        self.runtime = self.base / 'runtime'
        for folder in (self.panel, self.runtime):
            folder.mkdir(parents=True)
        (self.panel / 'max_brightness').write_text('1023\n')
        (self.panel / 'brightness').write_text('800\n')
        self.keyboard_log = self.base / 'keyboard.log'
        self.keyboard = self.base / 'fake-keyboard-backlight'
        self.keyboard.write_text('#!/bin/sh\nprintf \'%s\\n\' "$1" >> ' + str(self.keyboard_log) + '\n')
        self.keyboard.chmod(0o755)
        self.env = dict(os.environ, XDG_RUNTIME_DIR=str(self.runtime),
                        OLDBOOK_BACKLIGHT_ROOT=str(self.root),
                        OLDBOOK_KEYBOARD_BACKLIGHT=str(self.keyboard))

    def run_helper(self, action):
        result = subprocess.run([str(HELPER), action], env=self.env, capture_output=True,
                                text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def brightness(self):
        # A plain file is not a sysfs attribute: a reader can catch the worker's
        # truncate-then-write mid-way, so retry a transient empty read.
        for _ in range(50):
            text = (self.panel / 'brightness').read_text().strip()
            if text:
                return int(text)
            time.sleep(.002)
        self.fail('brightness file stayed empty')

    def keyboard_actions(self):
        try:
            return self.keyboard_log.read_text().split()
        except FileNotFoundError:
            return []

    def state(self):
        try:
            return json.loads((self.runtime / 'oldbook/idle/display.json').read_text())
        except FileNotFoundError:
            return None

    def wait_for(self, callback, message, seconds=8):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if callback():
                return
            time.sleep(.02)
        self.fail(message)

    def test_dim_returns_promptly_ramps_down_and_undim_restores(self):
        started = time.monotonic()
        self.assertEqual(self.run_helper('dim'), 'dimming')
        elapsed = time.monotonic() - started
        # The ramp runs detached: dim returns before the 1.5-second ease finishes.
        self.assertTrue(elapsed < 1.2 or self.state()['ramp'] or self.brightness() > 205,
                        f'dim blocked swayidle for {elapsed:.2f}s and the ramp had finished')
        self.assertLess(elapsed, 4.0, 'dim took far too long to return')
        self.assertEqual(self.keyboard_actions(), ['last-breath'])
        self.wait_for(lambda: self.brightness() == 205, 'display never reached 20%')
        self.wait_for(lambda: self.state() is not None and not self.state()['ramp'],
                      'ramp worker did not record completion')
        self.assertEqual(self.state()['original'], 800)
        self.assertEqual(self.run_helper('undim'), 'restored')
        self.assertEqual(self.brightness(), 800)
        self.assertIsNone(self.state())
        self.assertEqual(self.keyboard_actions(), ['last-breath', 'restore'])

    def test_ramp_eases_through_intermediate_levels(self):
        self.run_helper('dim')
        seen = set()
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline and self.brightness() != 205:
            seen.add(self.brightness())
            time.sleep(.01)
        self.assertEqual(self.brightness(), 205)
        self.assertGreater(len([level for level in seen if 205 < level < 800]), 5)
        self.run_helper('undim')

    def test_undim_mid_ramp_cancels_and_restores(self):
        self.run_helper('dim')
        self.wait_for(lambda: self.brightness() < 800, 'ramp never started')
        self.assertGreaterEqual(self.brightness(), 205)
        self.assertEqual(self.run_helper('undim'), 'restored')
        self.assertEqual(self.brightness(), 800)
        time.sleep(.6)
        self.assertEqual(self.brightness(), 800, 'a cancelled ramp kept writing')
        self.assertIsNone(self.state())
        self.assertFalse((self.runtime / 'oldbook/idle/cancel').exists())

    def test_manual_adjustment_during_dim_is_kept(self):
        self.run_helper('dim')
        self.wait_for(lambda: self.brightness() < 790, 'ramp never started')
        (self.panel / 'brightness').write_text('500\n')
        self.wait_for(lambda: self.state() is not None and self.state()['adjusted'],
                      'ramp did not notice the manual change')
        time.sleep(.3)
        self.assertEqual(self.brightness(), 500)
        self.assertEqual(self.run_helper('undim'), 'kept-adjusted-level')
        self.assertEqual(self.brightness(), 500)
        self.assertEqual(self.keyboard_actions(), ['last-breath', 'restore'])

    def test_already_dim_display_is_left_alone(self):
        (self.panel / 'brightness').write_text('100\n')
        self.assertEqual(self.run_helper('dim'), 'already-dim')
        self.assertEqual(self.brightness(), 100)
        self.assertEqual(self.run_helper('undim'), 'unchanged')
        self.assertEqual(self.brightness(), 100)
        self.assertEqual(self.keyboard_actions(), ['last-breath', 'restore'])

    def test_missing_display_still_breathes_the_keyboard(self):
        (self.panel / 'brightness').unlink()
        self.assertEqual(self.run_helper('dim'), 'no-display')
        self.assertEqual(self.run_helper('undim'), 'nothing-to-restore')
        self.assertEqual(self.keyboard_actions(), ['last-breath', 'restore'])

    def test_second_dim_while_ramping_is_ignored(self):
        self.assertEqual(self.run_helper('dim'), 'dimming')
        self.assertEqual(self.run_helper('dim'), 'already-dimming')
        self.assertEqual(self.keyboard_actions(), ['last-breath'])
        self.run_helper('undim')
        self.assertEqual(self.brightness(), 800)

    def test_stale_state_from_a_dead_worker_is_replaced(self):
        directory = self.runtime / 'oldbook/idle'
        directory.mkdir(parents=True)
        (directory / 'display.json').write_text(json.dumps(dict(
            device=str(self.panel), original=900, last=300, target=205, maximum=1023,
            pid=2 ** 22 - 1, started=0, ramp=True, adjusted=False)) + '\n')
        self.assertEqual(self.run_helper('dim'), 'dimming')
        self.assertEqual(self.state()['original'], 800)
        self.run_helper('undim')
        self.assertEqual(self.brightness(), 800)

    def test_status_reports_runtime_state_only(self):
        self.assertEqual(self.run_helper('status'), '{}')
        self.run_helper('dim')
        self.assertEqual(json.loads(self.run_helper('status'))['original'], 800)
        self.run_helper('undim')
        self.assertEqual(self.run_helper('status'), '{}')


if __name__ == '__main__':
    unittest.main()
