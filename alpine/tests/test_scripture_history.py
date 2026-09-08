"""Durable Scripture history, hourly transactions and offline reader navigation."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, redirect_stdout
import importlib.machinery
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'alpine/desktop/.local/lib/oldbook'))
import scripture_history as history
from scripture_history_reader import Reader


def passage(number=1):
    return {'kind': 'study-note', 'id': 'fixture-' + str(number), 'reference': f'John 1:{number}',
            'text': f'Complete passage {number}', 'reflection': 'Complete study body',
            'sources': [{'title': 'Source', 'text': 'Complete source quotation',
                         'url': 'https://example.invalid/source', 'license': 'Fixture license'}],
            'provenance': {'method': 'fixture', 'model': 'No model was called'}}


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / 'history.sqlite3'

    def test_hourly_advance_is_not_a_repaint_and_does_not_backfill_sleep(self):
        initial = history.advance(lambda: passage(), lambda old: passage(2), self.database, now=100)
        same = history.advance(lambda: passage(99), lambda old: passage(2), self.database, now=3699)
        self.assertEqual(initial['id'], same['id'])
        second = history.advance(lambda: passage(), lambda old: passage(2), self.database, now=3700)
        self.assertEqual(second['document']['reference'], 'John 1:2')
        self.assertEqual(second['reason'], 'hourly')
        history.advance(lambda: passage(), lambda old: passage(3), self.database, now=40000)
        self.assertEqual(len(history.entries(self.database)), 3)

    def test_manual_selection_resets_hour_and_duplicate_replays_keep_one_record(self):
        first = history.select(passage(), self.database, now=0)
        duplicate = history.select(passage(), self.database, now=3500)
        self.assertEqual(first['id'], duplicate['id'])
        self.assertEqual(duplicate['next_at'], 7100)
        selected = history.advance(lambda: passage(), lambda old: passage(2), self.database, now=3600)
        self.assertEqual(selected['id'], first['id'])
        self.assertEqual(len(history.entries(self.database)), 1)

    def test_snapshot_and_additions_survive_catalog_cache_rebuild(self):
        original = passage()
        chosen = history.select(original, self.database, now=100)
        original['sources'][0]['text'] = 'Changed source'
        cache = self.database.with_name('study.sqlite3')
        cache.write_bytes(b'disposable cache recreated elsewhere')
        extra = {'text': 'Additional research', 'license': 'Fixture license',
                 'provenance': {'method': 'user-supplied', 'model': 'fixture'}}
        addition = history.append(chosen['id'], extra, kind='research', database=self.database, now=120)
        self.assertEqual(history.append(chosen['id'], extra, kind='research', database=self.database, now=121), addition)
        saved = history.get(chosen['id'], self.database)
        self.assertEqual(saved['document']['sources'][0]['text'], 'Complete source quotation')
        self.assertEqual(len(saved['additions']), 1)
        self.assertEqual(saved['additions'][0]['document'], extra)
        with closing(sqlite3.connect(self.database)) as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('DELETE FROM entries')
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE additions SET document='{}'")

    def test_concurrent_hourly_refreshes_advance_only_once(self):
        history.select(passage(), self.database, now=100)
        def update(_):
            return history.advance(lambda: passage(), lambda old: passage(int(old['reference'].split(':')[-1]) + 1),
                                   self.database, now=3700)['id']
        with ThreadPoolExecutor(max_workers=8) as pool:
            identifiers = list(pool.map(update, range(16)))
        self.assertEqual(len(set(identifiers)), 1)
        self.assertEqual(len(history.entries(self.database)), 2)

    def test_return_walks_back_along_the_reading_path_without_editing_history(self):
        history.select(passage(), self.database, now=100)
        for number, now in ((2, 3700), (3, 7400)):
            history.advance(lambda: passage(), lambda old, n=number: passage(n), self.database, now=now)
        returned = history.retreat(self.database, now=7500)
        self.assertEqual(returned['document']['reference'], 'John 1:2')
        self.assertEqual((returned['reason'], returned['next_at']), ('manual-previous', 11100))
        self.assertEqual(history.retreat(self.database, now=7600)['document']['reference'], 'John 1:1')
        self.assertIsNone(history.retreat(self.database, now=7700))
        forward = history.advance(lambda: passage(), lambda old: passage(2), self.database, now=7800, force=True)
        self.assertEqual(forward['document']['reference'], 'John 1:2')
        # A return after Next goes back to where Next started, not to the newest older row.
        self.assertEqual(history.retreat(self.database, now=7900)['document']['reference'], 'John 1:1')
        self.assertIsNone(history.retreat(self.database, now=8000))
        rows = history.entries(self.database)
        self.assertEqual([row['document']['reference'] for row in reversed(rows)],
                         ['John 1:1', 'John 1:2', 'John 1:3', 'John 1:2', 'John 1:1', 'John 1:2', 'John 1:1'])
        self.assertEqual(history.current(self.database)['id'], rows[0]['id'])
        self.assertEqual(history.get(rows[-1]['id'], self.database)['document'], passage())

    def test_return_passes_repeated_passages_without_looping(self):
        for number, now in ((1, 100), (2, 200), (1, 300), (3, 400)):
            history.select(passage(number), self.database, now=now)
        references = []
        while len(references) < 10:
            returned = history.retreat(self.database, now=500 + len(references))
            if returned is None:
                break
            references.append(returned['document']['reference'])
        self.assertEqual(references, ['John 1:1', 'John 1:2', 'John 1:1'])
        self.assertEqual(len(history.entries(self.database)), 7)

    def test_history_navigation_preserves_notes_and_full_text(self):
        first = history.select(passage(), self.database, now=1)
        second = history.select(passage(2), self.database, now=2)
        reader = Reader(self.database)
        self.assertEqual(reader.latest()['id'], second['id'])
        self.assertEqual(reader.move('older')['id'], first['id'])
        reader.add('A personal note', source_url='https://example.invalid/note')
        self.assertIn('A personal note', history.render(reader.read()))
        self.assertIn('Complete source quotation', history.render(reader.read()))
        self.assertEqual(reader.move('older')['id'], first['id'])
        self.assertEqual(reader.move('newer')['id'], second['id'])
        self.assertFalse(reader.read()['additions'])

    def test_backup_is_consistent_independent_and_never_overwritten(self):
        first = history.select(passage(), self.database, now=1)
        history.append(first['id'], {'text': 'Saved note'}, database=self.database)
        backup = self.database.with_name('backup.sqlite3')
        history.backup(backup, self.database)
        history.select(passage(2), self.database, now=2)
        self.assertEqual(len(history.entries(backup)), 1)
        self.assertEqual(history.get(first['id'], backup)['additions'][0]['document']['text'], 'Saved note')
        with self.assertRaises(FileExistsError):
            history.backup(backup, self.database)
        self.assertEqual(backup.stat().st_mode & 0o777, 0o600)

    def test_reading_view_uses_attribution_without_duplicate_verse_records_or_internal_hashes(self):
        document = dict(passage(), passage_records=[{'text': 'Do not duplicate the individual verse records'}])
        document['sources'][0]['sha256'] = 'internal-source-hash'
        chosen = history.select(document, self.database, now=1)
        text = history.render(history.get(chosen['id'], self.database))
        self.assertIn('Complete passage 1', text)
        self.assertIn('Source: Source', text)
        self.assertIn('https://example.invalid/source', text)
        self.assertIn('License: Fixture license', text)
        self.assertIn('Method: fixture', text)
        self.assertNotIn('Do not duplicate', text)
        self.assertNotIn('internal-source-hash', text)
        self.assertNotIn('fingerprint', text)

    def test_foreign_or_corrupt_databases_are_preserved_and_rejected(self):
        with closing(sqlite3.connect(self.database)) as db:
            db.execute('CREATE TABLE personal(data TEXT)')
        before = self.database.read_bytes()
        with self.assertRaises(ValueError):
            history.entries(self.database)
        self.assertEqual(self.database.read_bytes(), before)
        corrupt = self.database.with_name('corrupt.sqlite3')
        corrupt.write_bytes(b'not a database')
        with self.assertRaises(sqlite3.DatabaseError):
            history.entries(corrupt)
        self.assertEqual(corrupt.read_bytes(), b'not a database')


class CommandHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        environment = patch.dict(os.environ, XDG_DATA_HOME=str(self.root / 'data'))
        environment.start()
        self.addCleanup(environment.stop)
        self.helper = importlib.machinery.SourceFileLoader('scripture_history_command_test',
            str(REPO / 'alpine/desktop/.local/bin/oldbook-scripture')).load_module()
        for key, value in [('STATE', self.root / 'state'), ('SELECTION', self.root / 'state/selection.json')]:
            replacement = patch.object(self.helper, key, value)
            replacement.start()
            self.addCleanup(replacement.stop)
        replacement = patch.object(self.helper, 'refresh_panel')
        self.refresh = replacement.start()
        self.addCleanup(replacement.stop)
        replacement = patch.object(self.helper, 'scripture_panel_running', return_value=True)
        replacement.start()
        self.addCleanup(replacement.stop)
        self.bible = self.helper.scripture.Bible([
            {'book': 'John', 'chapter': 1, 'verse': number, 'text': f'Full text {number}'}
            for number in (1, 2, 3)])

    def test_manual_selection_then_hourly_panel_keeps_full_history(self):
        with patch.object(history.time, 'time', return_value=100):
            self.helper.select_reference(self.bible, 'John 1:1')
        self.refresh.assert_called_once_with()
        with patch.object(history.time, 'time', return_value=3699):
            self.assertEqual(self.helper.current(self.bible)['reference'], 'John 1:1')
        with patch.object(history.time, 'time', return_value=3700):
            self.assertEqual(self.helper.current(self.bible)['reference'], 'John 1:2')
        rows = history.entries()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[-1]['document']['passage_records'][0]['text'], 'Full text 1')
        self.assertEqual(json.loads(self.helper.SELECTION.read_text())['reference'], 'John 1:2')

    def test_study_snapshot_keeps_sources_and_generated_provenance(self):
        study = passage()
        with patch.object(self.helper, 'study_entries', return_value=[study]):
            self.helper.select_reflection(self.bible, study['id'])
        saved = history.entries()[0]['document']
        self.assertEqual(saved['sources'], study['sources'])
        self.assertEqual(saved['provenance'], study['provenance'])
        self.assertEqual(saved['text'], 'Full text 1')

    def test_explicit_next_at_hour_boundary_advances_once(self):
        with patch.object(history.time, 'time', return_value=100):
            self.helper.select_reference(self.bible, 'John 1:1')
        with patch.object(history.time, 'time', return_value=3700):
            self.assertEqual(self.helper.next_selection(self.bible), 'John 1:2')
        self.assertEqual(len(history.entries()), 2)

    def test_previous_returns_to_the_earlier_passage_and_refreshes_only_then(self):
        with patch.object(history.time, 'time', return_value=100):
            self.helper.select_reference(self.bible, 'John 1:1')
        with patch.object(history.time, 'time', return_value=200):
            self.assertEqual(self.helper.next_selection(self.bible), 'John 1:2')
        self.refresh.reset_mock()
        with patch.object(history.time, 'time', return_value=300):
            self.assertEqual(self.helper.previous_selection(self.bible), 'John 1:1')
        self.refresh.assert_called_once_with()
        selection = json.loads(self.helper.SELECTION.read_text())
        self.assertEqual((selection['reference'], selection['next_at']), ('John 1:1', 3900))
        self.assertEqual(len(history.entries()), 3)
        with patch.object(history.time, 'time', return_value=400):
            self.assertIsNone(self.helper.previous_selection(self.bible))
        self.refresh.assert_called_once_with()
        self.assertEqual(len(history.entries()), 3)

    def test_clock_refreshes_only_due_card_independently_of_conky_cache(self):
        with patch.object(history.time, 'time', return_value=100):
            self.helper.select_reference(self.bible, 'John 1:1')
            with redirect_stdout(io.StringIO()):
                self.helper.panel(self.bible)
        self.refresh.reset_mock()
        with patch.object(history.time, 'time', return_value=3699):
            self.helper.tick(self.bible)
        self.refresh.assert_not_called()
        with patch.object(history.time, 'time', return_value=3700):
            self.helper.tick(self.bible)
            with redirect_stdout(io.StringIO()):
                self.helper.panel(self.bible)
            self.helper.tick(self.bible)
        self.refresh.assert_called_once_with()
        self.assertEqual(len(history.entries()), 2)

    def test_failed_hourly_render_retries_without_advancing_history_again(self):
        with patch.object(history.time, 'time', return_value=100):
            self.helper.select_reference(self.bible, 'John 1:1')
            with redirect_stdout(io.StringIO()):
                self.helper.panel(self.bible)
        self.refresh.reset_mock()
        self.refresh.side_effect = RuntimeError('Desktop layout is busy')
        with patch.object(history.time, 'time', return_value=3700):
            with self.assertRaisesRegex(RuntimeError, 'layout is busy'):
                self.helper.tick(self.bible)
        self.refresh.side_effect = None
        with patch.object(history.time, 'time', return_value=3760):
            self.helper.tick(self.bible)
        self.assertEqual(self.refresh.call_count, 2)
        self.assertEqual(len(history.entries()), 2)

    def test_clock_retries_an_absent_card_without_changing_selected_passage(self):
        with patch.object(history.time, 'time', return_value=100):
            self.helper.select_reference(self.bible, 'John 1:1')
            with redirect_stdout(io.StringIO()):
                self.helper.panel(self.bible)
        self.refresh.reset_mock()
        with patch.object(history.time, 'time', return_value=200), \
                patch.object(self.helper, 'scripture_panel_running', return_value=False):
            self.helper.tick(self.bible)
        self.refresh.assert_called_once_with()
        self.assertEqual(len(history.entries()), 1)

    def test_delayed_json_mirror_cannot_restore_older_selection(self):
        previous = history.select(passage(), now=100)
        latest = history.select(passage(2), now=200)
        self.helper.mirror_selection(latest)
        self.helper.mirror_selection(previous)
        self.assertEqual(json.loads(self.helper.SELECTION.read_text())['history_id'], latest['id'])

    def test_legacy_timestamp_is_retained_without_backdating_observation(self):
        self.helper.STATE.mkdir()
        self.helper.SELECTION.write_text(json.dumps({'kind': 'passage', 'reference': 'John 1:1',
            'text': 'Original saved text', 'chosen_utc': '2026-01-01T00:00:00Z'}))
        with patch.object(history.time, 'time', return_value=100):
            self.helper.current(self.bible)
        entry = history.entries()[0]
        self.assertEqual(entry['selected_at'], 100)
        self.assertEqual(entry['document']['legacy_chosen_utc'], '2026-01-01T00:00:00Z')


class CardRecoveryTests(unittest.TestCase):
    def test_missing_scripture_pid_revives_only_its_existing_layout(self):
        helper = importlib.machinery.SourceFileLoader('scripture_recovery_command_test',
            str(REPO / 'alpine/desktop/.local/bin/oldbook-scripture')).load_module()
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            conky = home / '.local/state/oldbook/conky'
            conky.mkdir(parents=True)
            config = conky / 'scripture.conf'
            config.write_text('existing placement and theme')
            (conky / 'pids.json').write_text(json.dumps({'scripture': 123456, 'gallery': 654321}))
            with patch.object(helper.Path, 'home', return_value=home), \
                    patch.object(helper.os, 'pidfd_open', side_effect=ProcessLookupError), \
                    patch.object(helper.subprocess, 'Popen', return_value=SimpleNamespace(pid=4321)) as launch, \
                    patch.object(helper.signal, 'pidfd_send_signal') as signal_process:
                helper.refresh_panel()
                self.assertEqual(launch.call_args.args[0], ['conky', '-c', str(config)])
                signal_process.assert_not_called()
                self.assertEqual(json.loads((conky / 'pids.json').read_text()), {'scripture': 4321, 'gallery': 654321})
                self.assertEqual(config.read_text(), 'existing placement and theme')
                (conky / 'disabled').touch()
                launch.reset_mock()
                helper.refresh_panel()
                launch.assert_not_called()



if __name__ == '__main__':
    unittest.main()
