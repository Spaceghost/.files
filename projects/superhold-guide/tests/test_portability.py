"""Desktop portability contracts, without opening host input or a display."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from superhold.shortcut_overlay import _default_graphical_probe
from superhold.shortcut_sources import ShortcutProvider


class PortabilityTests(unittest.TestCase):
    def test_xdg_profile_is_loaded_without_reading_mbp_intel_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)
            (config / 'superhold').mkdir()
            (config / 'superhold/shortcuts.json').write_text(json.dumps({
                'profiles': {'testapp': {'name': 'Test application',
                    'aliases': ['test.app'], 'coverage': 'Partial local profile',
                    'rows': [{'key': 'Ctrl+S', 'description': 'Save'}]}}
            }))
            with mock.patch.dict(os.environ, {'XDG_CONFIG_HOME': directory}):
                profiles, error = ShortcutProvider('/unused')._load_custom_profiles()
            self.assertIsNone(error)
            self.assertIn('testapp', profiles)

    def test_relative_xdg_config_home_falls_back_to_home(self):
        with mock.patch.dict(os.environ, {'XDG_CONFIG_HOME': 'relative'}):
            provider = ShortcutProvider('/unused')
        self.assertEqual(provider.profiles_path,
                         Path.home() / '.config/superhold/shortcuts.json')

    def test_logind_locked_hint_suppresses_otherwise_active_wayland_session(self):
        with tempfile.TemporaryDirectory() as directory:
            endpoint = Path(directory) / 'wayland-test'
            with socket.socket(socket.AF_UNIX) as server:
                server.bind(str(endpoint))
                response = subprocess.CompletedProcess(
                    ['loginctl'], 0,
                    'Active=yes\nState=active\nType=wayland\nLockedHint=yes\n', '')
                with mock.patch.dict(os.environ, {'XDG_SESSION_ID': 'test'}), \
                        mock.patch('superhold.shortcut_overlay.subprocess.run',
                                   return_value=response):
                    self.assertFalse(_default_graphical_probe(Path(directory), endpoint))

    def test_version_command_works_without_graphical_session(self):
        environment = dict(os.environ)
        for name in ('XDG_RUNTIME_DIR', 'WAYLAND_DISPLAY', 'SWAYSOCK'):
            environment.pop(name, None)
        result = subprocess.run([str(ROOT / 'bin/superhold'), '--version'],
                                env=environment, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith('superhold '))


if __name__ == '__main__':
    unittest.main()
