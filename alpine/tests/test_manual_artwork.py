import contextlib
import fcntl
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from test_wallpapers import REPO, art, generator



def open_actions_then(fragment, capture=None):
    """Drive the two-step gallery menu: open the actions page, then pick a label.

    The image pages are the only menu offering "Gallery actions…", so the first
    call always lands there and the second sees the action list.
    """
    def run(command, **kwargs):
        options = kwargs['input'].splitlines()
        if 'Gallery actions…' in options:
            return subprocess.CompletedProcess(command, 0, 'Gallery actions…\n', '')
        if capture is not None:
            capture.extend(options)
        selected = next(line for line in options if fragment in line)
        return subprocess.CompletedProcess(command, 0, selected + '\n', '')
    return run

class ManualArtworkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'
        self.state = self.root / 'generation'
        self.state.mkdir()
        prompts = self.repo / 'alpine/wallpapers'
        prompts.mkdir(parents=True)
        shutil.copyfile(REPO / 'alpine/wallpapers/prompts.json', prompts / 'prompts.json')
        self.native = self.root / 'codex/generated_images/new.png'
        self.native.parent.mkdir(parents=True)
        shutil.copyfile(REPO / 'alpine/assets/gallery/delaware.png', self.native)
        self.daily = self.state / (generator.dt.date.today().isoformat() + '.json')
        self.daily.write_text('{"status":"failed","scene":"american-gothic"}')
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(mock.patch.object(generator, 'STATE', self.state))
        self.stack.enter_context(mock.patch.object(generator, 'REPO', self.repo))
        self.stack.enter_context(mock.patch.object(generator, 'clean_environment', return_value={
            'HOME': str(self.root), 'CODEX_HOME': str(self.root / 'codex'),
            'PATH': '/usr/local/bin:/usr/bin:/bin'}))
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.stack.enter_context(contextlib.redirect_stderr(io.StringIO()))

    def test_manual_after_daily_reservation_saves_commits_and_selects_exact_new_image(self):
        original = self.daily.read_bytes()
        with mock.patch.object(generator, 'generate_native', return_value=str(self.native)), \
                mock.patch.object(generator, 'checkpoint_generated', return_value='abc123'), \
                mock.patch.object(generator.subprocess, 'run') as run:
            run.return_value = subprocess.CompletedProcess([], 0, 'Logged in using ChatGPT', '')
            self.assertEqual(generator.run_once(manual=True, activate=True), 0)
        self.assertEqual(self.daily.read_bytes(), original)
        records = list((self.state / 'manual').glob('*.json'))
        self.assertEqual(len(records), 1)
        saved = json.loads(records[0].read_text())
        image = self.repo / saved['file']
        self.assertEqual(image.read_bytes(), self.native.read_bytes())
        entry = json.loads(image.with_suffix('.json').read_text())
        self.assertEqual(saved['status'], 'complete')
        self.assertTrue(saved['activated'])
        selections = [c.args[0] for c in run.call_args_list if 'select' in c.args[0]]
        self.assertEqual(len(selections), 1)
        self.assertEqual(selections[0][-2:], ['select', entry['id']])

    def test_held_generation_lock_prevents_manual_request_and_clears_busy_on_release(self):
        with (self.state / 'generation.lock').open('w') as lock:
            lock.write('{"title":"Ghost at work"}')
            lock.flush()
            fcntl.flock(lock, fcntl.LOCK_EX)
            with mock.patch.object(generator, 'generate_native') as native, \
                    mock.patch.object(generator, 'notify'), \
                    mock.patch.object(art, 'GENERATION', self.state):
                self.assertEqual(generator.run_once(manual=True, activate=True), 0)
                native.assert_not_called()
                self.assertEqual(art.generation_status()['title'], 'Ghost at work')
        with mock.patch.object(art, 'GENERATION', self.state):
            self.assertIsNone(art.generation_status())
        self.assertFalse((self.state / 'manual').exists())

    def test_failed_native_request_never_selects_or_creates_artwork(self):
        with mock.patch.object(generator, 'generate_native', side_effect=RuntimeError('image unavailable')), \
                mock.patch.object(generator.subprocess, 'run') as run:
            run.return_value = subprocess.CompletedProcess([], 0, 'Logged in using ChatGPT', '')
            with self.assertRaisesRegex(RuntimeError, 'image unavailable'):
                generator.run_once(manual=True, activate=True)
        self.assertFalse((self.repo / 'alpine/assets/gallery').exists())
        self.assertFalse(any('select' in c.args[0] for c in run.call_args_list))
        saved = json.loads(next((self.state / 'manual').glob('*.json')).read_text())
        self.assertEqual(saved['status'], 'failed')

    def test_activation_failure_keeps_successful_checkpoint_and_artifact(self):
        def external(command, **kwargs):
            if 'select' in command:
                return subprocess.CompletedProcess(command, 1, '', 'No physical Sway session')
            return subprocess.CompletedProcess(command, 0, 'Logged in using ChatGPT', '')
        with mock.patch.object(generator, 'generate_native', return_value=str(self.native)), \
                mock.patch.object(generator, 'checkpoint_generated', return_value='abc123'), \
                mock.patch.object(generator.subprocess, 'run', side_effect=external):
            self.assertEqual(generator.run_once(manual=True, activate=True), 1)
        saved = json.loads(next((self.state / 'manual').glob('*.json')).read_text())
        self.assertEqual(saved['status'], 'complete')
        self.assertFalse(saved['activated'])
        self.assertIn('Sway', saved['activation_error'])
        self.assertTrue((self.repo / saved['file']).is_file())

    def test_pending_checkpoint_still_activates_and_cron_retries_only_its_commit(self):
        with mock.patch.object(generator, 'generate_native', return_value=str(self.native)), \
                mock.patch.object(generator, 'checkpoint_generated', side_effect=RuntimeError('Fossil busy')), \
                mock.patch.object(generator.subprocess, 'run') as run:
            run.return_value = subprocess.CompletedProcess([], 0, 'Logged in using ChatGPT', '')
            self.assertEqual(generator.run_once(manual=True, activate=True), 1)
        record = next((self.state / 'manual').glob('*.json'))
        saved = json.loads(record.read_text())
        self.assertEqual(saved['status'], 'checkpoint-pending')
        self.assertTrue(saved['activated'])
        with mock.patch.object(generator, 'generate_native') as native, \
                mock.patch.object(generator, 'checkpoint_generated', return_value='abc123'), \
                mock.patch.object(generator.subprocess, 'run') as run:
            self.assertEqual(generator.run_once(), 0)
            native.assert_not_called()
            run.assert_not_called()
        self.assertEqual(json.loads(record.read_text())['status'], 'complete')
        self.assertEqual(json.loads(self.daily.read_text())['status'], 'failed')

    def test_gallery_generation_entry_does_not_shift_existing_selections(self):
        entries = [{'id': 'a', 'title': 'Same title'}, {'id': 'b', 'title': 'Same title'}]
        pages, actions = [], []
        def menu(command, **kwargs):
            options = kwargs['input'].splitlines()
            if 'Gallery actions…' in options:
                pages.append(options)
                self.assertEqual(options[:2], ['01  Same title', '02  Same title'])
                return subprocess.CompletedProcess(command, 0, 'Gallery actions…\n', '')
            actions.extend(options)
            generation = next(label for label in options if 'Generate new artwork' in label)
            return subprocess.CompletedProcess(command, 0, generation + '\n', '')
        with mock.patch.object(art, 'load_gallery', return_value=(entries, 1200)), \
                mock.patch.object(art.subprocess, 'run', side_effect=menu), \
                mock.patch.object(art, 'start_generation') as generate, \
                mock.patch.object(art, 'update') as update:
            art.pick()
            generate.assert_called_once_with()
            update.assert_not_called()
        self.assertTrue(any('Help' in label for label in actions))
        self.assertTrue(any('command deck' in label for label in actions))
        # Identical titles stay distinguishable, so the second row is its own image.
        def second(command, **kwargs):
            return subprocess.CompletedProcess(command, 0, kwargs['input'].splitlines()[1] + '\n', '')
        with mock.patch.object(art, 'load_gallery', return_value=(entries, 1200)), \
                mock.patch.object(art.subprocess, 'run', side_effect=second), \
                mock.patch.object(art, 'update') as update:
            art.pick()
            update.assert_called_once_with('pick', 'a')

    def test_gallery_keeps_browse_and_pause_commands_without_generating(self):
        entries = [{'id': 'a', 'title': 'First'}]
        for label, action in [('Next artwork', 'next'), ('Previous artwork', 'prev'),
                              ('Pause / resume rotation', 'pause')]:
            with self.subTest(action=action), \
                    mock.patch.object(art, 'load_gallery', return_value=(entries, 1200)), \
                    mock.patch.object(art.subprocess, 'run', side_effect=open_actions_then(label)), \
                    mock.patch.object(art, 'start_generation') as generate, \
                    mock.patch.object(art, 'update') as update:
                art.pick()
                update.assert_called_once_with(action)
                generate.assert_not_called()

    def test_gallery_controls_remain_reachable_with_eighteen_paintings(self):
        entries = [{'id': str(i), 'title': f'Painting {i}'} for i in range(18)]
        pages, actions = [], []
        def browse(command, **kwargs):
            options = kwargs['input'].splitlines()
            visible = int(command[command.index('--lines') + 1])
            if 'Gallery actions…' in options:
                if actions:
                    return subprocess.CompletedProcess(command, 1, '', '')
                # An image page is short enough to read without scrolling.
                self.assertLessEqual(len(options), visible)
                pages.append(options)
                return subprocess.CompletedProcess(command, 0, 'Gallery actions…\n', '')
            actions.extend(options)
            return subprocess.CompletedProcess(command, 1, '', '')
        with mock.patch.object(art, 'load_gallery', return_value=(entries, 1200)), \
                mock.patch.object(art.subprocess, 'run', side_effect=browse), \
                mock.patch.object(art, 'start_generation') as generate, \
                mock.patch.object(art, 'update') as update:
            art.pick()
        # The first page shows a slice of the artwork plus a way onward.
        self.assertTrue(any('Older images' in option for option in pages[0]))
        self.assertLess(sum(1 for option in pages[0] if option.startswith('0')), len(entries))
        for label in ('Next artwork', 'Previous artwork', 'Pause / resume rotation',
                      'Help & gallery controls', 'Open command deck', 'Edit artwork prompts',
                      'Generate new artwork', 'Desktop panels', 'Refit desktop panels'):
            self.assertTrue(any(label in option for option in actions), label)
        generate.assert_not_called()
        update.assert_not_called()

    def test_gallery_opens_prompt_editor_without_changing_or_generating_art(self):
        with mock.patch.object(art, 'load_gallery', return_value=([], 1200)), \
                mock.patch.object(art.subprocess, 'run',
                                  side_effect=open_actions_then('Edit artwork prompts')), \
                mock.patch.object(art.subprocess, 'Popen') as launch, \
                mock.patch.object(art, 'start_generation') as generate, \
                mock.patch.object(art, 'update') as update:
            art.pick()
        self.assertEqual(launch.call_args.args[0], ['/usr/bin/python3',
                         str(art.REPO / 'alpine/desktop/.local/bin/oldbook-gallery-prompts')])
        generate.assert_not_called()
        update.assert_not_called()

    def test_edit_prompts_command_opens_editor(self):
        with mock.patch('sys.argv', ['oldbook-wallpaper', 'edit-prompts']), \
                mock.patch.object(art.subprocess, 'Popen') as launch:
            art.main()
        self.assertEqual(launch.call_args.args[0][-1],
                         str(art.REPO / 'alpine/desktop/.local/bin/oldbook-gallery-prompts'))

    def test_select_resets_rotation_deadline_and_preserves_pause(self):
        state = self.root / 'wallpaper'
        state.mkdir()
        (state / 'state.json').write_text('{"id":"a","paused":true,"next_at":1}')
        entries = [{'id': 'a', 'title': 'Old'}, {'id': 'new', 'title': 'New'}, {'id': 'b', 'title': 'Other'}]
        with mock.patch.object(art, 'STATE', state), \
                mock.patch.object(art, 'current_scope', return_value='global'), \
                mock.patch.object(art, 'load_gallery', return_value=(entries, 1200)), \
                mock.patch.object(art, 'apply', return_value='/owned/socket'), \
                mock.patch.object(art.time, 'time', return_value=5000):
            art.update('select', 'new')
            self.assertEqual(art.read_state()['id'], 'new')
            self.assertTrue(art.read_state()['paused'])
            self.assertEqual(art.read_state()['next_at'], 6200)

    def test_hover_tooltip_renders_full_help_in_every_state(self):
        import gi
        gi.require_version('Pango', '1.0')
        from gi.repository import Pango

        for paused in (False, True):
            for busy in (None, {'title': 'New <painting> & more'}):
                with self.subTest(paused=paused, busy=busy):
                    output = io.StringIO()
                    with mock.patch.object(art, 'read_state', return_value={
                            'title': 'A <painting> & its frame',
                            'description': 'Its story & <literal> details',
                            'theme_name': 'Gold & <Violet>', 'paused': paused}), \
                            mock.patch.object(art, 'generation_status', return_value=busy), \
                            contextlib.redirect_stdout(output):
                        art.status()
                    state = json.loads(output.getvalue())
                    self.assertEqual(state['class'], 'generating' if busy else
                                     'paused' if paused else 'rotating')
                    try:
                        valid, _attributes, visible, _accelerator = Pango.parse_markup(
                            state['tooltip'], -1, '\0')
                    except Exception as error:
                        self.fail(f'Tooltip cannot render in GTK: {error}')
                    self.assertTrue(valid)
                    for instruction in ('Left: gallery & themes', 'Right: next artwork',
                                        'scroll: browse', 'Middle: pause',
                                        'Super+click: generate & switch',
                                        'Super+Shift+left: random complete theme',
                                        'Super+Shift+right: describe a complete theme',
                                        'Shift+click: edit prompts'):
                        self.assertIn(instruction, visible)
                    for value in ('A <painting> & its frame', 'Its story & <literal> details',
                                  'Gold & <Violet>', 'Paused' if paused else 'Changes every'):
                        self.assertIn(value, visible)
                    if busy:
                        self.assertIn(busy['title'], visible)


if __name__ == '__main__':
    unittest.main()
