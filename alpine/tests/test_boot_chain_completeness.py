"""A theme switch must carry the palette to GRUB and the boot console itself.

Before this, refresh_boot_palette() only regenerated the console palette file
and printed a reminder telling a human to run build-grub-theme and doas
install-boot-console by hand afterward. It never ran them. Gruvbox-dark looked
complete at the GRUB menu only because someone once ran that reminder by hand
for it; every other theme's switch left the real boot chain on whatever was
last installed, regardless of what the desktop showed. A theme is not allowed
to count as complete while any themeable surface still needs an unenforced
follow-up command.
"""
import json
from pathlib import Path
import runpy
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[2]


class BootChainCompleteness(unittest.TestCase):
    def setUp(self):
        self.namespace = runpy.run_path(
            str(REPO / 'alpine/desktop/.local/bin/oldbook-theme'))

    def test_every_theme_actually_runs_the_grub_render_and_the_root_install(self):
        globals_ = self.namespace['refresh_boot_palette'].__globals__

        def fake_console_palette_module(_path):
            return {'build': lambda repo, identity: (Path('console-palette.json'), True, {})}

        for source in sorted((REPO / 'alpine/themes').glob('*.json')):
            theme = json.loads(source.read_text())
            with self.subTest(theme=theme['id']):
                calls = []

                def fake_run_boot_step(command, timeout, _calls=calls):
                    _calls.append(command)
                    return True, ''

                with mock.patch.dict(globals_, {'run_boot_step': fake_run_boot_step}), \
                        mock.patch('runpy.run_path', side_effect=fake_console_palette_module):
                    notes = self.namespace['refresh_boot_palette'](theme)

                scripts = [Path(command[-1]).name for command in calls]
                self.assertIn('build-grub-theme', scripts,
                              'a theme switch must render the GRUB theme itself, '
                              'not leave it for a human to run')
                self.assertIn('install-boot-console', scripts,
                              'a theme switch must install the boot console itself, '
                              'not just print a reminder to run it')
                install_command = next(c for c in calls
                                       if Path(c[-1]).name == 'install-boot-console')
                self.assertIn('doas', install_command,
                              'installing the boot console needs root')
                self.assertFalse(
                    any('run alpine/bin/build-grub-theme' in note for note in notes),
                    'must not fall back to a printed manual reminder: ' + repr(notes))

    def test_a_grub_render_failure_stops_before_installing_a_theme_it_never_built(self):
        globals_ = self.namespace['refresh_boot_palette'].__globals__
        theme = json.loads((REPO / 'alpine/themes/gruvbox-dark.json').read_text())
        calls = []

        def fake_console_palette_module(_path):
            return {'build': lambda repo, identity: (Path('console-palette.json'), True, {})}

        def failing_run_boot_step(command, timeout, _calls=calls):
            _calls.append(command)
            return False, 'a real GLSL-style compiler error, not a generic failure'

        with mock.patch.dict(globals_, {'run_boot_step': failing_run_boot_step}), \
                mock.patch('runpy.run_path', side_effect=fake_console_palette_module):
            notes = self.namespace['refresh_boot_palette'](theme)

        self.assertEqual(len(calls), 1, 'install-boot-console must not run after a failed render')
        self.assertTrue(any('GRUB theme render FAILED' in note
                            and 'a real GLSL-style compiler error' in note for note in notes),
                        'the failure note must carry the real cause: ' + repr(notes))


if __name__ == '__main__':
    unittest.main()
