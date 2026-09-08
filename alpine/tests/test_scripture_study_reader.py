"""Study records must survive selection, refresh, and picker scope changes."""
from contextlib import redirect_stdout
import importlib.machinery
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
reader = importlib.machinery.SourceFileLoader(
    'scripture_study_reader_test',
    str(REPO / 'alpine/desktop/.local/bin/mbp-intel-scripture')).load_module()


def entry(kind='inspiration', identifier='study-fixture'):
    return {'id': identifier, 'kind': kind, 'figure': 'Fixture figure',
            'reference': 'John 1:1', 'title': 'Fixture title',
            'trial': 'Fixture context', 'reflection': 'Current fixture body',
            'practice': 'Fixture practice', 'sources': [],
            'provenance': {'method': 'local-ollama'}}


class StudyReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        environment = patch.dict(os.environ, XDG_DATA_HOME=str(self.state / 'data'))
        environment.start()
        self.addCleanup(environment.stop)
        self.bible = reader.scripture.Bible([
            {'book': 'John', 'chapter': 1, 'verse': 1, 'text': 'Fixture passage'}])
        for name, value in (('STATE', self.state),
                            ('SELECTION', self.state / 'selection.json')):
            patcher = patch.object(reader, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(reader, 'refresh_panel')
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_each_study_kind_can_be_selected_and_rendered(self):
        for kind in ('study-note', 'inspiration', 'observation'):
            with self.subTest(kind=kind), \
                    patch.object(reader, 'study_entries', return_value=[entry(kind)], create=True):
                reader.select_reflection(self.bible, 'study-fixture')
                saved = json.loads(reader.SELECTION.read_text())
                self.assertEqual(saved['kind'], kind)
                rendered = io.StringIO()
                with redirect_stdout(rendered):
                    reader.panel(self.bible)
                self.assertIn('Current fixture body', rendered.getvalue())
                self.assertIn('Fixture practice', rendered.getvalue())

    def test_legacy_selection_materializes_current_catalog_text(self):
        stale = dict(entry('reflection'), reflection='Stale selection body')
        reader.SELECTION.write_text(json.dumps(stale))
        with patch.object(reader, 'study_entries', return_value=[entry('reflection')], create=True):
            self.assertEqual(reader.current(self.bible)['reflection'], 'Current fixture body')

    def test_next_wraps_from_study_to_first_preserved_reflection(self):
        entries = [entry('reflection', 'legacy-fixture'), entry()]
        reader.SELECTION.write_text(json.dumps({'kind': 'inspiration', 'id': 'study-fixture'}))
        with patch.object(reader, 'study_entries', return_value=entries, create=True):
            self.assertEqual(reader.next_selection(self.bible), 'legacy-fixture')

    def test_studies_appear_only_in_the_expanded_picker(self):
        with patch.object(reader, 'study_entries', return_value=[entry()], create=True), \
                patch.object(reader.subprocess, 'run',
                             return_value=subprocess.CompletedProcess([], 1, '', '')) as run:
            reader.find(self.bible)
            self.assertNotIn('Fixture title', run.call_args.kwargs['input'])
            reader.find(self.bible, include_all=True)
            rows = run.call_args.kwargs['input']
            self.assertLess(rows.index('Fixture title'), rows.index('John 1:1  Fixture passage'))

    def test_legacy_reflection_id_still_selects_from_the_library(self):
        with patch.object(reader, 'study_entries',
                          return_value=[entry('reflection', 'legacy-fixture')], create=True):
            self.assertEqual(reader.select_reflection(self.bible, 'legacy-fixture'), 'legacy-fixture')
            self.assertEqual(reader.current(self.bible)['kind'], 'reflection')

    def test_equal_titles_remain_individually_selectable(self):
        entries = [entry(identifier='study-first'), entry(identifier='study-second')]
        def choose_first(_command, **arguments):
            rows = arguments['input'].splitlines()
            self.assertEqual(len(rows), 2)
            self.assertNotEqual(rows[0], rows[1])
            return subprocess.CompletedProcess([], 0, rows[0] + '\n', '')
        with patch.object(reader, 'study_entries', return_value=entries), \
                patch.object(reader.subprocess, 'run', side_effect=choose_first), \
                redirect_stdout(io.StringIO()):
            reader.reflections(self.bible)
        self.assertEqual(json.loads(reader.SELECTION.read_text())['id'], 'study-first')


if __name__ == '__main__':
    unittest.main()
