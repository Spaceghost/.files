"""Workspace captions follow focus and keep vertical titles readable."""
import importlib.util
import json
import math
from pathlib import Path
import runpy
import sys
import tempfile
import unittest

MODEL = Path(__file__).resolve().parents[1] / 'desktop/.local/lib/oldbook/decoration.py'
SCRIPT = Path(__file__).resolve().parents[1] / 'desktop/.local/bin/oldbook-decoration'
# The model validates the landing wave's settings through its sibling module.
sys.path.insert(0, str(MODEL.parent))
import ripple  # noqa: E402


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
                         ['/home/fixture/.local/bin/oldbook-control', 'windows'])
        self.assertEqual(self.model.action_command(2, home),
                         ['swaymsg', 'floating', 'toggle'])
        self.assertIsNone(self.model.action_command(3, home))
        self.assertEqual(self.model.action_command(3, home, shifted=True),
                         ['/home/fixture/.local/bin/oldbook-decoration-settings'])

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
        with tempfile.TemporaryDirectory(prefix='oldbook-decoration-theme-') as directory:
            root = Path(directory)
            (root / 'foot').mkdir()
            (root / 'foot/foot.ini').write_text(
                '[main]\nfont=Fixture Mono:size=9.5\n')
            script = runpy.run_path(str(SCRIPT))
            script['appearance'].__globals__['CONFIG'] = root
            script['appearance'].__globals__['SETTINGS'] = root / 'oldbook/decoration.json'
            script['appearance'].__globals__['STATE'] = root / 'state'
            script['appearance'].__globals__['read_palette'] = lambda: {
                'background': '#13091f', 'surface': '#261631',
                'foreground': '#eaddf5', 'accent': '#dca7ff',
                'muted': '#816b91', 'border': '#261631',
                'background_hard': '#13091f'}
            script['appearance'].__globals__['design_font'] = lambda: None
            script['appearance'].__globals__['design_opacity'] = lambda: 0.78
            script['appearance'].__globals__['design_radius'] = lambda: 22

            (family, size, colors, settings, theme_opacity,
             window_corner) = script['appearance']()

            self.assertEqual((family, size), ('Fixture Mono', 9.5))
            self.assertEqual(settings, {'position': 'bottom', 'opacity': 0.78,
                                        'corner_radius': 7, 'reserve_band': True, 'agent_status': True,
                                        'powerline': False, 'ripple': ripple.settings()})
            # The strip matches the window it decorates, so the theme's terminal
            # transparency travels with the appearance.
            self.assertEqual(theme_opacity, 0.78)
            # The compositor's own window rounding travels with it too: the
            # strip closes the seam from this number and SwayFX will not report
            # or set a container's radius for anyone to ask instead.
            self.assertEqual(window_corner, 22)
            self.assertEqual(colors['surface'], '#261631')
            self.assertEqual(colors['accent'], '#dca7ff')
            self.assertEqual(colors['muted'], '#816b91')

            # Ghost Observatory: a theme design typeface replaces the terminal
            # face for captions, one point larger; the same face keeps its size.
            script['appearance'].__globals__['design_font'] = lambda: 'Fixture Sans'
            self.assertEqual(script['appearance']()[:2], ('Fixture Sans', 10.5))
            script['appearance'].__globals__['design_font'] = lambda: 'Fixture Mono'
            self.assertEqual(script['appearance']()[:2], ('Fixture Mono', 9.5))

    def test_an_attached_bottom_strip_and_its_window_are_one_shape(self):
        """The seam is closed on the strip's side, never on the compositor's.

        SwayFX 0.6 has no per-window corner radius: `cmd_corner_radius` writes
        the single global config value whatever criteria precede it and widens
        the titlebar padding on the way past, so asking it to square one window
        squares every window opened afterwards. The strip climbs over the arc
        the compositor clipped instead, which also means there is nothing to
        undo when the caption detaches or moves to another window.
        """
        self.assertEqual(self.model.seam_overlap('window', 'bottom', 22), 22)
        # A right-edge strip meets a vertical side and a workspace strip
        # belongs to no window at all; neither has a seam to close.
        self.assertEqual(self.model.seam_overlap('window', 'right', 22), 0)
        self.assertEqual(self.model.seam_overlap('workspace', 'bottom', 22), 0)
        # A theme with no radius, or an unusable one, simply does not merge.
        self.assertEqual(self.model.seam_overlap('window', 'bottom', None), 0)
        self.assertEqual(self.model.seam_overlap('window', 'bottom', True), 0)
        self.assertEqual(self.model.window_radius(-4), 0)
        self.assertEqual(self.model.window_radius(400), self.model.CORNER_LIMIT)

    def test_merged_corners_are_square_only_where_the_two_surfaces_meet(self):
        # Merged, the pair is one shape: the bottom takes the window's radius
        # so the assembly is not rounded 22 at the top and 6 at the bottom.
        self.assertEqual(self.model.corner_radii(6, False, True, 22), (0, 22))
        self.assertEqual(self.model.corner_radii(6, False, True), (0, 6))
        self.assertEqual(self.model.corner_radii(6, False, False), (6, 6))
        # Fullscreen tiled chrome stays square all round, as it always was.
        self.assertEqual(self.model.corner_radii(6, True, False), (0, 0))
        self.assertEqual(self.model.corner_radii(6, True, True), (0, 0))

    def test_design_radius_follows_the_theme_the_compositor_was_built_from(self):
        script = runpy.run_path(str(SCRIPT))
        with tempfile.TemporaryDirectory(prefix='oldbook-decoration-radius-') as directory:
            root = Path(directory)
            (root / 'current').write_text('fixture\n')
            (root / 'fixture.json').write_text(json.dumps(
                {'design': {'font': 'Fixture Sans', 'radius': 22, 'opacity': 0.78}}))
            self.assertEqual(script['design_radius'](root), 22)
            (root / 'fixture.json').write_text(json.dumps({'design': {}}))
            self.assertEqual(script['design_radius'](root), 0)
            (root / 'current').write_text('missing\n')
            self.assertEqual(script['design_radius'](root), 0)

    def test_the_seam_fill_is_the_captions_own_first_row(self):
        script = runpy.run_path(str(SCRIPT))
        self.assertEqual(script['components']('#261631', 1.0),
                         (0x26 / 255, 0x16 / 255, 0x31 / 255, 1.0))
        self.assertEqual(script['components']('#261631', 3)[3], 1.0)
        self.assertIsNone(script['components']('not a colour', 1.0))
        self.assertIsNone(script['components'](None, 1.0))

    def test_design_font_reads_the_active_theme_descriptor(self):
        script = runpy.run_path(str(SCRIPT))
        with tempfile.TemporaryDirectory(prefix='oldbook-decoration-font-') as directory:
            themes = Path(directory)
            (themes / 'current').write_text('fixture\n')
            (themes / 'fixture.json').write_text(json.dumps(
                {'palette': {}, 'design': {'font': 'Fixture Sans'}}))
            self.assertEqual(script['design_font'](themes), 'Fixture Sans')
            (themes / 'fixture.json').write_text(json.dumps({'palette': {}}))
            self.assertIsNone(script['design_font'](themes))
            (themes / 'current').write_text('../escape\n')
            self.assertIsNone(script['design_font'](themes))
            self.assertIsNone(script['design_font'](themes / 'missing'))

    def test_decoration_settings_validate_ranges_and_types(self):
        self.assertTrue(hasattr(self.model, 'validate_settings'))
        defaults = {'position': 'bottom', 'opacity': 0.78, 'corner_radius': 7,
                    'reserve_band': True, 'powerline': False, 'agent_status': True,
                    'ripple': ripple.settings()}
        self.assertEqual(self.model.validate_settings({}), defaults)
        self.assertEqual(self.model.validate_settings(
            {'position': 'right', 'opacity': 0.2, 'corner_radius': 24}),
            dict(defaults, position='right', opacity=0.2, corner_radius=24))
        # The band is on unless the user says otherwise; powerline is off until
        # they ask for it.
        self.assertEqual(self.model.validate_settings(
            {'powerline': True, 'reserve_band': False}),
            dict(defaults, powerline=True, reserve_band=False))
        # The landing wave's object is ripple.settings' to judge: a partial one
        # is filled in, and a wrong one is reported rather than drawn.
        self.assertEqual(self.model.validate_settings({'ripple': {'spacing': 30}}),
                         dict(defaults, ripple=ripple.settings({'spacing': 30})))
        invalid = [
            {'unknown': 1}, {'position': 'top'}, {'opacity': True},
            {'opacity': math.nan}, {'opacity': 0.19}, {'opacity': 1.01},
            {'corner_radius': True}, {'corner_radius': 1.5},
            {'corner_radius': -1}, {'corner_radius': 25},
            {'powerline': 'yes'}, {'reserve_band': 1},
            {'ripple': 3}, {'ripple': {'source': 'edge'}}, {'ripple': {'spacing': 'wide'}},
            {'ripple': {'module': ''}}, {'ripple': {'module': 1}},
        ]
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.model.validate_settings(values)

    def test_the_strip_is_as_transparent_as_the_window_it_decorates(self):
        """A translucent terminal gets a translucent strip; a solid application
        gets a solid one, so the caption reads as part of that window."""
        terminal = {'app_id': 'com.mitchellh.ghostty', 'name': '~'}
        browser = {'app_id': 'firefox', 'name': 'Rice Board'}
        self.assertEqual(self.model.window_opacity(terminal, True, 0.78, 0.67), 0.78)
        self.assertEqual(self.model.window_opacity(browser, False, 0.78, 0.67), 1.0)
        # Nothing to decorate: the saved preference decorates the desktop.
        self.assertEqual(self.model.window_opacity({}, False, 0.78, 0.67), 0.67)
        # A theme without a terminal opacity falls back the same way.
        self.assertEqual(self.model.window_opacity(terminal, True, None, 0.67), 0.67)

    def test_an_explicitly_transparent_window_is_believed_over_the_theme(self):
        """Sway only reports an opacity where something set one, and a window it
        calls fully opaque has told us nothing its application had not."""
        asked = {'app_id': 'firefox', 'name': 'Rice Board', 'opacity': 0.5}
        self.assertEqual(self.model.window_opacity(asked, False, 0.78, 0.67), 0.5)
        solid = {'app_id': 'com.mitchellh.ghostty', 'name': '~', 'opacity': 1.0}
        self.assertEqual(self.model.window_opacity(solid, True, 0.78, 0.67), 0.78)
        # Never so faint that the caption stops being readable.
        faint = {'app_id': 'firefox', 'opacity': 0.01}
        self.assertEqual(self.model.window_opacity(faint, False, 0.78, 0.67),
                         self.model.OPACITY_FLOOR)

    def test_design_opacity_reads_the_active_theme_descriptor(self):
        script = runpy.run_path(str(SCRIPT))
        with tempfile.TemporaryDirectory(prefix='oldbook-decoration-opacity-') as directory:
            themes = Path(directory)
            (themes / 'current').write_text('fixture\n')
            (themes / 'fixture.json').write_text(json.dumps(
                {'palette': {}, 'design': {'opacity': 0.78}}))
            self.assertEqual(script['design_opacity'](themes), 0.78)
            (themes / 'fixture.json').write_text(json.dumps({'palette': {}, 'design': {}}))
            self.assertIsNone(script['design_opacity'](themes))
            (themes / 'fixture.json').write_text(json.dumps(
                {'palette': {}, 'design': {'opacity': 'clear'}}))
            self.assertIsNone(script['design_opacity'](themes))
            self.assertIsNone(script['design_opacity'](themes / 'missing'))

    def test_settings_migrate_legacy_position_and_save_through_symlink(self):
        self.assertTrue(hasattr(self.model, 'load_settings'))
        self.assertTrue(hasattr(self.model, 'save_settings'))
        with tempfile.TemporaryDirectory(prefix='oldbook-decoration-settings-') as directory:
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
                                     'corner_radius': 7, 'reserve_band': True, 'agent_status': True,
                                     'powerline': False, 'ripple': ripple.settings()})
            self.assertEqual(json.loads(target.read_text()), saved)
            self.assertEqual(legacy.read_text(), 'bottom\n')


if __name__ == '__main__':
    unittest.main()
