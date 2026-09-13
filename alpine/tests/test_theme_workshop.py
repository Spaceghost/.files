"""A theme is designed as text and applied at once; no painting gates it.

Jack: "the theme selector in my super+shift+d when I generate is requiring
wallpapers to generate to make the theme, that shouldn't be ... I want to
freely generate themes even without the image gen." Every test here is
hermetic: the script's namespace is loaded under a temporary HOME and the
pieces that reach a model runner, the desktop or the boot chain are replaced,
so nothing below designs a theme with a real model, switches the live desktop
or installs anything into /boot.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / 'alpine/desktop/.local/bin/oldbook-theme'
THEME = {'id': 'moonlit-library-0123456789ab', 'name': 'Moonlit Library',
         'image_style': 'Ink blue books and gold moonlight.',
         'palette': {'background': '#101020', 'foreground': '#eeeecc', 'accent': '#ffcc44'},
         'design': {'font': 'DejaVu Serif', 'radius': 4, 'spacing': 8, 'opacity': 0.94,
                    'bar_position': 'top', 'widget_edge': 'left', 'launcher_width': 52,
                    'cursors': 'simp1e-cursors-gruvbox-dark', 'icons': 'Oldbook-Moonlit-Library'},
         'scene': 'Space Ghost reads a giant book on the moon.'}


class WorkshopTestCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='theme-workshop-')
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name) / 'home'
        (self.home / '.config/oldbook').mkdir(parents=True)
        self.enterContext(mock.patch.dict(os.environ, {
            'XDG_CONFIG_HOME': str(self.home / '.config')}))
        self.enterContext(mock.patch.object(Path, 'home', return_value=self.home))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.enterContext(contextlib.redirect_stderr(io.StringIO()))
        self.namespace = runpy.run_path(str(SCRIPT))
        self.globals = self.namespace['use'].__globals__
        self.notices, self.ran, self.announced = [], [], []
        self.enterContext(mock.patch.dict(self.globals, {
            'notify_user': lambda title, body, urgency=None: self.notices.append(
                (title, body, urgency)),
            'run': self.record_run}))
        self.enterContext(mock.patch.object(
            self.globals['failure_notice'], 'announce',
            lambda title, message, log: self.announced.append((title, message, log)) or True))

    def record_run(self, command, timeout=20):
        self.ran.append([str(part) for part in command])
        return True

    def policy(self, **switches):
        (self.home / '.config/oldbook/painting.json').write_text(json.dumps(switches))


class CreateTests(WorkshopTestCase):
    def test_a_description_becomes_a_theme_that_is_applied_at_once(self):
        designed, applied = [], []

        def design(config, env, log, phrase, *, history=None):
            designed.append((phrase, env, log))
            return dict(THEME)

        def use(identity, *, reload=True, boot_chain='background'):
            applied.append((identity, reload, boot_chain))
            return dict(THEME), Path('/profile'), Path('/backup'), ['sway reloaded']

        with mock.patch.dict(self.globals, {'design_with_retries': design, 'use': use}):
            self.assertEqual(self.namespace['create']('moonlit library', notify=True), 0)
        self.assertEqual(designed[0][0], 'moonlit library')
        self.assertEqual(designed[0][1]['CODEX_HOME'], str(self.home / '.codex'))
        self.assertTrue(str(designed[0][2]).startswith(str(self.home / '.local/state/oldbook/theme/designs/')))
        self.assertEqual(applied, [(THEME['id'], True, 'background')])
        self.assertEqual(self.notices[0][0], 'Designing a theme…')
        self.assertIn('no painting', self.notices[0][1])
        # The finished notice is the ordinary theme notice, saying it was created.
        finished = [command for command in self.ran if command[0] == 'notify-send']
        self.assertEqual(finished[-1][-2:], ['Theme created and applied', 'Moonlit Library'])
        self.assertEqual(self.announced, [])

    def test_no_painting_is_asked_for_unless_the_policy_says_so(self):
        requested = []
        with mock.patch.dict(self.globals, {
                'design_with_retries': lambda *a, **k: dict(THEME),
                'use': lambda identity, **k: (dict(THEME), None, None, []),
                'request_debut_painting': lambda theme: requested.append(theme['id']) or [
                    'debut painting requested from the gallery']}):
            self.assertEqual(self.namespace['create']('moonlit library'), 0)
            self.assertEqual(requested, [])
            self.policy(debut_painting=True)
            self.assertEqual(self.namespace['create']('moonlit library'), 0)
        self.assertEqual(requested, [THEME['id']])

    def test_the_debut_painting_is_the_gallery_s_own_manual_request(self):
        launched = []
        with mock.patch.object(subprocess, 'Popen', side_effect=lambda command, **kwargs: (
                launched.append((command, kwargs)) or mock.Mock(pid=1))):
            notes = self.namespace['request_debut_painting'](THEME)
        self.assertEqual(notes, ['debut painting requested from the gallery'])
        command, kwargs = launched[0]
        self.assertEqual(Path(command[1]).name, 'generate.py')
        self.assertEqual(command[2:], ['--manual', '--activate', '--theme', THEME['id']])
        self.assertTrue(kwargs.get('start_new_session'))

    def test_a_design_that_stops_is_reported_with_its_own_reason_and_its_log(self):
        log = self.home / 'design.jsonl'
        log.write_text('{"message": "You have hit your usage limit; try again at 6:21 PM"}\n')
        Stopped = self.globals['DesignStopped']

        def design(*args, **kwargs):
            raise Stopped('You have hit your usage limit; try again at 6:21 PM', log)

        with mock.patch.dict(self.globals, {'design_with_retries': design,
                                            'use': mock.Mock(side_effect=AssertionError)}):
            self.assertEqual(self.namespace['create']('moonlit library', notify=True), 1)
        title, message, announced_log = self.announced[0]
        self.assertEqual(title, 'Theme design stopped')
        self.assertIn('usage limit', message)
        self.assertIn(str(log), message)
        self.assertEqual(announced_log, log)

    def test_a_second_request_while_one_is_designing_is_refused_not_queued(self):
        import fcntl
        state = self.home / '.local/state/oldbook/theme'
        state.mkdir(parents=True)
        with (state / 'design.lock').open('a+') as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            with mock.patch.dict(self.globals, {
                    'design_with_retries': mock.Mock(side_effect=AssertionError)}):
                self.assertEqual(self.namespace['create']('moonlit library', notify=True), 2)
        self.assertEqual(self.notices[-1][0], 'A theme is already being designed')

    def test_the_command_line_takes_one_description_or_a_surprise(self):
        for argv in (['create'], ['create', 'moon', '--random'], ['create', 'a\tb\nc']):
            with self.subTest(argv=argv), mock.patch('sys.argv', ['oldbook-theme', *argv]), \
                    self.assertRaises(SystemExit):
                self.namespace['main']()
        calls = []
        with mock.patch.dict(self.globals, {'create': lambda phrase, **kwargs: calls.append(
                (phrase, kwargs)) or 0}):
            with mock.patch('sys.argv', ['oldbook-theme', 'create', '  moon books ', '--notify']):
                self.assertEqual(self.namespace['main'](), 0)
            with mock.patch('sys.argv', ['oldbook-theme', 'create', '--random', '--boot-chain', 'now']):
                self.assertEqual(self.namespace['main'](), 0)
        self.assertEqual(calls, [
            ('moon books', {'notify': True, 'reload': True, 'boot_chain': 'background'}),
            ('', {'notify': False, 'reload': True, 'boot_chain': 'now'})])


class RetryTests(WorkshopTestCase):
    def chain(self, outcomes):
        """A design chain answering from a script: an exception or a theme per call."""
        import new_themes
        calls = []

        def design_theme(repo, config, env, log, phrase, builder, *, history=None):
            calls.append(log)
            outcome = outcomes[len(calls) - 1]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        return calls, mock.patch.object(new_themes, 'design_theme', design_theme)

    def test_a_retryable_failure_is_tried_four_times_with_the_generator_s_waits(self):
        waits = []
        calls, patch = self.chain([ValueError('bad JSON'), RuntimeError('timed out'),
                                   OSError('blip'), dict(THEME)])
        with patch:
            theme = self.namespace['design_with_retries'](
                {'model': 'fixture', 'style': ''}, {}, self.home / 'design.jsonl', 'moon',
                sleep=waits.append)
        self.assertEqual(theme['id'], THEME['id'])
        self.assertEqual(waits, [2, 4, 8])
        self.assertEqual([log.name for log in calls], [
            'design.jsonl', 'design.attempt-2.jsonl', 'design.attempt-3.jsonl',
            'design.attempt-4.jsonl'])

    def test_a_spent_chain_stops_at_once_with_the_runner_s_own_words(self):
        import new_themes
        calls, patch = self.chain([new_themes.Exhausted('codex: usage limit until 6:21 PM')])
        with patch, self.assertRaises(self.globals['DesignStopped']) as stopped:
            self.namespace['design_with_retries'](
                {'model': 'fixture', 'style': ''}, {}, self.home / 'design.jsonl', 'moon',
                sleep=lambda seconds: self.fail('a spent chain must not wait'))
        self.assertEqual(len(calls), 1)
        self.assertIn('usage limit', str(stopped.exception))
        self.assertEqual(stopped.exception.log, self.home / 'design.jsonl')

    def test_the_log_outranks_an_exception_that_lost_the_reason(self):
        log = self.home / 'design.jsonl'

        def write_then_fail(*args, **kwargs):
            log.write_text('{"error": {"message": "Not logged in: run codex login"}}\n')
            raise RuntimeError('Artwork design exited with status 1 and recorded no reason')

        import new_themes
        with mock.patch.object(new_themes, 'design_theme', write_then_fail), \
                self.assertRaises(self.globals['DesignStopped']) as stopped:
            self.namespace['design_with_retries'](
                {'model': 'fixture', 'style': ''}, {}, log, 'moon', attempts=1)
        self.assertEqual(str(stopped.exception), 'Not logged in: run codex login')


class BootChainTests(WorkshopTestCase):
    def test_the_background_publish_records_its_outcome_and_says_so_quietly(self):
        with mock.patch.dict(self.globals, {'publish_boot_chain': lambda log=None: [
                'GRUB theme rendered', 'boot console installed for next boot']}):
            self.assertEqual(self.namespace['boot_chain']('gruvbox-dark'), 0)
        record = json.loads((self.home / '.local/state/oldbook/theme/boot-chain.json').read_text())
        self.assertEqual(record['theme'], 'gruvbox-dark')
        self.assertTrue(record['ok'])
        self.assertEqual(self.notices[-1][0], 'Boot chain themed')
        self.assertEqual(self.notices[-1][2], 'low')
        self.assertEqual(self.announced, [])

    def test_a_failed_publish_carries_the_installer_s_words_and_opens_the_log(self):
        log = self.home / '.local/state/oldbook/theme/boot-chain.log'
        with mock.patch.dict(self.globals, {'publish_boot_chain': lambda log=None: [
                'GRUB theme rendered',
                'boot console install FAILED: grub.cfg did not validate: syntax error line 12']}):
            self.assertEqual(self.namespace['boot_chain']('gruvbox-dark'), 1)
        record = json.loads((self.home / '.local/state/oldbook/theme/boot-chain.json').read_text())
        self.assertFalse(record['ok'])
        title, message, announced_log = self.announced[0]
        self.assertEqual(title, 'Boot chain not themed')
        self.assertIn('syntax error line 12', message)
        self.assertEqual(announced_log, log)
        self.assertEqual([notice for notice in self.notices if notice[0] == 'Boot chain themed'], [])

    def test_each_step_s_whole_output_lands_in_the_log(self):
        log = self.home / 'steps.log'
        ok, detail = self.namespace['run_boot_step'](
            ['/bin/sh', '-c', 'echo rendered; echo warning >&2; exit 3'], 10, log)
        self.assertFalse(ok)
        self.assertEqual(detail, 'warning')
        body = log.read_text()
        self.assertIn('rendered', body)
        self.assertIn('warning', body)
        self.assertIn('[exit 3]', body)

    def test_nothing_is_published_when_the_palette_did_not_change(self):
        with mock.patch.dict(self.globals, {'render_console_palette': lambda theme: (False, [])}), \
                mock.patch.object(subprocess, 'Popen') as launch:
            self.assertEqual(self.namespace['refresh_boot_palette_later'](THEME), [])
        launch.assert_not_called()

    def test_a_publish_that_cannot_start_is_a_failure_note_not_a_silence(self):
        with mock.patch.dict(self.globals, {
                'render_console_palette': lambda theme: (True, ['boot console palette updated']),
                'boot_chain_pending': lambda: True}), \
                mock.patch.object(subprocess, 'Popen', side_effect=OSError('no python')):
            notes = self.namespace['refresh_boot_palette_later'](THEME)
        self.assertEqual(notes[0], 'boot console palette updated')
        self.assertIn('FAILED', notes[1])
        self.assertIn('no python', notes[1])


class IconSetTests(WorkshopTestCase):
    def repository(self, installed=('Oldbook-Gruvbox',), builder=True):
        """A checkout with a stub builder and the named sets already present."""
        repo = self.home / 'repo'
        (repo / 'alpine/bin').mkdir(parents=True)
        if builder:
            (repo / 'alpine/bin/build-icon-theme').write_text('#!/bin/sh\nexit 0\n')
        for name in installed:
            (repo / 'alpine/desktop/.local/share/icons' / name).mkdir(parents=True)
            (repo / 'alpine/desktop/.local/share/icons' / name / 'index.theme').write_text(
                '[Icon Theme]\n')
        profile = repo / 'alpine/themes/profiles' / THEME['id']
        profile.mkdir(parents=True)
        return repo, profile

    def test_a_set_installed_anywhere_is_left_alone(self):
        built = []
        repo, profile = self.repository()
        with mock.patch.dict(self.globals, {'run_boot_step': lambda *a, **k: built.append(a) or (True, '')}):
            notes = self.namespace['ensure_icon_set'](
                repo, dict(THEME, design=dict(THEME['design'], icons='Oldbook-Gruvbox')), profile)
        self.assertEqual(notes, [])
        self.assertEqual(built, [])

    def test_a_set_nobody_has_is_built_into_the_theme_s_own_profile(self):
        built = []
        repo, profile = self.repository()
        with mock.patch.dict(self.globals, {
                'run_boot_step': lambda command, timeout, log=None: built.append(command) or (True, '')}):
            notes = self.namespace['ensure_icon_set'](repo, THEME, profile)
        self.assertEqual(notes, ['folder icons built (Oldbook-Moonlit-Library)'])
        command = built[0]
        self.assertEqual(Path(command[1]), repo / 'alpine/bin/build-icon-theme')
        self.assertEqual(command[2:], ['--theme', THEME['id'], '--output',
                                       str(profile / '.local/share/icons/Oldbook-Moonlit-Library')])

    def test_a_checkout_without_the_builder_has_nothing_to_report(self):
        repo, profile = self.repository(builder=False)
        with mock.patch.dict(self.globals, {'run_boot_step': mock.Mock(side_effect=AssertionError)}):
            self.assertEqual(self.namespace['ensure_icon_set'](repo, THEME, profile), [])

    def test_a_builder_that_cannot_draw_is_reported_with_its_reason(self):
        repo, profile = self.repository()
        with mock.patch.dict(self.globals, {
                'run_boot_step': lambda *a, **k: (False, 'Restore papirus-icon-theme 20250201-r0 first.')}):
            notes = self.namespace['ensure_icon_set'](repo, THEME, profile)
        self.assertEqual(len(notes), 1)
        self.assertIn('FAILED', notes[0])
        self.assertIn('papirus-icon-theme', notes[0])

    def test_a_profile_outside_the_checkout_is_refused(self):
        repo, _profile = self.repository()
        with mock.patch.dict(self.globals, {'run_boot_step': mock.Mock(side_effect=AssertionError)}):
            notes = self.namespace['ensure_icon_set'](repo, THEME, self.home / 'elsewhere')
        self.assertTrue(notes and 'FAILED' in notes[0], notes)

    def test_switching_builds_the_icons_before_the_profile_is_deployed(self):
        source = SCRIPT.read_text()
        self.assertLess(source.index('ensure_icon_set(REPO, theme, profile)'),
                        source.index("deployer['deploy'](Path.home(), profile)"))


if __name__ == '__main__':
    unittest.main()
