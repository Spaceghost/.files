"""The newest rice reaches the desktop as a list you can read and set off."""
import importlib.machinery
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / 'alpine/desktop/.local/bin'
LIB = REPO / 'alpine/desktop/.local/lib/oldbook'
SHIPPED = REPO / 'alpine/desktop/.config/oldbook/rice.json'
PANELS = REPO / 'alpine/desktop/.config/conky/panels.json'
HOOK = LIB / 'conky_click.lua'
sys.path.insert(0, str(LIB))
import conky_layout
import conky_policy
import power_source
import rice_tour


def helper_module(name, path):
    """Import a hyphenated command by path so its tables can be read here."""
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, str(path)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def entry(identity, date, title=None, **extra):
    return dict({'id': identity, 'date': date, 'title': title or identity.title(),
                 'summary': 'What it does, in one line.',
                 'trigger': f'oldbook-{identity}'}, **extra)


class ListTests(unittest.TestCase):
    def write(self, entries, version=1):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / 'rice.json'
        path.write_text(json.dumps({'version': version, 'entries': entries}))
        return path

    def test_newest_lands_at_the_top_and_a_shared_day_keeps_file_order(self):
        path = self.write([entry('newest', '2026-09-08'), entry('twin', '2026-09-08'),
                           entry('older', '2026-08-01'), entry('newer', '2026-09-09')])
        self.assertEqual([item['id'] for item in rice_tour.load(path)],
                         ['newer', 'newest', 'twin', 'older'])

    def test_the_shipped_list_loads_and_names_the_features_it_was_seeded_with(self):
        entries = rice_tour.load(SHIPPED)
        identities = [item['id'] for item in entries]
        self.assertLessEqual({'power-posture', 'strip-process-chain',
                              'notification-cards', 'lock-power-key'}, set(identities))
        self.assertEqual(len(identities), len(set(identities)))
        # More entries than one page, or there is nothing to page through.
        self.assertGreater(len(entries), rice_tour.ROWS)
        for item in entries:
            wrapped = textwrap.wrap(item['summary'], rice_tour.WIDTH,
                                    max_lines=2, placeholder='…')
            self.assertNotIn('…', ''.join(wrapped),
                             f'{item["id"]} does not fit the card in two lines')

    def test_the_shipped_list_is_exactly_what_the_cue_source_renders(self):
        # rice.json is rendered from alpine/cue/rice, byte for byte, so the list
        # cannot drift from its source; alpine/cue/rice/README.md says how.
        cue = shutil.which('cue')
        if cue is None:
            self.skipTest('cue is not installed')
        rendered = subprocess.run(
            [cue, 'export', './alpine/cue/rice', '-e', 'rice', '--out', 'json'],
            cwd=REPO, capture_output=True, check=True).stdout
        self.assertEqual(rendered, SHIPPED.read_bytes())

    def test_an_entry_the_card_could_not_draw_is_refused(self):
        for broken in ({'id': 'BAD'}, entry('no-date', '8 September 2026'),
                       entry('bad-month', '2026-13-01'), {**entry('gone', '2026-09-08'),
                                                          'summary': '  '},
                       {**entry('runny', '2026-09-08'), 'run': 'oldbook-rice'},
                       {**entry('runny', '2026-09-08'), 'run': []},
                       {**entry('termy', '2026-09-08'), 'terminal': 'yes'},
                       {**entry('detailed', '2026-09-08'), 'detail': 7}):
            with self.subTest(entry=broken):
                with self.assertRaises(ValueError):
                    rice_tour.load(self.write([broken]))

    def test_a_repeated_identifier_and_an_unknown_version_are_refused(self):
        with self.assertRaises(ValueError):
            rice_tour.load(self.write([entry('twice', '2026-09-08'),
                                       entry('twice', '2026-09-07')]))
        with self.assertRaises(ValueError):
            rice_tour.load(self.write([entry('fine', '2026-09-08')], version=2))


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.entries = [entry(f'item-{number}', '2026-09-08') for number in range(12)]

    def test_the_selection_wraps_in_both_directions(self):
        self.assertEqual(rice_tour.move(11, 12, 1), 0)
        self.assertEqual(rice_tour.move(0, 12, -1), 11)
        self.assertEqual(rice_tour.move(0, 0, 1), 0)

    def test_a_page_step_lands_on_a_page_start_and_wraps_at_the_end(self):
        self.assertEqual(rice_tour.page_move(0, 12, 1, rows=5), 5)
        self.assertEqual(rice_tour.page_move(7, 12, 1, rows=5), 10)
        self.assertEqual(rice_tour.page_move(10, 12, 1, rows=5), 0)
        self.assertEqual(rice_tour.page_move(0, 12, -1, rows=5), 10)

    def test_the_page_shown_is_always_the_one_holding_the_selection(self):
        for cursor in range(len(self.entries)):
            start, page = rice_tour.visible(self.entries, cursor, rows=5)
            self.assertIn(self.entries[cursor], page)
            self.assertEqual(start % 5, 0)

    def test_a_saved_cursor_beyond_the_list_still_selects_a_real_entry(self):
        text = rice_tour.panel(self.entries, {'cursor': 99, 'tried': []})
        self.assertIn('item-11', text)


