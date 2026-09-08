"""Theme reload waits for Sway's command reply without repeating the command."""
from contextlib import contextmanager, redirect_stdout
import io
import json
import os
from pathlib import Path
import runpy
import socket
import struct
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[2]
HEADER = struct.Struct('=6sII')


class ThemeSwayReloadTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='theme-sway-reload-')
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'sway.sock'
        self.module = runpy.run_path(str(REPO / 'alpine/desktop/.local/bin/mbp-intel-theme'))
        self.enterContext(mock.patch.dict(os.environ, {'SWAYSOCK': str(self.path)}))
        self.requests = []
        self.errors = []

    @contextmanager
    def server(self, reply=None, delay=0, magic=b'i3-ipc', kind=0,
               truncate=False, byte_delay=0):
        payload = json.dumps([{'success': True}] if reply is None else reply).encode()
        frame = HEADER.pack(magic, len(payload), kind) + payload
        if truncate:
            frame = frame[:-3]
        with socket.socket(socket.AF_UNIX) as listener:
            listener.bind(str(self.path))
            listener.listen(1)
            listener.settimeout(5)

            def respond():
                try:
                    connection, _ = listener.accept()
                    with connection:
                        connection.settimeout(5)

                        def read(size):
                            result = b''
                            while len(result) < size:
                                part = connection.recv(size - len(result))
                                if not part:
                                    raise AssertionError('Client truncated its reload command')
                                result += part
                            return result

                        received_magic, size, received_kind = HEADER.unpack(read(HEADER.size))
                        self.requests.append((received_magic, received_kind, read(size)))
                        if delay:
                            time.sleep(delay)
                        if byte_delay:
                            for byte in frame:
                                time.sleep(byte_delay)
                                connection.sendall(bytes([byte]))
                        else:
                            connection.sendall(frame)
                except BrokenPipeError:
                    pass  # Expected when exercising client timeout or rejection.
                except Exception as error:
                    self.errors.append(error)

            thread = threading.Thread(target=respond, daemon=True)
            thread.start()
            try:
                yield
            finally:
                thread.join(timeout=6)
                self.assertFalse(thread.is_alive(), 'Private IPC server did not finish')
                self.assertEqual(self.errors, [])

    def reload(self, **kwargs):
        callback = self.module.get('sway_reload')
        self.assertTrue(callable(callback), 'Theme reload needs a direct IPC response boundary')
        return callback(**kwargs)

    def test_refresh_accepts_a_reply_after_swaymsgs_three_second_limit(self):
        refresh = self.module['refresh_session']
        original_run = self.module['run']

        def only_sway(command, timeout=20):
            return original_run(command, timeout) if command[0] == 'swaymsg' else True

        with self.server(delay=3.15), mock.patch.dict(refresh.__globals__, {
                'run': only_sway, 'owned_processes': lambda *args: iter([]),
                'signal_processes': lambda *args: 0, 'tmux_reload': lambda: 0}):
            notes = refresh()
        self.assertFalse(any('FAILED' in note for note in notes), notes)
        self.assertEqual(self.requests, [(b'i3-ipc', 0, b'reload')])

    def test_rejected_command_retains_the_compositor_error(self):
        self.assertTrue(callable(self.module.get('sway_reload')))
        with self.server(reply=[{'success': False, 'error': 'Unknown option: fixture'}]):
            with self.assertRaisesRegex(RuntimeError, 'Unknown option: fixture'):
                self.reload()

    def test_refresh_cli_exits_unsuccessfully_when_sway_rejects_reload(self):
        original_run = self.module['run']

        def only_sway(command, timeout=20):
            return original_run(command, timeout) if command[0] == 'swaymsg' else True

        with self.server(reply=[{'success': False, 'error': 'Rejected fixture reload'}]), \
                mock.patch.dict(self.module['refresh_session'].__globals__, {
                    'run': only_sway, 'owned_processes': lambda *args: iter([]),
                    'signal_processes': lambda *args: 0, 'tmux_reload': lambda: 0}), \
                mock.patch.object(sys, 'argv', ['mbp-intel-theme', 'refresh']), \
                redirect_stdout(io.StringIO()):
            status = self.module['main']()
        self.assertEqual(status, 1)

    def test_wrong_frame_magic_or_reply_type_is_rejected(self):
        self.assertTrue(callable(self.module.get('sway_reload')))
        for fields in ({'magic': b'broken'}, {'kind': 4}):
            with self.subTest(fields=fields):
                self.path.unlink(missing_ok=True)
                with self.server(**fields), self.assertRaisesRegex(ValueError, 'IPC'):
                    self.reload()

    def test_truncated_reply_reports_disconnection(self):
        self.assertTrue(callable(self.module.get('sway_reload')))
        with self.server(truncate=True), self.assertRaisesRegex(ConnectionError, 'disconnected'):
            self.reload()

    def test_response_must_contain_boolean_command_success(self):
        self.assertTrue(callable(self.module.get('sway_reload')))
        for reply in ([], {'success': True}, [{'success': 'true'}], [True]):
            with self.subTest(reply=reply):
                self.path.unlink(missing_ok=True)
                with self.server(reply=reply), self.assertRaises((RuntimeError, ValueError)):
                    self.reload()

    def test_missing_session_never_discovers_another_compositor(self):
        with mock.patch.dict(os.environ, {'HOME': self.directory.name}, clear=True), \
                self.assertRaisesRegex(RuntimeError, 'SWAYSOCK'):
            self.reload()

    def test_fragmented_reply_cannot_extend_the_total_deadline(self):
        self.assertTrue(callable(self.module.get('sway_reload')))
        with self.server(byte_delay=.04):
            start = time.monotonic()
            with self.assertRaisesRegex(RuntimeError, 'confirmed'):
                self.reload(timeout=.12)
            self.assertLess(time.monotonic() - start, .8)


if __name__ == '__main__':
    unittest.main()
