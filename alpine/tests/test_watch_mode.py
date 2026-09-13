"""Watch mode regressions; never touches the live compositor or the session.

Watch mode is a cat guard, not a lock, and these tests are written to hold two
promises: a paw cannot leave it by accident, and a person can never be stranded
in it. The guard's Wayland surface needs a compositor and is exercised by
alpine/verification/watch-mode/verify-headless in a private headless session;
everything decidable without one is decided here.
"""
import json
import os
from pathlib import Path
import runpy
import signal
import stat
import subprocess
import tempfile
import time
import unittest

REPO = Path(__file__).resolve().parents[2]
WATCH_MODE = REPO / 'alpine/desktop/.local/lib/oldbook/watch_mode.py'
WATCH = REPO / 'alpine/desktop/.local/bin/oldbook-watch'
CONFIG = REPO / 'alpine/desktop/.config/sway/local.d/watch.conf'
module = runpy.run_path(str(WATCH_MODE))


class ReleaseChordTests(unittest.TestCase):
    """A cat lying on the keyboard must not be able to leave watch mode."""

    SUPER, SHIFT, ESCAPE, LETTER = 133, 50, 9, 38
    HELD = {'super', 'shift'}

    def chord(self):
        return module['ReleaseChord']()

    def take(self, chord, at=0.0, modifiers=None):
        """Press the release chord the way a person does: modifiers, then key."""
        modifiers = self.HELD if modifiers is None else modifiers
        chord.press(self.SUPER, 'Super_L', {'super'}, at)
        chord.press(self.SHIFT, 'Shift_L', {'super', 'shift'}, at)
        chord.press(self.ESCAPE, 'Escape', modifiers, at)

    def test_a_held_clean_chord_releases_after_a_full_second(self):
        chord = self.chord()
        self.take(chord, at=10.0)
        self.assertTrue(chord.armed)
        self.assertFalse(chord.ready(10.9), 'nearly a second is not a second')
        self.assertTrue(chord.ready(11.0))

    def test_a_tap_never_releases(self):
        chord = self.chord()
        self.take(chord, at=1.0)
        chord.release(self.ESCAPE, self.HELD, 1.08)
        self.assertFalse(chord.armed)
        self.assertFalse(chord.ready(9.0))

    def test_any_other_key_down_blocks_the_release(self):
        """The cat test. A settled cat holds a handful of neighbouring keys and
        never exactly one, so the clean-chord rule is what really guards this."""
        chord = self.chord()
        self.take(chord, at=2.0)
        chord.press(self.LETTER, 'a', self.HELD, 2.1)
        self.assertFalse(chord.armed)
        self.assertFalse(chord.ready(30.0), 'a paw resting on another key must not leave')
        chord.release(self.LETTER, self.HELD, 3.0)
        self.assertTrue(chord.armed, 'lifting the stray key re-arms')
        self.assertFalse(chord.ready(3.5), 'and restarts the clock from there')
        self.assertTrue(chord.ready(4.0))

    def test_autorepeat_is_not_a_second_press(self):
        """A held key repeats about twenty-five times a second. Each repeat
        must leave the hold's start time alone, because the guard schedules one
        timer per hold from it: restarting on every repeat means the timer
        never expires and the chord never releases."""
        chord = self.chord()
        self.take(chord, at=0.0)
        began = chord.armed_at
        for repeat in (0.04, 0.08, 0.12, 0.16, 0.2, 0.4, 0.6, 0.8, 0.96):
            chord.press(self.ESCAPE, 'Escape', self.HELD, repeat)
            chord.press(self.SUPER, 'Super_L', self.HELD, repeat)
            self.assertEqual(chord.armed_at, began, 'the hold clock never restarts')
        self.assertTrue(chord.ready(1.0), 'leaning on the chord must not restart it')

    def test_a_chord_typed_without_modifier_key_events_still_arms(self):
        """A virtual keyboard sets the modifier mask without ever sending
        Super_L or Shift_L as keys, and a real one sends both. Watch mode reads
        the mask and the non-modifier keys separately so either works."""
        chord = self.chord()
        chord.press(self.ESCAPE, 'Escape', self.HELD, 0.0)
        self.assertTrue(chord.armed)
        self.assertTrue(chord.ready(1.0))

    def test_extra_modifiers_block_the_release(self):
        chord = self.chord()
        self.take(chord, at=0.0, modifiers={'super', 'shift', 'ctrl'})
        self.assertFalse(chord.armed)
        self.assertFalse(chord.ready(5.0))

    def test_the_wrong_key_never_arms(self):
        chord = self.chord()
        chord.press(self.LETTER, 'a', self.HELD, 0.0)
        self.assertFalse(chord.armed)
        self.assertFalse(chord.ready(5.0))


