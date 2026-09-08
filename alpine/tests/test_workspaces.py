"""Workspace geometry and naming regressions; no live compositor mutations."""
from pathlib import Path
import contextlib
import io
import json
import runpy
import stat
import tempfile
import time
import unittest
from unittest import mock

MODEL = Path(__file__).resolve().parents[1] / 'desktop/.local/lib/oldbook/workspace_model.py'
SERVICE = Path(__file__).resolve().parents[1] / 'desktop/.local/bin/oldbook-workspaces'


def view(identifier, width, height, **extra):
    return dict(id=identifier, type='con', app_id='foot', name='foot',
                rect={'x': 0, 'y': 0, 'width': width, 'height': height},
                nodes=[], floating_nodes=[], **extra)


def workspace(*nodes, name='1', **extra):
    return dict(id=100, type='workspace', name=name, num=1,
                rect={'x': 0, 'y': 0, 'width': 1000, 'height': 1000},
                nodes=list(nodes), floating_nodes=extra.pop('floating_nodes', []),
                **extra)


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(MODEL.exists(), 'workspace model is missing')
        self.model = runpy.run_path(str(MODEL))

    def test_largest_app_wins_over_small_focused_window(self):
        ws = workspace(view(1, 800, 700), view(2, 200, 200, focused=True))
        self.assertEqual(self.model['largest_view'](ws)['id'], 1)

    def test_inactive_workspace_still_gets_its_largest_app(self):
        ws = workspace(view(1, 800, 700, visible=False), view(2, 200, 200, visible=False), visible=False)
        self.assertEqual(self.model['largest_view'](ws)['id'], 1)

    def test_inactive_tab_cannot_supply_the_workspace_label(self):
        tabs = {'id': 20, 'type': 'con', 'layout': 'tabbed', 'focus': [2, 1],
                'nodes': [view(1, 900, 900), view(2, 400, 400)]}
        self.assertEqual(self.model['largest_view'](workspace(tabs))['id'], 2)

    def test_fullscreen_subtree_wins_even_with_stale_small_geometry(self):
        ws = workspace(view(1, 900, 900), view(2, 300, 300, fullscreen_mode=1))
        self.assertEqual(self.model['largest_view'](ws)['id'], 2)

    def test_floating_window_and_focus_tie_are_accounted_for(self):
        ws = workspace(view(1, 500, 500), floating_nodes=[view(2, 700, 700)])
        self.assertEqual(self.model['largest_view'](ws)['id'], 2)
        ws = workspace(view(1, 500, 500), view(2, 500, 500), focus=[2, 1])
        self.assertEqual(self.model['largest_view'](ws)['id'], 2)

    def test_claude_window_is_named_and_available_in_ai_switcher(self):
        service = runpy.run_path(str(SERVICE))
        resolver = mock.Mock()
        resolver.resolve_all.return_value = {7: {'name': 'Claude', 'kind': 'claude'}}
        tree = {'nodes': [workspace(view(7, 700, 700), name='3')], 'floating_nodes': []}
        with tempfile.TemporaryDirectory() as temporary:
            plans, sessions = service['collect'](
                tree, resolver, Path(temporary), self.model['WorkspaceNames']())
        self.assertEqual(plans[0]['new'], '3: Lab · ✦ Claude')
        self.assertEqual([(item['id'], item['kind']) for item in sessions], [(7, 'claude')])

    def test_names_keep_numbers_and_do_not_accumulate_suffixes(self):
        names = self.model['WorkspaceNames']()
        ws = workspace(view(1, 100, 100))
        first = names.plan(ws, {'name': 'Codex', 'kind': 'codex'})
        self.assertEqual(first['new'], '1: Ghost · ✦ Codex')
        names.accept(first)
        ws['name'] = first['new']
        second = names.plan(ws, {'name': 'Firefox', 'kind': 'app'})
        self.assertEqual(second['new'], '1: Ghost · Firefox')
        self.assertEqual(second['original'], '1: Ghost')
        names.accept(second)
        ws['name'] = second['new']
        empty = names.plan(ws, None)
        self.assertEqual(empty['new'], '1: Ghost')

    def test_missing_state_recovers_generated_workspace_name(self):
        names = self.model['WorkspaceNames']()
        plan = names.plan(workspace(name='1: GHOST · ✦ Claude · ✦ Claude'), {'name': 'Firefox'})
        self.assertEqual(plan['new'], '1: Ghost · Firefox')
        self.assertEqual(plan['original'], '1: Ghost')

    def test_polluted_saved_base_is_repaired(self):
        polluted = '1: GHOST · ✦ Claude · ✦ Claude'
        names = self.model['WorkspaceNames']({'100': dict(original=polluted, base=polluted,
                                                         rendered=polluted + ' · Firefox')})
        plan = names.plan(workspace(name=polluted + ' · Firefox'), {'name': 'Codex', 'kind': 'codex'})
        self.assertEqual(plan['new'], '1: Ghost · ✦ Codex')
        self.assertEqual(plan['original'], '1: Ghost')

    def test_graceful_restart_retains_custom_base(self):
        names = self.model['WorkspaceNames']({'100': dict(original='1: My notes', base='1: My notes',
                                                         rendered='1: My notes · Firefox')})
        plan = names.plan(workspace(name='1: My notes'), {'name': 'Foot'})
        self.assertEqual(plan['new'], '1: My notes · Foot')

    def test_workspace_ten_keeps_strata_when_browser_changes(self):
        names = self.model['WorkspaceNames']()
        ws = workspace(name='10')
        ws['num'] = 10
        first = names.plan(ws, {'name': 'Fossil'})
        self.assertEqual(first['new'], '10: Strata · Fossil')
        names.accept(first)
        ws['name'] = first['new']
        self.assertEqual(names.plan(ws, None)['new'], '10: Strata')

    def test_workspace_six_is_available_for_ordinary_applications(self):
        plan = self.model['WorkspaceNames']().plan(workspace(name='6'), {'name': 'Foot'})
        self.assertEqual(plan['new'], '6: Foot')

    def test_manual_workspace_rename_becomes_the_new_base(self):
        names = self.model['WorkspaceNames']()
        first = names.plan(workspace(), {'name': 'Firefox'})
        names.accept(first)
        changed = names.plan(workspace(name='1: Writing'), {'name': 'Neovim'})
        self.assertEqual(changed['new'], '1: Writing · Neovim')
        self.assertEqual(changed['original'], '1: Writing')

    def test_malformed_persisted_name_record_is_ignored(self):
        for record in ({'rendered': '1'}, [], {'rendered': '1', 'original': '1'}):
            with self.subTest(record=record):
                names = self.model['WorkspaceNames']({'100': record})
                plan = names.plan(workspace(), {'name': 'Firefox', 'kind': 'app'})
                self.assertEqual(plan['new'], '1: Ghost · Firefox')
                self.assertEqual(plan['original'], '1: Ghost')

    def test_shared_workspace_names_are_complete_before_the_first_window(self):
        expected = {1: '1: Ghost', 2: '2: Orbit', 3: '3: Lab', 4: '4: Signal',
                    5: '5: Lounge', 10: '10: Strata'}
        for number, name in expected.items():
            for value in (number, str(number)):
                with self.subTest(value=value):
                    self.assertEqual(self.model['workspace_name'](value), name)
            plan = self.model['WorkspaceNames']().plan(workspace(name=name), None)
            self.assertEqual((plan['old'], plan['new'], plan['original']), (name, name, name))
        for value in (0, 6, 7, 11, '04', 'Writing'):
            with self.subTest(unknown=value):
                self.assertEqual(self.model['workspace_name'](value), str(value))

    def test_exact_legacy_uppercase_names_migrate_with_or_without_app_suffixes(self):
        defaults = {'1': 'Ghost', '2': 'Orbit', '3': 'Lab', '4': 'Signal',
                    '5': 'Lounge', '10': 'Strata'}
        for number, title in defaults.items():
            canonical = f'{number}: {title}'
            for suffix in ('', ' · Foot', ' · ✦ Codex · stale app'):
                original = f'{number}: {title.upper()}' + suffix
                with self.subTest(original=original):
                    plan = self.model['WorkspaceNames']().plan(workspace(name=original), None)
                    self.assertEqual(plan['new'], canonical)
                    self.assertEqual(plan['original'], canonical)

    def test_saved_uppercase_and_numeric_originals_restore_complete_names(self):
        for original in ('4', '4: SIGNAL', '4: SIGNAL · stale app'):
            with self.subTest(original=original):
                names = self.model['WorkspaceNames']({'100': {
                    'original': original, 'base': '4: SIGNAL', 'rendered': '4: SIGNAL · Foot'}})
                plan = names.plan(workspace(name='4: SIGNAL · Foot'), None)
                self.assertEqual((plan['new'], plan['base'], plan['original']),
                                 ('4: Signal', '4: Signal', '4: Signal'))
                names.accept(plan)
                self.assertEqual(names.records['100']['original'], '4: Signal')

    def test_migration_preserves_custom_names_and_manual_case(self):
        for original in ('4: signal', '4: sIgNaL', '4: SIGNAL notes', '4: Signal notes',
                         '4: My RADIO', '0: STRATA', '6: STRATA', 'Writing'):
            with self.subTest(original=original):
                plan = self.model['WorkspaceNames']().plan(workspace(name=original), None)
                self.assertEqual((plan['new'], plan['original']), (original, original))
                saved = self.model['WorkspaceNames']({'100': {
                    'original': original, 'base': original, 'rendered': original + ' · Foot'}})
                self.assertEqual(saved.plan(workspace(name=original + ' · Foot'), None)['new'], original)

    def test_unaddressable_manual_workspace_name_is_left_unchanged(self):
        original = 'manual" \\ $term\nname'
        names = self.model['WorkspaceNames']()
        plan = names.plan(workspace(name=original), {'name': 'Firefox', 'kind': 'app'})
        self.assertEqual(plan['new'], original)
        self.assertEqual(plan['original'], original)

    def test_application_text_cannot_inject_commands_or_markup(self):
        plan = self.model['WorkspaceNames']().plan(workspace(), {'name': 'bad"; exec evil\n<x>\x1b'})
        self.assertNotIn(';', plan['new'])
        self.assertNotIn('"', plan['new'])
        self.assertNotIn('<', plan['new'])
        self.assertNotIn('\n', plan['new'])
        self.assertNotIn('\x1b', plan['new'])

    def test_scratchpad_is_excluded_from_workspace_scan(self):
        tree = {'type': 'root', 'nodes': [
            {'type': 'output', 'name': '__i3', 'nodes': [workspace(name='__i3_scratch')]},
            {'type': 'output', 'name': 'eDP-1', 'nodes': [workspace()]}]}
        self.assertEqual([ws['name'] for ws in self.model['workspace_nodes'](tree)], ['1'])


