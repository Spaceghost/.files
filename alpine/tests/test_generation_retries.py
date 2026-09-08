"""Retry model work without repeating completed artwork or desktop changes."""
import json
import subprocess
import unittest
from unittest import mock

from test_wallpapers import generator
import test_themed_artwork as themed
import test_new_themes as themes


class GenerationRetryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = themed.ThemedArtworkTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.stack.enter_context(mock.patch.object(generator.time, 'sleep'))
        self.fixture.stack.enter_context(mock.patch.object(generator, 'notify'))
        self.fixture.stack.enter_context(mock.patch.object(
            generator.subprocess, 'run', return_value=subprocess.CompletedProcess(
                [], 0, 'Logged in using ChatGPT', '')))

    def record(self, manual=True):
        folder = self.fixture.state / 'manual' if manual else self.fixture.state
        paths = [p for p in folder.glob('*.json') if p.name != 'history.json']
        self.assertEqual(len(paths), 1)
        return json.loads(paths[0].read_text())

    def test_third_retry_saves_one_image_and_keeps_designed_name(self):
        theme = themes.new_themes.save_theme(self.fixture.repo, themes.NewThemeTests().definition(), 'moon books')
        logs = []
        def paint(config, prompt, env, log):
            logs.append(log)
            log.write_text('attempt ' + str(len(logs)))
            if len(logs) < 4:
                raise RuntimeError('Codex did not produce a native generated image')
            return str(self.fixture.native)
        with mock.patch('new_themes.design_theme', return_value=theme) as design, \
                mock.patch.object(generator, 'generate_native', side_effect=paint), \
                mock.patch.object(generator, 'checkpoint_generated', return_value='saved'):
            self.assertEqual(generator.run_once(manual=True, activate=True, new_theme='moon books'), 0)
        saved = self.record()
        self.assertEqual(saved['status'], 'complete')
        self.assertEqual(saved['theme_name'], 'Moonlit Library')
        self.assertTrue(saved['activated'])
        self.assertEqual(saved['attempts'], {'theme': 1, 'image': 4})
        self.assertEqual(len(saved['attempt_errors']), 3)
        self.assertEqual(len(set(logs)), 4)
        self.assertEqual([p.read_text() for p in logs], ['attempt 1', 'attempt 2', 'attempt 3', 'attempt 4'])
        self.assertEqual(len(list((self.fixture.repo / 'alpine/assets/gallery').rglob('*.png'))), 1)
        design.assert_called_once()

    def test_exhausted_daily_generation_stops_after_three_retries(self):
        with mock.patch.object(generator, 'generate_native', side_effect=RuntimeError('no image')) as paint:
            with self.assertRaisesRegex(RuntimeError, 'no image'):
                generator.run_once()
            self.assertEqual(paint.call_count, 4)
            self.assertEqual(generator.run_once(), 0)
            self.assertEqual(paint.call_count, 4)
        saved = self.record(manual=False)
        self.assertEqual(saved['status'], 'failed')
        self.assertEqual(saved['attempts'], {'image': 4})
        self.assertEqual(len(saved['attempt_errors']), 4)
        self.assertNotIn('file', saved)

    def test_failed_theme_design_retries_before_painting(self):
        theme = themes.new_themes.save_theme(self.fixture.repo, themes.NewThemeTests().definition(), 'moon books')
        with mock.patch('new_themes.design_theme', side_effect=[ValueError('bad JSON'), theme]), \
                mock.patch.object(generator, 'generate_native', return_value=str(self.fixture.native)), \
                mock.patch.object(generator, 'checkpoint_generated', return_value='saved'):
            self.assertEqual(generator.run_once(manual=True, new_theme='moon books'), 0)
        self.assertEqual(self.record()['attempts'], {'theme': 2, 'image': 1})

    def test_invalid_image_retries_and_checkpoint_failure_does_not_repaint(self):
        bad = self.fixture.native.parent / 'bad.png'
        bad.write_text('not an image')
        with mock.patch.object(generator, 'generate_native', side_effect=[str(bad), str(self.fixture.native)]) as paint, \
                mock.patch.object(generator, 'checkpoint_generated', side_effect=RuntimeError('checkout busy')):
            self.assertEqual(generator.run_once(manual=True), 1)
        self.assertEqual(paint.call_count, 2)
        saved = self.record()
        self.assertEqual(saved['status'], 'checkpoint-pending')
        self.assertEqual(saved['attempts'], {'image': 2})
        self.assertTrue((self.fixture.repo / saved['file']).is_file())

    def test_malformed_native_result_is_reported_as_a_retryable_failure(self):
        for answer in ([], {'image_path': []}, {'image_path': 42}):
            with self.subTest(answer=answer):
                def command(work, model):
                    (work / 'result.json').write_text(json.dumps(answer))
                    return ['codex']
                with mock.patch.object(generator, 'codex_command', side_effect=command), \
                        mock.patch.object(generator.subprocess, 'Popen', return_value=mock.Mock(returncode=0)):
                    with self.assertRaisesRegex(RuntimeError, 'native generated image'):
                        generator.generate_native({'model': 'fixture'}, 'moon', {}, self.fixture.root / 'native.log')
