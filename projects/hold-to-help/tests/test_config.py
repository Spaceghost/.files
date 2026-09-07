"""Configuration and display-free CLI boundary tests."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from hold_to_help.cli import parse_args, select_backend
from hold_to_help.config import Config, default_profiles_path, load_config
from hold_to_help.hold import HoldState, KEY_CAPSLOCK, KEY_LEFTMETA


class ConfigurationTests(unittest.TestCase):
    def test_defaults_and_explicit_xdg_configuration_overrides(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
                os.environ, {'XDG_CONFIG_HOME': directory}):
            self.assertEqual(load_config(), Config())
            path = Path(directory) / 'hold-to-help/config.toml'
            path.parent.mkdir()
            path.write_text("trigger='capslock'\nhold_seconds=0.25\nbackend='x11'\n")
            self.assertEqual(load_config(), Config('capslock', .25, 'x11'))
            self.assertEqual(load_config(trigger='super').trigger, 'super')
            self.assertEqual(default_profiles_path(), path.with_name('profiles.json'))

    def test_rejects_unknown_names_types_and_nonfinite_or_out_of_range_durations(self):
        for duration in (True, False, '0.5', None, float('nan'), float('inf'), -.5, .149, 3.01):
            with self.subTest(duration=duration), self.assertRaises(ValueError):
                Config(hold_seconds=duration)
        for options in ({'trigger': 'hyper'}, {'backend': 'wayland'}, {'backend': None}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                Config(**options)
        self.assertEqual(Config(hold_seconds=.15).hold_seconds, .15)
        self.assertEqual(Config(hold_seconds=3).hold_seconds, 3)

    def test_invalid_explicit_files_and_unknown_toml_fields_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.toml'
            with self.assertRaises(ValueError):
                load_config(path)
            for content in ("unknown=1", "trigger=[]", "hold_seconds=nan", "[broken", "a" * 65537):
                path.write_text(content)
                with self.subTest(content=content[:20]), self.assertRaises(ValueError):
                    load_config(path)

    def test_fifo_config_is_rejected_without_waiting_for_a_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.toml'
            os.mkfifo(path)
            started = time.monotonic()
            with self.assertRaisesRegex(ValueError, 'regular file'):
                load_config(path)
            self.assertLess(time.monotonic() - started, .1)

    def test_capslock_uses_pressed_key_not_toggle_state_and_preserves_chord_cancel(self):
        state = HoldState('capslock', .2)
        state.update('keyboard', KEY_CAPSLOCK, 1, 1)
        self.assertFalse(state.visible(1.19))
        self.assertTrue(state.visible(1.21))
        state.update('keyboard', KEY_LEFTMETA, 1, 1.22)
        self.assertFalse(state.visible(1.22))
        state.update('keyboard', KEY_LEFTMETA, 0, 1.23)
        self.assertFalse(state.visible(2))
        state.update('keyboard', KEY_CAPSLOCK, 0, 2)
        self.assertFalse(state.visible(3))
        state.update('keyboard', KEY_CAPSLOCK, 1, 3)
        self.assertTrue(state.visible(3.21))

    def test_help_and_version_require_no_display_or_optional_toolkit(self):
        env = {key: value for key, value in os.environ.items()
               if key not in {'DISPLAY', 'WAYLAND_DISPLAY', 'SWAYSOCK', 'XDG_RUNTIME_DIR'}}
        env['PYTHONPATH'] = str(Path(__file__).resolve().parents[1])
        for argument in ('--help', '--version'):
            result = subprocess.run([sys.executable, '-m', 'hold_to_help', argument],
                                    env=env, capture_output=True, text=True, timeout=3)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('Hold to Help', result.stdout)
        result = subprocess.run([sys.executable, '-c',
            'import sys; import hold_to_help.cli; '
            'assert not any(x in sys.modules for x in ("PyQt6", "Xlib", "gi"))'],
            env=env, capture_output=True, text=True, timeout=3)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_cli_rejects_nonfinite_preview_and_bad_hold_threshold(self):
        for options in (['preview', '--seconds', 'nan'], ['preview', '--seconds', 'inf'],
                        ['daemon', '--hold-seconds', '.1'], ['daemon', '--preview']):
            with mock.patch('sys.stderr'), self.subTest(options=options), self.assertRaises(SystemExit):
                parse_args(options)

    def test_auto_backend_does_not_silently_claim_other_wayland_desktops(self):
        self.assertEqual(select_backend('auto', environ={'SWAYSOCK': '/sway'}), 'sway')
        self.assertEqual(select_backend('auto', environ={'DISPLAY': ':1'}), 'x11')
        with self.assertRaises(RuntimeError):
            select_backend('auto', environ={'WAYLAND_DISPLAY': 'wayland-0', 'DISPLAY': ':0'})
        with self.assertRaises(ValueError):
            select_backend('x11', socket_path='/sway')


if __name__ == '__main__':
    unittest.main()
