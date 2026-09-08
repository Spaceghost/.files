"""Workspace captions follow focus and keep vertical titles readable."""
import importlib.util
import json
import math
from pathlib import Path
import runpy
import tempfile
import unittest

MODEL = Path(__file__).resolve().parents[1] / 'desktop/.local/lib/mbp_intel/decoration.py'
SCRIPT = Path(__file__).resolve().parents[1] / 'desktop/.local/bin/mbp-intel-decoration'


class DecorationTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(MODEL.exists(), 'workspace decoration model is missing')
        spec = importlib.util.spec_from_file_location('decoration', MODEL)
        self.model = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.model)

    def test_vertical_text_uses_horizontal_separators_and_preserves_accents(self):
        text = self.model.vertical_title('Cafe\u0301 | Claude', 50)
        self.assertIn('e\u0301', text.splitlines())
        self.assertNotIn('|', text)
        self.assertIn('—', text.splitlines())
        self.assertEqual(self.model.vertical_title('abcdef', 4), 'a\nb\nc\n…')

    def test_focus_path_includes_floating_windows_and_nested_splits(self):
        tree = {'id': 1, 'focus': [3, 2], 'nodes': [
            {'id': 2, 'app_id': 'foot', 'name': 'old'}], 'floating_nodes': [
            {'id': 3, 'focus': [4], 'nodes': [
                {'id': 4, 'app_id': 'foot', 'name': '<Claude> | ~/work'}]}]}
        self.assertEqual(self.model.focused_title(tree), '<Claude> | ~/work')
        self.assertEqual(self.model.focused_title({'nodes': []}), '')

    def test_captions_follow_each_outputs_selected_workspace(self):
        tree = {'nodes': [{'type': 'output', 'name': 'eDP-1', 'focus': [20],
                          'nodes': [
                              {'id': 10, 'type': 'workspace', 'name': 'old',
                               'nodes': [{'id': 11, 'app_id': 'foot', 'name': 'hidden'}]},
                              {'id': 20, 'type': 'workspace', 'name': 'work', 'focus': [21],
                               'nodes': [{'id': 21, 'app_id': 'foot', 'name': 'visible'}]}]}]}
        self.assertEqual(self.model.output_titles(tree), {'eDP-1': 'visible'})

    def test_fullscreen_square_caption_excludes_floating_windows(self):
        tree = {'nodes': [{'type': 'output', 'name': 'eDP-1', 'focus': [1],
                          'nodes': [{'id': 1, 'focus': [2], 'nodes': [
                              {'id': 2, 'app_id': 'foot', 'fullscreen_mode': 1}]}]}]}
        self.assertEqual(self.model.square_outputs(tree), {'eDP-1'})
        workspace = tree['nodes'][0]['nodes'][0]
        workspace['floating_nodes'] = workspace.pop('nodes')
        self.assertEqual(self.model.square_outputs(tree), set())

    def test_fullscreen_square_caption_uses_visible_output_and_root_state(self):
        tree = {'fullscreen_mode': 2, 'nodes': [
            {'type': 'output', 'name': '__i3', 'nodes': [
                {'id': 9, 'app_id': 'hidden'}]},
            {'type': 'output', 'name': 'eDP-1', 'focus': [1], 'nodes': [
                {'id': 1, 'focus': [2], 'nodes': [{'id': 2, 'app_id': 'visible'}]}]}]}
        self.assertEqual(self.model.square_outputs(tree), {'eDP-1'})

    def test_pointer_actions_use_fixed_argv_without_a_shell(self):
        home = Path('/home/fixture')
        self.assertEqual(self.model.action_command(1, home),
                         ['/home/fixture/.local/bin/mbp-intel-control', 'windows'])
        self.assertEqual(self.model.action_command(2, home),
                         ['swaymsg', 'floating', 'toggle'])
        self.assertIsNone(self.model.action_command(3, home))
        self.assertEqual(self.model.action_command(3, home, shifted=True),
                         ['/home/fixture/.local/bin/mbp-intel-decoration-settings'])

    def test_geometry_update_reaches_main_loop_before_ready_redrawing(self):
        try:
            from gi.repository import GLib
        except ImportError:
            self.skipTest('GLib introspection is unavailable')
        script = runpy.run_path(str(SCRIPT))
        loop = GLib.MainLoop()
        events = []
        redraws = 0

        def redraw():
            nonlocal redraws
            redraws += 1
            if not events:
                events.append('redraw')
            return redraws < 2

        def geometry():
            events.append('geometry')
            loop.quit()
            return False

        # GTK redraw work has priority 120. Keep it ready for another dispatch
        # so lower-priority geometry would visibly lose the ordering test.
        # A finite source avoids confusing scheduler delays with GLib priority.
        sources = [GLib.idle_add(redraw, priority=120),
                   script['queue_geometry_update'](geometry)]
        try:
            loop.run()
            self.assertEqual(events, ['geometry'],
                             'redrawing delayed the pending caption geometry')
        finally:
            context = GLib.MainContext.default()
            for identifier in sources:
                source = context.find_source_by_id(identifier)
                if source is not None:
                    source.destroy()

    def test_appearance_combines_foot_font_with_validated_active_palette(self):
        with tempfile.TemporaryDirectory(prefix='mbp-intel-decoration-theme-') as directory:
            root = Path(directory)
            (root / 'foot').mkdir()
            (root / 'foot/foot.ini').write_text(
                '[main]\nfont=Fixture Mono:size=9.5\n')
            script = runpy.run_path(str(SCRIPT))
            script['appearance'].__globals__['CONFIG'] = root
            script['appearance'].__globals__['SETTINGS'] = root / 'mbp-intel/decoration.json'
            script['appearance'].__globals__['STATE'] = root / 'state'
            script['appearance'].__globals__['read_palette'] = lambda: {
                'background': '#13091f', 'surface': '#261631',
                'foreground': '#eaddf5', 'accent': '#dca7ff',
                'muted': '#816b91', 'border': '#261631',
                'background_hard': '#13091f'}

            family, size, colors, settings = script['appearance']()

            self.assertEqual((family, size), ('Fixture Mono', 9.5))
            self.assertEqual(settings, {'position': 'bottom', 'opacity': 0.78,
                                        'corner_radius': 7})
            self.assertEqual(colors['surface'], '#261631')
            self.assertEqual(colors['accent'], '#dca7ff')
            self.assertEqual(colors['muted'], '#816b91')

    def test_decoration_settings_validate_ranges_and_types(self):
        self.assertTrue(hasattr(self.model, 'validate_settings'))
        defaults = {'position': 'bottom', 'opacity': 0.78, 'corner_radius': 7}
        self.assertEqual(self.model.validate_settings({}), defaults)
        self.assertEqual(self.model.validate_settings(
            {'position': 'right', 'opacity': 0.2, 'corner_radius': 24}),
            {'position': 'right', 'opacity': 0.2, 'corner_radius': 24})
        invalid = [
            {'unknown': 1}, {'position': 'top'}, {'opacity': True},
            {'opacity': math.nan}, {'opacity': 0.19}, {'opacity': 1.01},
            {'corner_radius': True}, {'corner_radius': 1.5},
            {'corner_radius': -1}, {'corner_radius': 25},
        ]
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.model.validate_settings(values)

    def test_settings_migrate_legacy_position_and_save_through_symlink(self):
        self.assertTrue(hasattr(self.model, 'load_settings'))
        self.assertTrue(hasattr(self.model, 'save_settings'))
        with tempfile.TemporaryDirectory(prefix='mbp-intel-decoration-settings-') as directory:
            root = Path(directory)
            config = root / 'profile/decoration.json'
            target = root / 'theme/decoration.json'
            legacy = root / 'state/position'
            target.parent.mkdir()
            config.parent.mkdir()
            legacy.parent.mkdir()
            legacy.write_text('right\n')
            config.symlink_to(target)

            migrated = self.model.load_settings(config, legacy)

            self.assertEqual(migrated['position'], 'right')
            self.assertTrue(config.is_symlink())
            self.assertEqual(json.loads(target.read_text()), migrated)
            saved = self.model.save_settings(config, {'position': 'bottom', 'opacity': 0.55},
                                             legacy)
            self.assertTrue(config.is_symlink())
            self.assertEqual(saved, {'position': 'bottom', 'opacity': 0.55,
                                     'corner_radius': 7})
            self.assertEqual(json.loads(target.read_text()), saved)
            self.assertEqual(legacy.read_text(), 'bottom\n')


if __name__ == '__main__':
    unittest.main()
