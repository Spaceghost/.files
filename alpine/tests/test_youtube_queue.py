from pathlib import Path
import runpy
import unittest
from unittest import mock
import subprocess

MODEL = Path(__file__).resolve().parents[1] / 'desktop/.local/lib/oldbook/youtube_queue.py'


class YoutubeQueueTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(MODEL.exists(), 'YouTube queue model is missing')
        self.model = runpy.run_path(str(MODEL))

    def test_end_requires_a_decision_and_rewatch_does_not_advance(self):
        queue = self.model['Queue']({'entries': [{'url': 'https://youtu.be/one'},
                                               {'url': 'https://youtu.be/two'}]})
        queue.end()
        self.assertEqual(queue.current()['url'], 'https://youtu.be/one')
        self.assertTrue(queue.data['awaiting'])
        queue.decide('rewatch')
        self.assertFalse(queue.data['awaiting'])
        self.assertEqual(queue.data['position'], 0)
        self.assertEqual(queue.current()['url'], 'https://youtu.be/one')

    def test_keep_and_remove_record_different_decisions_and_stop_at_end(self):
        queue = self.model['Queue']({'entries': [{'url': 'https://youtu.be/one'},
                                               {'url': 'https://youtu.be/two'}]})
        queue.decide('keep')
        self.assertEqual(queue.data['entries'][0]['decision'], 'keep')
        self.assertEqual(queue.current()['url'], 'https://youtu.be/two')
        queue.decide('remove')
        self.assertEqual(queue.data['entries'][1]['decision'], 'remove')
        self.assertIsNone(queue.current())
        restored = self.model['Queue'](queue.data)
        self.assertIsNone(restored.current())

    def test_background_exists_only_on_output_showing_workspace_one(self):
        target = self.model['output_for_mode']
        workspaces = [{'num': 1, 'visible': False, 'output': 'eDP-1'},
                      {'num': 6, 'visible': True, 'output': 'eDP-1'}]
        self.assertIsNone(target('desktop', workspaces))
        self.assertEqual(target('pip', workspaces), 'pip')
        workspaces[0]['visible'] = True
        self.assertEqual(target('desktop', workspaces), 'eDP-1')

    def test_empty_playlist_cannot_fall_back_to_mpv_playlist_autoplay(self):
        player = runpy.run_path(str(MODEL.parents[2] / 'bin/oldbook-youtube'))
        empty = subprocess.CompletedProcess([], 0, '{"entries":[],"webpage_url":"https://youtube.com/playlist?list=empty"}', '')
        with mock.patch.object(player['subprocess'], 'run', return_value=empty):
            with self.assertRaisesRegex(RuntimeError, 'No playable videos'):
                player['extract']('https://youtube.com/playlist?list=empty')
