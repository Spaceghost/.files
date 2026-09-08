"""Exercise the production caption with real, deliberately unmapped GTK widgets."""
import ast
import os
from pathlib import Path
import runpy
import subprocess
import sys
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'desktop/.local/bin/mbp-intel-decoration'
ISOLATION_MARKER = 'MBP_INTEL_DECORATION_HANDOFF_TEST_CHILD'


class CaptionHandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get(ISOLATION_MARKER) != '1':
            return
        try:
            import gi
            gi.require_version('Gtk', '3.0')
            gi.require_version('Gdk', '3.0')
            gi.require_version('GtkLayerShell', '0.1')
            from gi.repository import Gtk, Gdk, GLib, Gio, GtkLayerShell, Pango
        except (ImportError, ValueError):
            raise unittest.SkipTest('GTK3 and layer-shell introspection are unavailable')
        if Gdk.Display.get_default() is None or not GtkLayerShell.is_supported():
            raise unittest.SkipTest('The unmapped GTK fixture needs a Wayland display')
        # Caption is local to daemon() so its GTK imports stay lazy. Compile
        # that production class alone; never start the live session daemon.
        namespace = runpy.run_path(str(SCRIPT))
        daemon = next(node for node in ast.parse(SCRIPT.read_text()).body
                      if isinstance(node, ast.FunctionDef) and node.name == 'daemon')
        caption = next(node for node in daemon.body
                       if isinstance(node, ast.ClassDef) and node.name == 'Caption')
        namespace.update(Gtk=Gtk, Gdk=Gdk, GLib=GLib, Gio=Gio,
                         GtkLayerShell=GtkLayerShell, Pango=Pango, retired=set())
        exec(compile(ast.Module(body=[caption], type_ignores=[]), str(SCRIPT), 'exec'), namespace)
        cls.Caption = namespace['Caption']
        cls.monitor = Gdk.Display.get_default().get_monitor(0)

    def test_handoff_keeps_allocated_controls_and_styles_without_mapping_old_geometry(self):
        if os.environ.get(ISOLATION_MARKER) != '1':
            # GTK keeps a display connection and toolkit workers alive after
            # widgets are destroyed. Keep that global state out of other
            # tests, especially GTK4 fixtures and IPC cadence measurements.
            result = subprocess.run(
                [sys.executable, str(Path(__file__).resolve())],
                env=dict(os.environ, **{ISOLATION_MARKER: '1'}),
                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30)
            if result.returncode == 77:
                self.skipTest(result.stderr.strip())
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return
        initial = {'mode': 'window', 'edge': 'bottom', 'window_id': 1,
                   'rect': {'x': 200, 'y': 160, 'width': 620, 'height': 360}}
        target = {'mode': 'window', 'edge': 'bottom', 'window_id': 2,
                  'rect': {'x': 900, 'y': 120, 'width': 420, 'height': 280}}
        caption = self.Caption(self.monitor, initial, animate_entry=False)
        self.addCleanup(caption.destroy)
        window, label, provider = caption.window, caption.label, caption.provider
        style = ('fixture-style', False)
        caption.previous_style = style
        caption.previous_display = ('old title',)
        caption.previous_geometry = ('old geometry',)
        caption.rendered_size = (620, 28)
        caption.motion_rect = {'x': 200, 'y': 520, 'width': 620, 'height': 28}
        caption.motion_target = dict(caption.motion_rect)
        caption.motion_velocity = {key: 30 for key in caption.motion_rect}
        caption.alpha, caption.alpha_velocity = 0.5, 2

        replacement = caption.handoff(target)
        self.addCleanup(replacement.destroy)

        self.assertIs(replacement, caption, 'hover rebuilt the GTK widget tree')
        self.assertIs(replacement.window, window)
        self.assertIs(replacement.label, label)
        self.assertIs(replacement.provider, provider)
        self.assertEqual(replacement.previous_style, style)
        self.assertFalse(window.get_mapped())
        self.assertFalse(window.get_realized())
        self.assertEqual(window.get_opacity(), 1)
        for name in ('previous_display', 'previous_geometry', 'rendered_size',
                     'motion_rect', 'motion_target'):
            self.assertIsNone(getattr(replacement, name), name)
        self.assertEqual(set(replacement.motion_velocity.values()), {0})
        self.assertEqual(replacement.alpha_velocity, 0)


if __name__ == '__main__':
    result = unittest.main(exit=False).result
    sys.exit(77 if result.skipped else (0 if result.wasSuccessful() else 1))
