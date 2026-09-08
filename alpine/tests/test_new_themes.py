import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_wallpapers import REPO, art, generator, load

new_themes = load('new_themes', REPO / 'alpine/wallpapers/new_themes.py')


class NewThemeTests(unittest.TestCase):
    def definition(self):
        return {'name': 'Moonlit Library', 'image_style': 'Ink blue books and gold moonlight.',
                'palette': {'background': '#101020', 'foreground': '#eeeecc', 'accent': '#ffcc44'},
                'scene': 'Space Ghost reads a giant book on the moon.'}

    def test_save_unique_discoverable_collection_without_replacing_existing(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            first = new_themes.save_theme(repo, self.definition(), 'moon books')
            second = new_themes.save_theme(repo, self.definition(), 'moon books')
            self.assertNotEqual(first['id'], second['id'])
            self.assertEqual(generator.load_theme(repo, first['id'])['name'], 'Moonlit Library')
            self.assertEqual(first['source_phrase'], 'moon books')

    def test_invalid_model_output_never_writes_descriptor(self):
        invalid = [dict(self.definition(), name='../bad\nname'),
                   dict(self.definition(), palette={'background': 'url(evil)'}),
                   dict(self.definition(), scene=''), dict(self.definition(), id='../escape')]
        with tempfile.TemporaryDirectory() as directory:
            for definition in invalid:
                with self.subTest(definition=definition), self.assertRaises(ValueError):
                    new_themes.save_theme(Path(directory), definition, '')
            self.assertFalse(list(Path(directory).rglob('*.json')))

    def test_symlink_theme_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / 'repo'
            (repo / 'alpine').mkdir(parents=True)
            (repo / 'alpine/themes').symlink_to(directory)
            with self.assertRaises(RuntimeError):
                new_themes.save_theme(repo, self.definition(), '')

    def test_random_and_phrase_prompts(self):
        self.assertIn('surprising', new_themes.theme_prompt(''))
        self.assertIn('moon books', new_themes.theme_prompt('moon books'))
        self.assertNotEqual(new_themes.theme_prompt(''), new_themes.theme_prompt(''))

    def test_theme_design_receives_saved_artwork_guidance(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            guidance = 'Strong Christian faith, medieval Crusades and a love of history.'
            process = mock.Mock(returncode=0)
            def command(work, model):
                (work / 'result.json').write_text(json.dumps(self.definition()))
                return ['codex', '--sandbox', 'workspace-write', '--enable', 'image_generation']
            with mock.patch.object(new_themes.subprocess, 'Popen', return_value=process):
                theme = new_themes.design_theme(repo, {'model': 'fixture', 'style': guidance},
                                               {}, repo / 'log', 'illuminated chronicles', command)
            sent = process.communicate.call_args.args[0]
            self.assertIn(guidance, sent)
            self.assertIn('illuminated chronicles', sent)
            self.assertEqual(theme['source_phrase'], 'illuminated chronicles')

    def test_cancelled_phrase_menu_does_not_launch(self):
        from subprocess import CompletedProcess
        with mock.patch.object(art, 'load_gallery', return_value=([], {})), \
                mock.patch.object(art.subprocess, 'run', side_effect=[
                    CompletedProcess([], 0, '✦  Create theme from prompt\n', ''),
                    CompletedProcess([], 1, '', '')]), \
                mock.patch.object(art, 'start_generation') as start:
            art.pick()
        start.assert_not_called()

    def test_phrase_menu_passes_literal_text_to_background_job(self):
        from subprocess import CompletedProcess
        phrase = 'Moon books; $(touch /tmp/nope)'
        with mock.patch.object(art, 'load_gallery', return_value=([], {})), \
                mock.patch.object(art.subprocess, 'run', side_effect=[
                    CompletedProcess([], 0, '✦  Create theme from prompt\n', ''),
                    CompletedProcess([], 0, phrase + '\n', '')]), \
                mock.patch.object(art, 'start_generation') as start:
            art.pick()
        start.assert_called_once_with(new_theme=phrase)

    def test_existing_themes_are_selected_in_a_separate_picker(self):
        from subprocess import CompletedProcess
        menus = []
        def choose(command, **kwargs):
            options = kwargs['input'].splitlines()
            menus.append(options)
            if len(menus) == 1:
                self.assertIn('✦  Create theme from prompt', options)
                self.assertFalse(any('Paint a new ' in item for item in options))
                chosen = '✦  Paint in an existing theme…'
                self.assertIn(chosen, options)
            else:
                chosen = next(item for item in options if 'Space Ghost' in item)
            return CompletedProcess(command, 0, chosen + '\n', '')
        with mock.patch.object(art, 'load_gallery', return_value=([], {})), \
                mock.patch.object(art.subprocess, 'run', side_effect=choose), \
                mock.patch.object(art, 'start_generation') as start:
            art.pick()
        start.assert_called_once_with('spaceghost')

    def test_generated_name_matching_an_action_still_paints_that_theme(self):
        from subprocess import CompletedProcess
        name = '✦  Create theme from prompt'
        with mock.patch.object(art, 'load_gallery', return_value=([], {})), \
                mock.patch.object(art, 'available_themes', return_value=[{'name': name, 'id': 'moon-books'}]), \
                mock.patch.object(art.subprocess, 'run', side_effect=[
                    CompletedProcess([], 0, '✦  Paint in an existing theme…\n', ''),
                    CompletedProcess([], 0, name + '\n', '')]), \
                mock.patch.object(art, 'start_generation') as start:
            art.pick()
        start.assert_called_once_with('moon-books')

    def test_new_theme_debut_uses_requested_scene_and_existing_artwork_pipeline(self):
        import subprocess
        from test_themed_artwork import ThemedArtworkTests
        fixture = ThemedArtworkTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        theme = new_themes.save_theme(fixture.repo, self.definition(), 'moon books')
        with mock.patch('new_themes.design_theme', return_value=theme) as design, \
                mock.patch.object(generator, 'generate_native', return_value=str(fixture.native)) as native, \
                mock.patch.object(generator, 'checkpoint_generated', return_value='abc123'), \
                mock.patch.object(generator.subprocess, 'run', return_value=subprocess.CompletedProcess(
                    [], 0, 'Logged in using ChatGPT', '')):
            self.assertEqual(generator.run_once(manual=True, activate=True, new_theme='moon books'), 0)
        self.assertEqual(design.call_args.args[4], 'moon books')
        self.assertIn(theme['scene'], native.call_args.args[1])
        record = json.loads(next((fixture.state / 'manual').glob('*.json')).read_text())
        self.assertTrue(record['activated'])
        entry = json.loads((fixture.repo / record['file']).with_suffix('.json').read_text())
        self.assertEqual(entry['theme'], theme['id'])
        self.assertRegex(entry['theme_descriptor_sha256'], r'^[0-9a-f]{64}$')
