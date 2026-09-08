"""Native shortcut translation and target safety; never inject host input."""
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
try:
    from superhold import shortcut_actions as actions
except ImportError:
    actions = None


class ShortcutTranslationTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(actions, 'native shortcut backend is not implemented')

    def test_alternatives_and_prefixes_keep_case_and_punctuation(self):
        cases = {
            'Ctrl++ / Ctrl+-': [
                {'label': 'Ctrl++', 'sequence': [{'modifiers': ['ctrl'], 'key': 'plus'}]},
                {'label': 'Ctrl+-', 'sequence': [{'modifiers': ['ctrl'], 'key': 'minus'}]}],
            'Ctrl+A, c': [
                {'label': 'Ctrl+A, c', 'sequence': [
                    {'modifiers': ['ctrl'], 'key': 'a'}, {'modifiers': [], 'key': 'c'}]}],
            'n / N': [
                {'label': 'n', 'sequence': [{'modifiers': [], 'key': 'n'}]},
                {'label': 'N', 'sequence': [{'modifiers': ['shift'], 'key': 'N'}]}],
            '/keymap, Enter': [
                {'label': '/keymap, Enter', 'sequence': [
                    {'text': '/keymap'}, {'modifiers': [], 'key': 'Return'}]}],
            'Shift+PageDown': [
                {'label': 'Shift+PageDown', 'sequence': [{'modifiers': ['shift'], 'key': 'Page_Down'}]}],
        }
        for key, expected in cases.items():
            with self.subTest(key=key):
                self.assertEqual(actions.prepare_actions(key), expected)

    def test_source_keys_follow_sway_case_insensitive_resolution_and_release(self):
        row = actions.sway_actions('Mod4+Shift+X', release=True)
        self.assertEqual(row, [{'label': 'Mod4+Shift+X', 'sequence': [
            {'modifiers': ['logo', 'shift'], 'key': 'x'}]}])
        argv = actions.wtype_argv(row[0], key_delay_ms=12)
        self.assertEqual(argv, ['wtype', '-M', 'logo', '-M', 'shift',
                               '-P', 'x', '-s', '12', '-p', 'x',
                               '-m', 'shift', '-m', 'logo'])
        self.assertEqual(actions.prepare_actions('XF86AudioRaiseVolume')[0]['sequence'],
                         [{'modifiers': [], 'key': 'XF86AudioRaiseVolume'}])

    def test_numeric_sway_keysym_preserves_explicit_uppercase(self):
        row = actions.sway_actions('Mod4+Shift+0x58')
        self.assertTrue(row)
        self.assertEqual(row[0]['sequence'], [{'modifiers': ['logo', 'shift'], 'key': 'X'}])
        self.assertIn('0x58', actions.wtype_argv(row[0]))

    def test_sway_ascii_resolution_remains_available_without_xkb_library(self):
        with mock.patch.object(actions, '_xkb', return_value=None):
            row = actions.sway_actions('Mod4+Shift+X')
            self.assertEqual(row[0]['sequence'], [{'modifiers': ['logo', 'shift'], 'key': 'x'}])
            self.assertEqual(actions.sway_actions('Mod4+NotAKeysym'), [])

    def test_tmux_compound_modifiers_and_terminal_key_names_are_native(self):
        from superhold.shortcut_sources import ShortcutProvider
        cases = {
            'C-M-x': {'modifiers': ['ctrl', 'alt'], 'key': 'x'},
            'M-C-X': {'modifiers': ['alt', 'ctrl', 'shift'], 'key': 'X'},
            'BTab': {'modifiers': ['shift'], 'key': 'Tab'},
            'BSpace': {'modifiers': [], 'key': 'BackSpace'},
            'PPage': {'modifiers': [], 'key': 'Page_Up'},
            'NPage': {'modifiers': [], 'key': 'Page_Down'},
        }
        for key, expected in cases.items():
            with self.subTest(key=key):
                translated = actions.prepare_actions(ShortcutProvider._tmux_key(key))
                self.assertTrue(translated)
                self.assertEqual(translated[0]['sequence'], [expected])

    def test_literal_text_cannot_become_shell_or_wtype_options(self):
        action = {'label': 'literal', 'sequence': [{'text': '-;$(id)`x`'}]}
        argv = actions.wtype_argv(action, key_delay_ms=1)
        self.assertEqual(argv[:4], ['wtype', '-P', '0x2d', '-s'])
        self.assertNotIn('$(id)', argv)
        self.assertNotIn('--', argv)
        self.assertNotIn('-;', argv)

    def test_rejects_unknown_gestures_and_unbounded_actions(self):
        for key in ('Super (hold)', 'button1', 'Group2+Super+X', 'code 42',
                    'Ctrl+NotARealKey', 'Ctrl+\nX'):
            with self.subTest(key=key):
                self.assertEqual(actions.prepare_actions(key), [])
        for sequence in ([{'text': 'x' * 257}], [{'key': 'a', 'modifiers': []}] * 65,
                         [{'key': 'a', 'modifiers': ['untrusted']}], [{'command': 'reboot'}]):
            with self.subTest(sequence=sequence):
                with self.assertRaises(ValueError):
                    actions.wtype_argv({'label': 'invalid', 'sequence': sequence})

    def test_long_text_and_slow_key_delay_are_rejected_before_partial_input(self):
        self.assertIn('250', actions.wtype_argv(
            {'label': 'a', 'sequence': [{'key': 'a', 'modifiers': []}]}, key_delay_ms=250))
        with self.assertRaises(ValueError):
            actions.wtype_argv({'label': 'long', 'sequence': [{'text': 'x' * 100}]},
                               key_delay_ms=100)


class NativeDispatchTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(actions, 'native shortcut backend is not implemented')
        self.target = {'con_id': 42, 'pid': 700, 'app_id': 'foot',
                       'window_class': '', 'process_start': '12345',
                       'socket_identity': [8, 900, 123]}
        self.view = {'id': 42, 'pid': 700, 'app_id': 'foot', 'focused': True,
                     'type': 'con', 'nodes': [], 'floating_nodes': []}
        self.calls = []
        self.trees = [{'type': 'root', 'nodes': [self.view]}]
        self.allowed = True
        self.process_start = '12345'
        self.socket_identity = [8, 900, 123]
        self.patchers = [
            mock.patch.object(actions, 'socket_identity', side_effect=lambda _: self.socket_identity),
            mock.patch.object(actions, 'process_start', side_effect=lambda _: self.process_start),
        ]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.sender = actions.NativeShortcutSender(
            '/test/sway.sock', wayland_display='/test/wayland',
            guard=lambda: self.allowed, request=self.request, runner=self.record_input)
        self.action = {'label': 'Copy', 'sequence': [{'key': 'c', 'modifiers': ['ctrl', 'shift']}]}

    def request(self, message_type, payload=''):
        self.calls.append(('ipc', message_type, payload))
        if message_type == 4:
            return self.trees.pop(0) if len(self.trees) > 1 else self.trees[0]
        return [{'success': True}]

    def record_input(self, argv, **kwargs):
        self.calls.append(('input', argv, kwargs))
        return mock.Mock(returncode=0, stderr='')

    def test_restores_verified_original_window_then_sends_only_native_keys(self):
        result = self.sender.send(self.target, self.action)
        self.assertTrue(result['ok'], result)
        self.assertEqual(self.calls[:3], [
            ('ipc', 4, ''), ('ipc', 0, '[con_id=42] focus'), ('ipc', 4, '')])
        argv = self.calls[-1][1]
        self.assertEqual(argv, ['wtype', '-M', 'ctrl', '-M', 'shift',
                               '-P', 'c', '-s', '12', '-p', 'c', '-m', 'shift', '-m', 'ctrl'])
        self.assertEqual(self.calls[-1][2]['env']['WAYLAND_DISPLAY'], '/test/wayland')
        self.assertNotIn('shell', self.calls[-1][2])

    def test_gone_reused_or_changed_target_never_receives_input(self):
        changes = ('missing', 'pid', 'start', 'socket', 'focus', 'locked')
        for change in changes:
            with self.subTest(change=change):
                self.calls.clear()
                self.view.update(pid=700, focused=True)
                self.process_start = '12345'
                self.socket_identity = [8, 900, 123]
                self.allowed = True
                self.trees = [{'type': 'root', 'nodes': [dict(self.view)]}]
                if change == 'missing': self.trees[0]['nodes'] = []
                if change == 'pid': self.trees[0]['nodes'][0]['pid'] = 701
                if change == 'start': self.process_start = '99999'
                if change == 'socket': self.socket_identity = [8, 999, 123]
                if change == 'focus':
                    self.trees[0]['nodes'][0]['focused'] = False
                    self.trees[0]['nodes'].append(dict(self.view, id=99, pid=800))
                if change == 'locked': self.allowed = False
                result = self.sender.send(self.target, self.action)
                self.assertFalse(result['ok'], result)
                self.assertFalse(any(call[0] == 'input' for call in self.calls))

    def test_focus_change_after_restore_aborts_injection(self):
        self.trees = [self.trees[0], {'type': 'root', 'nodes': [
            dict(self.view, focused=False), dict(self.view, id=99, pid=800)]}]
        result = self.sender.send(self.target, self.action)
        self.assertFalse(result['ok'])
        self.assertFalse(any(call[0] == 'input' for call in self.calls))

    def test_sequence_stops_when_first_chord_closes_original_window(self):
        self.action = {'label': 'Close, then type', 'sequence': [
            {'key': 'w', 'modifiers': ['ctrl']}, {'key': 'x', 'modifiers': []}]}
        def close_window(argv, **kwargs):
            result = self.record_input(argv, **kwargs)
            self.trees = [{'type': 'root', 'nodes': []}]
            return result
        self.sender.runner = close_window
        result = self.sender.send(self.target, self.action)
        self.assertFalse(result['ok'])
        injections = [call[1] for call in self.calls if call[0] == 'input']
        self.assertEqual(len(injections), 1)
        self.assertNotIn('x', injections[0])

    def test_missing_backend_and_timeout_are_reported(self):
        for failure in (FileNotFoundError(), __import__('subprocess').TimeoutExpired('wtype', 3)):
            with self.subTest(failure=failure):
                self.sender.runner = mock.Mock(side_effect=failure)
                self.assertFalse(self.sender.send(self.target, self.action)['ok'])


if __name__ == '__main__':
    unittest.main()