class CardTests(unittest.TestCase):
    def setUp(self):
        self.entries = rice_tour.load(SHIPPED)

    def card(self, state, **options):
        return rice_tour.panel_lines(self.entries, state, **options)

    def test_the_newest_entry_is_the_first_row_and_carries_the_description(self):
        lines = self.card({'cursor': 0, 'tried': []})
        self.assertIn(self.entries[0]['title'], lines[0])
        self.assertTrue(lines[0].startswith('${color1}▸ '))
        self.assertIn(self.entries[0]['trigger'][:20], '\n'.join(lines))
        self.assertIn('1/', lines[-2])

    def test_the_description_follows_the_selection_rather_than_the_pointer(self):
        first = self.card({'cursor': 0, 'tried': []})
        second = self.card({'cursor': 1, 'tried': []})
        self.assertNotEqual(first[-4:], second[-4:])
        self.assertTrue(second[1].startswith('${color1}▸ '))
        self.assertIn(self.entries[1]['title'], '\n'.join(second[-6:]))

    def test_the_card_keeps_one_height_whatever_it_is_describing(self):
        heights = {len(self.card({'cursor': cursor, 'tried': []}))
                   for cursor in range(len(self.entries))}
        self.assertEqual(heights, {rice_tour.ROWS + 6})

    def test_a_ticked_entry_is_marked_where_it_sits(self):
        identity = self.entries[2]['id']
        lines = self.card({'cursor': 0, 'tried': [identity]})
        self.assertIn('✓', lines[2])
        self.assertNotIn('✓', lines[1])

    def test_the_legend_says_what_the_try_link_will_do_for_this_entry(self):
        runnable = next(index for index, item in enumerate(self.entries) if item.get('run'))
        described = next(index for index, item in enumerate(self.entries) if not item.get('run'))
        self.assertIn('runs it', self.card({'cursor': runnable, 'tried': []})[-1])
        self.assertIn('says how', self.card({'cursor': described, 'tried': []})[-1])

    def test_no_line_of_the_card_overruns_the_column_it_was_given(self):
        for cursor in (0, 1, len(self.entries) - 1):
            for line in self.card({'cursor': cursor, 'tried': []}, width=40):
                drawn = re.sub(r'\$\{[a-z_]+[^}]*\}', '', line.replace('$$', '\x00'))
                self.assertLessEqual(len(drawn), 40, line)

    def test_a_dollar_in_the_data_cannot_become_a_conky_variable(self):
        entries = [entry('shell', '2026-09-08', title='Costs $HOME',
                         trigger='echo ${cpu}')]
        text = rice_tour.panel(entries, {'cursor': 0, 'tried': []})
        self.assertIn('$$HOME', text)
        self.assertIn('$${cpu}', text)
        self.assertNotIn('${cpu}', text.replace('$${cpu}', ''))


class BatteryTests(unittest.TestCase):
    """The description block is the part that redraws on every click."""

    def supply(self, **files):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        for name, values in files.items():
            (root / name).mkdir()
            for key, value in values.items():
                (root / name / key).write_text(value + '\n')
        state = root / 'state'
        state.mkdir()
        os.environ['OLDBOOK_POWER_ROOT'] = str(root)
        os.environ['XDG_STATE_HOME'] = str(state)
        self.addCleanup(os.environ.pop, 'OLDBOOK_POWER_ROOT', None)
        return root

    def setUp(self):
        self.previous = os.environ.get('XDG_STATE_HOME')
        self.addCleanup(lambda: os.environ.__setitem__('XDG_STATE_HOME', self.previous)
                        if self.previous else os.environ.pop('XDG_STATE_HOME', None))
        self.ladder = dict(power_source.LADDER)
        self.addCleanup(power_source.LADDER.update, self.ladder)
        self.addCleanup(power_source.LADDER.pop, rice_tour.LADDER_EFFECT, None)
        # The rung this card asks for; until it is registered the card, like
        # every unregistered effect, simply runs everywhere.
        power_source.LADDER[rice_tour.LADDER_EFFECT] = 'battery-low'
        self.entries = rice_tour.load(SHIPPED)

    def test_the_list_survives_a_critical_battery_and_the_description_sheds(self):
        self.supply(BAT0={'type': 'Battery', 'status': 'Discharging', 'capacity': '5'})
        self.assertEqual(power_source.posture(), 'battery-critical')
        self.assertFalse(rice_tour.detailed_now())
        lines = rice_tour.panel_lines(self.entries, {'cursor': 0, 'tried': []},
                                      detailed=rice_tour.detailed_now())
        self.assertEqual(len(lines), rice_tour.ROWS)
        self.assertIn(self.entries[0]['title'], lines[0])

    def test_the_cord_brings_the_description_back(self):
        self.supply(AC={'type': 'Mains', 'online': '1'},
                    BAT0={'type': 'Battery', 'status': 'Charging', 'capacity': '5'})
        self.assertEqual(power_source.posture(), 'mains')
        self.assertTrue(rice_tour.detailed_now())

    def test_an_unregistered_card_is_never_switched_off_by_omission(self):
        power_source.LADDER.pop(rice_tour.LADDER_EFFECT, None)
        self.supply(BAT0={'type': 'Battery', 'status': 'Discharging', 'capacity': '3'})
        self.assertTrue(rice_tour.detailed_now())


