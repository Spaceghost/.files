"""Launchpad and Mission Control: application index, ranking and grid geometry."""

import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'alpine/desktop/.local/lib/oldbook'))

import app_index
import grid_layout
from launchpad import launch_arguments
from mission_control import next_workspace_number, workspace_cards


def write_entry(directory, name, **fields):
    values = {'Type': 'Application', 'Name': name, 'Exec': name.lower()}
    values.update(fields)
    body = '[Desktop Entry]\n' + ''.join(f'{key}={value}\n' for key, value in values.items())
    path = Path(directory) / (fields.pop('filename', name.lower().replace(' ', '-')) + '.desktop')
    path.write_text(body)
    return path


class ApplicationIndexTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)

    def scan(self):
        return app_index.scan([self.directory], locales=[])

    def test_reads_a_plain_entry(self):
        write_entry(self.directory, 'Firefox', Exec='firefox %u', Icon='firefox',
                    Comment='Browse the web')
        entries = self.scan()
        self.assertEqual([entry['name'] for entry in entries], ['Firefox'])
        self.assertEqual(entries[0]['arguments'], ['firefox'])
        self.assertEqual(entries[0]['icon'], 'firefox')

    def test_hidden_and_nodisplay_entries_never_reach_the_grid(self):
        write_entry(self.directory, 'Visible')
        write_entry(self.directory, 'Quiet', NoDisplay='true')
        write_entry(self.directory, 'Gone', Hidden='true')
        self.assertEqual([entry['name'] for entry in self.scan()], ['Visible'])

    def test_foreign_desktop_entries_are_filtered_both_ways(self):
        write_entry(self.directory, 'Gnome Only', OnlyShowIn='GNOME;')
        write_entry(self.directory, 'Not Here', NotShowIn='sway;')
        write_entry(self.directory, 'Sway Only', OnlyShowIn='sway;')
        self.assertEqual([entry['name'] for entry in self.scan()], ['Sway Only'])

    def test_entries_without_a_name_or_exec_are_skipped(self):
        write_entry(self.directory, 'Nameless', Name='', filename='nameless')
        write_entry(self.directory, 'Execless', Exec='')
        write_entry(self.directory, 'Link', Type='Link', URL='https://example.invalid')
        self.assertEqual(self.scan(), [])

    def test_tryexec_that_is_missing_removes_the_entry(self):
        write_entry(self.directory, 'Absent', TryExec='/nonexistent/oldbook-not-a-binary')
        write_entry(self.directory, 'Present', TryExec='/bin/sh')
        self.assertEqual([entry['name'] for entry in self.scan()], ['Present'])

    def test_first_directory_wins_for_a_repeated_identifier(self):
        with tempfile.TemporaryDirectory() as other:
            second = Path(other)
            write_entry(self.directory, 'Editor', filename='editor', Comment='preferred')
            write_entry(second, 'Editor', filename='editor', Comment='fallback')
            entries = app_index.scan([self.directory, second], locales=[])
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['comment'], 'preferred')

    def test_a_subdirectory_becomes_part_of_the_identifier(self):
        nested = self.directory / 'kde'
        nested.mkdir()
        write_entry(nested, 'Konsole', filename='konsole')
        self.assertEqual([entry['id'] for entry in self.scan()], ['kde-konsole.desktop'])

    def test_localized_names_are_used_when_the_locale_matches(self):
        path = self.directory / 'termy.desktop'
        path.write_text('[Desktop Entry]\nType=Application\nName=Terminal\n'
                        'Name[fr]=Terminal Français\nExec=foot\n')
        entry = app_index.read_entry(path, ['fr'])
        self.assertEqual(entry['name'], 'Terminal Français')
        self.assertEqual(app_index.read_entry(path, [])['name'], 'Terminal')

    def test_data_directories_follow_the_xdg_search_path(self):
        directories = app_index.data_directories(
            {'HOME': '/home/ghost', 'XDG_DATA_DIRS': '/opt/share:/usr/share'})
        self.assertEqual([str(item) for item in directories],
                         ['/home/ghost/.local/share/applications',
                          '/opt/share/applications', '/usr/share/applications'])


