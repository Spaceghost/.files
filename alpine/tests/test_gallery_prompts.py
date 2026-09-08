"""Prompt editor tests use disposable prompt files, never the live catalog."""
import json
import os
from pathlib import Path
import runpy
import stat
import tempfile
import unittest


HELPER = (Path(__file__).resolve().parents[1]
          / 'desktop/.local/bin/mbp-intel-gallery-prompts')


class GalleryPromptDocumentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mbp-intel-prompts-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'prompts.json'
        self.backups = self.root / 'state/prompt-backups'
        self.original = (
            b'{\n'
            b'  "model": "image-model",\n'
            b'  "timeout_seconds": 91,\n'
            b'  "style": "Old style",\n'
            b'  "unknown_top": {"keep": true},\n'
            b'  "scenes": [\n'
            b'    {"id": "first", "title": "First", "description": "One", '
            b'"unknown_scene": 7},\n'
            b'    {"id": "second", "title": "Second", "description": "Two"}\n'
            b'  ]\n'
            b'}\n')
        self.path.write_bytes(self.original)
        self.path.chmod(0o640)

    def module(self):
        self.assertTrue(HELPER.is_file(), 'prompt editor helper is missing')
        return runpy.run_path(str(HELPER))

    def test_save_changes_only_editable_fields_and_backs_up_exact_bytes(self):
        module = self.module()
        document = module['PromptDocument'].load(self.path, self.backups)

        document.set_style('New shared style')
        document.update_scene('first', 'Changed title', 'Changed description')
        document.save()

        saved = json.loads(self.path.read_text())
        self.assertEqual(saved, {
            'model': 'image-model',
            'timeout_seconds': 91,
            'style': 'New shared style',
            'unknown_top': {'keep': True},
            'scenes': [
                {'id': 'first', 'title': 'Changed title',
                 'description': 'Changed description', 'unknown_scene': 7},
                {'id': 'second', 'title': 'Second', 'description': 'Two'},
            ],
        })
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o640)
        backups = list(self.backups.iterdir())
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), self.original)
        self.assertEqual(stat.S_IMODE(backups[0].stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.backups.stat().st_mode), 0o700)

    def test_external_change_refuses_overwrite_and_creates_no_backup(self):
        module = self.module()
        document = module['PromptDocument'].load(self.path, self.backups)
        document.set_style('Editor change')
        external = b'{"style":"external","scenes":[],"new_field":42}\n'
        self.path.write_bytes(external)

        with self.assertRaisesRegex(module['FileChangedError'], 'changed outside'):
            document.save()

        self.assertEqual(self.path.read_bytes(), external)
        self.assertFalse(self.backups.exists())

    def test_closing_without_save_leaves_source_and_backup_untouched(self):
        module = self.module()
        document = module['PromptDocument'].load(self.path, self.backups)
        document.set_style('Unsaved style')
        document.update_scene('second', 'Unsaved title', 'Unsaved description')

        del document

        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertFalse(self.backups.exists())


class GalleryPromptBankTests(unittest.TestCase):
    """Scenes and insertions can be switched off and re-ordered without data loss."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mbp-intel-banks-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'prompts.json'
        self.backups = self.root / 'state/prompt-backups'
        self.path.write_text(json.dumps({
            'style': 'Shared style',
            'scene_selection': 'shuffle',
            'scenes': [
                {'id': 'first', 'title': 'First', 'description': 'One', 'extra': 1},
                {'id': 'second', 'title': 'Second', 'description': 'Two'},
            ],
            'insertions': [
                {'id': 'cameo', 'title': 'Cameo', 'description': 'Small'},
                {'id': 'statue', 'title': 'Statue', 'description': 'Stone'},
            ],
        }, indent=2) + '\n')

    def document(self):
        module = runpy.run_path(str(HELPER))
        return module, module['PromptDocument'].load(self.path, self.backups)

    def test_switching_a_scene_off_is_saved_and_keeps_its_wording(self):
        _module, document = self.document()
        document.set_enabled('scenes', 'first', False)
        document.save()

        saved = json.loads(self.path.read_text())
        self.assertFalse(saved['scenes'][0]['enabled'])
        self.assertEqual(saved['scenes'][0]['description'], 'One')
        self.assertEqual(saved['scenes'][0]['extra'], 1, 'unknown scene fields must survive')
        self.assertNotIn('enabled', saved['scenes'][1])

    def test_selection_modes_round_trip(self):
        _module, document = self.document()
        document.set_selection_mode('scenes', 'rotate')
        document.set_selection_mode('insertions', 'random')
        document.save()

        saved = json.loads(self.path.read_text())
        self.assertEqual(saved['scene_selection'], 'rotate')
        self.assertEqual(saved['insertion_selection'], 'random')

    def test_insertions_are_editable_like_scenes(self):
        _module, document = self.document()
        self.assertEqual([entry['id'] for entry in document.insertions], ['cameo', 'statue'])
        document.update_entry('insertions', 'statue', 'Bronze', 'Cast in bronze')
        document.save()

        saved = json.loads(self.path.read_text())
        self.assertEqual(saved['insertions'][1],
                         {'id': 'statue', 'title': 'Bronze', 'description': 'Cast in bronze'})

    def test_refuses_to_save_with_every_scene_switched_off(self):
        _module, document = self.document()
        for identifier in ('first', 'second'):
            document.set_enabled('scenes', identifier, False)
        with self.assertRaises(ValueError):
            document.save()
        self.assertNotIn('enabled', json.loads(self.path.read_text())['scenes'][0])

    def test_rejects_an_unknown_selection_mode(self):
        _module, document = self.document()
        with self.assertRaises(ValueError):
            document.set_selection_mode('scenes', 'occasionally')

    def test_unknown_entry_is_reported(self):
        _module, document = self.document()
        with self.assertRaises(KeyError):
            document.set_enabled('scenes', 'missing', False)



if __name__ == '__main__':
    unittest.main()