class DesktopCardTests(unittest.TestCase):
    """The card is a Conky panel and has to obey the quiet-display policy."""

    def panel(self):
        document = conky_layout.load_panels(PANELS)
        return next(item for item in document['panels'] if item['id'] == 'rice')

    def test_the_card_ships_enabled_and_the_quiet_policy_leaves_it_alone(self):
        source = json.loads(PANELS.read_text())
        shipped = next(item for item in source['panels'] if item['id'] == 'rice')
        self.assertTrue(shipped.get('enabled', True))
        self.assertEqual(self.panel(), shipped)

    def test_the_card_carries_no_telemetry_and_refreshes_slowly(self):
        text = self.panel()['text']
        interval = int(re.search(r'\$\{execpi (\d+)', text).group(1))
        self.assertTrue(conky_policy.MIN_INTERVAL <= interval <= conky_policy.MAX_INTERVAL)
        for name in re.findall(r'\$(?:\{\s*)?([A-Za-z_][A-Za-z_0-9]*)', text):
            self.assertFalse(name.lower().startswith(conky_policy.TELEMETRY_PREFIXES), name)

    def test_the_generated_config_answers_the_pointer_and_names_the_try_target(self):
        placement = {'x': 40, 'y': 60, 'width': 420, 'height': 250, 'background': [20, 20, 20]}
        colours = conky_layout.panel_colours(placement, conky_layout.resolve_palette({}))
        config = conky_layout.render_config(self.panel(), placement, colours,
                                            {'click_hook': str(HOOK), 'font': 'Mono:size=9'})
        self.assertIn('lua_mouse_hook', config)
        self.assertIn("lua_startup_hook = 'oldbook_rice ", config)
        self.assertIn('${color1}Try${color}', config)

    def test_the_scripture_history_target_keeps_the_geometry_it_had(self):
        placement = {'x': 0, 'y': 0, 'width': 420, 'height': 204, 'background': [20, 20, 20]}
        colours = conky_layout.panel_colours(placement, conky_layout.resolve_palette({}))
        panel = {'id': 'scripture', 'text': '${color1}SCRIPTURE${color2} ${hr 1}\nPassage'}
        config = conky_layout.render_config(panel, placement, colours,
                                            {'click_hook': str(HOOK), 'font': 'Mono:size=9'})
        width = math.ceil(9 * 8)
        self.assertIn(f"lua_startup_hook = 'oldbook_history {420 - width} {width} 18'", config)


