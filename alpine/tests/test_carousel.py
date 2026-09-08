"""Controller boundaries: IPC framing, private previews and stale captures."""
import concurrent.futures
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'desktop/.local/lib/oldbook'))
from carousel import Controller, EventFrames, PreviewStore, decode_preview, runtime_directory
from window_switching import SwitchState


class DeferredExecutor:
    def __init__(self):
        self.calls = []

    def submit(self, function, candidate):
        future = concurrent.futures.Future()
        future.set_running_or_notify_cancel()
        self.calls.append((function, candidate, future))
        return future


class CarouselTests(unittest.TestCase):
    def test_ipc_handles_partial_and_coalesced_frames(self):
        reader = EventFrames()
        payload = b'{"change":"focus"}'
        packet = struct.pack('=6sII', b'i3-ipc', len(payload), 0x80000003) + payload
        self.assertEqual(reader.feed(packet[:9]), [])
        self.assertEqual(reader.feed(packet[9:] + packet), [
            (0x80000003, {'change': 'focus'}), (0x80000003, {'change': 'focus'})])

    def test_ipc_rejects_corrupt_or_oversized_frames(self):
        for magic, length in ((b'broken', 2), (b'i3-ipc', 40 * 1024 * 1024)):
            with self.assertRaises(ValueError):
                EventFrames().feed(struct.pack('=6sII', magic, length, 3))

    def test_preview_decodes_exact_pixel_bytes(self):
        pixels = b'\x00\x20\xff' * 6
        self.assertEqual(decode_preview(b'P6\n3 2\n255\n' + pixels), (3, 2, pixels))

    def test_preview_rejects_truncated_and_excessive_sizes(self):
        for data in (b'P6\n2 2\n255\nabc', b'P6\n10000 10000\n255\n'):
            with self.assertRaises(ValueError):
                decode_preview(data)

    def test_runtime_is_scoped_to_compositor(self):
        first = runtime_directory(Path('/run/user/1000'), '/one.sock')
        self.assertNotEqual(first, runtime_directory(Path('/run/user/1000'), '/two.sock'))
        self.assertEqual(first.parent, Path('/run/user/1000/oldbook'))

    def test_closed_gesture_discards_late_capture(self):
        executor = DeferredExecutor()
        received = []
        store = PreviewStore(executor, lambda callback: callback(), lambda *args: received.append(args))
        candidate = {'id': 9, 'pid': 100, 'app_id': 'fixture',
                     'foreign_toplevel_identifier': 'private-window'}
        store.request([candidate])
        store.clear()
        executor.calls[0][2].set_result((1, 1, b'abc'))
        self.assertEqual(received, [])
        self.assertEqual(store.ready, set())

    def test_capture_failure_has_no_foreground_screenshot_fallback(self):
        from carousel import capture_preview
        with patch('carousel.subprocess.run', side_effect=FileNotFoundError) as run:
            self.assertIsNone(capture_preview({'foreign_toplevel_identifier': 'exact-window'}))
        self.assertEqual(run.call_count, 1)
        self.assertIn('exact-window', run.call_args.args[0])
        self.assertIn('-T', run.call_args.args[0])

    def test_each_identity_captured_once_and_reuse_is_distinct(self):
        executor = DeferredExecutor()
        received = []
        store = PreviewStore(executor, lambda callback: callback(), lambda *args: received.append(args))
        first = {'id': 9, 'pid': 100, 'app_id': 'one', 'foreign_toplevel_identifier': 'one'}
        second = dict(first, pid=101, foreign_toplevel_identifier='two')
        store.request([first, first, second])
        self.assertEqual(len(executor.calls), 2)
        executor.calls[1][2].set_result((1, 1, b'abc'))
        self.assertEqual(received, [(second, 1, 1, b'abc')])

    def test_mode_takeover_prevents_late_modifier_commit(self):
        controller = Controller.__new__(Controller)
        controller.popup = object()
        controller.ipc = {'request': lambda *_args: {'name': 'default'}}
        controller.sway = '/fixture.sock'
        controller.dismiss = Mock()
        controller.command = Mock()
        controller.candidates = Mock()
        controller.action('commit')
        controller.dismiss.assert_called_once_with()
        controller.command.assert_not_called()
        controller.candidates.assert_not_called()

    def test_commit_dismisses_before_focus_and_records_selected_window(self):
        live = [{'id': 7, 'pid': 10, 'app_id': 'fixture', 'focused': True}]
        controller = Controller.__new__(Controller)
        controller.popup = object()
        controller.state = SwitchState(live)
        controller.sway = '/fixture.sock'
        controller.ipc = {'request': lambda *_args: {'name': 'window-switcher'}}
        controller.candidates = lambda: live
        operations = []
        controller.dismiss = lambda: operations.append('dismiss')
        controller.command = operations.append
        controller.history = Mock()
        controller.action('commit')
        self.assertEqual(operations, ['dismiss', '[con_id=7] focus'])
        controller.history.record.assert_called_once_with(live, 7)


if __name__ == '__main__':
    unittest.main()