class FieldCodeTests(unittest.TestCase):
    def test_every_field_code_is_removed(self):
        self.assertEqual(app_index.command_arguments('app %f %F %u %U %d %D %n %N %i %c %k %v %m'),
                         ['app'])

    def test_a_literal_percent_survives(self):
        self.assertEqual(app_index.command_arguments('meter --at 50%%'), ['meter', '--at', '50%'])

    def test_quoted_arguments_stay_whole(self):
        self.assertEqual(app_index.command_arguments('run --title "Ghost Planet" %U'),
                         ['run', '--title', 'Ghost Planet'])

    def test_unbalanced_quoting_yields_no_arguments(self):
        self.assertEqual(app_index.command_arguments('run "unbalanced'), [])

    def test_terminal_entries_launch_inside_a_terminal(self):
        entry = {'arguments': ['htop'], 'terminal': True}
        self.assertEqual(launch_arguments(entry, ('foot', '-e')), ['foot', '-e', 'htop'])
        entry['terminal'] = False
        self.assertEqual(launch_arguments(entry, ('foot', '-e')), ['htop'])


class RankingTests(unittest.TestCase):
    def entries(self):
        return [{'id': 'firefox.desktop', 'name': 'Firefox', 'generic': 'Web Browser',
                 'comment': 'Browse the web', 'keywords': ['Internet'], 'categories': ['Network']},
                {'id': 'files.desktop', 'name': 'Fractal Object Explorer', 'generic': '',
                 'comment': '', 'keywords': [], 'categories': []},
                {'id': 'ghostty.desktop', 'name': 'Ghostty', 'generic': 'Terminal',
                 'comment': 'A terminal emulator', 'keywords': ['shell'], 'categories': []}]

    def test_an_empty_query_keeps_every_entry_in_order(self):
        entries = self.entries()
        self.assertEqual(app_index.search(entries, '  '), entries)

    def test_contiguous_matches_outrank_scattered_ones(self):
        results = app_index.search(self.entries(), 'fox')
        self.assertEqual(results[0]['name'], 'Firefox')

    def test_a_query_can_match_a_generic_name_or_keyword(self):
        self.assertEqual(app_index.search(self.entries(), 'terminal')[0]['name'], 'Ghostty')
        self.assertEqual(app_index.search(self.entries(), 'internet')[0]['name'], 'Firefox')

    def test_a_query_that_fits_nothing_returns_nothing(self):
        self.assertEqual(app_index.search(self.entries(), 'zzqq'), [])

    def test_matching_ignores_case(self):
        self.assertEqual(app_index.search(self.entries(), 'GHOST')[0]['name'], 'Ghostty')

    def test_a_prefix_scores_above_a_late_match(self):
        self.assertGreater(app_index.fuzzy_score('gh', 'Ghostty'),
                           app_index.fuzzy_score('gh', 'Alright Ghost'))

    def test_an_impossible_subsequence_scores_none(self):
        self.assertIsNone(app_index.fuzzy_score('xyz', 'Firefox'))


class LaunchpadGeometryTests(unittest.TestCase):
    def test_the_grid_fits_inside_its_margins(self):
        grid = grid_layout.launchpad_grid(1440, 900, 40)
        self.assertGreaterEqual(grid['columns'], grid_layout.ICON_MIN_COLUMNS)
        self.assertLessEqual(grid['columns'], grid_layout.ICON_MAX_COLUMNS)
        self.assertGreaterEqual(grid['origin_x'], 0)
        cells = grid_layout.launchpad_cells(grid, 40, 0)
        for cell in cells:
            self.assertLessEqual(cell['x'] + cell['width'], 1440 + 0.001)
            self.assertLessEqual(cell['y'] + cell['height'], 900 + 0.001)

    def test_pages_cover_every_entry_exactly_once(self):
        grid = grid_layout.launchpad_grid(1440, 900, 97)
        seen = []
        for page in range(grid['pages']):
            seen.extend(cell['index'] for cell in grid_layout.launchpad_cells(grid, 97, page))
        self.assertEqual(seen, list(range(97)))

    def test_a_short_last_page_stops_at_the_final_entry(self):
        grid = grid_layout.launchpad_grid(1440, 900, 5)
        cells = grid_layout.launchpad_cells(grid, 5, 0)
        self.assertEqual(len(cells), 5)

    def test_an_empty_viewport_produces_no_grid(self):
        grid = grid_layout.launchpad_grid(0, 0, 12)
        self.assertEqual(grid['page_size'], 0)
        self.assertEqual(grid_layout.launchpad_cells(grid, 12, 0), [])

    def test_hit_testing_finds_the_cell_under_a_point(self):
        grid = grid_layout.launchpad_grid(1440, 900, 20)
        cells = grid_layout.launchpad_cells(grid, 20, 0)
        target = cells[3]
        found = grid_layout.hit_cell(cells, target['x'] + 2, target['y'] + 2)
        self.assertEqual(found, target['index'])
        self.assertIsNone(grid_layout.hit_cell(cells, -5, -5))

    def test_page_of_maps_an_index_to_its_page(self):
        self.assertEqual(grid_layout.page_of(0, 10), 0)
        self.assertEqual(grid_layout.page_of(10, 10), 1)
        self.assertEqual(grid_layout.page_of(29, 10), 2)


