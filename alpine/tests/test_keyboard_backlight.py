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


HELPER = Path(__file__).resolve().parents[1] / 'desktop/.local/bin/mbp-intel-keyboard-backlight'


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