class WatchStateTests(unittest.TestCase):
    def test_a_stale_record_is_never_reported_as_engaged(self):
        with tempfile.TemporaryDirectory(prefix='oldbook-watch-state-') as directory:
            root = Path(directory)
            record = {'process': module['process_identity'](os.getpid()), 'engaged_at': 1.0}
            module['publish'](record, root)
            self.assertEqual(module['engaged'](root)['engaged_at'], 1.0)
            self.assertEqual(oct(module['state_path'](root).stat().st_mode & 0o777), '0o600')
            record['process']['start_time'] = 'invalid'
            module['publish'](record, root)
            self.assertIsNone(module['engaged'](root),
                              'a matching pid has never proved a live guard')
            module['state_path'](root).unlink()
            self.assertIsNone(module['engaged'](root))

    def test_a_shared_runtime_directory_is_refused(self):
        with tempfile.TemporaryDirectory(prefix='oldbook-watch-state-') as directory:
            (Path(directory) / 'oldbook').mkdir(mode=0o755)
            with self.assertRaises(RuntimeError):
                module['runtime_directory'](directory)


def recording_sway(root):
    """An environment whose swaymsg records every call and always succeeds."""
    binary = root / 'bin'
    binary.mkdir()
    recorder = binary / 'swaymsg'
    recorder.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> ' + str(root / 'calls') + '\n'
                        'echo \'[{"success": true}]\'\n')
    recorder.chmod(0o755)
    return dict(os.environ, PATH=str(binary) + ':/usr/bin:/bin')


