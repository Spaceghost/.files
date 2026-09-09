"""Captions attach to focused floating views until fullscreen needs the edge."""
import importlib.util
from pathlib import Path
import sys
import unittest

LIBRARY = Path(__file__).resolve().parents[1] / 'desktop/.local/lib/oldbook'
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
        for app_id in ('com.oldbook.dropdown', 'oldbook-dropdown', 'com.oldbook.monitor'):
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
        console = dict(view(8), app_id='com.oldbook.dropdown')
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
        console = dict(view(8), app_id='com.oldbook.dropdown')
        visible = workspace(2, floating=[console], focus=[8, 7])
        tree = {'nodes': [output('eDP-1', [visible])]}
        placement = self.model.output_placements(tree)['eDP-1']
        self.assertEqual(placement['mode'], 'workspace')
        self.assertIsNone(placement['window_id'])
        self.assertIsNone(decoration_actions.output_contexts(tree)['eDP-1']['id'])

    def test_similarly_named_terminals_remain_caption_targets(self):
        import decoration_actions
        for app_id in ('com.oldbook.monitor-notes', 'com.oldbook.dropdown-notes', 'ghostty'):
            with self.subTest(app_id=app_id):
                target = dict(view(8), app_id=app_id)
                tree = {'nodes': [output('eDP-1', [workspace(2, floating=[target])])]}
                self.assertEqual(self.model.output_placements(tree)['eDP-1']['window_id'], 8)
                self.assertEqual(decoration_actions.output_contexts(tree)['eDP-1']['id'], 8)

    def test_fullscreen_console_does_not_override_retained_floating_caption(self):
        for mode in (1, 2):
            for app_id in ('com.oldbook.dropdown', 'oldbook-dropdown', 'com.oldbook.monitor'):
                with self.subTest(mode=mode, app_id=app_id):
                    console = dict(view(8, fullscreen=mode), app_id=app_id)
                    tree = {'nodes': [output('eDP-1', [workspace(
                        2, floating=[view(7), console], focus=[8, 7])])]}
                    placement = self.model.output_placements(tree, 'right')['eDP-1']
                    self.assertEqual((placement['mode'], placement['edge'], placement['window_id']),
                                     ('window', 'right', 7))

    def test_console_only_fullscreen_wrapper_keeps_ordinary_fullscreen_siblings(self):
        console = dict(view(8), app_id='com.oldbook.dropdown')
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


