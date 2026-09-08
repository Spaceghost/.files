"""oldbook-wallpaper prefers the crossfade daemon and keeps Sway's bg as the fallback."""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'alpine/desktop/.local/lib/oldbook'))
import background_fade as fade  # noqa: E402


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


art = load('crossfade_wallpapers', REPO / 'alpine/desktop/.local/bin/oldbook-wallpaper')


class GalleryIntegration(unittest.TestCase):
    def apply_with(self, reply):
        entry = {'path': '/paintings/next.png'}
        with tempfile.TemporaryDirectory(prefix='gallery-apply-') as directory:
            current = Path(directory) / 'current-wallpaper.png'
            commands = []

            def run(command, **_kwargs):
                commands.append(command)
                return mock.Mock(returncode=0, stdout='[{"success": true}]')
            with mock.patch.object(art.fade, 'crossfade', return_value=reply) as crossfade, \
                    mock.patch.object(art.subprocess, 'run', side_effect=run), \
                    mock.patch.object(art, 'CURRENT', current), \
                    mock.patch.object(art, 'sway_socket', return_value='/owned/socket'), \
                    mock.patch.object(art, 'relayout_panels'):
                result = art.apply(entry, origin=(5, 6), duration=1600)
            self.assertEqual(result, '/owned/socket')
            self.assertEqual(os.readlink(current), '/paintings/next.png')
            return crossfade.call_args, commands

    def test_daemon_acknowledgement_skips_the_sway_background_command(self):
        call, commands = self.apply_with({'ok': True, 'state': 'accepted'})
        self.assertEqual(call.args[:3], ('/paintings/next.png', 1600, (5, 6)))
        self.assertEqual(commands, [])

    def test_missing_daemon_falls_back_to_sway(self):
        _, commands = self.apply_with(None)
        self.assertEqual(commands, [['swaymsg', '-s', '/owned/socket', '-r',
                                     'output * bg "/paintings/next.png" fill']])

    def test_refused_fade_falls_back_to_sway(self):
        _, commands = self.apply_with({'ok': False, 'state': 'error', 'error': 'no'})
        self.assertEqual(len(commands), 1)

    def test_rotation_ticks_fade_slowly_and_manual_changes_quickly(self):
        self.assertGreater(fade.ROTATION_DURATION_MS, fade.DEFAULT_DURATION_MS)
        self.assertEqual(art.fade_duration('tick'), fade.ROTATION_DURATION_MS)
        self.assertIsNone(art.fade_duration('next'))

    def test_reveal_origin_is_only_for_image_changes(self):
        with mock.patch.object(sys, 'argv', ['oldbook-wallpaper', 'pause', '--from', '1,2']), \
                self.assertRaises(SystemExit):
            art.main()


if __name__ == '__main__':
    unittest.main()