class NeverStuckTests(unittest.TestCase):
    """The one outcome worse than not starting is a desktop nobody can reach."""

    def fake_sway(self, root):
        return recording_sway(root)

    def test_the_watchdog_restores_the_default_mode_when_the_guard_is_killed(self):
        with tempfile.TemporaryDirectory(prefix='oldbook-watch-dog-') as directory:
            root = Path(directory)
            environment = self.fake_sway(root)
            ready = root / 'armed'
            code = (f'import runpy, time;'
                    f'm = runpy.run_path({str(WATCH_MODE)!r});'
                    f'fd = m["mode_watchdog"]({environment!r});'
                    f'open({str(ready)!r}, "w").write("1");'
                    f'time.sleep(30)')
            child = subprocess.Popen(['/usr/bin/python3', '-c', code], start_new_session=True,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline and not ready.exists():
                    time.sleep(0.05)
                self.assertTrue(ready.exists(), 'the watchdog never armed')
                self.assertFalse((root / 'calls').exists(),
                                 'the watchdog must not restore the mode while the guard lives')
                os.killpg(child.pid, signal.SIGKILL)
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline and not (root / 'calls').exists():
                    time.sleep(0.05)
                self.assertIn('mode default', (root / 'calls').read_text().replace('"', ''),
                              'a killed guard must leave Sway in its default mode')
            finally:
                if child.poll() is None:
                    os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=5)

    def test_a_refused_sway_command_is_raised_and_never_swallowed(self):
        with tempfile.TemporaryDirectory(prefix='oldbook-watch-sway-') as directory:
            root = Path(directory)
            binary = root / 'bin'
            binary.mkdir()
            refuser = binary / 'swaymsg'
            refuser.write_text('#!/bin/sh\necho \'[{"success": false, "error": "no such mode"}]\'\n')
            refuser.chmod(0o755)
            environment = dict(os.environ, PATH=str(binary) + ':/usr/bin:/bin')
            with self.assertRaises(RuntimeError):
                module['sway']('mode "watch"', environment=environment)
            refuser.write_text('#!/bin/sh\necho "boom" >&2\nexit 1\n')
            refuser.chmod(0o755)
            with self.assertRaises(RuntimeError):
                module['sway']('mode "watch"', environment=environment)

    def test_stop_restores_the_mode_even_with_no_guard_running(self):
        with tempfile.TemporaryDirectory(prefix='oldbook-watch-stop-') as directory:
            root = Path(directory)
            environment = self.fake_sway(root)
            environment['XDG_RUNTIME_DIR'] = str(root)
            Path(root).chmod(0o700)
            result = subprocess.run([str(WATCH), 'stop'], env=environment,
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            recorded = (root / 'calls').read_text().replace('"', '')
            self.assertIn('mode default', recorded)


class HonestyTests(unittest.TestCase):
    """Watch mode must never be sold, in code or on screen, as security."""

    def test_the_indicator_names_the_chord_and_denies_being_a_lock(self):
        self.assertIn('Super + Shift + Escape', module['HOW_TO_LEAVE'])
        self.assertIn('second', module['HOW_TO_LEAVE'])
        self.assertIn('not a lock', module['NOT_A_LOCK'])
        self.assertIn('Super + Escape', module['NOT_A_LOCK'])
        self.assertIn('cat guard, not a lock', module['__doc__'])

    def test_the_helper_reports_plainly_that_it_is_not_security(self):
        text = WATCH.read_text()
        self.assertIn('cat guard, not a lock', text)
        self.assertEqual(text.splitlines()[0], '#!/usr/bin/env python3')
        self.assertTrue(WATCH.stat().st_mode & stat.S_IXUSR, 'oldbook-watch must be executable')

    def test_the_bindings_enter_on_the_asked_chord_and_leave_the_lock_alone(self):
        config = CONFIG.read_text()
        self.assertIn('bindsym $mod+Shift+Escape exec ~/.local/bin/oldbook-watch start', config)
        self.assertIn('mode "watch" {', config)
        self.assertNotIn('mode "default"', config,
                         'nothing in the config leaves the mode; only the held chord does')
        self.assertNotIn('$mod+Escape exec', config, 'the real lock binding is not touched here')
        session = (REPO / 'alpine/desktop/.config/sway/config').read_text()
        self.assertIn('bindsym $mod+Escape exec $lock', session)

    def test_the_empty_mode_binds_nothing_a_paw_could_reach(self):
        body = CONFIG.read_text().split('mode "watch" {', 1)[1].split('}', 1)[0]
        bindings = [line.strip() for line in body.splitlines()
                    if line.strip().startswith('bindsym')]
        self.assertEqual(bindings, [], 'the watch mode binds nothing at all: a settled cat '
                                       'holds five keys at once, and any chord is hers')

    def test_the_mode_block_carries_one_line_so_sway_creates_the_mode(self):
        """Sway creates a mode only when a line inside its block runs: the
        opener is a block start, not a command, so an empty block leaves no
        `watch` mode at all, `swaymsg mode watch` is refused as unknown, and
        the guard reads that as a refusal to start. The line must bind
        nothing, and `set` is the one mode subcommand that does not."""
        body = CONFIG.read_text().split('mode "watch" {', 1)[1].split('}', 1)[0]
        commands = [line.strip() for line in body.splitlines()
                    if line.strip() and not line.strip().startswith('#')]
        self.assertTrue(commands, 'an empty mode block creates no mode, so the guard '
                                  'can never start')
        for command in commands:
            self.assertTrue(command.startswith('set '),
                            f'the watch block may carry nothing that binds: {command!r}')


class OnlyTheUserLeavesTests(unittest.TestCase):
    """Catbed mode is applied by hand and ended by hand, and it outlasts
    everything else: the cat getting up, the screen lock, a Sway reload."""

    def test_losing_the_keyboard_waits_instead_of_ending(self):
        text = WATCH.read_text()
        self.assertIn('on_keyboard_lost=waiting', text)
        self.assertNotIn("finish('keyboard-lost')", text)
        self.assertNotIn('ended early', text)

    def test_a_mode_change_that_is_not_ours_is_undone(self):
        lost = module['mode_lost']
        self.assertTrue(lost('{ "change": "default", "pango_markup": false }'))
        self.assertTrue(lost('{ "change": "resize", "pango_markup": false }'))
        self.assertFalse(lost('{ "change": "watch", "pango_markup": false }'),
                         'our own re-entry is not a loss')
        self.assertFalse(lost('not json'))
        self.assertFalse(lost('{"change": 3, "pango_markup": false}'))
        self.assertFalse(lost('[]'))
        text = WATCH.read_text()
        self.assertIn('watch_mode.mode_events()', text)
        self.assertIn('watch_mode.mode_lost(', text)

    def test_a_reload_is_a_loss_although_sway_sends_no_mode_event(self):
        """A reload resets every binding mode to default and announces itself
        only as a workspace event whose change is "reload". A guard listening
        for mode events alone never hears it, never re-enters, and leaves the
        compositor's bindings live under the cat -- which is what happened."""
        lost = module['mode_lost']
        self.assertTrue(lost('{"change": "reload", "current": null, "old": null}'))
        for change in ('focus', 'init', 'empty', 'move', 'rename', 'urgent'):
            self.assertFalse(lost(f'{{"change": "{change}", "current": {{"id": 1}}, "old": null}}'),
                             f'a workspace {change} says nothing about modes')
        with tempfile.TemporaryDirectory(prefix='oldbook-watch-events-') as directory:
            root = Path(directory)
            events = module['mode_events'](recording_sway(root))
            events.wait(timeout=10)
            recorded = (root / 'calls').read_text()
            self.assertIn('subscribe', recorded)
            self.assertIn('"mode"', recorded)
            self.assertIn('"workspace"', recorded, 'the reload arrives as a workspace event')

    def test_the_guard_holds_what_the_lock_holds_and_lets_go_last(self):
        text = WATCH.read_text()
        self.assertIn("catbed_guard.hold_all(", text)
        run = text.split('def run(runtime):', 1)[1].split('def stop(runtime):', 1)[0]
        cleanup = run.split('finally:', 1)[1]
        self.assertLess(cleanup.index('mode "default"'), cleanup.index('guard.close()'))
        self.assertLess(cleanup.index('guard.close()'), cleanup.index('catbed_guard.release('))

    def test_the_helper_says_it_is_the_users_alone(self):
        text = WATCH.read_text()
        self.assertIn("Leaving is the user's alone", text)
        self.assertIn('no exit chord', text)


if __name__ == '__main__':
    unittest.main()
