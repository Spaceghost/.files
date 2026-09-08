import fcntl
from pathlib import Path
import runpy
import sys
import tempfile
import threading
import time
import unittest


MODULE = (Path(__file__).resolve().parents[1]
          / 'desktop/.local/lib/oldbook/agent_switcher.py')
sys.path.insert(0, str(MODULE.parent))


class Resolver:
    def resolve_all(self, views):
        identities = {
            11: {'name': 'Codex', 'kind': 'codex', 'state': 'Working'},
            12: {'name': 'Firefox', 'kind': 'app', 'state': None},
            21: {'name': 'Claude', 'kind': 'claude', 'state': None,
                 'tmux_pane': '%3'},
            31: {'name': 'ChatGPT', 'kind': 'chatgpt', 'state': None},
            41: {'name': 'ssh', 'kind': 'app', 'state': None},
            99: {'name': 'Codex', 'kind': 'codex', 'state': None},
        }
        return {view['id']: identities[view['id']] for view in views}


def view(identifier, *, focused=False, app_id='foot'):
    return {'id': identifier, 'type': 'con', 'pid': 1000 + identifier,
            'app_id': app_id, 'name': 'Private title', 'focused': focused,
            'nodes': [], 'floating_nodes': []}


def workspace(identifier, name, views):
    return {'id': identifier, 'type': 'workspace', 'name': name, 'num': identifier,
            'focus': [item['id'] for item in reversed(views)],
            'nodes': views, 'floating_nodes': []}


class AgentSwitcherTests(unittest.TestCase):
    def setUp(self):
        if not MODULE.exists():
            self.fail('agent switcher implementation is missing')
        self.api = runpy.run_path(str(MODULE))

    def tree(self):
        one = workspace(1, '1: GHOST · Firefox', [view(11), view(12)])
        two = workspace(2, '2: ORBIT · Codex', [view(21, focused=True)])
        scratch = workspace(-1, '__i3_scratch', [view(99)])
        three = workspace(3, 'Research', [view(31, app_id='firefox')])
        four = workspace(4, 'Remote', [view(41, app_id='oldbook-agent')])
        output = {'id': 100, 'type': 'output', 'name': 'eDP-1',
                  'focus': [two['id'], one['id'], three['id'], four['id'], scratch['id']],
                  'nodes': [one, two, three, four, scratch], 'floating_nodes': []}
        return {'id': 1_000, 'type': 'root', 'focus': [output['id']],
                'nodes': [output], 'floating_nodes': []}

    def test_candidates_use_resolved_agent_identity_mru_and_exclude_scratch(self):
        candidates = self.api['agent_candidates'](self.tree(), Resolver())
        self.assertEqual([item['id'] for item in candidates], [21, 11, 31, 41])
        self.assertEqual(candidates[0], {
            'id': 21, 'workspace': '2: ORBIT · Codex', 'title': 'Private title',
            'agent': 'Claude (tmux)',
            'kind': 'claude', 'event': None, 'focused': True,
            'pid': 1021, 'app_id': 'foot',
        })
        self.assertNotIn(99, [item['id'] for item in candidates])
        self.assertNotIn(12, [item['id'] for item in candidates])
        self.assertEqual(candidates[-1]['agent'], 'Agent')

    def test_first_step_starts_after_focused_agent_and_wraps_both_directions(self):
        candidates = [
            {'id': 21, 'focused': True}, {'id': 11, 'focused': False},
            {'id': 31, 'focused': False},
        ]
        state = self.api['SwitchState'](candidates, 'next')
        self.assertEqual(state.selected['id'], 11)
        state.step('next')
        self.assertEqual(state.selected['id'], 31)
        state.step('next')
        self.assertEqual(state.selected['id'], 21)
        state.step('previous')
        self.assertEqual(state.selected['id'], 31)

    def test_reverse_first_step_selects_last_when_no_agent_is_focused(self):
        state = self.api['SwitchState'](
            [{'id': 11, 'focused': False}, {'id': 31, 'focused': False}],
            'previous')
        self.assertEqual(state.selected['id'], 31)

    def test_commit_requires_selected_container_to_remain_a_resolved_agent(self):
        state = self.api['SwitchState'](
            [{'id': 11, 'pid': 1011, 'app_id': 'foot', 'focused': True},
             {'id': 21, 'pid': 1021, 'app_id': 'oldbook-agent', 'focused': False}],
            'next')
        fresh = [{'id': 11, 'pid': 1011, 'app_id': 'foot', 'focused': True}]
        self.assertIsNone(state.commit_target(fresh))
        fresh.append({'id': 21, 'pid': 9999, 'app_id': 'oldbook-agent', 'focused': False})
        self.assertIsNone(state.commit_target(fresh))
        fresh[-1] = {'id': 21, 'pid': 1021, 'app_id': 'oldbook-agent', 'focused': False}
        self.assertEqual(state.commit_target(fresh), 21)

    def test_empty_candidates_have_no_selection_or_commit(self):
        state = self.api['SwitchState']([], 'next')
        self.assertIsNone(state.selected)
        state.step('previous')
        self.assertIsNone(state.commit_target([]))

    def test_final_alt_release_commits_only_after_both_alt_keys_are_up(self):
        released = self.api['alt_release_commits']
        self.assertFalse(released('Alt_L', {'Mod1'}))
        self.assertTrue(released('Alt_L', set()))
        self.assertTrue(released('Alt_R', set()))
        self.assertFalse(released('Escape', set()))

    def test_popup_routes_tab_and_shift_tab_without_async_relay(self):
        direction = self.api['tab_direction']
        self.assertEqual(direction('Tab', set()), 'next')
        self.assertEqual(direction('Tab', {'Shift'}), 'previous')
        self.assertEqual(direction('ISO_Left_Tab', {'Shift'}), 'previous')
        self.assertIsNone(direction('Escape', set()))

    def test_waiting_gesture_claims_server_lock_after_predecessor_exits(self):
        with tempfile.TemporaryDirectory() as temporary:
            lock_path = Path(temporary) / 'switcher.lock'
            missing_socket = Path(temporary) / 'switcher.sock'
            owner = lock_path.open('a')
            contender = lock_path.open('a')
            self.addCleanup(owner.close)
            self.addCleanup(contender.close)
            fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)

            release = threading.Thread(target=lambda: (
                time.sleep(.03), fcntl.flock(owner, fcntl.LOCK_UN)))
            release.start()
            self.addCleanup(release.join)
            claimed = self.api['claim_or_forward'](
                contender, missing_socket, 'next', attempts=20, delay=.01)
            self.assertTrue(claimed)

    def test_commit_is_allowed_only_while_switcher_mode_still_owns_gesture(self):
        active = self.api['switcher_mode']
        self.assertTrue(active({'name': 'agent-switcher'}))
        self.assertFalse(active({'name': 'default'}))
        self.assertFalse(active({}))
        self.assertFalse(active([]))

    def test_scrolling_reveals_highlight_only_when_it_leaves_viewport(self):
        reveal = self.api['revealed_scroll_value']
        self.assertEqual(reveal(120, 180, 100, 200), 100)
        self.assertEqual(reveal(40, 90, 100, 200), 40)
        self.assertEqual(reveal(280, 340, 100, 200), 140)

    def test_popup_shows_a_small_agent_set_and_caps_large_sets(self):
        content_height = self.api['popup_content_height']
        self.assertEqual(content_height(1), 64)
        self.assertEqual(content_height(3), 192)
        self.assertEqual(content_height(20), 480)


if __name__ == '__main__':
    unittest.main()
