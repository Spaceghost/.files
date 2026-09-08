"""Theme application reports partial failures and still refreshes deployed styling."""
import contextlib
import io
from pathlib import Path
import runpy
import shutil
import sys
import tempfile
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[2]


class ThemeRefreshTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='theme-refresh-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'repo'
        self.home = Path(self.temporary.name) / 'home'
        self.home.mkdir()
        for relative in ('alpine/desktop', 'alpine/themes/profiles/gruvbox-dark',
                         'alpine/wallpapers'):
            shutil.copytree(REPO / relative, self.root / relative,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*-original*'))
        for relative in ('alpine/themes/gruvbox-dark.json', 'alpine/bin/deploy-home'):
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / relative, target)
        self.namespace = runpy.run_path(str(self.root / 'alpine/desktop/.local/bin/oldbook-theme'))
        self.globals = self.namespace['use'].__globals__
        self.enterContext(mock.patch.object(Path, 'home', return_value=self.home))

    def test_wallpaper_failure_still_refreshes_deployed_application_theme(self):
        real_run_path = runpy.run_path
        refreshed = []

        def load(path):
            if str(path).endswith('/oldbook-wallpaper'):
                return {'load_gallery': lambda: ([{'theme': 'gruvbox-dark', 'id': 'painting'}], 60),
                        'update': lambda *args: (_ for _ in ()).throw(RuntimeError('display unavailable'))}
            return real_run_path(path)

        def refresh():
            refreshed.append((self.home / '.config/foot/foot.ini').read_text())
            return ['sway reloaded']

        with mock.patch.object(runpy, 'run_path', side_effect=load), \
                mock.patch.dict(self.globals, refresh_session=refresh):
            try:
                theme, profile, backup, notes = self.namespace['use']('gruvbox-dark')
            except RuntimeError as error:
                self.fail(f'Wallpaper prevented application refresh: {error}')
        self.assertEqual(len(refreshed), 1)
        self.assertIn('background=282828', refreshed[0])
        self.assertEqual((self.root / 'alpine/themes/current').read_text(), 'gruvbox-dark\n')
        self.assertTrue(any('wallpaper' in note.lower() and 'FAILED' in note for note in notes))

    def test_cli_notifies_when_a_real_interrupted_deployment_blocks_selection(self):
        journal = self.home / '.local/state/oldbook/backups/123/manifest.json'
        journal.parent.mkdir(parents=True)
        journal.write_text('{"version": 2, "status": "in_progress", "entries": []}')
        delivered = []

        def run(command, timeout=20):
            delivered.append(command)
            return True

        with mock.patch.dict(self.globals, run=run), \
                mock.patch.object(sys, 'argv', ['oldbook-theme', 'use', 'gruvbox-dark',
                                              '--no-reload', '--notify']), \
                contextlib.redirect_stderr(io.StringIO()):
            try:
                status = self.namespace['main']()
            except SystemExit as error:
                status = error.code
        self.assertEqual(status, 1)
        self.assertEqual(len(delivered), 1)
        self.assertEqual(delivered[0][0], 'notify-send')
        self.assertIn('Interrupted deployment', delivered[0][-1])
        self.assertFalse((self.root / 'alpine/themes/current').exists())

    def test_cli_reports_failed_terminal_refresh_in_the_visible_result(self):
        # Treating the terminal helper's nonzero result as "unchanged" makes
        # this real refresh path incorrectly exit successfully and hide it.
        delivered = []

        def run(command, timeout=20):
            if command[0] == 'notify-send':
                delivered.append(command)
            return not any(str(part).endswith('/oldbook-refresh-terminal-theme')
                           for part in command)

        with mock.patch.dict(self.globals, {
                'run': run,
                'sway_reload': lambda: None,
                'owned_processes': lambda *names: iter([]),
                'signal_processes': lambda *args: 0,
                'tmux_reload': lambda: 0}):
            notes = self.namespace['refresh_session']()
            with mock.patch.dict(self.globals, use=lambda *args, **kwargs: (
                    {'name': 'Fixture theme'}, None, None, notes)), \
                    mock.patch.object(sys, 'argv',
                                      ['oldbook-theme', 'use', 'fixture', '--notify']), \
                    contextlib.redirect_stdout(io.StringIO()):
                status = self.namespace['main']()
        self.assertEqual(status, 1)
        self.assertEqual(len(delivered), 1)
        self.assertIn('foot', delivered[0][-1].lower())

    def test_cli_includes_unmanaged_browser_limit_in_the_visible_result(self):
        # The CLI must carry a browser limitation from refresh to its user;
        # filtering only the old "startup" text silently drops that warning.
        notes = ['Firefox custom styling is not managed; browser appearance may retain its own theme']
        delivered = []
        with mock.patch.dict(self.globals, {
                'use': lambda *args, **kwargs: ({'name': 'Fixture theme'}, None, None, notes),
                'run': lambda command, **kwargs: delivered.append(command) or True}), \
                mock.patch.object(sys, 'argv',
                                  ['oldbook-theme', 'use', 'fixture', '--notify']), \
                contextlib.redirect_stdout(io.StringIO()):
            self.namespace['main']()
        self.assertEqual(len(delivered), 1)
        self.assertIn('Firefox', delivered[0][-1])


if __name__ == '__main__':
    unittest.main()
