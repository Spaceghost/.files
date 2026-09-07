"""Behavior tests for the read-only contextual-shortcut hold detector."""
from pathlib import Path
import errno
from hold_to_help import hold
import struct
import unittest


MODULE = Path(hold.__file__)
EVENT = struct.Struct('@llHHi')


def packet(event_type, code, value):
    return EVENT.pack(0, 0, event_type, code, value)


def bitmap(*codes):
    result = bytearray(max(codes, default=0) // 8 + 1)
    for code in codes:
        result[code // 8] |= 1 << (code % 8)
    return bytes(result)


class FakeBackend:
    """A deterministic boundary double for Linux input syscalls."""

    def __init__(self):
        self.paths = []
        self.fds = {}
        self.capabilities = {}
        self.down = {}
        self.ioctl_errors = {}
        self.reads = {}
        self.closed = []
        self.read_sizes = []
        self.read_fds = []

    def list_devices(self, _directory):
        return list(self.paths)

    def open(self, path):
        value = self.fds.get(path)
        if isinstance(value, BaseException):
            raise value
        return value

    def close(self, fd):
        self.closed.append(fd)

    def read(self, fd, size):
        self.read_sizes.append(size)
        self.read_fds.append(fd)
        queued = self.reads.setdefault(fd, [])
        if not queued:
            raise BlockingIOError(errno.EAGAIN, 'empty')
        data = queued.pop(0)
        if len(data) > size:
            queued.insert(0, data[size:])
            data = data[:size]
        return data

    def ioctl(self, fd, request, target):
        operation = request & 0xff
        error = self.ioctl_errors.get((fd, operation))
        if error is not None:
            raise error
        if operation == 0x20:
            source = bitmap(1)
        elif operation == 0x21:
            source = bitmap(*self.capabilities.get(fd, ()))
        elif operation == 0x18:
            source = bitmap(*self.down.get(fd, ()))
        else:
            raise AssertionError(f'unexpected ioctl operation {operation:#x}')
        target[:min(len(source), len(target))] = source[:len(target)]
        return 0


class HoldStateTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(MODULE.exists(), 'shortcut hold implementation is missing')
        self.module = vars(hold)
        self.state = self.module['HoldState']()

    def test_lone_super_appears_at_exact_threshold_and_release_hides_it(self):
        self.state.update('kbd', 125, 1, 0.0)
        self.assertFalse(self.state.visible(0.499))
        self.assertTrue(self.state.visible(0.5))
        self.state.update('kbd', 125, 0, 0.6)
        self.assertFalse(self.state.visible(0.6))

    def test_quick_tap_never_appears_later(self):
        self.state.update('kbd', 126, 1, 1.0)
        self.state.update('kbd', 126, 0, 1.2)
        self.assertFalse(self.state.visible(2.0))

    def test_chord_cancels_until_super_is_released(self):
        self.state.update('kbd', 125, 1, 0.0)
        self.state.update('kbd', 30, 1, 0.2)
        self.state.update('kbd', 30, 0, 0.3)
        self.assertFalse(self.state.visible(1.0))
        self.state.update('kbd', 125, 0, 1.1)
        self.state.update('kbd', 125, 1, 2.0)
        self.assertTrue(self.state.visible(2.5))

    def test_chord_after_threshold_hides_immediately_and_stays_hidden(self):
        self.state.update('kbd', 125, 1, 0.0)
        self.assertTrue(self.state.visible(0.5))
        self.state.update('kbd', 29, 1, 0.6)
        self.assertFalse(self.state.visible(0.6))
        self.state.update('kbd', 29, 0, 0.7)
        self.assertFalse(self.state.visible(1.2))

    def test_super_pressed_while_another_key_is_down_is_suppressed(self):
        self.state.update('kbd', 30, 1, 0.0)
        self.state.update('kbd', 125, 1, 0.1)
        self.state.update('kbd', 30, 0, 0.2)
        self.assertFalse(self.state.visible(1.0))
        self.state.update('kbd', 125, 0, 1.1)
        self.state.update('kbd', 126, 1, 2.0)
        self.assertTrue(self.state.visible(2.5))

    def test_repeat_events_do_not_cancel_or_restart_the_timer(self):
        self.state.update('kbd', 125, 1, 0.0)
        self.state.update('kbd', 30, 2, 0.2)
        self.state.update('kbd', 125, 2, 0.4)
        self.assertTrue(self.state.visible(0.5))

    def test_keys_on_multiple_keyboards_form_one_global_chord(self):
        self.state.update('built-in', 125, 1, 0.0)
        self.state.update('usb', 30, 1, 0.2)
        self.state.update('usb', 30, 0, 0.3)
        self.assertFalse(self.state.visible(0.8))

    def test_two_super_keys_are_conservatively_suppressed(self):
        self.state.update('built-in', 125, 1, 0.0)
        self.state.update('usb', 126, 1, 0.1)
        self.state.update('usb', 126, 0, 0.2)
        self.assertFalse(self.state.visible(1.0))
        self.state.update('built-in', 125, 0, 1.1)
        self.state.update('usb', 126, 1, 2.0)
        self.assertTrue(self.state.visible(2.5))

    def test_cancel_and_device_removal_require_a_fresh_press(self):
        self.state.update('built-in', 125, 1, 0.0)
        self.state.cancel()
        self.assertFalse(self.state.visible(1.0))
        self.state.remove_device('built-in')
        self.state.update('usb', 125, 1, 2.0)
        self.assertTrue(self.state.visible(2.5))


class EvdevMonitorTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(MODULE.exists(), 'shortcut hold implementation is missing')
        self.module = vars(hold)
        self.backend = FakeBackend()

    def add_device(self, path='/dev/input/event1', fd=11, capabilities=(30, 57, 125)):
        self.backend.paths.append(path)
        self.backend.fds[path] = fd
        self.backend.capabilities[fd] = capabilities
        return fd

    def monitor(self, **kwargs):
        return self.module['EvdevMonitor'](
            backend=self.backend, scan_interval=0, **kwargs)

    def test_discovers_keyboards_without_treating_a_mouse_as_one(self):
        self.add_device('/dev/input/event1', 11, (272, 273, 274))
        self.add_device('/dev/input/event2', 12, (30, 57, 125))
        self.add_device('/dev/input/event3', 13, (30, 57))
        monitor = self.monitor()
        self.assertFalse(monitor.poll(0.0))
        self.assertEqual(monitor.device_count, 2)
        self.assertEqual(self.backend.closed, [11])

    def test_key_on_a_non_super_keyboard_cancels_another_keyboard_hold(self):
        super_fd = self.add_device('/dev/input/event1', 11, (30, 57, 125))
        plain_fd = self.add_device('/dev/input/event2', 12, (30, 57))
        monitor = self.monitor()
        monitor.poll(0.0)
        self.backend.reads[super_fd] = [packet(1, 125, 1)]
        monitor.poll(0.1)
        self.backend.reads[plain_fd] = [packet(1, 30, 1)]
        self.assertFalse(monitor.poll(0.6))

    def test_initial_down_state_cannot_trigger_a_delayed_overlay(self):
        fd = self.add_device()
        self.backend.down[fd] = (125,)
        monitor = self.monitor()
        monitor.poll(0.0)
        self.assertFalse(monitor.poll(1.0))
        self.backend.reads[fd] = [packet(1, 125, 0), packet(1, 125, 1)]
        monitor.poll(1.1)
        self.assertTrue(monitor.poll(1.6))

    def test_poll_parses_key_packets_and_returns_visibility(self):
        fd = self.add_device()
        monitor = self.monitor()
        monitor.poll(0.0)
        self.backend.reads[fd] = [packet(1, 125, 1)]
        self.assertFalse(monitor.poll(1.0))
        self.assertTrue(monitor.poll(1.5))
        self.backend.reads[fd] = [packet(1, 30, 1)]
        self.assertFalse(monitor.poll(1.6))

    def test_exposed_state_can_cancel_visibility_for_session_gating(self):
        fd = self.add_device()
        monitor = self.monitor()
        monitor.poll(0.0)
        self.backend.reads[fd] = [packet(1, 125, 1)]
        monitor.poll(0.1)
        self.assertTrue(monitor.poll(0.6))
        monitor.state.cancel()
        self.assertFalse(monitor.poll(0.7))

    def test_syn_dropped_cancels_and_resynchronizes_without_a_flash(self):
        fd = self.add_device()
        monitor = self.monitor()
        monitor.poll(0.0)
        self.backend.reads[fd] = [packet(1, 125, 1)]
        monitor.poll(0.1)
        self.assertTrue(monitor.poll(0.6))
        self.backend.down[fd] = (125,)
        self.backend.reads[fd] = [
            packet(0, 3, 0) + packet(1, 30, 1) + packet(0, 0, 0)]
        self.assertFalse(monitor.poll(0.7))
        self.assertFalse(monitor.poll(2.0))
        self.backend.reads[fd] = [packet(1, 125, 0) + packet(1, 125, 1)]
        monitor.poll(2.1)
        self.assertTrue(monitor.poll(2.6))

    def test_disconnect_during_drop_resync_ignores_remaining_packet_bytes(self):
        fd = self.add_device()
        monitor = self.monitor()
        monitor.poll(0.0)
        self.backend.ioctl_errors[(fd, 0x18)] = OSError(errno.ENODEV, 'gone')
        self.backend.reads[fd] = [
            packet(0, 3, 0) + packet(0, 0, 0) + packet(1, 125, 1)]
        self.assertFalse(monitor.poll(0.1))
        self.assertFalse(monitor.poll(1.0))
        self.assertEqual(monitor.device_count, 0)

    def test_disconnect_removes_pressed_state_and_closes_device(self):
        fd = self.add_device()
        monitor = self.monitor()
        monitor.poll(0.0)
        self.backend.reads[fd] = [packet(1, 125, 1)]
        monitor.poll(0.1)
        self.backend.paths.clear()
        self.assertFalse(monitor.poll(0.7))
        self.assertEqual(monitor.device_count, 0)
        self.assertEqual(self.backend.closed, [fd])

    def test_unreadable_and_disconnected_devices_do_not_break_polling(self):
        self.backend.paths.extend(['/dev/input/event1', '/dev/input/event2'])
        self.backend.fds['/dev/input/event1'] = PermissionError(errno.EACCES, 'denied')
        self.backend.fds['/dev/input/event2'] = 12
        self.backend.capabilities[12] = (30, 57, 125)
        monitor = self.monitor()
        monitor.poll(0.0)
        self.backend.reads[12] = [OSError(errno.ENODEV, 'gone')]
        original_read = self.backend.read

        def read(fd, size):
            value = self.backend.reads.get(fd, [None])[0]
            if isinstance(value, BaseException):
                self.backend.reads[fd].pop(0)
                raise value
            return original_read(fd, size)

        self.backend.read = read
        self.assertFalse(monitor.poll(0.1))
        self.assertEqual(monitor.device_count, 0)
        self.assertEqual(self.backend.closed, [12])

    def test_each_poll_has_an_explicit_event_budget(self):
        fd = self.add_device()
        monitor = self.monitor(max_events_per_poll=4)
        monitor.poll(0.0)
        self.backend.reads[fd] = [packet(1, 125, 2) * 20]
        monitor.poll(0.1)
        self.assertEqual(self.backend.read_sizes[-1], EVENT.size * 4)

    def test_budget_exhaustion_cancels_and_next_poll_visits_waiting_keyboard(self):
        super_fd = self.add_device('/dev/input/event1', 11, (30, 57, 125))
        plain_fd = self.add_device('/dev/input/event2', 12, (30, 57))
        monitor = self.monitor(max_events_per_poll=4)
        monitor.poll(0.0)
        self.backend.reads[super_fd] = [packet(1, 125, 1)]
        monitor.poll(0.1)
        self.assertTrue(monitor.state.visible(0.6))

        self.backend.reads[super_fd] = [packet(1, 125, 2) * 8]
        self.backend.reads[plain_fd] = [packet(1, 30, 1)]
        self.assertFalse(monitor.poll(0.7))
        read_index = len(self.backend.read_fds)
        monitor.poll(0.8)
        self.assertEqual(self.backend.read_fds[read_index], plain_fd)
        self.assertEqual(self.backend.reads[plain_fd], [])

    def test_close_is_idempotent_and_clears_all_devices(self):
        fd = self.add_device()
        monitor = self.monitor()
        monitor.poll(0.0)
        monitor.close()
        monitor.close()
        self.assertEqual(monitor.device_count, 0)
        self.assertEqual(self.backend.closed, [fd])


if __name__ == '__main__':
    unittest.main()