class PointerTests(unittest.TestCase):
    """Conky reports the pointer; these are the words each gesture turns into."""

    def dispatch(self, script):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'gestures.lua'
            path.write_text(
                'conky_config = "/tmp/rice.conf"\n'
                + f'dofile({json.dumps(str(HOOK))})\n'
                + 'conky_oldbook_rice(380, 40, 18)\n'
                + 'local commands = {}\n'
                + 'os.execute = function(command) table.insert(commands, command) end\n'
                + 'local function word(event)\n'
                + '    if conky_oldbook_click(event) == false then return "ignored" end\n'
                + '    return commands[#commands]:match(\'oldbook%-conky%-click" ([%w%-]+)\')\n'
                + 'end\n' + script)
            result = subprocess.run(['lua', str(path)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_every_button_and_the_wheel_map_to_their_own_word(self):
        self.dispatch('''
assert(word{type='button_down', button='left', x=10, y=40} == 'rice', 'body click')
assert(word{type='button_down', button='left', x=390, y=8} == 'rice-try', 'try link')
assert(word{type='button_down', button='left', x=390, y=40} == 'rice', 'below the link')
assert(word{type='button_down', button='right', x=10, y=40} == 'rice-back', 'right')
assert(word{type='button_down', button='middle', x=10, y=40} == 'rice-tried', 'middle')
assert(word{type='mouse_scroll', direction='down'} == 'rice-page-down', 'wheel down')
assert(word{type='mouse_scroll', direction='up'} == 'rice-page-up', 'wheel up')
''')

    def test_events_the_card_cannot_read_change_nothing(self):
        self.dispatch('''
assert(word{type='mouse_move', x=10, y=40} == 'ignored', 'hover')
assert(word{type='button_up', button='left', x=10, y=40} == 'ignored', 'release')
assert(word{type='mouse_scroll'} == 'ignored', 'a wheel with no direction')
conky_config = '/tmp/scripture.conf'
assert(word{type='mouse_scroll', direction='up'} == 'ignored', 'scripture never pages')
assert(word{type='button_down', button='middle', x=10, y=40} == 'ignored', 'scripture middle')
conky_config = '/tmp/power.conf'
assert(word{type='button_down', button='left', x=10, y=40} == 'ignored', 'power is not a card')
''')

    def test_the_dispatcher_knows_every_word_the_hook_can_send(self):
        actions = helper_module('rice_click_helper', BIN / 'oldbook-conky-click').ACTIONS
        self.assertLessEqual({'rice', 'rice-back', 'rice-page-down', 'rice-page-up',
                              'rice-try', 'rice-tried'}, set(actions))
        for word, (helper, _) in actions.items():
            if word.startswith('rice'):
                self.assertEqual(helper, 'oldbook-rice')
        for word in ('scripture', 'scripture-history', 'scripture-previous',
                     'witness', 'ghost', 'gallery'):
            self.assertIn(word, actions, 'an existing card lost its click')


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        home = Path(self.temporary.name)
        (home / '.config/oldbook').mkdir(parents=True)
        self.entries = [entry('first', '2026-09-09', run=['true']),
                        entry('second', '2026-09-08'),
                        entry('third', '2026-09-07'),
                        entry('fourth', '2026-09-06')]
        (home / '.config/oldbook/rice.json').write_text(
            json.dumps({'version': 1, 'entries': self.entries}))
        self.env = dict(os.environ, HOME=str(home),
                        XDG_CONFIG_HOME=str(home / '.config'),
                        XDG_STATE_HOME=str(home / '.local/state'))
        self.env.pop('OLDBOOK_POWER_ROOT', None)
        self.state = home / '.local/state/oldbook/rice-state.json'

    def command(self, *arguments, expect=0):
        result = subprocess.run([sys.executable, str(BIN / 'oldbook-rice'), *arguments],
                                env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, expect, result.stderr)
        return result.stdout

    def saved(self):
        return json.loads(self.state.read_text())

    def test_stepping_and_paging_are_saved_where_the_card_will_read_them(self):
        self.command('next')
        self.assertEqual(self.saved()['cursor'], 1)
        self.command('previous')
        self.command('previous')
        self.assertEqual(self.saved()['cursor'], 3)
        self.command('page-down')
        self.assertEqual(self.saved()['cursor'], 0)

    def test_running_an_entry_counts_as_trying_it_and_the_tick_is_reversible(self):
        self.command('try')
        self.assertEqual(self.saved()['tried'], ['first'])
        self.command('tried')
        self.assertEqual(self.saved()['tried'], [])

    def test_an_entry_with_nothing_to_run_is_explained_rather_than_ticked(self):
        self.env['PATH'] = str(Path(self.temporary.name) / 'empty')
        output = self.command('try', 'second')
        self.assertIn('oldbook-second', output)
        self.assertFalse(self.state.exists() and self.saved()['tried'])

    def test_an_unknown_entry_is_named_rather_than_guessed_at(self):
        result = subprocess.run([sys.executable, str(BIN / 'oldbook-rice'), 'show', 'nope'],
                                env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 1)
        self.assertIn('No such rice entry: nope', result.stderr)

    def test_the_card_body_the_helper_prints_is_the_one_the_module_renders(self):
        printed = self.command('panel', '--width', '44', '--rows', '2').rstrip('\n')
        self.assertEqual(printed, rice_tour.panel(
            rice_tour.load(Path(self.env['XDG_CONFIG_HOME']) / 'oldbook/rice.json'),
            {'cursor': 0, 'tried': []}, 44, 2, rice_tour.detailed_now()))


if __name__ == '__main__':
    unittest.main()
