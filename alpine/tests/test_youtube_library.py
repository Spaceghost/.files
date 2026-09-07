import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
MODULE = REPO / 'alpine/desktop/.local/lib/oldbook/youtube_library.py'


class YoutubeLibraryTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(MODULE.exists(), 'YouTube library support is missing')
        spec = importlib.util.spec_from_file_location('youtube_library_test', MODULE)
        self.lib = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.lib)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.lib.ACCOUNT = Path(self.temp.name) / 'account.json'

    def test_browser_selection_stores_reference_only_and_reaches_playback(self):
        self.lib.save_account('firefox:/home/jack/browser-profile')
        saved = json.loads(self.lib.ACCOUNT.read_text())
        self.assertEqual(saved, {'browser': 'firefox:/home/jack/browser-profile'})
        self.assertEqual(self.lib.ACCOUNT.stat().st_mode & 0o777, 0o600)
        self.assertIn('cookies-from-browser=firefox:/home/jack/browser-profile',
                      ' '.join(self.lib.playback_options('https://www.youtube.com/watch?v=abc')))
        self.assertEqual(self.lib.playback_options('/tmp/local-test.mkv'), [])
        self.lib.save_account(None)
        self.assertEqual(self.lib.playback_options('https://youtu.be/abc'), [])

    def test_private_feed_requires_selected_account(self):
        with self.assertRaisesRegex(RuntimeError, 'account'):
            self.lib.fetch('https://www.youtube.com/feed/history', private=True)

    def test_search_is_literal_and_page_normalizes_videos_and_playlists(self):
        payload={'entries':[{'id':'abcdefghijk','title':'A\nvideo','url':'https://www.youtube.com/watch?v=abcdefghijk'},
                            {'title':'Collection','url':'https://www.youtube.com/playlist?list=PLtest'},
                            None, {'title':'bad','url':'https://evil.invalid/foo'}]}
        with mock.patch.object(self.lib.subprocess, 'run', return_value=subprocess.CompletedProcess(
                [],0,json.dumps(payload),'')) as run:
            page=self.lib.fetch('ytsearch51:books; $(touch nope)')
        self.assertEqual([e['kind'] for e in page['entries']], ['video','playlist'])
        self.assertEqual(page['entries'][0]['title'], 'A video')
        self.assertEqual(run.call_args.args[0][-1], 'ytsearch51:books; $(touch nope)')
        self.assertNotIn('--cookies-from-browser', run.call_args.args[0])

    def test_cookie_reference_is_never_sent_to_arbitrary_hosts(self):
        self.lib.save_account('firefox:/home/jack/profile')
        with mock.patch.object(self.lib.subprocess, 'run') as run:
            with self.assertRaises(ValueError):self.lib.fetch('https://youtube.com.evil.invalid/path')
        run.assert_not_called()

    def test_empty_history_is_valid_and_failed_login_is_actionable(self):
        self.lib.save_account('firefox:/home/jack/profile')
        with mock.patch.object(self.lib.subprocess, 'run', return_value=subprocess.CompletedProcess(
                [],0,'{"entries":[]}','')):
            self.assertEqual(self.lib.fetch('https://www.youtube.com/feed/history',private=True)['entries'],[])
        with mock.patch.object(self.lib.subprocess, 'run', return_value=subprocess.CompletedProcess(
                [],1,'','ERROR: Sign in to confirm')):
            with self.assertRaisesRegex(RuntimeError,'Sign in'):
                self.lib.fetch('https://www.youtube.com/feed/history',private=True)

    def test_pagination_fetches_lookahead_without_duplicate_page_boundary(self):
        payload={'entries':[{'title':str(i),'url':f'https://youtu.be/video{i}'} for i in range(51)]}
        with mock.patch.object(self.lib.subprocess,'run',return_value=subprocess.CompletedProcess(
                [],0,json.dumps(payload),'')) as run:
            page=self.lib.fetch('ytsearch51:old books',page=2)
        self.assertEqual(len(page['entries']),50)
        self.assertTrue(page['more'])
        command=run.call_args.args[0]
        self.assertEqual(command[command.index('--playlist-items')+1],'51:101')
        self.assertEqual(command[-1],'ytsearch101:old books')

    def test_browsing_playlist_selects_video_without_loading_playlist_as_video(self):
        import runpy
        player=runpy.run_path(str(REPO / 'alpine/desktop/.local/bin/oldbook-youtube'))
        globals_=player['browse'].__globals__
        pages=[{'entries':[{'url':'https://www.youtube.com/playlist?list=PLone',
                           'title':'Books','channel':'','kind':'playlist'}],'more':False},
               {'entries':[{'url':'https://youtu.be/abcdefghijk','title':'Chapter one',
                            'channel':'','kind':'video'}],'more':False}]
        with mock.patch.dict(globals_,library=self.lib), \
                mock.patch.object(self.lib,'fetch',side_effect=pages), \
                mock.patch.dict(globals_,choose=mock.Mock(side_effect=['01  ▤ Books','01  ▶ Chapter one']),
                                notify=mock.Mock(),request=mock.Mock()) as patched:
            player['browse']('https://www.youtube.com/feed/playlists','Playlists')
            loaded=patched['request'].call_args.kwargs['entries']
        self.assertEqual([entry['url'] for entry in loaded],['https://youtu.be/abcdefghijk'])

    def test_cancel_browsing_preserves_current_queue(self):
        import runpy
        player=runpy.run_path(str(REPO / 'alpine/desktop/.local/bin/oldbook-youtube'))
        with mock.patch.object(player['library'],'fetch',return_value={'entries':[],'more':False}), \
                mock.patch.dict(player['browse'].__globals__,choose=mock.Mock(return_value=None),
                                notify=mock.Mock(),request=mock.Mock()) as patched:
            player['browse']('ytsearch51:books','Search')
            patched['request'].assert_not_called()
