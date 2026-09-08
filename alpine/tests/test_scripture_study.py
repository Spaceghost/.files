from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'alpine/desktop/.local/lib/mbp_intel'))
import scripture_study as study


class StudyStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mbp-intel-study-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.assets = self.root / 'alpine/assets/scripture'
        self.entries = self.assets / 'study/entries'
        self.entries.mkdir(parents=True)
        self.database = self.root / 'data/study.sqlite3'
        self.legacy = {
            'id': 'legacy-one',
            'figure': 'A figure',
            'title': 'Legacy title',
            'reference': 'Book 1:1',
            'trial': 'Legacy trial',
            'reflection': 'Legacy reflection',
            'practice': 'Legacy practice',
        }
        (self.assets / 'reflections.json').write_text(
            json.dumps({'reflections': [self.legacy]}) + '\n')

    @staticmethod
    def generated(identifier='study-0123456789abcdef0123456789abcdef'):
        source_text = 'A quoted source excerpt.'
        return {
            'schema': 1,
            'id': identifier,
            'kind': 'study-note',
            'figure': '',
            'title': 'A generated note',
            'reference': 'Book 2:3',
            'trial': '',
            'reflection': 'An observation grounded in the cited source.',
            'practice': '',
            'cited_source_ids': ['source-1'],
            'sources': [{
                'id': 'source-1',
                'title': 'Source title',
                'url': 'https://example.test/source',
                'license': 'Public domain',
                'text': source_text,
                'sha256': hashlib.sha256(source_text.encode()).hexdigest(),
            }],
            'provenance': {
                'method': 'local-ollama',
                'model': 'example-model',
                'model_digest': 'sha256:' + 'a' * 64,
                'endpoint': 'http://127.0.0.1:11434',
                'created_utc': '2026-09-07T12:34:56Z',
                'prompt_sha256': 'b' * 64,
            },
        }

    def write_generated(self, entry=None):
        entry = entry or self.generated()
        path = self.entries / f"{entry['id']}.json"
        path.write_text(json.dumps(entry, indent=2) + '\n')
        return path

    def test_load_preserves_legacy_order_and_materializes_valid_generated_entries(self):
        generated = self.generated()
        self.write_generated(generated)

        found = study.load_entries(self.assets, self.database)

        expected_legacy = dict(self.legacy, kind='reflection')
        self.assertEqual(found, [expected_legacy, generated])
        self.assertTrue(self.database.is_file())
        self.assertEqual(self.database.stat().st_mode & 0o777, 0o600)
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT id, kind FROM entries ORDER BY position').fetchall(),
                             [('legacy-one', 'reflection'), (generated['id'], 'study-note')])

    def test_unchanged_sources_are_read_without_rewriting_the_database(self):
        self.write_generated()
        first = study.load_entries(self.assets, self.database)
        initial_mtime = self.database.stat().st_mtime_ns
        os.utime(self.database, ns=(initial_mtime - 1_000_000_000,
                                    initial_mtime - 1_000_000_000))
        preserved_mtime = self.database.stat().st_mtime_ns

        second = study.load_entries(self.assets, self.database)

        self.assertEqual(second, first)
        self.assertEqual(self.database.stat().st_mtime_ns, preserved_mtime)

    def test_deleting_a_canonical_entry_rebuilds_the_database(self):
        path = self.write_generated()
        study.load_entries(self.assets, self.database)
        path.unlink()

        found = study.load_entries(self.assets, self.database)

        self.assertEqual(found, [dict(self.legacy, kind='reflection')])
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM entries').fetchone()[0], 1)

    def test_corrupt_changed_source_leaves_the_last_good_database_intact(self):
        path = self.write_generated()
        expected = study.load_entries(self.assets, self.database)
        snapshot = self.database.read_bytes()
        path.write_text('{broken json\n')

        with self.assertRaisesRegex(ValueError, 'Unreadable study entry'):
            study.load_entries(self.assets, self.database)

        self.assertEqual(self.database.read_bytes(), snapshot)
        path.unlink()
        self.assertEqual(study.load_entries(self.assets, self.database),
                         [expected[0]])

    def test_generated_entries_require_provenance_and_verified_https_sources(self):
        cases = []
        missing = self.generated()
        del missing['provenance']
        cases.append((missing, 'provenance'))
        insecure = self.generated('study-1123456789abcdef0123456789abcdef')
        insecure['sources'][0]['url'] = 'http://example.test/source'
        cases.append((insecure, 'HTTPS'))
        malformed = self.generated('study-4123456789abcdef0123456789abcdef')
        malformed['sources'][0]['url'] = 'https:source-without-a-host'
        cases.append((malformed, 'HTTPS'))
        altered = self.generated('study-2123456789abcdef0123456789abcdef')
        altered['sources'][0]['sha256'] = '0' * 64
        cases.append((altered, 'sha256'))
        control = self.generated('study-3123456789abcdef0123456789abcdef')
        control['reflection'] = 'unsafe ${exec command}'
        cases.append((control, 'Conky'))
        unknown = self.generated('study-5123456789abcdef0123456789abcdef')
        unknown['cited_source_ids'] = ['missing-source']
        cases.append((unknown, 'cited_source_ids'))
        duplicate = self.generated('study-6123456789abcdef0123456789abcdef')
        duplicate['cited_source_ids'] = ['source-1', 'source-1']
        cases.append((duplicate, 'cited_source_ids'))

        for entry, message in cases:
            with self.subTest(message=message):
                for path in self.entries.glob('*.json'):
                    path.unlink()
                self.write_generated(entry)
                with self.assertRaisesRegex(ValueError, message):
                    study.load_entries(self.assets, self.database)

    def test_database_symlink_is_refused_without_touching_its_target(self):
        target = self.root / 'unrelated.sqlite3'
        target.write_bytes(b'unrelated content')
        self.database.parent.mkdir(parents=True)
        self.database.symlink_to(target)

        with self.assertRaisesRegex(ValueError, 'symlink'):
            study.load_entries(self.assets, self.database)

        self.assertTrue(self.database.is_symlink())
        self.assertEqual(target.read_bytes(), b'unrelated content')

    def test_foreign_sqlite_database_is_refused_without_replacement(self):
        self.database.parent.mkdir(parents=True)
        with closing(sqlite3.connect(self.database)) as db:
            db.execute('CREATE TABLE valuable (content TEXT NOT NULL)')
            db.execute("INSERT INTO valuable VALUES ('keep me')")
            db.commit()
        snapshot = self.database.read_bytes()

        with self.assertRaisesRegex(ValueError, 'foreign'):
            study.load_entries(self.assets, self.database)

        self.assertEqual(self.database.read_bytes(), snapshot)
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(db.execute('SELECT content FROM valuable').fetchone()[0], 'keep me')

    def test_concurrent_initial_reads_return_the_same_complete_catalog(self):
        generated = self.generated()
        self.write_generated(generated)
        barrier = threading.Barrier(5)
        results = []
        errors = []

        def read():
            try:
                barrier.wait()
                results.append(study.load_entries(self.assets, self.database))
            except BaseException as error:
                errors.append(error)

        threads = [threading.Thread(target=read) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(5)

        self.assertEqual(errors, [])
        self.assertEqual(results, [[dict(self.legacy, kind='reflection'), generated]] * 5)

    def test_save_creates_an_immutable_entry_and_stages_only_its_exact_path(self):
        checkout = self.assets.parents[2]
        fake_bin = self.root / 'bin'
        fake_bin.mkdir()
        log = self.root / 'fossil-arguments.json'
        fossil = fake_bin / 'fossil'
        fossil.write_text(
            '#!/usr/bin/env python3\n'
            'import json, os, pathlib, sys\n'
            'pathlib.Path(os.environ["FOSSIL_TEST_LOG"]).write_text('
            'json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd()}))\n')
        fossil.chmod(0o755)
        entry = self.generated()
        environment = {
            'PATH': str(fake_bin) + os.pathsep + os.environ.get('PATH', ''),
            'FOSSIL_TEST_LOG': str(log),
        }

        with mock.patch.dict(os.environ, environment):
            path = study.save_entry(self.assets, entry, self.database)

        self.assertEqual(path, self.entries / f"{entry['id']}.json")
        self.assertEqual(json.loads(path.read_text()), entry)
        self.assertEqual(study.load_entries(self.assets, self.database)[-1], entry)
        invocation = json.loads(log.read_text())
        self.assertEqual(invocation, {
            'argv': ['add', str(path.relative_to(checkout))],
            'cwd': str(checkout),
        })
        with mock.patch.dict(os.environ, environment):
            with self.assertRaisesRegex(FileExistsError, 'immutable'):
                study.save_entry(self.assets, entry, self.database)

    def test_tracking_failure_reports_saved_path_and_keeps_the_entry(self):
        fake_bin = self.root / 'failing-bin'
        fake_bin.mkdir()
        fossil = fake_bin / 'fossil'
        fossil.write_text('#!/bin/sh\necho staging-denied >&2\nexit 7\n')
        fossil.chmod(0o755)
        entry = self.generated()
        expected_path = self.entries / f"{entry['id']}.json"

        with mock.patch.dict(os.environ, {'PATH': str(fake_bin)}):
            with self.assertRaisesRegex(RuntimeError, 'saved.*staging-denied'):
                study.save_entry(self.assets, entry, self.database)

        self.assertTrue(expected_path.is_file())
        self.assertEqual(study.load_entries(self.assets, self.database)[-1], entry)


if __name__ == '__main__':
    unittest.main()
