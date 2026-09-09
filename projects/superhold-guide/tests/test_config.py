"""Configuration persistence contracts; no desktop or host files involved."""
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from superhold.config import (SECTION_IDS, AppConfig, ConfigError, SectionLayout,
                              config_path, load_config, save_config)


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / 'superhold/config.json'

    def write(self, document):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(document))

    def test_missing_config_defaults_without_writing(self):
        self.assertEqual(load_config(self.path), AppConfig())
        self.assertFalse(self.path.exists())
        self.assertEqual(AppConfig().dismiss_mode, 'focus_loss')

    def test_xdg_path_uses_absolute_directory_and_falls_back_for_relative(self):
        with mock.patch.dict(os.environ, {'XDG_CONFIG_HOME': self.temporary.name}):
            self.assertEqual(config_path(), self.path)
        with mock.patch.dict(os.environ, {'XDG_CONFIG_HOME': 'relative'}):
            self.assertEqual(config_path(), Path.home() / '.config/superhold/config.json')

    def test_round_trip_writes_private_versioned_file(self):
        config = AppConfig(hold_delay_ms=750, dismiss_mode='release', key_delay_ms=25,
                           release_timeout_ms=8000, profiles_path='~/profiles.json')
        save_config(config, self.path)
        self.assertEqual(load_config(self.path), config)
        self.assertEqual(json.loads(self.path.read_text())['version'], 1)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_unknown_fields_survive_edits(self):
        self.write({'version': 1, 'future': {'enabled': True}, 'hold_delay_ms': 600})
        loaded = load_config(self.path)
        from dataclasses import replace
        save_config(replace(loaded, hold_delay_ms=900), self.path)
        saved = json.loads(self.path.read_text())
        self.assertEqual(saved['future'], {'enabled': True})
        self.assertEqual(saved['hold_delay_ms'], 900)
        save_config(AppConfig(), self.path)
        self.assertEqual(json.loads(self.path.read_text())['future'], {'enabled': True})

    def test_default_section_order_reads_from_the_most_local_context_outward(self):
        self.assertEqual(AppConfig().sections.order, SECTION_IDS)
        self.assertEqual(SECTION_IDS, ('application', 'tmux', 'terminal', 'desktop',
                                       'system', 'diagnostics'))

    def test_sections_order_hidden_titles_and_custom_rows_round_trip(self):
        document = {
            'order': ['system', 'desktop', 'mine'],
            'hidden': ['diagnostics'],
            'titles': {'desktop': 'Window manager'},
            'custom': {'mine': {'title': 'My keys', 'coverage': 'Partial local section',
                                'rows': [{'key': 'Super+G',
                                          'description': 'Grid overlay'}]}},
        }
        self.write({'version': 1, 'sections': document})
        loaded = load_config(self.path)

        self.assertEqual(loaded.sections.order, ('system', 'desktop', 'mine'))
        self.assertEqual(loaded.sections.hidden, ('diagnostics',))
        self.assertEqual(loaded.sections.as_document(), document)
        save_config(loaded, self.path)
        self.assertEqual(load_config(self.path), loaded)
        self.assertEqual(json.loads(self.path.read_text())['sections'], document)

    def test_sections_reject_unknown_names_shadowing_and_untidy_text(self):
        for document in ({'order': ['nope']},
                         {'hidden': 'system'},
                         {'order': ['system', 'system']},
                         {'titles': {'nope': 'Anything'}},
                         {'titles': {'desktop': 'two\nlines'}},
                         {'custom': {'system': {'title': 'Shadow'}}},
                         {'custom': {'mine': {'title': ' padded '}}},
                         {'custom': {'mine': {'coverage': 'Complete coverage'}}},
                         {'custom': {'mine': {'rows': [{'key': 'a'}]}}},
                         {'unknown': []}):
            self.write({'version': 1, 'sections': document})
            with self.subTest(document=document), self.assertRaises(ConfigError):
                load_config(self.path)

    def test_hidden_section_still_accepts_a_title_and_a_place_in_the_order(self):
        layout = SectionLayout.from_document(
            {'order': ['system'], 'hidden': ['system'], 'titles': {'system': 'Machine'}})
        built = {'system': {'title': 'System controls', 'coverage': 'c', 'rows': []},
                 'desktop': {'title': 'Sway', 'coverage': 'c', 'rows': []}}

        self.assertEqual([section['title'] for section in layout.arrange(built)], ['Sway'])

    def test_invalid_types_ranges_versions_and_duplicate_fields_are_rejected(self):
        for document in (
            [], {'version': 2}, {'version': True}, {'hold_delay_ms': True},
            {'hold_delay_ms': 99}, {'hold_delay_ms': 5001}, {'key_delay_ms': -1},
            {'key_delay_ms': 251}, {'release_timeout_ms': 249},
            {'release_timeout_ms': 30001}, {'dismiss_mode': 'forever'},
            {'profiles_path': None}, {'profiles_path': 'relative.json'},
            {'profiles_path': '~missing-account/profiles.json'},
            {'profiles_path': '/tmp/invalid\x00.json'},
        ):
            with self.subTest(document=document):
                self.write(document)
                with self.assertRaises(ConfigError):
                    load_config(self.path)
        self.path.write_text('{"hold_delay_ms": 500, "hold_delay_ms": 900}')
        with self.assertRaises(ConfigError):
            load_config(self.path)
        self.path.write_text('{"hold_delay_ms": ' + '9' * 5000 + '}')
        with self.assertRaises(ConfigError):
            load_config(self.path)

    def test_malformed_file_is_preserved_when_saving(self):
        self.path.parent.mkdir()
        original = '{ unfinished JSON'
        self.path.write_text(original)
        with self.assertRaises(ConfigError):
            save_config(AppConfig(), self.path)
        self.assertEqual(self.path.read_text(), original)

    def test_invalid_config_cannot_be_saved(self):
        with self.assertRaises(ConfigError):
            save_config(AppConfig(hold_delay_ms=False), self.path)
        self.assertFalse(self.path.exists())

    def test_symlink_is_refused_without_touching_target(self):
        self.path.parent.mkdir()
        target = self.path.parent / 'original.json'
        target.write_text('{"hold_delay_ms": 650}')
        self.path.symlink_to(target)
        with self.assertRaises(ConfigError):
            load_config(self.path)
        with self.assertRaises(ConfigError):
            save_config(AppConfig(), self.path)
        self.assertEqual(target.read_text(), '{"hold_delay_ms": 650}')
        self.assertTrue(self.path.is_symlink())

    def test_oversized_and_non_regular_files_are_rejected(self):
        self.path.parent.mkdir()
        self.path.write_text(' ' * 65537)
        with self.assertRaises(ConfigError):
            load_config(self.path)
        self.path.unlink()
        os.mkfifo(self.path)
        with self.assertRaises(ConfigError):
            load_config(self.path)

    def test_replace_failure_preserves_existing_file_and_removes_temporary_file(self):
        save_config(AppConfig(), self.path)
        original = self.path.read_bytes()
        with mock.patch('superhold.config.os.replace', side_effect=OSError('read only')):
            with self.assertRaises(ConfigError):
                save_config(AppConfig(hold_delay_ms=700), self.path)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])


if __name__ == '__main__':
    unittest.main()
