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
sys.path.insert(0, str(REPO / 'alpine/desktop/.local/lib/mbp_intel'))
import desktop_journal as journal
import conky_layout


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
        return json.loads((self.home / '.local/state/mbp-intel/scripture/selection.json').read_text())

    def test_click_continues_after_the_selected_passage(self):
        self.command('mbp-intel-scripture', 'select', 'John 3:16-17')
        self.command('mbp-intel-scripture', 'next')
        self.assertEqual(self.selection()['reference'], 'John 3:18')

    def test_click_continues_torah_with_its_attribution(self):
        self.command('mbp-intel-scripture', 'select', 'Torah Genesis 1:1')
        self.command('mbp-intel-scripture', 'next')
        selected = self.selection()
        self.assertEqual(selected['reference'], 'Torah Genesis 1:2')
        self.assertEqual(selected['edition'], 'JPS 1917')

    def test_click_advances_reflection_and_persists_it(self):
        self.command('mbp-intel-scripture', 'daily')
        previous = self.selection()['id']
        self.command('mbp-intel-scripture', 'next')
        selected = self.selection()
        self.assertEqual(selected['kind'], 'reflection')
        self.assertNotEqual(selected['id'], previous)
        self.assertIn(selected['reference'], self.command('mbp-intel-scripture', 'panel'))

    def test_click_advances_witness_without_changing_scripture(self):
        self.command('mbp-intel-scripture', 'select', 'John 3:16')
        scripture = self.selection()
        previous = self.command('mbp-intel-scripture', 'witness')
        self.command('mbp-intel-scripture', 'witness-next')
        current = self.command('mbp-intel-scripture', 'witness')
        self.assertNotEqual(current, previous)
        self.assertEqual(current, self.command('mbp-intel-scripture', 'witness'))
        self.assertEqual(self.selection(), scripture)

    def test_lua_click_dispatches_once_and_ignores_other_events(self):
        target = self.home / '.local/bin/mbp-intel-conky-click'
        target.parent.mkdir(parents=True)
        target.symlink_to(BIN / 'mbp-intel-conky-click')
        hook = REPO / 'alpine/desktop/.local/lib/mbp_intel/conky_click.lua'
        self.command('mbp-intel-scripture', 'select', 'John 3:16')
        script = self.home / 'exercise.lua'
        script.write_text('conky_config = "/tmp/scripture.conf"\n'
                          + f'dofile({json.dumps(str(hook))})\n'
                          + '''assert(conky_mbp_intel_click({type='mouse_move'}) == false)
assert(conky_mbp_intel_click({type='button_down',button='right'}) == false)
assert(conky_mbp_intel_click({type='button_up',button='left'}) == false)
assert(conky_mbp_intel_click({type='button_down',button='left'}) == true)
conky_config = '/tmp/power.conf'
assert(conky_mbp_intel_click({type='button_down',button='left'}) == false)
''')
        result = subprocess.run(['lua', str(script)], env=self.env,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and self.selection()['reference'] == 'John 3:16':
            time.sleep(.1)
        self.assertEqual(self.selection()['reference'], 'John 3:17')

    def test_disabled_desktop_does_not_advance_from_stale_click(self):
        selection = self.home / '.local/state/mbp-intel/scripture/selection.json'
        selection.parent.mkdir(parents=True)
        selection.write_text(json.dumps({'kind': 'passage', 'reference': 'John 3:16',
                                         'text': 'Saved reading'}) + '\n')
        previous = selection.read_bytes()
        state = self.home / '.local/state/mbp-intel/conky'
        state.mkdir(parents=True)
        (state / 'disabled').touch()
        result = subprocess.run(['python3', str(BIN / 'mbp-intel-conky-click'), 'scripture'],
                                env=self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(selection.read_bytes(), previous)

    def test_header_history_hit_target_does_not_advance_the_passage(self):
        hook = REPO / 'alpine/desktop/.local/lib/mbp_intel/conky_click.lua'
        panel = {'id': 'scripture', 'text': '${color1}SCRIPTURE${color2} ${hr 1}\nPassage'}
        placement = {'x': 40, 'y': 60, 'width': 420, 'height': 200,
                     'background': [20, 20, 20]}
        colours = conky_layout.panel_colours(placement, conky_layout.resolve_palette({}))
        config = self.home / 'scripture.conf'
        config.write_text(conky_layout.render_config(panel, placement, colours,
                          {'click_hook': str(hook)}))
        script = self.home / 'header.lua'
        script.write_text('conky = {}\n' + f'dofile({json.dumps(str(config))})\n'
                          + f'conky_config = {json.dumps(str(config))}\n'
                          + f'dofile({json.dumps(str(hook))})\n' + '''
if conky.config.lua_startup_hook then
    local name, x, width, height = conky.config.lua_startup_hook:match('(%S+) (%S+) (%S+) (%S+)')
    _G['conky_' .. name](x, width, height)
end
local commands = {}
os.execute = function(command) table.insert(commands, command) end
local function click(x, y, action)
    assert(conky_mbp_intel_click({type='button_down', button='left', x=x, y=y}))
    assert(commands[#commands]:match('mbp%-intel%-conky%-click" ' .. action .. ' >'),
           'Wrong action for click at ' .. x .. ',' .. y .. ': ' .. commands[#commands])
end
click(390, 8, 'scripture%-history')
click(390, 40, 'scripture')
click(30, 8, 'scripture')
click(347, 8, 'scripture')
click(348, 0, 'scripture%-history')
click(419, 17, 'scripture%-history')
click(390, 18, 'scripture')
assert(#commands == 7)
''')
        result = subprocess.run(['lua', str(script)], env=self.env,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)


class JournalClickTests(unittest.TestCase):
    def test_explicit_advance_keeps_rotation_ratio_and_four_minute_slot(self):
        with tempfile.TemporaryDirectory() as directory:
            db = journal.open_database(Path(directory) / 'entries.sqlite3')
            try:
                for number in range(3):
                    journal.add_entry(db, f'Quip {number}', 'quip', '2026-09-07', 'test')
                journal.add_entry(db, 'Observed note', 'journal', '2026-09-07', 'test')
                first = journal.choose(db, now=1000)
                result = subprocess.run([str(BIN / 'mbp-intel-journal'), '--database',
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
