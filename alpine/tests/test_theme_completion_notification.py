"""Completion notices must describe the saved theme and use its actual painting."""
import json
from pathlib import Path
import subprocess
import unittest
from unittest import mock

import test_new_themes
import test_themed_artwork
from test_wallpapers import generator


class ThemeCompletionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_themed_artwork.ThemedArtworkTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        definition = test_new_themes.NewThemeTests().definition()
        definition['name'] = 'Moonlight & <Brass>'
        self.theme = test_new_themes.new_themes.save_theme(self.fixture.repo, definition, 'fixture only')

    def generate(self, *, activate=True, checkpoint_error=False, activation_error=False,
                 image_error=False):
        events = []

        def external(command, **kwargs):
            if 'use' in command or 'select' in command:
                events.append(command[-2])
                if activation_error:
                    return subprocess.CompletedProcess(command, 1, '', 'fixture activation failure')
            if command[0] == 'notify-send' and any('Theme created' in part for part in command):
                events.append('complete-notification')
                records = list((self.fixture.state / 'manual').glob('*.json'))
                saved = json.loads(records[0].read_text())
                self.assertEqual(saved['status'], 'checkpoint-pending' if checkpoint_error else 'complete')
                if activate and not activation_error:
                    self.assertTrue(saved['activated'])
            return subprocess.CompletedProcess(command, 0, 'Logged in using ChatGPT', '')

        def checkpoint(*_args):
            events.append('checkpoint')
            if checkpoint_error:
                raise RuntimeError('fixture checkpoint failure')
            return 'abc123'

        with mock.patch('new_themes.design_theme', return_value=self.theme), \
                mock.patch.object(generator, 'generate_native', return_value=str(self.fixture.native),
                                  side_effect=RuntimeError('fixture image failure') if image_error else None), \
                mock.patch.object(generator, 'checkpoint_generated', side_effect=checkpoint), \
                mock.patch.object(generator.time, 'sleep'), \
                mock.patch.object(generator.subprocess, 'run', side_effect=external) as run:
            if image_error:
                with self.assertRaisesRegex(RuntimeError, 'fixture image failure'):
                    generator.run_once(manual=True, activate=activate, new_theme='fixture only')
                result = 1
            else:
                result = generator.run_once(manual=True, activate=activate, new_theme='fixture only')
        notices = [call.args[0] for call in run.call_args_list if call.args[0][0] == 'notify-send'
                   and any('Theme created' in part for part in call.args[0])]
        return result, notices, events

    def test_success_names_theme_and_previews_exact_saved_image_after_activation(self):
        result, notices, events = self.generate()
        self.assertEqual(result, 0)
        self.assertEqual(events, ['checkpoint', 'use', 'select', 'complete-notification'])
        self.assertEqual(len(notices), 1)
        self.assertIn('Theme created: Moonlight & <Brass>', notices[0])
        self.assertIn('Moonlight &amp; &lt;Brass&gt;', notices[0][-1])
        saved = json.loads(next((self.fixture.state / 'manual').glob('*.json')).read_text())
        self.assertIn('--hint=string:image-path:' + str(self.fixture.repo / saved['file']), notices[0])
        self.assertIn('now on your desktop', notices[0][-1])

    def test_gallery_only_success_does_not_claim_desktop_activation(self):
        result, notices, events = self.generate(activate=False)
        self.assertEqual(result, 0)
        self.assertEqual(events, ['checkpoint', 'complete-notification'])
        self.assertEqual(len(notices), 1)
        self.assertIn('saved in your gallery', notices[0][-1])
        self.assertNotIn('now on your desktop', notices[0][-1])

    def test_failed_activation_announces_saved_artwork_without_claiming_desktop_switch(self):
        result, notices, _ = self.generate(activation_error=True)
        self.assertEqual(result, 1)
        self.assertEqual(len(notices), 1)
        self.assertIn('saved in your gallery', notices[0][-1])
        self.assertIn('desktop could not switch', notices[0][-1])
        self.assertNotIn('now on your desktop', notices[0][-1])

    def test_pending_checkpoint_announces_saved_artwork_with_accurate_pending_status(self):
        result, notices, _ = self.generate(checkpoint_error=True)
        self.assertEqual(result, 1)
        self.assertEqual(len(notices), 1)
        self.assertIn('now on your desktop', notices[0][-1])
        self.assertIn('checkpoint is pending', notices[0][-1])

    def test_failed_image_does_not_announce_completion(self):
        result, notices, _ = self.generate(image_error=True)
        self.assertEqual(result, 1)
        self.assertFalse(notices)


class NotificationTransportTests(unittest.TestCase):
    def test_image_path_and_titles_remain_literal_arguments(self):
        entry = {'theme_name': 'Gold & <Violet> $(touch /tmp/never)',
                 'title': '<b>Painting & "Moon"</b>',
                 'file': 'alpine/assets/gallery/a painting $(never).png'}
        with mock.patch.object(generator.subprocess, 'run') as run:
            generator.notify_theme_complete(entry, {'status': 'complete', 'activated': True})
        command = run.call_args.args[0]
        self.assertIn('--hint=string:image-path:' + str(generator.REPO / entry['file']), command)
        self.assertIn('<img src="' + (generator.REPO / entry['file']).as_uri() + '"', command[-1])
        self.assertEqual(command[-2], 'Theme created: ' + entry['theme_name'])
        self.assertIn('&lt;b&gt;Painting &amp; &quot;Moon&quot;&lt;/b&gt;', command[-1])
        self.assertNotIn('shell', run.call_args.kwargs)

    def test_unavailable_notifier_does_not_fail_completed_artwork(self):
        for error in (FileNotFoundError('notify-send'), subprocess.TimeoutExpired('notify-send', 5)):
            with self.subTest(error=type(error).__name__), \
                    mock.patch.object(generator.subprocess, 'run', side_effect=error):
                generator.notify('Theme ready: Fixture', 'Fixture painting', image=Path('/tmp/fixture image.png'))


if __name__ == '__main__':
    unittest.main()
