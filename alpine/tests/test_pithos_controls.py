"""Pithos window routing and click arbitration without touching the live desktop."""
import importlib.machinery
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'desktop/.local/bin/mbp-intel-pithos'


class PithosControlsTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.exists(), 'Pithos controls helper is missing')
        loader = importlib.machinery.SourceFileLoader('pithos_controls', str(SCRIPT))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        self.module = importlib.util.module_from_spec(spec)
        loader.exec_module(self.module)

    def tree(self, workspace='music', visible=True, app_id='io.github.Pithos'):
        return {'nodes': [{'type': 'workspace', 'name': workspace, 'nodes': [],
                          'floating_nodes': [{'id': 42, 'app_id': app_id,
                                              'visible': visible}]}]}

    def command(self, action, tree):
        commands = []
        def ipc(kind, command=None):
            if kind == 'get_tree':
                return tree
            commands.append(command)
            return [{'success': True}]
        with patch.object(self.module, 'ipc', side_effect=ipc):
            self.module.window_action(action)
        return commands

    def test_right_click_hides_visible_window_without_quitting(self):
        self.assertEqual(self.command('toggle', self.tree()), ['[con_id=42] move scratchpad'])

    def test_middle_click_selects_tired_and_super_selects_ban(self):
        for held, expected in ((False, 'tired'), (True, 'ban')):
            with self.subTest(super_held=held), \
                    patch.object(self.module, 'super_pressed', return_value=held), \
                    patch.object(self.module, 'rate_song') as rate:
                self.module.middle_click()
                rate.assert_called_once_with(expected)

    def test_meta_on_non_keyboard_is_ignored(self):
        meta = bytearray(96)
        meta[125 // 8] |= 1 << (125 % 8)
        self.assertFalse(self.module.keyboard_super(bytearray(96), meta))

    def test_both_command_keys_are_supported(self):
        capabilities = bytearray(96)
        for key in (30, 28, 57):
            capabilities[key // 8] |= 1 << (key % 8)
        for key in (125, 126):
            pressed = bytearray(96)
            pressed[key // 8] |= 1 << (key % 8)
            self.assertTrue(self.module.keyboard_super(capabilities, pressed))
        self.assertFalse(self.module.keyboard_super(capabilities, bytearray(96)))

    def test_alpine_lowercase_app_id_is_recognized(self):
        self.assertEqual(self.command('toggle', self.tree(app_id='pithos')),
                         ['[con_id=42] move scratchpad'])

    def test_right_click_shows_hidden_scratchpad(self):
        self.assertEqual(self.command('toggle', self.tree('__i3_scratch', False)),
                         ['[con_id=42] scratchpad show, focus'])

    def test_double_click_focuses_visible_window_instead_of_hiding(self):
        self.assertEqual(self.command('show', self.tree()), ['[con_id=42] focus'])

    def test_window_on_another_workspace_is_brought_here(self):
        self.assertEqual(self.command('toggle', self.tree('other', False)),
                         ['[con_id=42] move workspace current, focus'])

    def test_start_does_not_raise_or_hide_existing_instance(self):
        with patch.object(self.module, 'running', return_value=True), patch.object(self.module, 'ipc') as ipc:
            self.module.window_action('start')
        ipc.assert_not_called()

    def test_cold_start_launches_and_keeps_window_hidden(self):
        commands = []
        trees = iter([{'nodes': []}, self.tree('__i3_scratch', False)])
        def ipc(kind, command=None):
            if kind == 'get_tree':
                return next(trees)
            commands.append(command)
            return [{'success': True}]
        with patch.object(self.module, 'running', return_value=False), patch.object(self.module, 'ipc', side_effect=ipc):
            self.module.window_action('start')
        self.assertEqual(commands, ['exec pithos'])

    def test_show_reactivates_a_window_hidden_by_the_tray(self):
        commands = []
        trees = iter([{'nodes': []}, self.tree('__i3_scratch', False)])
        def ipc(kind, command=None):
            if kind == 'get_tree':
                return next(trees)
            commands.append(command)
            return [{'success': True}]
        with patch.object(self.module, 'ipc', side_effect=ipc):
            self.module.window_action('show')
        self.assertEqual(commands, ['exec pithos', '[con_id=42] scratchpad show, focus'])

    def test_single_click_toggles_once(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(self.module, 'play_pause') as play, patch.object(self.module, 'window_action') as window:
                self.module.click(Path(directory), delay=.01)
        play.assert_called_once_with()
        window.assert_not_called()

    def test_double_click_opens_without_toggling_playback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sleep = self.module.time.sleep
            entered = False
            def second_click(delay):
                nonlocal entered
                if not entered:
                    entered = True
                    self.module.click(root, delay=1)
                else:
                    sleep(.001)
            with patch.object(self.module.time, 'sleep', side_effect=second_click), patch.object(self.module, 'play_pause') as play, patch.object(self.module, 'window_action') as window:
                self.module.click(root, delay=1)
        play.assert_not_called()
        window.assert_called_once_with('show')


if __name__ == '__main__':
    unittest.main()
