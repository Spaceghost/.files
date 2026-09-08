"""Warm gestures reach the owning daemon without another interpreter launch."""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

LIBRARY = Path(__file__).resolve().parents[1] / 'desktop/.local/lib/oldbook'
sys.path.insert(0, str(LIBRARY))
import showdesktop
import ui_command


class WarmHandoffTests(unittest.TestCase):
    def test_executables_deliver_gestures_with_minimal_python_startup(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtime = Path(temporary)
            sway = runtime / 'sway.sock'
            token = hashlib.sha256(str(sway).encode()).hexdigest()[:12]
            env = dict(os.environ, XDG_RUNTIME_DIR=temporary, SWAYSOCK=str(sway))
            with socket.socket(socket.AF_UNIX) as compositor:
                compositor.bind(str(sway))
                for name, arguments, address, expected in (
                    ('carousel', ['next', '--modifier', 'alt'],
                     runtime / 'oldbook' / ('carousel-' + token) / 'control.sock',
                     {'action': 'next', 'modifier': 'alt'}),
                    ('showdesktop', ['restore-or-carousel'],
                     runtime / 'oldbook' / 'showdesktop' / ('control-' + token + '.sock'),
                     b'restore-or-carousel'),
                ):
                    with self.subTest(service=name):
                        address.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as receiver:
                            receiver.bind(str(address))
                            receiver.settimeout(.5)
                            binary = LIBRARY.parent.parent / 'bin' / ('oldbook-' + name)
                            result = subprocess.run([str(binary), *arguments], env=env,
                                                    capture_output=True, timeout=5)
                            self.assertEqual(result.returncode, 0, result.stderr.decode())
                            data = receiver.recv(1024)
                            self.assertEqual(json.loads(data) if name == 'carousel' else data,
                                             expected)

    def test_showdesktop_protocol_uses_its_existing_session_socket(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtime = Path(temporary)
            sway = runtime / 'sway.sock'
            token = hashlib.sha256(str(sway).encode()).hexdigest()[:12]
            directory = runtime / 'oldbook' / 'showdesktop'
            directory.mkdir(parents=True, mode=0o700)
            with socket.socket(socket.AF_UNIX) as compositor, \
                    socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as receiver:
                compositor.bind(str(sway))
                receiver.bind(str(directory / ('control-' + token + '.sock')))
                receiver.settimeout(.5)
                with patch.dict(os.environ, XDG_RUNTIME_DIR=temporary, SWAYSOCK=str(sway)):
                    self.assertTrue(ui_command.fast_command('showdesktop', ['restore-or-carousel']))
                self.assertEqual(receiver.recv(1024), b'restore-or-carousel')

    def test_cold_or_invalid_commands_leave_recovery_to_full_cli(self):
        with patch.dict(os.environ, XDG_RUNTIME_DIR='/missing', SWAYSOCK='/missing/sway.sock'):
            for service, arguments in [('carousel', ['next', '--modifier', 'alt']),
                                       ('carousel', ['next', '--modifier', 'invalid']),
                                       ('carousel', ['--help']), ('showdesktop', ['daemon']),
                                       ('showdesktop', ['show', 'unexpected'])]:
                self.assertFalse(ui_command.fast_command(service, arguments))

    def test_down_swipe_reaches_ready_carousel_without_spawning(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtime = Path(temporary)
            sway = runtime / 'sway.sock'
            token = hashlib.sha256(str(sway).encode()).hexdigest()[:12]
            directory = runtime / 'oldbook' / ('carousel-' + token)
            directory.mkdir(parents=True, mode=0o700)
            with socket.socket(socket.AF_UNIX) as compositor, \
                    socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as carousel:
                compositor.bind(str(sway))
                carousel.bind(str(directory / 'control.sock'))
                carousel.settimeout(.5)
                with patch.dict(os.environ, XDG_RUNTIME_DIR=temporary, SWAYSOCK=str(sway)), \
                        patch.object(showdesktop.subprocess, 'Popen',
                                     side_effect=AssertionError('warm swipe launched a process')):
                    showdesktop.launch_carousel()
                self.assertEqual(json.loads(carousel.recv(1024)),
                                 {'action': 'show', 'modifier': None})


if __name__ == '__main__':
    unittest.main()