class NavigationTests(unittest.TestCase):
    def test_horizontal_movement_wraps_around_the_whole_list(self):
        self.assertEqual(grid_layout.move_selection(0, 12, 4, 'left'), 11)
        self.assertEqual(grid_layout.move_selection(11, 12, 4, 'right'), 0)

    def test_vertical_movement_stops_at_the_edges(self):
        self.assertEqual(grid_layout.move_selection(1, 12, 4, 'up'), 1)
        self.assertEqual(grid_layout.move_selection(10, 12, 4, 'down'), 10)
        self.assertEqual(grid_layout.move_selection(1, 12, 4, 'down'), 5)

    def test_home_and_end_reach_the_ends(self):
        self.assertEqual(grid_layout.move_selection(5, 12, 4, 'home'), 0)
        self.assertEqual(grid_layout.move_selection(5, 12, 4, 'end'), 11)

    def test_an_empty_list_has_nowhere_to_go(self):
        self.assertIsNone(grid_layout.move_selection(0, 0, 4, 'right'))

    def test_a_missing_selection_starts_at_the_beginning(self):
        self.assertEqual(grid_layout.move_selection(None, 5, 2, 'right'), 1)


class WorkspaceGridTests(unittest.TestCase):
    def test_cards_stay_inside_the_viewport(self):
        grid = grid_layout.workspace_grid(1440, 900, 7)
        self.assertEqual(len(grid['cards']), 7)
        for card in grid['cards']:
            self.assertGreaterEqual(card['x'], -0.001)
            self.assertLessEqual(card['x'] + card['width'], 1440.001)
            self.assertLessEqual(card['y'] + card['height'], 900.001)

    def test_more_workspaces_make_smaller_cards(self):
        few = grid_layout.workspace_grid(1440, 900, 2)['card_width']
        many = grid_layout.workspace_grid(1440, 900, 12)['card_width']
        self.assertGreater(few, many)

    def test_no_workspaces_produce_no_cards(self):
        self.assertEqual(grid_layout.workspace_grid(1440, 900, 0)['cards'], [])

    def test_stills_tile_without_overlapping(self):
        slots = grid_layout.tile_stills(4, 200, 120)
        self.assertEqual(len(slots), 4)
        for first in range(len(slots)):
            for second in range(first + 1, len(slots)):
                a, b = slots[first], slots[second]
                separated = (a['x'] + a['width'] <= b['x'] + 0.001
                             or b['x'] + b['width'] <= a['x'] + 0.001
                             or a['y'] + a['height'] <= b['y'] + 0.001
                             or b['y'] + b['height'] <= a['y'] + 0.001)
                self.assertTrue(separated)

    def test_letterbox_preserves_the_aspect_ratio(self):
        x, y, width, height = grid_layout.letterbox(1600, 1000, 200, 200)
        self.assertAlmostEqual(width / height, 1.6, places=3)
        self.assertAlmostEqual(x, 0.0, places=3)
        self.assertGreater(y, 0.0)


