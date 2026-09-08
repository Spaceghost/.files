"""Focused window sizing respects usable workspace bounds and mode changes."""
import copy
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


HELPER = Path(__file__).resolve().parents[1] / 'desktop/.local/bin/oldbook-resize'
loader = importlib.machinery.SourceFileLoader('oldbook_resize', str(HELPER))
spec = importlib.util.spec_from_loader(loader.name, loader)
resize_helper = importlib.util.module_from_spec(spec)
loader.exec_module(resize_helper)


class NearFullResize(unittest.TestCase):
    def run_resize(self, bounds, actual, *, floating=True, fullscreen=False,
                   direction='near-full'):
        target = {'id': 7, 'app_id': 'resize-fixture', 'focused': True,
                  'type': 'floating_con' if floating else 'con',
                  'fullscreen_mode': int(fullscreen),
                  'rect': {'x': 90, 'y': 70, 'width': 600, 'height': 400}}
        workspace = {'type': 'workspace', 'rect': bounds, 'nodes': [],
                     'floating_nodes': []}
        workspace['floating_nodes' if floating else 'nodes'] = [target]
        tree = {'type': 'root', 'nodes': [
            {'type': 'output', 'nodes': [workspace]},
            {'type': 'output', 'nodes': [{'type': 'workspace', 'focused': True,
             'rect': {'x': 0, 'y': 0, 'width': 800, 'height': 600}, 'nodes': []}]}]}
        updated = copy.deepcopy(tree)
        changed = resize_helper.find_window(updated, 7)
        changed['rect'] = actual
        responses = [tree]
        commands = []

        def ipc(kind, command=None):
            if kind == 'get_tree':
                return responses.pop(0) if responses else updated
            self.assertEqual(kind, 'command')
            commands.append(command)
            return [{'success': True}]

        with tempfile.TemporaryDirectory() as runtime, patch.dict(os.environ, {
                'XDG_RUNTIME_DIR': runtime, 'SWAYSOCK': '/private/fixture.sock'}), \
                patch.object(resize_helper, 'ipc', side_effect=ipc):
            resize_helper.resize(direction)
        return commands

    def test_floating_window_uses_its_workspace_not_its_old_center(self):
        bounds = {'x': -1600, 'y': 50, 'width': 1600, 'height': 900}
        commands = self.run_resize(bounds, {'x': -1520, 'y': 95,
                                            'width': 1440, 'height': 810})
        self.assertIn('resize set 1440 px 810 px', commands[0])
        self.assertIn('move absolute position -1520 px 95 px', ', '.join(commands))
        self.assertNotIn('floating enable', commands[0])

    def test_fullscreen_tiled_window_floats_and_centers_constrained_size(self):
        bounds = {'x': 1600, 'y': 40, 'width': 1600, 'height': 860}
        commands = self.run_resize(bounds, {'x': 0, 'y': 0,
                                            'width': 1500, 'height': 800},
                                   floating=False, fullscreen=True)
        self.assertIn('fullscreen disable, floating enable, resize set 1440 px 774 px',
                      commands[0])
        self.assertEqual(commands[-1], '[con_id=7] move absolute position 1650 px 70 px')

    def test_small_workspace_keeps_twenty_four_pixel_margins(self):
        bounds = {'x': 20, 'y': 30, 'width': 400, 'height': 300}
        commands = self.run_resize(bounds, {'x': 44, 'y': 54,
                                            'width': 352, 'height': 252})
        self.assertIn('resize set 352 px 252 px', commands[0])
        self.assertIn('move absolute position 44 px 54 px', ', '.join(commands))

    def test_tiny_workspace_never_requests_zero_or_negative_dimensions(self):
        bounds = {'x': 0, 'y': 0, 'width': 32, 'height': 40}
        commands = self.run_resize(bounds, {'x': 0, 'y': 0, 'width': 1, 'height': 1})
        self.assertIn('resize set 1 px 1 px', commands[0])

    def test_grow_still_uses_the_existing_centered_step(self):
        bounds = {'x': 0, 'y': 0, 'width': 1600, 'height': 900}
        commands = self.run_resize(bounds, {'x': 70, 'y': 50,
                                            'width': 640, 'height': 440},
                                   direction='grow')
        self.assertEqual(commands, ['[con_id=7] resize set 640 px 440 px'])

    def test_no_focused_window_does_nothing(self):
        with tempfile.TemporaryDirectory() as runtime, patch.dict(os.environ, {
                'XDG_RUNTIME_DIR': runtime, 'SWAYSOCK': '/private/fixture.sock'}), \
                patch.object(resize_helper, 'ipc', return_value={'type': 'root'}) as ipc:
            resize_helper.resize('near-full')
        ipc.assert_called_once_with('get_tree')


if __name__ == '__main__':
    unittest.main()
