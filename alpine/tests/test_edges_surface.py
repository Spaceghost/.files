"""The backdrop is off until asked for, never animates and reserves nothing."""
import json
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'alpine/desktop/.local/lib/oldbook'))
import desktop_space
import edges_surface
import power_source

QML = REPO / 'alpine/desktop/.local/share/oldbook/qml/SignalMargin.qml'
BRIDGE = REPO / 'alpine/desktop/.local/lib/oldbook/native/layer_shell_bridge.cpp'
BUILDER = REPO / 'alpine/bin/build-layer-shell-bridge'
SESSION = REPO / 'alpine/desktop/.local/bin/oldbook-session'
EFFECTS = REPO / 'alpine/desktop/.config/swayfx/effects.conf'


class PreferenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / 'edges.json'
        self.addCleanup(self.directory.cleanup)

    def test_absent_preferences_leave_the_backdrop_off(self):
        self.assertEqual(edges_surface.preferences(self.path),
                         {'enabled': False, 'signal-margin': True})

    def test_enabling_is_the_only_way_it_starts(self):
        self.path.write_text(json.dumps({'enabled': True}))
        self.assertTrue(edges_surface.preferences(self.path)['enabled'])

    def test_a_damaged_or_hostile_file_falls_back_to_off(self):
        for text in ('', 'not json', '[]', '{"enabled": "yes"}',
                     '{"enabled": true, "rm": "-rf"}'):
            self.path.write_text(text)
            settings = edges_surface.preferences(self.path)
            self.assertEqual(set(settings), {'enabled', 'signal-margin'})
            self.assertIs(settings['enabled'], text.startswith('{"enabled": true'))

    def test_the_session_starts_it_only_through_that_preference(self):
        text = SESSION.read_text()
        self.assertIn('oldbook-edges start', text)
        self.assertNotIn('oldbook-edges start --force', text)
        self.assertNotIn('oldbook-edges run', text)


class LadderTests(unittest.TestCase):
    def test_the_effect_asks_the_ladder_by_a_name_of_its_own(self):
        self.assertEqual(edges_surface.LADDER_EFFECT, 'desktop-edges')
        self.assertNotIn(edges_surface.LADDER_EFFECT, ('shaders', 'window-ghosts'))

    def test_an_unregistered_name_still_runs_at_every_posture(self):
        # POWER-POSTURE: the ladder is a list of things that shed, so a helper
        # is never switched off by omission. Registering the name is what makes
        # it shed, and that edit belongs to power_source.py.
        for posture in power_source.POSTURES:
            self.assertTrue(power_source.allows(edges_surface.LADDER_EFFECT, posture))

    def test_a_registered_name_would_shed_with_no_change_here(self):
        ladder = dict(power_source.LADDER, **{edges_surface.LADDER_EFFECT: 'battery-low'})
        original = power_source.LADDER
        power_source.LADDER = ladder
        try:
            self.assertTrue(power_source.allows(edges_surface.LADDER_EFFECT, 'battery-low'))
            self.assertFalse(power_source.allows(edges_surface.LADDER_EFFECT, 'battery-critical'))
        finally:
            power_source.LADDER = original


class SurfaceContractTests(unittest.TestCase):
    def test_the_surface_is_bottom_layer_with_no_reservation_and_no_keyboard(self):
        self.assertEqual(edges_surface.LAYER_BOTTOM, 1)
        self.assertEqual(edges_surface.ANCHOR_ALL, 1 | 2 | 4 | 8)
        self.assertEqual(edges_surface.EXCLUSIVE_ZONE, 0)
        self.assertEqual(edges_surface.KEYBOARD_NONE, 0)

    def test_the_namespace_is_the_one_the_region_and_the_effects_file_use(self):
        self.assertEqual(edges_surface.NAMESPACE, desktop_space.EFFECT_NAMESPACE)
        self.assertIn(f'layer_effects "{edges_surface.NAMESPACE}"', EFFECTS.read_text())

    def test_every_colour_is_a_palette_role(self):
        import overlay_theme

        self.assertIn(edges_surface.TICK_ROLE, overlay_theme.read_palette())
        source = Path(edges_surface.__file__).read_text() + QML.read_text()
        literals = set(re.findall(r'"#[0-9a-fA-F]{3,8}"', source))
        # The QML default is a placeholder that every apply() overwrites; no
        # other hex colour may appear in either file.
        self.assertEqual(literals, {'"#aaaaaa"'})

    def test_the_bridge_refuses_anything_that_would_reserve_space(self):
        bridge = edges_surface.load_bridge()
        call = bridge.oldbook_layer_shell_configure
        # DECORATION-PLACEMENT: the caption band owns the only exclusive zone on
        # this desktop, and oldbook-background's -1 is one careless copy away.
        self.assertEqual(call(None, None, b'x', 1, 15, -1, 0, 1440, 900), -5)
        self.assertEqual(call(None, None, b'x', 1, 15, 32, 0, 1440, 900), -5)
        self.assertEqual(call(None, None, b'x', 4, 15, 0, 0, 1440, 900), -2)
        self.assertEqual(call(None, None, b'x', 1, 99, 0, 0, 1440, 900), -3)
        self.assertEqual(call(None, None, b'x', 1, 15, 0, 5, 1440, 900), -4)
        self.assertEqual(call(None, None, b'x', 1, 15, 0, 0, 0, 900), -7)
        # Everything valid, and only the window is missing.
        self.assertEqual(call(None, None, b'x', 1, 15, 0, 0, 1440, 900), -1)