class MissionControlModelTests(unittest.TestCase):
    def tree(self):
        def view(identifier, app, name, toplevel='ff'):
            return {'id': identifier, 'type': 'con', 'app_id': app, 'name': name,
                    'foreign_toplevel_identifier': toplevel, 'nodes': [], 'floating_nodes': []}
        return {'type': 'root', 'nodes': [
            {'type': 'output', 'name': 'eDP-1', 'nodes': [
                {'type': 'workspace', 'num': 1, 'name': '1: Ghost', 'focused': True,
                 'nodes': [view(11, 'foot', 'shell')], 'floating_nodes': []},
                {'type': 'workspace', 'num': 3, 'name': '3: Lab', 'focused': False,
                 'nodes': [view(31, 'firefox', 'web'), view(32, 'nvim', 'edit')],
                 'floating_nodes': []},
                {'type': 'workspace', 'name': '__i3_scratch', 'num': -1,
                 'nodes': [], 'floating_nodes': []},
            ], 'floating_nodes': []}], 'floating_nodes': []}

    def test_cards_cover_the_real_workspaces_in_order(self):
        cards = workspace_cards(self.tree())
        self.assertEqual([card['num'] for card in cards], [1, 3])
        self.assertTrue(cards[0]['focused'])
        self.assertEqual(len(cards[1]['views']), 2)

    def test_the_scratchpad_never_becomes_a_card(self):
        self.assertNotIn('__i3_scratch', [card['name'] for card in workspace_cards(self.tree())])

    def test_views_carry_the_identifier_the_capture_provider_needs(self):
        cards = workspace_cards(self.tree())
        self.assertEqual(cards[0]['views'][0]['foreign_toplevel_identifier'], 'ff')

    def test_the_stills_per_card_are_capped(self):
        cards = workspace_cards(self.tree(), limit=1)
        self.assertEqual(len(cards[1]['views']), 1)
        self.assertEqual(cards[1]['count'], 2)

    def test_the_new_workspace_takes_the_first_free_number(self):
        self.assertEqual(next_workspace_number(workspace_cards(self.tree())), 2)
        self.assertEqual(next_workspace_number([{'num': 1}, {'num': 2}]), 3)
        self.assertEqual(next_workspace_number([]), 1)


class SessionLockTests(unittest.TestCase):
    """An overview key pressed behind the lock must not map an invisible grab."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.runtime = Path(self.temporary.name)
        (self.runtime / 'oldbook-screen-lock').mkdir()
        self.addCleanup(self.temporary.cleanup)

    def write_record(self, pid, start_time):
        import json
        (self.runtime / 'oldbook-screen-lock' / 'ready.json').write_text(
            json.dumps({'process': {'pid': pid, 'start_time': start_time}}))

    def own_start_time(self):
        fields = (Path('/proc') / str(os.getpid()) / 'stat').read_text().rsplit(')', 1)[1].split()
        return fields[19]

    def test_no_record_means_no_lock(self):
        from grid_overlay import session_locked
        self.assertFalse(session_locked(self.runtime))

    def test_a_live_locker_counts_as_locked(self):
        from grid_overlay import session_locked
        self.write_record(os.getpid(), self.own_start_time())
        self.assertTrue(session_locked(self.runtime))

    def test_a_reused_pid_with_another_start_time_is_stale(self):
        from grid_overlay import session_locked
        self.write_record(os.getpid(), '1')
        self.assertFalse(session_locked(self.runtime))

    def test_a_dead_locker_is_stale(self):
        from grid_overlay import session_locked
        self.write_record(2 ** 22, '1')
        self.assertFalse(session_locked(self.runtime))

    def test_a_damaged_record_is_not_a_lock(self):
        from grid_overlay import session_locked
        (self.runtime / 'oldbook-screen-lock' / 'ready.json').write_text('{not json')
        self.assertFalse(session_locked(self.runtime))


class OverlayEasingTests(unittest.TestCase):
    def test_the_reveal_curve_settles_exactly_at_both_ends(self):
        from grid_overlay import smoothstep
        self.assertEqual(smoothstep(0.0), 0.0)
        self.assertEqual(smoothstep(1.0), 1.0)
        self.assertEqual(smoothstep(-3.0), 0.0)
        self.assertEqual(smoothstep(4.0), 1.0)

    def test_the_reveal_curve_never_overshoots(self):
        from grid_overlay import smoothstep
        for step in range(0, 101):
            value = smoothstep(step / 100)
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)


if __name__ == '__main__':
    unittest.main()
