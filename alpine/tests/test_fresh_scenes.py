"""Automatic artwork must move on from painted subjects, not just change a seed."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_prompt_catalog import catalog, prompt_catalog
from test_wallpapers import generator
import new_themes


class FreshSceneTests(unittest.TestCase):
    def test_an_unpainted_mix_does_not_make_an_old_scene_fresh(self):
        history = prompt_catalog.PaintHistory('unused')
        history.record('a', 'x', 'm')
        first = mock.Mock(choice=lambda items: items[0])
        chosen = prompt_catalog.choose(catalog(mediums=('m', 'n')), history,
                                       fresh_scene=True, rng=first)
        self.assertEqual(chosen[0]['id'], 'b')
        self.assertNotEqual(tuple(item['id'] for item in chosen[1:]), ('x', 'm'))

    def test_exhaustion_never_silently_returns_an_old_scene(self):
        history = prompt_catalog.PaintHistory('unused')
        history.record('a', 'x')
        with self.assertRaises(prompt_catalog.SceneBankExhausted):
            prompt_catalog.choose(catalog(scenes=('a',)), history, fresh_scene=True)

    def test_exhausted_mix_requests_invention_instead_of_recycling_it(self):
        history = prompt_catalog.PaintHistory('unused')
        history.record('a', 'x', 'm')
        with self.assertRaises(prompt_catalog.SceneBankExhausted):
            prompt_catalog.choose(catalog(insertions=('x',), mediums=('m',)), history,
                                  fresh_scene=True)

    def test_history_merges_archive_even_when_local_history_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'history.json'
            history = prompt_catalog.PaintHistory(path)
            history.record('a', 'x', seed='one')
            history.save()
            restored = {'scene': 'b', 'insertion': 'y', 'seed': 'two'}
            history = prompt_catalog.PaintHistory.load(path, [restored])
            history.save()
            history = prompt_catalog.PaintHistory.load(path, [restored])
            self.assertEqual(len(history.records), 2)
            self.assertEqual({r['scene'] for r in history.records}, {'a', 'b'})

    def test_old_scenes_are_not_forgotten_after_two_thousand_images(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'history.json'
            history = prompt_catalog.PaintHistory(path)
            for i in range(2001):
                history.record('scene-' + str(i), None)
            history.save()
            self.assertIn(('scene-0', None, None), prompt_catalog.PaintHistory.load(path).used())

    def test_archive_enrichment_preserves_local_paint_order(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'history.json'
            records = [{'scene': 'a', 'seed': 'first'}, {'scene': 'b', 'seed': 'last'}]
            path.write_text(json.dumps({'records': records}))
            history = prompt_catalog.PaintHistory.load(path, list(reversed(records)))
            self.assertEqual(history.last('scenes'), 'b')

    def test_gallery_restores_scene_medium_and_description_without_local_records(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            gallery = repo / 'alpine/assets/gallery/themes/test'
            gallery.mkdir(parents=True)
            (gallery / 'old.json').write_text(json.dumps({
                'title': 'A', 'description': 'Scene a', 'insertion': 'x', 'medium': 'm',
                'variation_seed': 'old-seed', 'file': 'alpine/assets/gallery/themes/test/old.png'}))
            with mock.patch.object(generator, 'REPO', repo), \
                    mock.patch.object(generator, 'STATE', repo / 'state'):
                history = generator.load_history(catalog())
            self.assertIn(('a', 'x', 'm'), history.used())
            self.assertEqual(history.records[0]['description'], 'Scene a')

    def test_renaming_a_painted_catalog_scene_does_not_make_it_new(self):
        history = prompt_catalog.PaintHistory('unused', [
            {'scene': 'old-name', 'title': 'Other title', 'description': 'Scene a'}])
        chosen = prompt_catalog.choose(catalog(), history, fresh_scene=True)
        self.assertEqual(chosen[0]['id'], 'b')

    def test_duplicate_invented_proposals_never_reach_image_generation(self):
        from test_themed_artwork import ThemedArtworkTests
        fixture = ThemedArtworkTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        (fixture.config / 'prompts.json').write_text(json.dumps(dict(catalog(scenes=('a',)), model='fixture')))
        history = prompt_catalog.PaintHistory(fixture.state / 'history.json')
        history.record('a', 'x', title='A', description='Scene a')
        history.save()
        repeated = {'scene': {'title': 'Renamed', 'description': 'Scene a'},
                    'insertion': {'title': 'Different', 'description': 'A completely new cameo.'},
                    'medium': {'title': 'Different', 'description': 'A completely new treatment.'}}
        with mock.patch.object(new_themes, 'request_design', return_value=repeated), \
                mock.patch.object(generator, 'generate_native') as painting, \
                mock.patch.object(generator.time, 'sleep'), \
                mock.patch.object(generator.subprocess, 'run', return_value=subprocess.CompletedProcess(
                    [], 0, 'Logged in using ChatGPT', '')):
            with self.assertRaisesRegex(ValueError, 'already been painted'):
                generator.run_once(manual=True, activate=True)
        painting.assert_not_called()
        saved = json.loads(next((fixture.state / 'manual').glob('*.json')).read_text())
        self.assertEqual(saved['attempts'], {'scene': 4})
        self.assertEqual(saved['status'], 'failed')
        self.assertNotIn('scene', saved)

    def test_explicit_old_scene_is_refused_before_requesting_design_or_image(self):
        from test_themed_artwork import ThemedArtworkTests
        fixture = ThemedArtworkTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        (fixture.config / 'prompts.json').write_text(json.dumps(dict(catalog(), model='fixture')))
        history = prompt_catalog.PaintHistory(fixture.state / 'history.json')
        history.record('a', 'x')
        history.save()
        with mock.patch.object(generator, 'generate_native') as painting, \
                mock.patch.object(new_themes, 'request_design') as design:
            with self.assertRaisesRegex(RuntimeError, 'Omit --scene'):
                generator.run_once('a', manual=True)
        painting.assert_not_called()
        design.assert_not_called()

    def test_failed_image_attempt_preserves_invented_mix_descriptions(self):
        from test_themed_artwork import ThemedArtworkTests
        fixture = ThemedArtworkTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        config = dict(catalog(scenes=('a',)), model='fixture')
        (fixture.config / 'prompts.json').write_text(json.dumps(config))
        history = prompt_catalog.PaintHistory(fixture.state / 'history.json')
        history.record('a', 'x')
        history.save()
        scene = {'id': 'new', 'title': 'New', 'description': 'Space Ghost cleans an orbital laundromat.'}
        insertion = {'id': 'novel-role', 'title': 'Laundry', 'description': 'He examines an unruly cape.'}
        medium = {'id': 'novel-medium', 'title': 'Tiles', 'description': 'Hand glazed ceramic mosaic.'}
        with mock.patch.object(new_themes, 'design_scene', return_value=(scene, insertion, medium)), \
                mock.patch.object(generator, 'generate_native', side_effect=RuntimeError('Lost response')), \
                mock.patch.object(generator.time, 'sleep'), \
                mock.patch.object(generator.subprocess, 'run', return_value=subprocess.CompletedProcess(
                    [], 0, 'Logged in using ChatGPT', '')):
            with self.assertRaisesRegex(RuntimeError, 'Lost response'):
                generator.run_once(manual=True)
        recovered = generator.load_history(config)
        with self.assertRaisesRegex(ValueError, 'mix has already'):
            prompt_catalog.require_fresh_mix(dict(insertion, id='renamed'),
                                             dict(medium, id='renamed'), recovered)

    def test_manual_request_designs_a_new_subject_after_catalog_exhaustion(self):
        from test_themed_artwork import ThemedArtworkTests
        fixture = ThemedArtworkTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        (fixture.config / 'prompts.json').write_text(json.dumps(dict(catalog(scenes=('a',)), model='fixture')))
        history = prompt_catalog.PaintHistory(fixture.state / 'history.json')
        history.record('a', 'x')
        history.save()
        scene = {'id': 'new-railway', 'title': 'A railway through Saturn',
                 'description': 'Space Ghost drives a crystal locomotive through Saturn’s rings.'}
        insertion = {'id': 'driver', 'title': 'Driver', 'description': 'His cape tangles in a ticket punch.'}
        medium = {'id': 'paper', 'title': 'Paper sculpture', 'description': 'Photographed folded paper sculpture.'}
        with mock.patch('new_themes.design_scene', return_value=(scene, insertion, medium)), \
                mock.patch.object(generator, 'generate_native', return_value=str(fixture.native)), \
                mock.patch.object(generator, 'checkpoint_generated', return_value='abc123'), \
                mock.patch.object(generator.subprocess, 'run', return_value=subprocess.CompletedProcess(
                    [], 0, 'Logged in using ChatGPT', '')):
            self.assertEqual(generator.run_once(manual=True, activate=True), 0)
        record = json.loads(next((fixture.state / 'manual').glob('*.json')).read_text())
        entry = json.loads((fixture.repo / record['file']).with_suffix('.json').read_text())
        self.assertEqual(entry['scene'], 'new-railway')
        self.assertEqual(entry['description'], scene['description'])
        self.assertIn(medium['description'], entry['prompt'])
        self.assertTrue(record['activated'])


class FreshDesignTests(unittest.TestCase):
    def test_removed_theme_descriptor_does_not_make_its_art_direction_new(self):
        from test_new_themes import NewThemeTests
        definition = NewThemeTests().definition()
        history = prompt_catalog.PaintHistory('unused', [
            {'scene': 'other', 'description': 'Space Ghost visits a radio shop.',
             'theme_style': definition['image_style']}])
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            with mock.patch.object(new_themes, 'request_design', return_value=definition), \
                    self.assertRaisesRegex(ValueError, 'art direction already exists'):
                new_themes.design_theme(repo, {'model': 'fixture'}, {}, repo / 'log', '',
                                        mock.Mock(), history=history)
            self.assertFalse(list((repo / 'alpine/themes').glob('*.json')))

    def test_reused_mix_with_new_ids_is_rejected(self):
        history = prompt_catalog.PaintHistory('unused', [{
            'insertion': 'old-role', 'medium': 'old-medium',
            'insertion_description': 'Space Ghost peers from a shop window.',
            'medium_description': 'Hand glazed ceramic mosaic.'}])
        with self.assertRaisesRegex(ValueError, 'mix has already'):
            prompt_catalog.require_fresh_mix(
                {'id': 'renamed-role', 'description': 'Space Ghost peers from a shop window.'},
                {'id': 'renamed-medium', 'description': 'Hand glazed ceramic mosaic.'}, history)

    def test_theme_design_rejects_a_reused_subject_before_saving_a_theme(self):
        from test_new_themes import NewThemeTests
        definition = NewThemeTests().definition()
        history = prompt_catalog.PaintHistory('unused', [
            {'scene': 'old', 'description': definition['scene']}])
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            def command(work, model):
                (work / 'result.json').write_text(json.dumps(definition))
                return ['codex', '--sandbox', 'workspace-write', '--enable', 'image_generation']
            with mock.patch.object(new_themes.subprocess, 'Popen', return_value=mock.Mock(returncode=0)), \
                    self.assertRaisesRegex(ValueError, 'already been painted'):
                new_themes.design_theme(repo, {'model': 'fixture'}, {}, repo / 'log', '',
                                        command, history=history)
            self.assertFalse(list((repo / 'alpine/themes').glob('*.json')))

    def test_scene_design_receives_prior_subjects_and_produces_new_mix(self):
        history = prompt_catalog.PaintHistory('unused', [
            {'scene': 'old', 'description': 'Space Ghost rows across the Delaware.'}])
        definition = {
            'scene': {'title': 'Orbital laundry', 'description': 'Space Ghost untangles solar sails in a zero-gravity laundromat.'},
            'insertion': {'title': 'Laundry inspector', 'description': 'He checks a cape with a magnifying glass.'},
            'medium': {'title': 'Ceramic mosaic', 'description': 'Hand glazed ceramic tiles with copper grout.'}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            process = mock.Mock(returncode=0)
            def command(work, model):
                (work / 'result.json').write_text(json.dumps(definition))
                return ['codex', '--sandbox', 'workspace-write', '--enable', 'image_generation']
            with mock.patch.object(new_themes.subprocess, 'Popen', return_value=process):
                scene, insertion, medium = new_themes.design_scene(
                    dict(catalog(), model='fixture'), {'name': 'Violet', 'image_style': 'Purple ink.'},
                    history, {}, root / 'log', command)
            prompt = process.communicate.call_args.args[0]
            self.assertIn('rows across the Delaware', prompt)
            self.assertIn('Purple ink.', prompt)
            self.assertIn('Shared style.', prompt)
            self.assertEqual(scene['description'], definition['scene']['description'])
            self.assertEqual(insertion['description'], definition['insertion']['description'])
            self.assertEqual(medium['description'], definition['medium']['description'])

    def test_light_rewording_of_a_scene_is_rejected(self):
        history = prompt_catalog.PaintHistory('unused', [{
            'description': 'Space Ghost drives a crystal locomotive through the rings of Saturn at dusk.'}])
        with self.assertRaisesRegex(ValueError, 'already been painted'):
            prompt_catalog.require_fresh_scene({
                'description': 'Space Ghost drives a crystal locomotive through the rings of Saturn at dawn.'}, history)


if __name__ == '__main__':
    unittest.main()
