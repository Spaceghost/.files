import json
from pathlib import Path
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'alpine/desktop/.local/lib/mbp_intel'))
import desktop_journal as journal


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'entries.sqlite3'
        self.db = journal.open_database(self.path)
        self.addCleanup(self.db.close)

    def seed(self):
        journal.seed(self.db, [{'kind':'journal','date':'2026-09-07',
                               'body':'The desktop now keeps quiet notes.', 'source':'test'},
                              {'kind':'quip','date':'2026-09-07',
                               'body':'Moltar, bring the notebook.', 'source':'test'}], ['Legacy line'])

    def test_migration_is_once_only_and_preserves_disabled_entries(self):
        self.seed()
        self.db.execute('UPDATE entries SET enabled=0 WHERE body=?', ('Legacy line',))
        self.db.commit()
        self.seed()
        self.assertEqual(self.db.execute('SELECT count(*) FROM entries').fetchone()[0], 3)
        self.assertEqual(self.db.execute('SELECT enabled FROM entries WHERE body=?',
                                        ('Legacy line',)).fetchone()[0], 0)

    def test_rotation_survives_reopen_with_three_quips_then_one_journal(self):
        self.seed()
        first = journal.choose(self.db, now=1000)
        self.assertEqual(first['kind'], 'quip')
        other = journal.open_database(self.path)
        try:
            self.assertEqual(journal.choose(other, now=1001)['id'], first['id'])
            second = journal.choose(other, now=1240)
            self.assertEqual(second['kind'], 'quip')
            self.assertNotEqual(first['id'], second['id'])
            self.assertEqual(journal.choose(other, now=1480)['kind'], 'quip')
            self.assertEqual(journal.choose(other, now=1720)['kind'], 'journal')
            self.assertNotIn('Journal', journal.render(first))
        finally:
            other.close()

    def test_manual_entry_is_stored_verbatim_and_backup_is_readable(self):
        body = "Today's note: don't lose the full text. " * 12
        identifier = journal.add_entry(self.db, body, 'journal', '2026-09-07', 'manual')
        row = journal.choose(self.db, now=1000)
        self.assertEqual(row['id'], identifier)
        self.assertEqual(row['body'], body.strip())
        self.assertLessEqual(len(journal.render(row).splitlines()), 5)
        backup = Path(self.temp.name) / 'backup.sqlite3'
        journal.backup(self.db, backup)
        restored = journal.open_database(backup)
        try:
            self.assertEqual(restored.execute('SELECT body FROM entries').fetchone()[0], body.strip())
        finally:
            restored.close()
        with self.assertRaises(FileExistsError):
            journal.backup(self.db, backup)

    def test_disabled_current_entry_is_not_shown_again(self):
        self.seed()
        first = journal.choose(self.db, now=1000)
        self.db.execute('UPDATE entries SET enabled=0 WHERE id=?', (first['id'],))
        self.db.commit()
        self.assertNotEqual(journal.choose(self.db, now=1001)['id'], first['id'])

    def test_seed_has_real_dated_journal_entries_and_the_original_quips(self):
        records = json.loads((REPO / 'alpine/desktop/.local/share/mbp-intel/journal-seed.json').read_text())
        self.assertGreaterEqual(sum(r['kind']=='journal' for r in records), 6)
        self.assertGreaterEqual(sum(r['kind']=='quip' for r in records), 8)
        self.assertTrue(all(r['date']=='2026-09-07' for r in records))


if __name__ == '__main__':
    unittest.main()
