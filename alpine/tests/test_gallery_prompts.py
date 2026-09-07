"""Prompt editor tests use disposable prompt files, never the live catalog."""
import json
import os
from pathlib import Path
import runpy
import stat
import tempfile
import unittest


HELPER = (Path(__file__).resolve().parents[1]
          / 'desktop/.local/bin/oldbook-gallery-prompts')


class GalleryPromptDocumentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='oldbook-prompts-test-')
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


if __name__ == '__main__':
    unittest.main()
