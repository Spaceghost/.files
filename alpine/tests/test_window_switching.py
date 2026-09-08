"""Behavior of the shared carousel without GTK or a running compositor."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                     / 'desktop/.local/lib/mbp_intel'))
import window_switching as switching


def view(identifier, app_id='foot', **values):
    return {'id': identifier, 'type': 'con', 'pid': identifier + 1000,
            'app_id': app_id, 'name': f'Window {identifier}', 'focused': False,
            'visible': False, 'rect': {'x': 0, 'y': 0, 'width': 400, 'height': 300},
            'nodes': [], 'floating_nodes': [], **values}


def workspace(identifier, number, views, **values):
    return {'id': identifier, 'type': 'workspace', 'num': number,
            'name': f'{number}: Example', 'nodes': views, 'floating_nodes': [],
            'focus': [item['id'] for item in views], **values}


def candidate(identifier, **values):
    return {'id': identifier, 'pid': identifier + 1000, 'app_id': 'foot',
            'focused': False, 'title': f'Window {identifier}', **values}


class CandidateTests(unittest.TestCase):
    def tree(self):
        one = workspace(101, 1, [view(11), view(12)],
                        floating_nodes=[view(13, 'firefox')], focus=[13, 12, 11])
        ten = workspace(110, 10, [view(21, 'mbp-intel-strata')], name='10: Strata')
        scratch = workspace(199, -1, [view(99)], name='__i3_scratch')
        named = workspace(120, -1, [view(31, 'mbp-intel-agent')], name='Research')
        first = {'id': 201, 'type': 'output', 'name': 'eDP-1',
                 'nodes': [one, ten, scratch], 'focus': [110, 101, 199]}
        second = {'id': 202, 'type': 'output', 'name': 'HDMI-A-1', 'nodes': [named]}
        return {'type': 'root', 'nodes': [first, second], 'focus': [201, 202]}

    def test_includes_all_apps_tiled_floating_named_workspaces_and_outputs(self):
        result = switching.window_candidates(self.tree())
        self.assertEqual([item['id'] for item in result], [21, 13, 12, 11, 31])
        self.assertEqual(result[0]['workspace_num'], 10)
        self.assertEqual(result[0]['workspace'], '10: Strata')
        self.assertEqual(result[0]['workspace_id'], 110)
        self.assertEqual(result[0]['output'], 'eDP-1')
        self.assertEqual(result[-1]['output'], 'HDMI-A-1')
        self.assertEqual(result[-1]['workspace'], 'Research')

    def test_excludes_scratch_and_exact_helper_ids_without_excluding_agent_apps(self):
        tree = self.tree()
        tree['nodes'][0]['nodes'][0]['nodes'].extend([
            view(40, 'mbp-intel-carousel'), view(41, 'mbp-intel-showdesktop'),
            view(42, 'mbp-intel-agent-switcher'), view(43, 'mbp-intel-shortcuts'),
            view(44, 'mbp-intel-carousel-editor'),
        ])
        ids = [item['id'] for item in switching.window_candidates(tree)]
        self.assertNotIn(99, ids)
        for identifier in (40, 41, 42, 43):
            self.assertNotIn(identifier, ids)
        self.assertIn(44, ids)
        self.assertIn(31, ids)

    def test_preserves_raw_unicode_title_and_capture_identifier_for_hidden_views(self):
        tree = self.tree()
        source = tree['nodes'][0]['nodes'][1]['nodes'][0]
        source.update(name='Café <Review> & Δοκιμή', visible=False,
                      foreign_toplevel_identifier='native-handle-21')
        item = switching.window_candidates(tree)[0]
        self.assertEqual(item['title'], source['name'])
        self.assertEqual(item['app_id'], 'mbp-intel-strata')
        self.assertEqual(item['application'], 'mbp-intel-strata')
        self.assertEqual(item['foreign_toplevel_identifier'], 'native-handle-21')
        self.assertIs(item['visible'], False)
        source['rect']['width'] = 1
        self.assertEqual(item['rect']['width'], 400)

    def test_includes_xwayland_and_uses_its_class_without_inventing_app_id(self):
        tree = self.tree()
        source = tree['nodes'][0]['nodes'][1]['nodes'][0]
        source.update(app_id=None, window=314, name='', visible=True,
                      window_properties={'class': 'Legacy Editor'})
        item = switching.window_candidates(tree)[0]
        self.assertIsNone(item['app_id'])
        self.assertEqual(item['application'], 'Legacy Editor')
        self.assertEqual(item['title'], 'Legacy Editor')
        self.assertTrue(item['visible'])

    def test_invalid_ids_and_duplicate_focus_entries_do_not_duplicate_candidates(self):
        tree = self.tree()
        one = tree['nodes'][0]['nodes'][0]
        one['focus'] = [13, 13, 12, 111111]
        one['nodes'].append(view(True))
        self.assertEqual([item['id'] for item in switching.window_candidates(tree)],
                         [21, 13, 12, 11, 31])


class FocusHistoryTests(unittest.TestCase):
    def test_actual_focus_events_interleave_windows_across_workspace_groups(self):
        # Tree fallback groups A1/A2 before B1; actual usage is A1, B1, A2.
        items = [candidate(11), candidate(12), candidate(21)]
        history = switching.FocusHistory()
        history.update(items)
        history.record(items, 11)
        history.record(items, 21)
        result = history.record(items, 12)
        self.assertEqual([item['id'] for item in result], [12, 21, 11])
        # A later tree traversal order must not overwrite the observed history.
        self.assertEqual([item['id'] for item in history.update(list(reversed(items)))],
                         [12, 21, 11])

    def test_closed_identity_is_pruned_and_reused_id_starts_as_unseen(self):
        items = [candidate(11), candidate(21), candidate(31)]
        history = switching.FocusHistory()
        history.record(items, 11)
        replacement = candidate(11, pid=9999)
        result = history.update([replacement, items[2], items[1]])
        self.assertEqual([item['id'] for item in result], [21, 31, 11])
        self.assertEqual(result[-1]['pid'], 9999)
        self.assertEqual(history.update([]), [])

    def test_explicit_focus_event_wins_over_a_stale_tree_flag(self):
        items = [candidate(11, focused=True), candidate(21)]
        history = switching.FocusHistory()
        self.assertEqual([item['id'] for item in history.record(items, 21)], [21, 11])
        items[0]['focused'] = False
        self.assertEqual([item['id'] for item in history.record(items, 999)], [21, 11])
        self.assertEqual([item['id'] for item in history.record(items, 21)], [21, 11])


class SwitchStateTests(unittest.TestCase):
    def setUp(self):
        self.items = [candidate(11, focused=True), candidate(21), candidate(31)]

    def test_show_keeps_current_while_first_forward_and_reverse_step_select_neighbors(self):
        self.assertEqual(switching.SwitchState(self.items, 'show').selected['id'], 11)
        self.assertEqual(switching.SwitchState(self.items, 'next').selected['id'], 21)
        self.assertEqual(switching.SwitchState(self.items, 'previous').selected['id'], 31)

    def test_unfocused_desktop_starts_at_mru_or_reverse_end(self):
        items = [candidate(11), candidate(21)]
        for action in ('show', 'next'):
            self.assertEqual(switching.SwitchState(items, action).selected['id'], 11)
        self.assertEqual(switching.SwitchState(items, 'previous').selected['id'], 21)

    def test_steps_wrap_in_the_frozen_order(self):
        state = switching.SwitchState(self.items, 'next')
        state.step('next')
        self.assertEqual(state.selected['id'], 31)
        state.step('next')
        self.assertEqual(state.selected['id'], 11)
        state.step('previous')
        self.assertEqual(state.selected['id'], 31)

    def test_refresh_preserves_selection_and_order_despite_new_windows_and_tree_reorder(self):
        state = switching.SwitchState(self.items, 'next')
        changed = dict(self.items[1], title='Updated title')
        state.refresh([self.items[2], candidate(41), changed, self.items[0]])
        self.assertEqual([item['id'] for item in state.candidates], [11, 21, 31])
        self.assertEqual(state.selected['id'], 21)
        self.assertEqual(state.selected['title'], 'Updated title')
        state.refresh([changed, self.items[2]])
        self.assertEqual(state.selected['id'], 21)
        self.assertEqual(state.index, 0)

    def test_closed_selection_advances_to_next_survivor_and_wraps(self):
        state = switching.SwitchState(self.items, 'next')
        state.refresh([self.items[0], self.items[2]])
        self.assertEqual(state.selected['id'], 31)
        state.refresh([self.items[0]])
        self.assertEqual(state.selected['id'], 11)
        state.refresh([])
        self.assertIsNone(state.selected)
        state.step('next')
        self.assertIsNone(state.commit_target(self.items))

    def test_commit_revalidates_pid_and_app_id_not_just_container_number(self):
        state = switching.SwitchState(self.items, 'next')
        self.assertEqual(state.commit_target(self.items), 21)
        for replacement in (candidate(21, pid=9999), candidate(21, app_id='firefox')):
            self.assertIsNone(state.commit_target([self.items[0], replacement]))
        state.refresh([self.items[0], candidate(21, pid=9999), self.items[2]])
        self.assertEqual([item['id'] for item in state.candidates], [11, 31])
        self.assertEqual(state.selected['id'], 31)

    def test_empty_and_single_window_gestures_are_safe(self):
        empty = switching.SwitchState([], 'show')
        self.assertIsNone(empty.selected)
        empty.refresh(self.items)
        self.assertIsNone(empty.selected)
        single = switching.SwitchState(self.items[:1], 'previous')
        single.step('next')
        self.assertEqual(single.commit_target(self.items), 11)


class GestureInputTests(unittest.TestCase):
    def test_only_final_initiating_modifier_release_commits(self):
        commits = switching.modifier_release_commits
        for family, keys, mask in (
                ('alt', ('Alt_L', 'Alt_R'), 'Mod1'),
                ('super', ('Super_L', 'Super_R'), 'Mod4')):
            for key in keys:
                self.assertFalse(commits(family, key, {mask}))
                self.assertTrue(commits(family, key, set()))
                self.assertTrue(commits(family, key, {'Shift'}))
        self.assertFalse(commits('super', 'Alt_L', set()))
        self.assertFalse(commits('alt', 'Super_R', set()))
        self.assertFalse(commits('super', 'Shift_L', set()))

    def test_persistent_gesture_never_accepts_a_modifier_release(self):
        for key in ('Alt_L', 'Alt_R', 'Super_L', 'Super_R'):
            self.assertFalse(switching.modifier_release_commits(None, key, set()))
        self.assertEqual(switching.key_action('Return', set()), 'commit')
        self.assertEqual(switching.key_action('KP_Enter', set()), 'commit')
        self.assertEqual(switching.key_action('Escape', {'Mod4'}), 'cancel')

    def test_tab_directions_and_unrelated_keys(self):
        self.assertEqual(switching.tab_direction('Tab', {'Mod4'}), 'next')
        self.assertEqual(switching.tab_direction('Tab', {'Shift', 'Mod1'}), 'previous')
        self.assertEqual(switching.tab_direction('ISO_Left_Tab', set()), 'previous')
        self.assertEqual(switching.key_action('Tab', {'Shift'}), 'previous')
        self.assertIsNone(switching.key_action('a', set()))


if __name__ == '__main__':
    unittest.main()