class WorkspaceServiceTests(unittest.TestCase):
    def setUp(self):
        self.module = runpy.run_path(str(SERVICE))
        self.temp = tempfile.TemporaryDirectory(prefix='oldbook-workspaces-test-')
        self.addCleanup(self.temp.cleanup)
        self.runtime = Path(self.temp.name)
        self.events = self.runtime / 'oldbook/codex-events'
        self.events.mkdir(parents=True)

    def test_events_match_exact_panes_and_disappear_when_cleared(self):
        path = self.events / 'event.json'
        now = time.time()
        path.write_text(json.dumps({'version': 1, 'event': 'turn-complete',
                                    'observed_at': now, 'valid_until': now + 300,
                                    'tmux_pane': '%2', 'tty': None}))
        apps = {1: {'kind': 'codex', 'tmux_pane': '%2'},
                2: {'kind': 'codex', 'tmux_pane': '%7'}}
        self.module['events_for_apps'](self.runtime, apps)
        self.assertEqual(apps[1]['event'], 'turn-complete')
        self.assertNotIn('event', apps[2])
        path.unlink()
        self.module['events_for_apps'](self.runtime, apps)
        self.assertNotIn('event', apps[1])

    def test_event_tty_takes_precedence_over_inherited_tmux_pane(self):
        now = time.time()
        (self.events / 'tty.json').write_text(json.dumps({
            'version': 1, 'event': 'approval-requested',
            'observed_at': now, 'valid_until': now + 300,
            'tmux_pane': '%2', 'tty': '/dev/pts/9',
        }))
        (self.events / 'pane.json').write_text(json.dumps({
            'version': 1, 'event': 'turn-complete',
            'observed_at': now, 'valid_until': now + 300,
            'tmux_pane': '%7', 'tty': None,
        }))
        apps = {
            1: {'kind': 'codex', 'tmux_pane': '%2', 'tty': '/dev/pts/4'},
            2: {'kind': 'codex', 'tmux_pane': '%8', 'tty': '/dev/pts/9'},
            3: {'kind': 'codex', 'tmux_pane': '%7', 'tty': '/dev/pts/5'},
        }
        self.module['events_for_apps'](self.runtime, apps)
        self.assertNotIn('event', apps[1])
        self.assertEqual(apps[2]['event'], 'approval-requested')
        self.assertEqual(apps[3]['event'], 'turn-complete')

    def test_malformed_or_expired_events_do_not_crash_or_set_badges(self):
        for index, event in enumerate([[], {'version': 1},
                                      {'version': 1, 'event': 'turn-complete',
                                       'observed_at': 1, 'valid_until': 2, 'tmux_pane': '%2'}]):
            (self.events / f'{index}.json').write_text(json.dumps(event))
        apps = {1: {'kind': 'codex', 'tmux_pane': '%2'}}
        self.module['events_for_apps'](self.runtime, apps)
        self.assertNotIn('event', apps[1])

    def test_status_falls_back_to_idle_for_bad_or_stale_state(self):
        for state in [[], {'updated_at': 1, 'ai': [{'id': 5}]}]:
            (self.runtime / 'state.json').write_text(json.dumps(state))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.module['status'](self.runtime)
            self.assertEqual(json.loads(output.getvalue())['class'], 'idle')

    def test_status_falls_back_to_idle_for_fresh_malformed_ai_state(self):
        for ai in ({}, 'bad', [{'id': 5}]):
            with self.subTest(ai=ai):
                (self.runtime / 'state.json').write_text(json.dumps({
                    'updated_at': time.time(),
                    'ai': ai,
                }))
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.module['status'](self.runtime)
                status = json.loads(output.getvalue())
                self.assertEqual(status['class'], 'idle')
                self.assertEqual(status['text'], '✦')

    def test_codex_launcher_uses_resolver_recognized_app_id(self):
        switch_ai = self.module['switch_ai']
        original_collect = switch_ai.__globals__['collect']
        original_request = switch_ai.__globals__['request']
        switch_ai.__globals__['collect'] = lambda *args: ([], [])
        self.addCleanup(switch_ai.__globals__.__setitem__, 'collect', original_collect)
        switch_ai.__globals__['request'] = lambda *args: {}
        self.addCleanup(switch_ai.__globals__.__setitem__, 'request', original_request)
        selection = mock.Mock(returncode=0, stdout='✦ Open Codex in a terminal\n')
        with mock.patch.object(self.module['subprocess'], 'run', return_value=selection), \
                mock.patch.object(self.module['subprocess'], 'Popen') as launch:
            switch_ai(Path('/unused.sock'), self.runtime)
        self.assertEqual(launch.call_args.args[0], [
            'foot', '--app-id=codex', '--title=Codex', '-e', 'codex',
        ])

    def test_records_are_reused_only_for_the_current_sway_socket(self):
        record = {'100': {'original': '1', 'base': '1: GHOST', 'rendered': '1: GHOST'}}
        snapshot = {'socket': '/run/user/1000/current.sock', 'records': record}
        select_records = self.module['records_for_socket']
        self.assertEqual(select_records(snapshot, Path('/run/user/1000/current.sock')), record)
        self.assertEqual(select_records(snapshot, Path('/run/user/1000/new.sock')), {})
        self.assertEqual(select_records({'socket': '/run/user/1000/current.sock', 'records': []},
                                        Path('/run/user/1000/current.sock')), {})

    def test_restore_ignores_malformed_record_collections_and_entries(self):
        restore = self.module['restore']
        original_request = restore.__globals__['request']
        original_rename = restore.__globals__['rename']
        restore.__globals__['request'] = lambda *args: {
            'type': 'root', 'nodes': [workspace(name='1: GHOST')],
        }
        renamed = []
        restore.__globals__['rename'] = lambda *args: renamed.append(args)
        self.addCleanup(restore.__globals__.__setitem__, 'request', original_request)
        self.addCleanup(restore.__globals__.__setitem__, 'rename', original_rename)
        restore(Path('/unused.sock'), [])
        restore(Path('/unused.sock'), {'100': []})
        restore(Path('/unused.sock'), {'100': {'rendered': '1: GHOST'}})
        self.assertEqual(renamed, [])

    def test_rename_refuses_names_sway_cannot_address_losslessly(self):
        for value in ('quote"name', 'back\\slash', '$term', 'line\nname'):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.module['rename'](Path('/unused.sock'), value, 'safe')
                with self.assertRaises(ValueError):
                    self.module['rename'](Path('/unused.sock'), 'safe', value)

    def test_workspace_runtime_directories_are_private_or_rejected(self):
        runtime = self.runtime / 'runtime'
        runtime.mkdir(mode=0o700)
        directory = self.module['prepare_directory'](runtime)
        self.assertEqual(stat.S_IMODE((runtime / 'oldbook').stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)

        unsafe = self.runtime / 'unsafe'
        unsafe.mkdir(mode=0o700)
        (unsafe / 'oldbook').mkdir(mode=0o755)
        with self.assertRaises(RuntimeError):
            self.module['prepare_directory'](unsafe)
        self.assertEqual(stat.S_IMODE((unsafe / 'oldbook').stat().st_mode), 0o755)
        self.assertFalse((unsafe / 'oldbook/workspaces').exists())


if __name__ == '__main__':
    unittest.main()