class ReservedBandTests(unittest.TestCase):
    """The band that stops a hover from resizing anything."""

    @classmethod
    def setUpClass(cls):
        path = LIBRARY / 'decoration_reserve.py'
        spec = importlib.util.spec_from_file_location('decoration_reserve', path)
        cls.band = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.band)
        placement = LIBRARY / 'decoration_placement.py'
        spec = importlib.util.spec_from_file_location('decoration_placement', placement)
        cls.model = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.model)

    def test_the_band_is_the_same_on_every_output_whatever_has_focus(self):
        """A floating window takes its caption with it; the band stays put.

        This is the whole fix: the reservation used to travel with the caption,
        so crossing from a tiled terminal to a floating one released it and
        every tiled window on the output was resized by its thickness.
        """
        floating = view(7)
        attached = {'nodes': [output('eDP-1', [workspace(2, [view(4)], [floating], [7, 4])])]}
        tiled = {'nodes': [output('eDP-1', [workspace(2, [view(4)], [floating], [4, 7])])]}
        placements = [self.model.output_placements(tree) for tree in (attached, tiled)]
        self.assertEqual([found['eDP-1']['mode'] for found in placements],
                         ['window', 'workspace'])
        plans = [self.band.band_plan(found, 'bottom', 39) for found in placements]
        self.assertEqual(plans[0], plans[1])
        self.assertEqual(plans[0], {'eDP-1': {'edge': 'bottom', 'thickness': 39}})

    def test_fullscreen_moves_the_caption_and_leaves_the_band_alone(self):
        """Fullscreen ignores exclusive zones, so moving the band would only
        resize the ordinary windows on the way in and again on the way out."""
        tree = {'nodes': [output('eDP-1', [workspace(2, [view(4, fullscreen=1)])])]}
        placement = self.model.output_placements(tree, 'right')['eDP-1']
        self.assertEqual(placement['edge'], 'bottom')
        self.assertEqual(self.band.band_plan({'eDP-1': placement}, 'right', 44),
                         {'eDP-1': {'edge': 'right', 'thickness': 44}})

    def test_a_caption_steps_back_over_the_band_it_may_not_reserve(self):
        """Zero zone keeps the strip inside the usable area; the negative margin
        puts it back over its own band, exactly where it has always been."""
        self.assertEqual(self.band.caption_margin(39), self.band.EDGE_MARGIN - 39)
        self.assertEqual(self.band.caption_margin(0), self.band.EDGE_MARGIN)
        self.assertEqual(self.band.caption_offset(39), (0, self.band.EDGE_MARGIN - 39))
        # No band: reserve nothing, and keep respecting whoever else reserved.
        self.assertEqual(self.band.caption_offset(0), (0, self.band.EDGE_MARGIN))
        # Fullscreen borrows the bottom while the band holds the right edge;
        # that band is not this caption's, so it takes the whole output.
        self.assertEqual(self.band.caption_offset(39, matching=False),
                         (-1, self.band.EDGE_MARGIN))

    def test_the_band_is_measured_from_a_reference_line_not_the_live_caption(self):
        reference = self.band.REFERENCE
        for glyph in ('\ue725', '\ue0b0', '›', '·'):
            self.assertIn(glyph, reference)
        self.assertEqual(self.band.band_thickness(34), 34 + self.band.EDGE_MARGIN)
        # A failed measurement must not hand the compositor a nonsense band.
        for broken in (0, -20, None, 'tall'):
            self.assertEqual(self.band.band_thickness(broken), self.band.MINIMUM)
        self.assertEqual(self.band.band_thickness(10_000), self.band.MAXIMUM)

    def test_the_band_is_measured_by_a_caption_on_its_own_edge(self):
        """Fullscreen borrows the bottom while the band stays on the saved edge.

        Sizing the reservation from whichever caption happened to exist made
        entering fullscreen re-measure the right band from a bottom caption and
        resize the windows beside it — the same bug wearing a different hat.
        """
        measured = {'bottom': 39, 'right': 55}
        self.assertEqual(self.band.band_measurement(measured, 'right'), 55)
        self.assertEqual(self.band.band_measurement(measured, 'bottom'), 39)
        # No caption has been drawn along that edge yet, so it keeps the floor
        # rather than the other edge's number.
        self.assertEqual(self.band.band_measurement({'bottom': 39}, 'right'),
                         self.band.band_thickness(0))
        self.assertEqual(self.band.band_measurement({}, 'bottom'),
                         self.band.band_thickness(0))

    def test_turning_the_band_off_reserves_nothing_at_all(self):
        placements = {'eDP-1': {'mode': 'workspace'}}
        self.assertEqual(self.band.band_plan(placements, 'bottom', 39, enabled=False), {})
        self.assertEqual(self.band.band_plan(placements, 'bottom', 0), {})

    def test_the_band_only_ever_uses_an_edge_the_strip_uses(self):
        with self.assertRaises(ValueError):
            self.band.band_plan({'eDP-1': {}}, 'top', 39)
        self.assertEqual(self.band.band_anchors('bottom'), ('BOTTOM', 'LEFT', 'RIGHT'))
        self.assertEqual(self.band.band_anchors('right'), ('RIGHT', 'TOP', 'BOTTOM'))

    def test_the_caption_budget_leaves_room_for_the_controls(self):
        wide = self.band.character_budget(1440, 7.5, 200)
        narrow = self.band.character_budget(400, 7.5, 200)
        self.assertGreater(wide, narrow)
        self.assertEqual(wide, int((1440 - 200) / 7.5))
        self.assertEqual(self.band.character_budget(40, 7.5, 200), self.band.MINIMUM_BUDGET)
        self.assertIsNone(self.band.character_budget(1440, 0))
        self.assertIsNone(self.band.character_budget(1440, None))


if __name__ == '__main__':
    unittest.main()
