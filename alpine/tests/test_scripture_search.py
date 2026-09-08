"""Inline search keeps collection boundaries and full reference choices."""
import importlib.machinery
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'alpine/desktop/.local/lib/mbp_intel'))
import scripture
from scripture_search import SearchIndex
import scripture_bar_ipc


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.bible = scripture.Bible([
            {'book': 'John', 'chapter': 3, 'verse': 16, 'text': 'God so loved the world'},
            {'book': 'John', 'chapter': 3, 'verse': 17, 'text': 'God sent his Son'},
            {'book': 'Torah Genesis', 'chapter': 1, 'verse': 1, 'text': 'God created'},
            {'book': 'Talmud Berakhot', 'chapter': '2a', 'verse': 1, 'text': 'God is one'},
        ])
        self.studies = [{'id': 'care', 'kind': 'reflection', 'figure': 'A witness',
                         'title': 'God cares', 'reference': 'John 3:16',
                         'reflection': 'Love in suffering'}]

    def test_bible_scope_excludes_other_collections_and_studies(self):
        results = SearchIndex(self.bible, self.studies, 'bible').search('God')
        self.assertEqual([item['reference'] for item in results], ['John 3:16', 'John 3:17'])

    def test_all_scope_preserves_torah_talmud_study_bible_order(self):
        results = SearchIndex(self.bible, self.studies, 'all').search('God')
        self.assertEqual([item['query'] for item in results],
                         ['Torah Genesis 1:1', 'Talmud Berakhot 2a:1', 'care',
                          'John 3:16', 'John 3:17'])

    def test_reflections_scope_retains_reflection_body_search(self):
        results = SearchIndex(self.bible, self.studies, 'reflections').search('suffering')
        self.assertEqual([(item['action'], item['query']) for item in results],
                         [('select-reflection', 'care')])

    def test_reference_range_is_one_complete_selection(self):
        results = SearchIndex(self.bible, [], 'bible').search('Jn 3:16-17')
        self.assertEqual(results[0]['query'], 'John 3:16-17')
        self.assertIn('sent his Son', results[0]['text'])

    def test_words_match_reference_and_text_and_results_are_bounded(self):
        index = SearchIndex(self.bible, [], 'bible')
        self.assertEqual(index.search('john loved')[0]['reference'], 'John 3:16')
        self.assertEqual(len(index.search('', limit=1)), 1)
        self.assertEqual(index.search('missing word'), [])

    def test_bible_cannot_resolve_torah_reference_from_mixed_fixture(self):
        self.assertEqual(SearchIndex(self.bible, [], 'bible').search('Torah Genesis 1:1'), [])

    def test_all_reference_search_keeps_torah_before_bible(self):
        bible = scripture.Bible(self.bible.verses + [
            {'book': 'Genesis', 'chapter': 1, 'verse': 1, 'text': 'In the beginning'}])
        results = SearchIndex(bible, [], 'all').search('Genesis 1:1')
        self.assertEqual([item['reference'] for item in results],
                         ['Torah Genesis 1:1', 'Genesis 1:1'])

    def test_all_range_keeps_matching_study_then_complete_bible_passage(self):
        studies = [dict(self.studies[0], reference='John 3:16-17')]
        index = SearchIndex(self.bible, studies, 'all')
        self.assertEqual([(item['action'], item['query']) for item in index.search('John 3:16-17')],
                         [('select-reflection', 'care'), ('select', 'John 3:16-17')])
        self.assertEqual(len(index.search('John 3:16-17', limit=1)), 1)


class RoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.command = importlib.machinery.SourceFileLoader(
            'inline_scripture_command', str(REPO / 'alpine/desktop/.local/bin/mbp-intel-scripture')).load_module()

    def test_normal_find_requests_existing_inline_bar_without_loading_picker(self):
        with patch.object(sys, 'argv', ['mbp-intel-scripture', 'find']), \
             patch.object(self.command, 'launch_inline', return_value=0, create=True) as inline, \
             patch.object(self.command, 'find') as picker:
            self.assertEqual(self.command.main(), 0)
        inline.assert_called_once_with('bible', '', None)
        picker.assert_not_called()

    def test_all_and_reflections_keep_separate_inline_scopes(self):
        for arguments, scope in [(['find', '--all'], 'all'), (['reflections'], 'reflections')]:
            with self.subTest(scope=scope), patch.object(sys, 'argv', ['mbp-intel-scripture', *arguments]), \
                 patch.object(self.command, 'launch_inline', return_value=0, create=True) as inline:
                self.assertEqual(self.command.main(), 0)
                inline.assert_called_once_with(scope, '', None)

    def test_explicit_picker_flag_keeps_recovery_available(self):
        with patch.object(sys, 'argv', ['mbp-intel-scripture', 'find', '--picker']), \
             patch.object(self.command, 'find', return_value=0) as picker:
            self.assertEqual(self.command.main(), 0)
        picker.assert_called_once()


class ActivationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='scripture-ipc-')
        self.addCleanup(temporary.cleanup)
        environment = patch.dict(os.environ, {'XDG_RUNTIME_DIR': temporary.name,
                                              'SWAYSOCK': temporary.name + '/private-sway.sock'})
        environment.start()
        self.addCleanup(environment.stop)

    def test_request_delivers_query_scope_and_translation_to_existing_daemon(self):
        path = scripture_bar_ipc.endpoint()
        path.parent.mkdir(mode=0o700)
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as server:
            server.bind(str(path))
            server.settimeout(.5)
            self.assertTrue(scripture_bar_ipc.request('all', 'John 3:16', 'asv'))
            self.assertEqual(json.loads(server.recv(4096)),
                             {'scope': 'all', 'query': 'John 3:16', 'translation': 'asv'})

    def test_other_compositor_uses_a_different_endpoint(self):
        first = scripture_bar_ipc.endpoint()
        with patch.dict(os.environ, {'SWAYSOCK': '/another/private-sway.sock'}):
            self.assertNotEqual(first, scripture_bar_ipc.endpoint())

    def test_absent_daemon_is_reported_without_any_picker(self):
        self.assertFalse(scripture_bar_ipc.request())
        with self.assertRaises(ValueError):
            scripture_bar_ipc.request('unknown')


if __name__ == '__main__':
    unittest.main()
