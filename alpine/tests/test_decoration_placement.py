"""Captions attach to focused floating views until fullscreen needs the edge."""
import importlib.util
from pathlib import Path
import sys
import unittest

LIBRARY = Path(__file__).resolve().parents[1] / 'desktop/.local/lib/mbp_intel'
sys.path.insert(0, str(LIBRARY))


def view(identifier, rect=None, fullscreen=0):
    return {'id': identifier, 'type': 'con', 'app_id': 'fixture',
            'fullscreen_mode': fullscreen,
            'rect': rect or {'x': 100, 'y': 80, 'width': 640, 'height': 400}}


def workspace(identifier, tiled=(), floating=(), focus=None):
    children = list(tiled) + list(floating)
    return {'id': identifier, 'type': 'workspace', 'name': str(identifier),
            'fullscreen_mode': 1,
            'nodes': list(tiled), 'floating_nodes': list(floating),
            'focus': focus if focus is not None else [child['id'] for child in children]}


def output(name, workspaces, focus=None, x=0):
    return {'type': 'output', 'name': name, 'nodes': list(workspaces),
            'focus': focus if focus is not None else [workspaces[0]['id']],
            'rect': {'x': x, 'y': 0, 'width': 1280, 'height': 720}}


class DecorationPlacementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = LIBRARY / 'decoration_placement.py'
        spec = importlib.util.spec_from_file_location('decoration_placement', path)
        cls.model = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.model)

    def test_focused_floating_caption_uses_window_geometry(self):
        floating = view(7)
        tree = {'nodes': [output('eDP-1', [workspace(2, [view(4)], [floating], [7, 4])])]}
        self.assertEqual(self.model.output_placements(tree)['eDP-1'], {
            'mode': 'window', 'edge': 'bottom', 'rect': floating['rect'],
            'square': False, 'window_id': 7})

    def test_dropdown_focus_keeps_last_ordinary_window_context_and_geometry(self):
        import decoration_actions
        for app_id in ('com.mbp-intel.dropdown', 'mbp-intel-dropdown', 'com.mbp-intel.monitor'):
            with self.subTest(app_id=app_id):
                ordinary, console = view(7), view(8)
                console['app_id'] = app_id
                visible = workspace(2, floating=[ordinary, console], focus=[7, 8])
                tree = {'nodes': [output('eDP-1', [visible])]}
                before = self.model.output_placements(tree)['eDP-1']
                visible['focus'] = [8, 7]
                self.assertEqual(self.model.output_placements(tree)['eDP-1'], before)
                self.assertEqual(decoration_actions.output_contexts(tree)['eDP-1']['id'], 7)
                ordinary['rect']['x'] = 260
                self.assertEqual(self.model.output_placements(tree)['eDP-1']['rect']['x'], 260)

    def test_dropdown_focus_history_skips_nested_console_and_resumes_on_leaving(self):
        import decoration_actions
        console = dict(view(8), app_id='com.mbp-intel.dropdown')
        wrapper = {'id': 18, 'type': 'floating_con', 'nodes': [console], 'focus': [8]}
        visible = workspace(2, tiled=[view(4)], floating=[view(7), wrapper], focus=[18, 7, 4])
        tree = {'nodes': [output('eDP-1', [visible])]}
        self.assertEqual(self.model.output_placements(tree)['eDP-1']['window_id'], 7)
        visible['focus'] = [4, 18, 7]
        self.assertEqual(self.model.output_placements(tree)['eDP-1']['window_id'], 4)
        self.assertEqual(self.model.output_placements(tree)['eDP-1']['mode'], 'workspace')
        self.assertEqual(decoration_actions.output_contexts(tree)['eDP-1']['id'], 4)

    def test_closed_last_ordinary_window_does_not_leave_stale_caption_target(self):
        import decoration_actions
        console = dict(view(8), app_id='com.mbp-intel.dropdown')
        visible = workspace(2, floating=[console], focus=[8, 7])
        tree = {'nodes': [output('eDP-1', [visible])]}
        placement = self.model.output_placements(tree)['eDP-1']
        self.assertEqual(placement['mode'], 'workspace')
        self.assertIsNone(placement['window_id'])
        self.assertIsNone(decoration_actions.output_contexts(tree)['eDP-1']['id'])

    def test_similarly_named_terminals_remain_caption_targets(self):
        import decoration_actions
        for app_id in ('com.mbp-intel.monitor-notes', 'com.mbp-intel.dropdown-notes', 'ghostty'):
            with self.subTest(app_id=app_id):
                target = dict(view(8), app_id=app_id)
                tree = {'nodes': [output('eDP-1', [workspace(2, floating=[target])])]}
                self.assertEqual(self.model.output_placements(tree)['eDP-1']['window_id'], 8)
                self.assertEqual(decoration_actions.output_contexts(tree)['eDP-1']['id'], 8)

    def test_fullscreen_console_does_not_override_retained_floating_caption(self):
        for mode in (1, 2):
            for app_id in ('com.mbp-intel.dropdown', 'mbp-intel-dropdown', 'com.mbp-intel.monitor'):
                with self.subTest(mode=mode, app_id=app_id):
                    console = dict(view(8, fullscreen=mode), app_id=app_id)
                    tree = {'nodes': [output('eDP-1', [workspace(
                        2, floating=[view(7), console], focus=[8, 7])])]}
                    placement = self.model.output_placements(tree, 'right')['eDP-1']
                    self.assertEqual((placement['mode'], placement['edge'], placement['window_id']),
                                     ('window', 'right', 7))

    def test_console_only_fullscreen_wrapper_keeps_ordinary_fullscreen_siblings(self):
        console = dict(view(8), app_id='com.mbp-intel.dropdown')
        wrapper = {'id': 18, 'type': 'floating_con', 'fullscreen_mode': 2,
                   'nodes': [console], 'focus': [8]}
        ordinary = view(4)
        visible = workspace(2, tiled=[ordinary], floating=[view(7), wrapper], focus=[18, 7, 4])
        tree = {'nodes': [output('eDP-1', [visible])]}
        placement = self.model.output_placements(tree, 'right')['eDP-1']
        self.assertEqual((placement['mode'], placement['edge']), ('window', 'right'))
        ordinary['fullscreen_mode'] = 1
        placement = self.model.output_placements(tree, 'right')['eDP-1']
        self.assertEqual((placement['mode'], placement['edge'], placement['square']),
                         ('workspace', 'bottom', True))

    def test_attached_caption_tracks_move_and_resize_without_mutating_tree(self):
        floating = view(7)
        tree = {'nodes': [output('eDP-1', [workspace(2, floating=[floating])])]}
        before = self.model.output_placements(tree)['eDP-1']
        floating['rect'].update(x=245, y=110, width=810, height=530)
        after = self.model.output_placements(tree)['eDP-1']
        self.assertEqual(before['rect'], {'x': 100, 'y': 80, 'width': 640, 'height': 400})
        self.assertEqual(after['rect'], {'x': 245, 'y': 110, 'width': 810, 'height': 530})
        after['rect']['width'] = 1
        self.assertEqual(floating['rect']['width'], 810)

    def test_nested_floating_container_attaches_to_focused_view(self):
        target = view(8)
        floating = {'id': 7, 'type': 'floating_con', 'nodes': [view(9), target],
                    'focus': [8, 9]}
        tree = {'nodes': [output('eDP-1', [workspace(2, floating=[floating])])]}
        self.assertEqual(self.model.output_placements(tree)['eDP-1']['window_id'], 8)
        self.assertEqual(self.model.output_placements(tree)['eDP-1']['mode'], 'window')

    def test_tiled_focus_keeps_workspace_strip_despite_other_floating_window(self):
        screen = output('eDP-1', [workspace(2, [view(4)], [view(7)], [4, 7])])
        self.assertEqual(self.model.output_placements({'nodes': [screen]}, 'right')['eDP-1'], {
            'mode': 'workspace', 'edge': 'right', 'rect': screen['rect'],
            'square': False, 'window_id': 4})

    def test_empty_workspace_retains_configured_edge(self):
        screen = output('eDP-1', [workspace(2)])
        placement = self.model.output_placements({'nodes': [screen]}, 'right')['eDP-1']
        self.assertEqual(placement['mode'], 'workspace')
        self.assertEqual(placement['edge'], 'right')
        self.assertIsNone(placement['window_id'])

    def test_fullscreen_sibling_overrides_floating_focus_and_right_preference(self):
        fullscreen = {'id': 5, 'type': 'con', 'nodes': [view(6, fullscreen=1)]}
        screen = output('eDP-1', [workspace(2, [fullscreen], [view(7)], [7, 5])])
        placement = self.model.output_placements({'nodes': [screen]}, 'right')['eDP-1']
        self.assertEqual((placement['mode'], placement['edge'], placement['square']),
                         ('workspace', 'bottom', True))
        self.assertEqual(placement['rect'], screen['rect'])

    def test_hidden_workspace_fullscreen_does_not_displace_visible_floating_caption(self):
        screen = output('eDP-1', [workspace(2, [view(6, fullscreen=1)]),
                                  workspace(3, floating=[view(7)])], focus=[3, 2])
        placement = self.model.output_placements({'nodes': [screen]}, 'right')['eDP-1']
        self.assertEqual((placement['mode'], placement['edge'], placement['square']),
                         ('window', 'right', False))

    def test_workspace_fullscreen_does_not_change_other_output(self):
        floating = view(7, {'x': 1420, 'y': 95, 'width': 720, 'height': 490})
        screens = [output('eDP-1', [workspace(2, [view(6, fullscreen=1)])]),
                   output('DP-1', [workspace(3, floating=[floating])], x=1280)]
        placements = self.model.output_placements({'nodes': screens}, 'right')
        self.assertEqual(placements['eDP-1']['edge'], 'bottom')
        self.assertEqual((placements['DP-1']['mode'], placements['DP-1']['edge']),
                         ('window', 'right'))
        self.assertEqual(placements['DP-1']['rect'], floating['rect'])

    def test_global_fullscreen_anywhere_forces_all_outputs_to_bottom(self):
        screens = [output('eDP-1', [workspace(2, [view(6, fullscreen=2)]),
                                     workspace(4, floating=[view(8)])], focus=[4, 2]),
                   output('DP-1', [workspace(3, floating=[view(7)])], x=1280)]
        placements = self.model.output_placements({'nodes': screens}, 'right')
        self.assertEqual(set(placements), {'eDP-1', 'DP-1'})
        for screen in screens:
            self.assertEqual(placements[screen['name']]['rect'], screen['rect'])
            self.assertEqual((placements[screen['name']]['mode'],
                              placements[screen['name']]['edge'],
                              placements[screen['name']]['square']),
                             ('workspace', 'bottom', True))

    def test_non_container_fullscreen_markers_do_not_override_window_state(self):
        visible = workspace(2, floating=[view(7)])
        screen = output('eDP-1', [visible])
        tree = {'fullscreen_mode': 2, 'nodes': [screen]}
        screen['fullscreen_mode'] = 2
        visible['fullscreen_mode'] = 2
        placement = self.model.output_placements(tree, 'right')['eDP-1']
        self.assertEqual((placement['mode'], placement['edge'], placement['square']),
                         ('window', 'right', False))

    def test_sway_workspace_fullscreen_marker_does_not_block_floating_attachment(self):
        visible = workspace(2, floating=[view(7)])
        visible['fullscreen_mode'] = 1
        tree = {'nodes': [output('eDP-1', [visible])]}
        placement = self.model.output_placements(tree, 'right')['eDP-1']
        self.assertEqual((placement['mode'], placement['edge'], placement['square']),
                         ('window', 'right', False))

    def test_sway_workspace_fullscreen_marker_keeps_tiled_preferred_edge(self):
        visible = workspace(2, tiled=[view(7)])
        visible['fullscreen_mode'] = 1
        tree = {'nodes': [output('eDP-1', [visible])]}
        placement = self.model.output_placements(tree, 'right')['eDP-1']
        self.assertEqual((placement['mode'], placement['edge'], placement['square']),
                         ('workspace', 'right', False))

    def test_floating_fullscreen_keeps_rounding_at_forced_bottom(self):
        screen = output('eDP-1', [workspace(2, floating=[view(7, fullscreen=1)])])
        placement = self.model.output_placements({'nodes': [screen]}, 'right')['eDP-1']
        self.assertEqual((placement['mode'], placement['edge'], placement['square']),
                         ('workspace', 'bottom', False))

    def test_global_floating_fullscreen_keeps_rounding_on_all_outputs(self):
        screens = [output('eDP-1', [workspace(2, floating=[view(7, fullscreen=2)])]),
                   output('DP-1', [workspace(3, [view(8)])], x=1280)]
        placements = self.model.output_placements({'nodes': screens}, 'right')
        self.assertTrue(all(value['edge'] == 'bottom' for value in placements.values()))
        self.assertTrue(all(not value['square'] for value in placements.values()))

    def test_leaving_fullscreen_restores_floating_attachment_and_right_preference(self):
        floating = view(7, fullscreen=1)
        tree = {'nodes': [output('eDP-1', [workspace(2, floating=[floating])])]}
        self.assertEqual(self.model.output_placements(tree, 'right')['eDP-1']['edge'], 'bottom')
        floating['fullscreen_mode'] = 0
        placement = self.model.output_placements(tree, 'right')['eDP-1']
        self.assertEqual((placement['mode'], placement['edge']), ('window', 'right'))

    def test_internal_outputs_and_outputs_without_workspace_have_no_caption(self):
        tree = {'nodes': [output('__i3', [workspace(2, [view(7)])]),
                          {'type': 'output', 'name': 'DP-1', 'nodes': []}]}
        self.assertEqual(self.model.output_placements(tree), {})


class DecorationActionContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import decoration_actions
        cls.actions = decoration_actions

    def test_normal_floating_view_offers_enter_fullscreen_despite_workspace_marker(self):
        visible = workspace(2, floating=[view(7)])
        screen = output('eDP-1', [visible])
        screen['fullscreen_mode'] = 1
        tree = {'fullscreen_mode': 2, 'nodes': [screen]}
        context = self.actions.output_contexts(tree)['eDP-1']
        self.assertFalse(context['fullscreen'])
        self.assertTrue(context['floating'])
        commands = {entry['label']: entry['command']
                    for entry in self.actions.menu_items(context, tree) if entry}
        self.assertEqual(commands['Fullscreen'], ['swaymsg', '[con_id=7] fullscreen enable'])
        self.assertNotIn('Leave fullscreen', commands)

    def test_fullscreen_floating_view_offers_leave_fullscreen(self):
        tree = {'nodes': [output('eDP-1', [workspace(2, floating=[view(7, fullscreen=1)])])]}
        context = self.actions.output_contexts(tree)['eDP-1']
        self.assertTrue(context['fullscreen'])
        commands = {entry['label']: entry['command']
                    for entry in self.actions.menu_items(context, tree) if entry}
        self.assertEqual(commands['Leave fullscreen'], ['swaymsg', '[con_id=7] fullscreen disable'])
        self.assertNotIn('Fullscreen', commands)

    def test_fullscreen_context_follows_actual_focused_ancestors_not_siblings(self):
        focused = {'id': 8, 'type': 'con', 'fullscreen_mode': 1,
                   'nodes': [view(7)], 'focus': [7]}
        visible = workspace(2, tiled=[focused, view(9, fullscreen=1)], focus=[8, 9])
        tree = {'nodes': [output('eDP-1', [visible])]}
        self.assertTrue(self.actions.output_contexts(tree)['eDP-1']['fullscreen'])
        focused['fullscreen_mode'] = 0
        self.assertFalse(self.actions.output_contexts(tree)['eDP-1']['fullscreen'])


if __name__ == '__main__':
    unittest.main()
