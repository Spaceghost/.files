"""Explicit clicks advance quiet content without waiting for periodic refresh."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / 'alpine/desktop/.local/bin'
sys.path.insert(0, str(REPO / 'alpine/desktop/.local/lib/oldbook'))
import desktop_journal as journal


class ClickCommandsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.env = dict(os.environ, HOME=str(self.home),
                        XDG_DATA_HOME=str(self.home / '.local/share'))

    def command(self, name, *arguments):
        result = subprocess.run([str(BIN / name), *arguments], env=self.env,
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def selection(self):
        return json.loads((self.home / '.local/state/oldbook/scripture/selection.json').read_text())

    def test_click_continues_after_the_selected_passage(self):
        self.command('oldbook-scripture', 'select', 'John 3:16-17')
        self.command('oldbook-scripture', 'next')
        self.assertEqual(self.selection()['reference'], 'John 3:18')

    def test_click_continues_torah_with_its_attribution(self):
        self.command('oldbook-scripture', 'select', 'Torah Genesis 1:1')
        self.command('oldbook-scripture', 'next')
        selected = self.selection()
        self.assertEqual(selected['reference'], 'Torah Genesis 1:2')
        self.assertEqual(selected['edition'], 'JPS 1917')

    def test_click_advances_reflection_and_persists_it(self):
        self.command('oldbook-scripture', 'daily')
        previous = self.selection()['id']
        self.command('oldbook-scripture', 'next')
        selected = self.selection()
        self.assertEqual(selected['kind'], 'reflection')
        self.assertNotEqual(selected['id'], previous)
        self.assertIn(selected['reference'], self.command('oldbook-scripture', 'panel'))

    def test_click_advances_witness_without_changing_scripture(self):
        self.command('oldbook-scripture', 'select', 'John 3:16')
        scripture = self.selection()
        previous = self.command('oldbook-scripture', 'witness')
        self.command('oldbook-scripture', 'witness-next')
        current = self.command('oldbook-scripture', 'witness')
        self.assertNotEqual(current, previous)
        self.assertEqual(current, self.command('oldbook-scripture', 'witness'))
        self.assertEqual(self.selection(), scripture)

    def test_lua_click_dispatches_once_and_ignores_other_events(self):
        target = self.home / '.local/bin/oldbook-conky-click'
        target.parent.mkdir(parents=True)
        target.symlink_to(BIN / 'oldbook-conky-click')
        hook = REPO / 'alpine/desktop/.local/lib/oldbook/conky_click.lua'
        self.command('oldbook-scripture', 'select', 'John 3:16')
        script = self.home / 'exercise.lua'
        script.write_text('conky_config = "/tmp/scripture.conf"\n'
                          + f'dofile({json.dumps(str(hook))})\n'
                          + '''assert(conky_oldbook_click({type='mouse_move'}) == false)
assert(conky_oldbook_click({type='button_down',button='right'}) == false)
assert(conky_oldbook_click({type='button_up',button='left'}) == false)
assert(conky_oldbook_click({type='button_down',button='left'}) == true)
conky_config = '/tmp/power.conf'
assert(conky_oldbook_click({type='button_down',button='left'}) == false)
''')
        result = subprocess.run(['lua', str(script)], env=self.env,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and self.selection()['reference'] == 'John 3:16':
            time.sleep(.1)
        self.assertEqual(self.selection()['reference'], 'John 3:17')

    def test_disabled_desktop_does_not_advance_from_stale_click(self):
        selection = self.home / '.local/state/oldbook/scripture/selection.json'
        selection.parent.mkdir(parents=True)
        selection.write_text(json.dumps({'kind': 'passage', 'reference': 'John 3:16',
                                         'text': 'Saved reading'}) + '\n')
        previous = selection.read_bytes()
        state = self.home / '.local/state/oldbook/conky'
        state.mkdir(parents=True)
        (state / 'disabled').touch()
        result = subprocess.run(['python3', str(BIN / 'oldbook-conky-click'), 'scripture'],
                                env=self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(selection.read_bytes(), previous)


class JournalClickTests(unittest.TestCase):
    def test_explicit_advance_keeps_rotation_ratio_and_four_minute_slot(self):
        with tempfile.TemporaryDirectory() as directory:
            db = journal.open_database(Path(directory) / 'entries.sqlite3')
            try:
                for number in range(3):
                    journal.add_entry(db, f'Quip {number}', 'quip', '2026-09-07', 'test')
                journal.add_entry(db, 'Observed note', 'journal', '2026-09-07', 'test')
                first = journal.choose(db, now=1000)
                result = subprocess.run([str(BIN / 'oldbook-journal'), '--database',
                    str(Path(directory) / 'entries.sqlite3'), 'next'], capture_output=True,
                    text=True, env=dict(os.environ, HOME=directory), timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                second = journal.choose(db)
                self.assertEqual(second['kind'], 'quip')
                self.assertNotEqual(second['id'], first['id'])
                # Stable reads within the automatic slot must not count as clicks.
                self.assertEqual(journal.choose(db)['id'], second['id'])
                third = journal.choose(db, now=1001, advance=True)
                fourth = journal.choose(db, now=1002, advance=True)
                self.assertEqual([third['kind'], fourth['kind']], ['quip', 'journal'])
                self.assertEqual(journal.choose(db, now=1003)['id'], fourth['id'])
                self.assertEqual(journal.choose(db, now=1240)['kind'], 'quip')
            finally:
                db.close()


if __name__ == '__main__':
    unittest.main()
