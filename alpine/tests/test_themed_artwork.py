import contextlib
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from test_wallpapers import REPO, art, generator


class ThemedArtworkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'
        self.config = self.repo / 'alpine/wallpapers'
        self.config.mkdir(parents=True)
        shutil.copyfile(REPO / 'alpine/wallpapers/prompts.json', self.config / 'prompts.json')
        self.themes = self.repo / 'alpine/themes'
        self.themes.mkdir()
        (self.themes / 'current').write_text('gruvbox-dark\n')
        (self.themes / 'gruvbox-dark.json').write_text(json.dumps({
            'id': 'gruvbox-dark', 'name': 'Gruvbox Dark',
            'palette': {'background': '#282828'}, 'image_style': 'Warm charcoal and ochre.'}))
        (self.themes / 'spaceghost.json').write_text(json.dumps({
            'id': 'spaceghost', 'name': 'Space Ghost', 'image_style': 'Violet moonlight.'}))
        self.state = self.root / 'generation'
        self.state.mkdir()
        self.native = self.root / 'codex/generated_images/new.png'
        self.native.parent.mkdir(parents=True)
        shutil.copyfile(REPO / 'alpine/assets/gallery/delaware.png', self.native)
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(mock.patch.object(generator, 'STATE', self.state))
        self.stack.enter_context(mock.patch.object(generator, 'REPO', self.repo))
        self.stack.enter_context(mock.patch.object(art, 'REPO', self.repo))
        self.stack.enter_context(mock.patch.object(generator, 'clean_environment', return_value={
            'HOME': str(self.root), 'CODEX_HOME': str(self.root / 'codex'),
            'PATH': '/usr/local/bin:/usr/bin:/bin'}))
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.stack.enter_context(contextlib.redirect_stderr(io.StringIO()))

    def add_image(self, relative, identity, theme=None):
        image = self.repo / 'alpine/assets/gallery' / relative
        image.parent.mkdir(parents=True, exist_ok=True)
        image.write_bytes(identity.encode())
        entry = {'id': identity, 'title': identity, 'file': str(image.relative_to(self.repo)),
                 'sha256': hashlib.sha256(image.read_bytes()).hexdigest()}
        if theme is not None:
            entry['theme'] = theme
        image.with_suffix('.json').write_text(json.dumps(entry))
        return entry

    def write_gallery(self, **values):
        (self.config / 'gallery.json').write_text(json.dumps({'entries': [], **values}))

    def test_manual_active_theme_records_palette_and_saves_nested_pair(self):
        daily = self.state / (generator.dt.date.today().isoformat() + '.json')
        daily.write_text('{"status":"complete"}')
        original = daily.read_bytes()
        with mock.patch.object(generator, 'generate_native', return_value=str(self.native)), \
                mock.patch.object(generator, 'checkpoint_generated', return_value='abc123'), \
                mock.patch.object(generator.subprocess, 'run', return_value=subprocess.CompletedProcess(
                    [], 0, 'Logged in using ChatGPT', '')):
            self.assertEqual(generator.run_once(manual=True, activate=True), 0)
        saved = json.loads(next((self.state / 'manual').glob('*.json')).read_text())
        self.assertTrue(saved['file'].startswith('alpine/assets/gallery/themes/gruvbox-dark/'))
        entry = json.loads((self.repo / saved['file']).with_suffix('.json').read_text())
        self.assertEqual(entry['theme'], 'gruvbox-dark')
        self.assertEqual(entry['theme_name'], 'Gruvbox Dark')
        self.assertIn('Warm charcoal and ochre.', entry['prompt'])
        self.assertTrue(saved['activated'])
        self.assertEqual(daily.read_bytes(), original)

    def test_unthemed_generation_uses_general_folder_without_active_palette(self):
        with mock.patch.object(generator, 'generate_native', return_value=str(self.native)), \
                mock.patch.object(generator, 'checkpoint_generated', return_value='abc123'), \
                mock.patch.object(generator.subprocess, 'run', return_value=subprocess.CompletedProcess(
                    [], 0, 'Logged in using ChatGPT', '')):
            self.assertEqual(generator.run_once(manual=True, theme='none'), 0)
        saved = json.loads(next((self.state / 'manual').glob('*.json')).read_text())
        self.assertTrue(saved['file'].startswith('alpine/assets/gallery/general/'))
        entry = json.loads((self.repo / saved['file']).with_suffix('.json').read_text())
        self.assertEqual(entry['theme'], 'none')
        self.assertNotIn('Warm charcoal and ochre.', entry['prompt'])

    def test_unsafe_or_unknown_theme_does_not_reserve_attempt(self):
        for theme in ('../outside', 'unknown', '/tmp/theme', 'A Theme'):
            with self.subTest(theme=theme), self.assertRaises((RuntimeError, ValueError)):
                generator.run_once(theme=theme)
        self.assertEqual(list(self.state.glob('*.json')), [])

    def test_symlinked_theme_configuration_never_reserves_or_generates(self):
        current = self.themes / 'current'
        current.unlink()
        outside = self.root / 'current-theme'
        outside.write_text('gruvbox-dark')
        current.symlink_to(outside)
        with self.assertRaisesRegex(RuntimeError, 'regular file'):
            generator.run_once(manual=True)
        self.assertEqual(list((self.state / 'manual').glob('*.json')), [])

    def test_destination_changed_during_generation_never_receives_artwork(self):
        outside = self.root / 'outside-gallery'
        outside.mkdir()
        def native(*args):
            directory = self.repo / 'alpine/assets/gallery/themes'
            directory.mkdir(parents=True)
            (directory / 'gruvbox-dark').symlink_to(outside, target_is_directory=True)
            return str(self.native)
        with mock.patch.object(generator, 'generate_native', side_effect=native), \
                mock.patch.object(generator.subprocess, 'run', return_value=subprocess.CompletedProcess(
                    [], 0, 'Logged in using ChatGPT', '')):
            with self.assertRaisesRegex(RuntimeError, 'regular directory'):
                generator.run_once(manual=True)
        self.assertEqual(list(outside.iterdir()), [])

    def test_recursive_gallery_keeps_legacy_and_skips_tampered_or_escaping_art(self):
        self.add_image('old.png', 'legacy')
        self.add_image('general/general.png', 'general', 'none')
        self.add_image('themes/gruvbox-dark/new.png', 'warm', 'gruvbox-dark')
        bad = self.add_image('themes/gruvbox-dark/bad.png', 'bad', 'gruvbox-dark')
        (self.repo / bad['file']).write_bytes(b'tampered')
        outside = self.root / 'outside.png'
        outside.write_bytes(b'private')
        linked = self.repo / 'alpine/assets/gallery/general/linked.png'
        linked.symlink_to(outside)
        linked.with_suffix('.json').write_text(json.dumps({'id': 'leak', 'title': 'No',
                                                          'file': str(linked.relative_to(self.repo))}))
        self.write_gallery(legacy_theme='spaceghost', rotation_themes=['active', 'none'])
        entries, _ = art.load_gallery(self.repo)
        self.assertEqual({entry['id'] for entry in entries}, {'legacy', 'general', 'warm'})
        by_id = {entry['id']: entry for entry in entries}
        self.assertEqual(by_id['legacy']['theme'], 'spaceghost')
        self.assertEqual(by_id['warm']['theme_name'], 'Gruvbox Dark')
        self.assertFalse(by_id['legacy']['rotate'])
        self.assertTrue(by_id['general']['rotate'])
        self.assertTrue(by_id['warm']['rotate'])

    def test_timer_filters_theme_while_browsing_and_selection_keep_old_art_available(self):
        self.add_image('old.png', 'legacy')
        self.add_image('general/general.png', 'general', 'none')
        self.add_image('themes/gruvbox-dark/new.png', 'warm', 'gruvbox-dark')
        self.write_gallery(legacy_theme='spaceghost', rotation_themes=['active', 'none'])
        state = self.root / 'wallpaper'
        state.mkdir()
        (state / 'state.json').write_text('{"id":"warm"}')
        with mock.patch.object(art, 'STATE', state), \
                mock.patch.object(art, 'apply', return_value='/owned/socket'):
            art.update('tick')
            self.assertEqual(art.read_state()['id'], 'general')
            art.update('next')
            self.assertEqual(art.read_state()['id'], 'warm')
            art.update('next')
            self.assertEqual(art.read_state()['id'], 'legacy')
            art.update('select', 'legacy')
            self.assertEqual(art.read_state()['id'], 'legacy')
            art.update('refresh')
            self.assertEqual(art.read_state()['id'], 'legacy')

    def test_gallery_adds_theme_and_general_generation_after_existing_controls(self):
        self.add_image('old.png', 'legacy')
        self.write_gallery(legacy_theme='spaceghost')
        selected_options = []
        def menu(command, **kwargs):
            options = kwargs['input'].splitlines()
            self.assertTrue(options[0].startswith('01  legacy'))
            self.assertIn('Space Ghost', options[0])
            for text in ('Next artwork', 'Previous artwork', 'Pause / resume rotation',
                         'Help & gallery controls', 'Open command deck', 'Generate new artwork'):
                self.assertTrue(any(text in option for option in options), text)
            selected = next(option for option in options if 'Generate unthemed artwork' in option)
            selected_options.append(selected)
            return subprocess.CompletedProcess(command, 0, selected + '\n', '')
        with mock.patch.object(art.subprocess, 'run', side_effect=menu), \
                mock.patch.object(art.subprocess, 'Popen') as launch, \
                mock.patch.object(art, 'GENERATION', self.state):
            art.pick()
        self.assertEqual(len(selected_options), 1)
        command = launch.call_args.args[0]
        self.assertIn('--activate', command)
        self.assertEqual(command[command.index('--theme') + 1], 'none')


if __name__ == '__main__':
    unittest.main()
