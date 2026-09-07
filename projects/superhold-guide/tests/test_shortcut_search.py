"""Search the actual contextual shortcut choices in stable presentation order."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
try:
    from superhold import shortcut_search as search
except ImportError:
    search = None


def snapshot():
    return {'app': 'Straße Editor', 'sections': [
        {'title': 'Editor shortcuts', 'coverage': 'Partial application profile', 'rows': [
            {'key': 'Alt+Left / Alt+Right', 'description': 'Back / forward', 'actions': [
                {'label': 'Alt+Left', 'sequence': [{'modifiers': ['alt'], 'key': 'Left'}]},
                {'label': 'Alt+Right', 'sequence': [{'modifiers': ['alt'], 'key': 'Right'}]},
            ]},
            {'key': 'Ctrl+Shift+S', 'description': 'Save As', 'actions': [
                {'label': 'Ctrl+Shift+S', 'sequence': [{'modifiers': ['ctrl', 'shift'], 'key': 's'}]}]},
        ]},
        {'title': 'Sway — default', 'coverage': 'Loaded configuration', 'rows': [
            {'key': 'Super+F', 'description': 'Toggle fullscreen', 'actions': [
                {'label': 'Super+F', 'sequence': [{'modifiers': ['logo'], 'key': 'f'}]}]},
            {'key': 'code 42', 'description': 'Physical shortcut', 'actions': [],
             'unavailable_reason': 'Physical keycode bindings require the original keyboard map'},
        ]},
        {'title': 'tmux', 'coverage': 'Live bindings', 'rows': [
            {'key': 'Ctrl+B, c', 'description': 'New window', 'actions': [
                {'label': 'Ctrl+B, c', 'sequence': [
                    {'modifiers': ['ctrl'], 'key': 'b'}, {'modifiers': [], 'key': 'c'}]}]},
        ]},
    ]}


class ShortcutSearchTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(search, 'contextual search is not implemented')

    def test_empty_query_keeps_app_sway_context_order_and_separate_alternatives(self):
        results = search.search_shortcuts(snapshot())
        self.assertEqual([result['key'] for result in results], [
            'Alt+Left', 'Alt+Right', 'Ctrl+Shift+S', 'Super+F', 'code 42', 'Ctrl+B, c'])
        self.assertEqual([result['section'] for result in results], [
            'Editor shortcuts', 'Editor shortcuts', 'Editor shortcuts',
            'Sway — default', 'Sway — default', 'tmux'])
        self.assertEqual(results[1]['action']['sequence'], [{'modifiers': ['alt'], 'key': 'Right'}])
        self.assertEqual(results[1]['source_key'], 'Alt+Left / Alt+Right')
        self.assertEqual((results[1]['section_index'], results[1]['row_index']), (0, 0))
        self.assertIsNone(results[4]['action'])
        self.assertIn('Physical keycode', results[4]['unavailable_reason'])

    def test_tokens_match_across_fields_using_and_not_or(self):
        results = search.search_shortcuts(snapshot(), 'EDITOR save SHIFT')
        self.assertEqual([result['key'] for result in results], ['Ctrl+Shift+S'])
        self.assertEqual(search.search_shortcuts(snapshot(), 'save fullscreen'), [])
        self.assertEqual([r['key'] for r in search.search_shortcuts(snapshot(), 'sway full')], ['Super+F'])

    def test_key_search_selects_the_matching_alternative_only(self):
        results = search.search_shortcuts(snapshot(), 'Alt+Right')
        self.assertEqual([result['key'] for result in results], ['Alt+Right'])

    def test_unicode_casefold_matches_equivalent_app_names(self):
        self.assertEqual(len(search.search_shortcuts(snapshot(), 'STRASSE')), 6)
        self.assertEqual([r['key'] for r in search.search_shortcuts(snapshot(), 'STRASSE screen')], ['Super+F'])

    def test_whitespace_query_is_empty_and_metadata_is_preserved(self):
        results = search.search_shortcuts(snapshot(), ' \t\n')
        self.assertEqual(len(results), 6)
        self.assertEqual(results[0]['app'], 'Straße Editor')
        self.assertEqual(results[0]['coverage'], 'Partial application profile')
        self.assertEqual(results[0]['description'], 'Back / forward')

    def test_search_does_not_modify_snapshot_or_turn_unavailable_rows_into_actions(self):
        document = snapshot()
        before = copy.deepcopy(document)
        results = search.search_shortcuts(document, 'physical')
        self.assertEqual(document, before)
        self.assertEqual(len(results), 1)
        self.assertIsNone(results[0]['action'])

    def test_empty_or_malformed_snapshot_has_no_search_results(self):
        for document in (None, {}, {'sections': None}, {'sections': [None, {'rows': None}]}):
            with self.subTest(document=document):
                self.assertEqual(search.search_shortcuts(document), [])


if __name__ == '__main__':
    unittest.main()
