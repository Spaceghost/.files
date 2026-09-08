"""Keyboard-light controls use synthetic LED files; never access real hardware."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import math
from pathlib import Path
import runpy
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch


HELPER = Path(__file__).resolve().parents[1] / 'desktop/.local/bin/oldbook-keyboard-backlight'


class SessionPeer:
    """A listening Unix peer that can die without unlinking its socket path."""

    def __init__(self, path):
        self.path = path
        self.listener = socket.socket(socket.AF_UNIX)
        self.listener.bind(str(path))
        self.listener.listen(8)
        self.listener.settimeout(.05)
        self.clients = []
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self.accept_clients, daemon=True)
        self.thread.start()

    def accept_clients(self):
        while not self.stopping.is_set():
            try:
                client, _address = self.listener.accept()
                self.clients.append(client)
            except socket.timeout:
                continue
            except OSError:
                return

    def close(self):
        self.stopping.set()
        self.listener.close()
        self.thread.join(timeout=1)
        for client in self.clients:
            client.close()


def load_helper():
    return runpy.run_path(str(HELPER))['KeyboardBacklight']


class KeyboardBacklightTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='keyboard-light-test-')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.led = self.base / 'smc::kbd_backlight'
        self.state = self.base / 'state'
        self.runtime = self.base / 'runtime'
        for folder in (self.led, self.state, self.runtime):
            folder.mkdir()
        (self.led / 'max_brightness').write_text('255\n')
        (self.led / 'brightness').write_text('64\n')
        self.saved = self.state / 'keyboard-backlight'
        self.mode = self.state / 'keyboard-backlight-mode'
        self.Helper = load_helper()

    def helper(self, **kwargs):
        return self.Helper(self.led, self.state, self.runtime, **kwargs)

    def brightness(self):
        return int((self.led / 'brightness').read_text())

    def wait_for(self, callback, message, seconds=3):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                result = callback()
            except (ValueError, FileNotFoundError):
                result = None
            if result:
                return result
            time.sleep(.005)
        self.fail(message)

    def serve_in_thread(self, helper):
        stop = threading.Event()
        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='keyboard-light-service')
        future = pool.submit(helper.serve, stop)

        def cleanup():
            stop.set()
            future.result(timeout=3)
            pool.shutdown(wait=True)

        self.addCleanup(cleanup)
        self.wait_for(lambda: helper.status()['running'], 'breathing service did not own its runtime lock')
        return stop, future

    def test_status_describes_whole_keyboard_control_without_writing(self):
        before = (self.led / 'brightness').stat().st_mtime_ns
        status = self.helper().status()
        self.assertTrue(status['available'])
        self.assertTrue(status['device'])
        self.assertEqual(status['control'], 'whole-keyboard')
        self.assertIs(status['per_key'], False)
        self.assertEqual(status['maximum'], 255)
        self.assertEqual(status['brightness'], 64)
        self.assertEqual(status['level'], 64)
        self.assertEqual(status['mode'], 'steady')
        self.assertFalse(status['running'])
        self.assertEqual((self.led / 'brightness').stat().st_mtime_ns, before)

    def test_missing_device_is_reported_without_creating_hardware_files(self):
        missing = self.base / 'absent-led'
        status = self.Helper(missing, self.state, self.runtime).status()
        self.assertFalse(status['available'])
        self.assertFalse(missing.exists())

    def test_brightness_steps_and_toggle_preserve_existing_controls(self):
        helper = self.helper()
        self.assertEqual(helper.command('down', spawn=False)['level'], 39)
        self.assertEqual(self.brightness(), 39)
        self.assertEqual(helper.command('up', spawn=False)['level'], 64)
        self.assertEqual(helper.command('toggle', spawn=False)['level'], 0)
        self.assertEqual(self.brightness(), 0)
        self.assertEqual(helper.command('toggle', spawn=False)['level'], 64)
        self.assertEqual(int(self.saved.read_text()), 64)

    def test_first_use_zero_remains_off_until_a_requested_action(self):
        for action, expected in (('up', 25), ('toggle', 64), ('restore', 64)):
            with self.subTest(action=action):
                self.saved.unlink(missing_ok=True)
                self.mode.unlink(missing_ok=True)
                (self.led / 'brightness').write_text('0\n')
                helper = self.helper()
                self.assertEqual(helper.status()['level'], 0)
                self.assertEqual(helper.command(action, spawn=False)['level'], expected)
                self.assertEqual(self.brightness(), expected)

    def test_steps_clamp_at_both_hardware_limits(self):
        helper = self.helper()
        for _ in range(12):
            helper.command('up', spawn=False)
        self.assertEqual(helper.status()['level'], 255)
        self.assertEqual(self.brightness(), 255)
        for _ in range(12):
            helper.command('down', spawn=False)
        self.assertEqual(helper.status()['level'], 0)
        self.assertEqual(self.brightness(), 0)
        self.assertEqual(helper.status()['mode'], 'steady')

    def test_restore_recovers_saved_peak_and_breathing_preference(self):
        self.saved.write_text('175\n')
        self.mode.write_text('breathing\n')
        (self.led / 'brightness').write_text('0\n')
        status = self.helper().command('restore', spawn=False)
        self.assertEqual(status['level'], 175)
        self.assertEqual(status['mode'], 'breathing')
        self.assertEqual(self.brightness(), 175)
        self.assertFalse(status['running'])

    def test_breathe_toggles_mode_and_steady_restores_peak(self):
        helper = self.helper()
        self.assertEqual(helper.command('breathe', spawn=False)['mode'], 'breathing')
        (self.led / 'brightness').write_text('8\n')
        status = helper.command('breathe', spawn=False)
        self.assertEqual(status['mode'], 'steady')
        self.assertEqual(self.brightness(), 64)
        helper.command('breathe', spawn=False)
        (self.led / 'brightness').write_text('8\n')
        self.assertEqual(helper.command('steady', spawn=False)['mode'], 'steady')
        self.assertEqual(self.brightness(), 64)

    def test_brightness_keys_adjust_breathing_peak_not_current_pulse(self):
        helper = self.helper()
        helper.command('breathe', spawn=False)
        (self.led / 'brightness').write_text('8\n')
        status = helper.command('down', spawn=False)
        self.assertEqual(status['level'], 39)
        self.assertEqual(status['mode'], 'breathing')
        self.assertEqual(int(self.saved.read_text()), 39)
        (self.led / 'brightness').write_text('5\n')
        self.assertEqual(helper.command('up', spawn=False)['level'], 64)

    def test_wpm_mode_can_be_activated(self):
        status = self.helper().command('typing-wpm', spawn=False)
        self.assertEqual(status['mode'], 'typing-wpm')
        self.assertEqual(status['level'], 64)

    def test_typing_dark_wpm_mode_can_be_activated(self):
        self.saved.write_text('0\n')
        (self.led / 'brightness').write_text('0\n')
        status = self.helper().command('typing-dark-wpm', spawn=False)
        self.assertEqual(status['mode'], 'typing-dark-wpm')
        self.assertEqual(status['level'], 255)

    def test_off_and_down_to_zero_stop_breathing(self):
        for action in ('toggle', 'down'):
            with self.subTest(action=action):
                self.saved.write_text('20\n')
                self.mode.write_text('breathing\n')
                (self.led / 'brightness').write_text('3\n')
                status = self.helper().command(action, spawn=False)
                self.assertEqual(status['mode'], 'steady')
                self.assertEqual(status['level'], 0)
                self.assertEqual(self.brightness(), 0)

    def test_concurrent_key_commands_do_not_lose_saved_increments(self):
        (self.led / 'brightness').write_text('0\n')
        self.saved.write_text('0\n')
        ready = threading.Barrier(8)

        def up(_index):
            helper = self.helper()
            ready.wait(timeout=3)
            return helper.command('up', spawn=False)

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(up, range(8)))
        self.assertTrue(all(25 <= result['level'] <= 200 for result in results))
        self.assertEqual(self.helper().status()['level'], 200)
        self.assertEqual(self.brightness(), 200)

    def test_breathing_service_is_singleton_and_stop_restores_saved_level(self):
        helper = self.helper()
        helper.command('breathe', spawn=False)
        stop, future = self.serve_in_thread(helper)
        already_stopped = threading.Event()
        already_stopped.set()
        self.assertIs(self.helper().serve(already_stopped), False)
        self.assertFalse(future.done())
        stop.set()
        self.assertIs(future.result(timeout=3), True)
        self.assertEqual(self.brightness(), 64)
        self.assertEqual(int(self.saved.read_text()), 64)
        self.assertFalse(helper.status()['running'])

    def test_service_cleanup_does_not_undo_a_later_manual_off(self):
        helper = self.helper()
        helper.command('breathe', spawn=False)
        _stop, future = self.serve_in_thread(helper)
        self.wait_for(lambda: 0 < self.brightness() < 64, 'pulse never moved below its saved peak')
        status = self.helper().command('toggle', spawn=False)
        self.assertEqual(status['level'], 0)
        self.assertIs(future.result(timeout=3), True)
        self.assertEqual(self.brightness(), 0)
        self.assertEqual(int(self.saved.read_text()), 0)
        self.assertEqual(helper.status()['mode'], 'steady')

    def test_stale_session_cannot_persist_an_unserved_breathing_request(self):
        session = self.base / 'stale-session.sock'
        with socket.socket(socket.AF_UNIX) as listener:
            listener.bind(str(session))
            listener.listen(1)
        self.assertTrue(session.is_socket())
        helper = self.helper(session=session)
        try:
            helper.command('breathe', spawn=False)
        except (OSError, RuntimeError):
            pass
        self.assertEqual(helper.status()['mode'], 'steady')
        self.assertEqual(self.brightness(), 64)

    def test_dead_session_peer_stops_service_even_while_socket_path_remains(self):
        session = self.base / 'session.sock'
        peer = SessionPeer(session)
        self.addCleanup(peer.close)
        helper = self.helper(session=session)
        helper.command('breathe', spawn=False)
        _stop, future = self.serve_in_thread(helper)
        peer.close()
        self.assertTrue(session.is_socket())
        self.assertIs(future.result(timeout=3), True)
        self.assertEqual(self.brightness(), 64)
        self.assertEqual(int(self.saved.read_text()), 64)

    def test_steady_to_breathing_cannot_mistake_an_exiting_worker_for_a_live_owner(self):
        unlocked = threading.Event()
        resume = threading.Event()
        helper = self.helper()
        original_lock = helper.locked

        @contextmanager
        def interpose():
            with original_lock():
                yield
                pause = (threading.current_thread().name.startswith('keyboard-light-service')
                         and not unlocked.is_set() and self.mode.read_text().strip() == 'steady')
            if pause:
                unlocked.set()
                if not resume.wait(timeout=3):
                    raise AssertionError('test did not release the paused worker')

        helper.command('breathe', spawn=False)
        def replacement(*_args, **_kwargs):
            return self.serve_in_thread(self.helper())[1]

        with patch.object(helper, 'locked', interpose), patch('subprocess.Popen', side_effect=replacement) as spawn:
            _stop, future = self.serve_in_thread(helper)
            try:
                helper.command('steady', spawn=False)
                self.assertTrue(unlocked.wait(timeout=3), 'worker never completed its steady decision')
                self.helper().command('breathe', spawn=True)
                spawn.assert_called_once()
            finally:
                resume.set()
            self.assertIs(future.result(timeout=3), True)
        self.assertEqual(helper.status()['mode'], 'breathing')

    def test_new_session_waits_for_dead_owner_but_does_not_replace_a_live_session(self):
        old_peer = SessionPeer(self.base / 'old-session.sock')
        new_peer = SessionPeer(self.base / 'new-session.sock')
        self.addCleanup(old_peer.close)
        self.addCleanup(new_peer.close)
        old = self.helper(session=old_peer.path)
        old.command('breathe', spawn=False)
        _stop, future = self.serve_in_thread(old)
        new = self.helper(session=new_peer.path)
        def replacement(*_args, **_kwargs):
            return self.serve_in_thread(new)[1]

        with patch('subprocess.Popen', side_effect=replacement) as spawn:
            with self.assertRaises(RuntimeError):
                new.command('restore', spawn=True)
            spawn.assert_not_called()
            old_peer.close()
            self.assertTrue(old_peer.path.is_socket())
            status = new.command('restore', spawn=True)
            self.assertEqual(status['mode'], 'breathing')
            self.assertEqual(status['level'], 64)
            spawn.assert_called_once()
        self.assertIs(future.result(timeout=3), True)
        self.assertEqual(self.brightness(), 64)

    def controlled_run(self, prepare, stop_at, hooks=(), sensor=False):
        """Serve on a synthetic clock; hooks are (time, callback) pairs run in order."""
        now = [0.0]
        samples = []
        pending = sorted(hooks, key=lambda item: item[0])

        def advance(seconds):
            if len(samples) >= 6000:
                raise AssertionError('worker did not make bounded clock progress')
            samples.append((now[0], self.brightness()))
            now[0] += max(float(seconds), .000001)
            while pending and pending[0][0] <= now[0]:
                pending.pop(0)[1]()

        class ControlledStop:
            def is_set(self):
                return now[0] >= stop_at

            def wait(self, seconds):
                advance(seconds)
                return self.is_set()

        with patch('time.monotonic', side_effect=lambda: now[0]), patch('time.sleep', side_effect=advance):
            helper = load_helper()(self.led, self.state, self.runtime, sensor=sensor)
            prepare(helper)
            self.assertIs(helper.serve(ControlledStop()), True)
        return samples

    @staticmethod
    def nearest(samples, stamp):
        return min(samples, key=lambda row: abs(row[0] - stamp))[1]

    def test_last_breath_rises_falls_dark_and_holds_without_saving(self):
        self.saved.write_text('200\n')
        (self.led / 'brightness').write_text('60\n')
        saved_mtime = self.saved.stat().st_mtime_ns
        samples = self.controlled_run(lambda helper: helper.command('last-breath', spawn=False),
                                      stop_at=8.0)
        self.assertEqual(samples[0][1], 60)
        self.assertAlmostEqual(self.nearest(samples, 0.75), 130, delta=4)
        self.assertAlmostEqual(self.nearest(samples, 1.5), 200, delta=3)
        self.assertAlmostEqual(self.nearest(samples, 3.75), 100, delta=4)
        self.assertEqual(self.nearest(samples, 6.1), 0)
        self.assertEqual(self.nearest(samples, 7.9), 0)
        rise = [level for stamp, level in samples if stamp <= 1.5]
        fall = [level for stamp, level in samples if 1.5 <= stamp <= 6.0]
        self.assertEqual(rise, sorted(rise))
        self.assertEqual(fall, sorted(fall, reverse=True))
        # Once dark the worker only checks for changes a few times a second.
        self.assertLessEqual(len([row for row in samples if 6.5 <= row[0] <= 8.0]), 8)
        self.assertEqual(int(self.saved.read_text()), 200)
        self.assertEqual(self.saved.stat().st_mtime_ns, saved_mtime)
        self.assertEqual(self.helper().status()['mode'], 'steady')
        # The overlay outlives the worker until restore clears it; stopping restores the level.
        self.assertEqual(self.helper().status()['overlay'], 'last-breath')
        self.assertEqual(self.brightness(), 200)
        status = self.helper().command('restore', spawn=False)
        self.assertNotIn('overlay', status)
        self.assertEqual(status['level'], 200)
        self.assertEqual(self.brightness(), 200)

    def test_last_breath_interrupts_breathing_and_restore_resumes_it(self):
        self.saved.write_text('200\n')
        self.mode.write_text('breathing\n')
        (self.led / 'brightness').write_text('200\n')
        hooks = [(7.0, lambda: self.helper().command('restore', spawn=False))]
        samples = self.controlled_run(lambda helper: helper.command('last-breath', spawn=False),
                                      stop_at=9.0, hooks=hooks)
        self.assertEqual(self.nearest(samples, 6.5), 0)
        resumed = [level for stamp, level in samples if stamp >= 7.4]
        self.assertTrue(resumed and min(resumed) >= 24, 'breathing did not resume after restore')
        self.assertEqual(self.helper().status()['mode'], 'breathing')
        self.assertNotIn('overlay', self.helper().status())
        self.assertEqual(int(self.saved.read_text()), 200)

    def test_last_breath_keeps_keys_off_when_the_preference_is_off(self):
        self.saved.write_text('0\n')
        (self.led / 'brightness').write_text('0\n')
        status = self.helper().command('last-breath', spawn=False)
        self.assertNotIn('overlay', status)
        self.assertEqual(self.brightness(), 0)
        self.assertFalse(status['running'])

    def test_explicit_actions_end_a_pending_last_breath(self):
        helper = self.helper()
        self.assertEqual(helper.command('last-breath', spawn=False)['overlay'], 'last-breath')
        status = helper.command('up', spawn=False)
        self.assertNotIn('overlay', status)
        self.assertEqual(status['level'], 89)
        self.assertEqual(self.brightness(), 89)

    def test_ambient_requires_a_readable_sensor(self):
        with self.assertRaises(ValueError):
            self.helper(sensor=self.base / 'missing-light').command('ambient', spawn=False)
        self.assertEqual(self.helper().status()['mode'], 'steady')
        self.assertEqual(self.brightness(), 64)

    def test_ambient_status_and_peak_adjustment(self):
        sensor = self.base / 'light'
        sensor.write_text('(11,0)\n')
        helper = self.helper(sensor=sensor)
        status = helper.command('ambient', spawn=False)
        self.assertEqual(status['mode'], 'ambient')
        self.assertEqual(status['level'], 64)
        self.assertEqual(status['light'], 11)
        self.assertEqual(status['sensor'], str(sensor))
        self.assertEqual(helper.command('up', spawn=False)['level'], 89)
        self.assertEqual(helper.status()['mode'], 'ambient')
        self.assertEqual(helper.command('steady', spawn=False)['mode'], 'steady')
        self.assertEqual(self.brightness(), 89)

    def test_ambient_mapping_glows_in_the_dark_and_sleeps_in_daylight(self):
        module = runpy.run_path(str(HELPER))
        target = module['_ambient_target']
        self.assertEqual(target(0, 200), 200)
        self.assertEqual(target(3, 200), 200)
        self.assertEqual(target(240, 200), 0)
        self.assertEqual(target(1000, 200), 0)
        levels = [target(reading, 200) for reading in range(0, 260, 5)]
        self.assertEqual(levels, sorted(levels, reverse=True))
        self.assertTrue(0 < target(30, 200) < 200)
        parse = module['_parse_light']
        self.assertEqual(parse('(11,0)\n'), 11)
        self.assertEqual(parse('(4,17)\n'), 17)
        self.assertEqual(parse('42\n'), 42)
        self.assertIsNone(parse('garbage\n'))

    def test_ambient_mode_fades_with_the_room_light_without_saving(self):
        sensor = self.base / 'light'
        sensor.write_text('(2,0)\n')
        self.saved.write_text('200\n')
        (self.led / 'brightness').write_text('200\n')
        recorded = {}

        def prepare(helper):
            # Choosing the mode saves it once; the animation must not save again.
            helper.command('ambient', spawn=False)
            recorded['mtime'] = self.saved.stat().st_mtime_ns

        hooks = [(10.0, lambda: sensor.write_text('(600,0)\n')),
                 (30.0, lambda: sensor.write_text('(1,0)\n'))]
        samples = self.controlled_run(prepare, stop_at=50.0, hooks=hooks, sensor=sensor)
        saved_mtime = recorded['mtime']
        dark = [level for stamp, level in samples if stamp < 10.0]
        self.assertTrue(dark and min(dark) == 200 and max(dark) == 200)
        self.assertEqual(self.nearest(samples, 22.0), 0)
        self.assertEqual(self.nearest(samples, 29.5), 0)
        self.assertEqual(self.nearest(samples, 45.0), 200)
        steps = [abs(after[1] - before[1]) for before, after in zip(samples, samples[1:])]
        self.assertLessEqual(max(steps), 8, 'ambient changes must fade, not jump')
        self.assertEqual(int(self.saved.read_text()), 200)
        self.assertEqual(self.saved.stat().st_mtime_ns, saved_mtime)
        self.assertEqual(self.helper().status()['mode'], 'ambient')
        self.assertEqual(self.brightness(), 200)

    def pulse_samples(self, peak):
        (self.led / 'max_brightness').write_text('1000\n')
        (self.led / 'brightness').write_text(f'{peak}\n')
        now = [0.0]
        samples = []

        def advance(seconds):
            if len(samples) >= 2000:
                raise AssertionError('breathing loop did not make bounded clock progress')
            samples.append((now[0], self.brightness(),
                            (self.led / 'brightness').stat().st_mtime_ns))
            now[0] += max(float(seconds), .000001)

        class ControlledStop:
            def is_set(self):
                return now[0] >= 6.01

            def wait(self, seconds):
                advance(seconds)
                return self.is_set()

        # Load under the standard clock overrides so either time.monotonic or
        # `from time import monotonic` observes the same synthetic timeline.
        with patch('time.monotonic', side_effect=lambda: now[0]), patch('time.sleep', side_effect=advance):
            helper = load_helper()(self.led, self.state, self.runtime)
            helper.command('breathe', spawn=False)
            saved_mtime = self.saved.stat().st_mtime_ns
            self.assertIs(helper.serve(ControlledStop()), True)
        self.assertEqual(int(self.saved.read_text()), peak)
        self.assertEqual(self.saved.stat().st_mtime_ns, saved_mtime)
        self.assertEqual(self.brightness(), peak)
        return samples

    def test_breathing_uses_elapsed_six_second_cosine_without_saving_each_frame(self):
        samples = self.pulse_samples(1000)
        self.assertGreaterEqual(len(samples), 350)
        self.assertLessEqual(len(samples), 365)
        self.assertEqual(samples[0][1], 1000)
        for stamp, brightness, _mtime in samples:
            expected = 1000 * (.56 + .44 * math.cos(2 * math.pi * stamp / 6))
            self.assertAlmostEqual(brightness, expected, delta=1)
        for stamp, expected in ((1.5, 560), (3, 120), (4.5, 560), (6, 1000)):
            nearest = min(samples, key=lambda row: abs(row[0] - stamp))
            self.assertAlmostEqual(nearest[1], expected, delta=2)

    def test_quantized_pulse_skips_identical_brightness_writes(self):
        samples = self.pulse_samples(10)
        repeated = [(before, after) for before, after in zip(samples, samples[1:])
                    if before[1] == after[1]]
        self.assertGreater(len(repeated), 200)
        for before, after in repeated:
            self.assertEqual(before[2], after[2], 'the same integer LED level was rewritten')


if __name__ == '__main__':
    unittest.main()