class MotionRuleTests(unittest.TestCase):
    """Plank 1 animates nothing, and the gate on that is plank 3."""

    FORBIDDEN = ('Behavior', 'NumberAnimation', 'ColorAnimation', 'PropertyAnimation',
                 'SequentialAnimation', 'ParallelAnimation', 'SpringAnimation',
                 'SmoothedAnimation', 'PathAnimation', 'AnimatedSprite', 'Transition',
                 'Timer', 'FrameAnimation', 'frameSwapped', 'animations')

    def test_the_scene_carries_no_animation_primitive(self):
        text = QML.read_text()
        for name in self.FORBIDDEN:
            self.assertNotIn(name + ' {', text)
            self.assertNotIn(name + '{', text)
        self.assertNotIn('running: true', text)

    def test_the_only_timer_is_the_one_that_coalesces_a_burst(self):
        text = Path(edges_surface.__file__).read_text()
        self.assertEqual(text.count('QTimer('), 1)
        self.assertIn('setSingleShot(True)', text)
        self.assertNotIn('start(0)', text)

    def test_nothing_is_drawn_inside_the_output_corner_arc(self):
        text = QML.read_text()
        self.assertIn('cornerInset', text)
        self.assertIn('inCorner', text)
        self.assertIn('property real cornerInset: 20', text)


class ServiceTests(unittest.TestCase):
    def test_the_space_service_publishes_nothing_with_no_consumer(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = dict(os.environ, XDG_RUNTIME_DIR=directory)
            environment.pop('SWAYSOCK', None)
            result = subprocess.run(
                [sys.executable, str(REPO / 'alpine/desktop/.local/bin/oldbook-space'), 'run'],
                env=environment, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((Path(directory) / 'oldbook/space.json').exists())

    def test_the_bridge_source_is_the_only_native_code_and_needs_no_package(self):
        self.assertEqual(sorted(path.name for path in BRIDGE.parent.iterdir()),
                         ['layer_shell_bridge.cpp'])
        self.assertNotIn('abuild', BUILDER.read_text())

    def test_starting_the_surfaces_never_compiles_anything(self):
        loader = importlib.machinery.SourceFileLoader('bridge_builder', str(BUILDER))
        specification = importlib.util.spec_from_loader(loader.name, loader)
        builder = importlib.util.module_from_spec(specification)
        loader.exec_module(builder)

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'unbuilt.cpp'
            source.write_text('int oldbook_layer_shell_configure(void) { return 0; }\n')
            with mock.patch.dict(os.environ, {'XDG_CACHE_HOME': directory}, clear=False):
                os.environ.pop('OLDBOOK_ALLOW_LOCAL_BUILD', None)
                # The session start asks for the cache and accepts being told no.
                with self.assertRaises(RuntimeError) as refused:
                    builder.build(source=source, allow_local=False)
                self.assertIn('build-layer-shell-bridge', str(refused.exception))
                # A cache entry that already matches is handed over, not rebuilt.
                target = builder.library_path(source)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b'')
                self.assertEqual(builder.build(source=source, allow_local=False), target)

    def test_the_surfaces_ask_for_the_cache_rather_than_a_build(self):
        text = (REPO / 'alpine/desktop/.local/lib/oldbook/edges_surface.py').read_text()
        self.assertIn('module.build(allow_local=allow_local)', text)
        self.assertIn('def library_path(allow_local=False)', text)


if __name__ == '__main__':
    unittest.main()
