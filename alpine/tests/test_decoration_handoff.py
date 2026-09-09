"""Exercise the production caption with real, deliberately unmapped GTK widgets."""
import ast
import os
from pathlib import Path
import runpy
import subprocess
import sys
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'desktop/.local/bin/oldbook-decoration'
ISOLATION_MARKER = 'OLDBOOK_DECORATION_HANDOFF_TEST_CHILD'


class CaptionHandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get(ISOLATION_MARKER) != '1':
            return
        try:
            import gi
            sys.path.insert(0, str(SCRIPT.resolve().parents[1] / 'lib/oldbook'))
            from showdesktop import preload_layer_shell
            preload_layer_shell()
            gi.require_version('Gtk', '4.0')
            gi.require_version('Gdk', '4.0')
            gi.require_version('Gtk4LayerShell', '1.0')
            from gi.repository import Gtk, Gdk, GLib, Gio, Gtk4LayerShell, Pango
        except (ImportError, ValueError, OSError):
            raise unittest.SkipTest('GTK4 and layer-shell introspection are unavailable')
        Gtk.init()
        if Gdk.Display.get_default() is None or not Gtk4LayerShell.is_supported():
            raise unittest.SkipTest('The unmapped GTK fixture needs a Wayland display')
        # Caption is local to daemon() so its GTK imports stay lazy. Compile
        # that production class alone; never start the live session daemon.
        namespace = runpy.run_path(str(SCRIPT))
        daemon = next(node for node in ast.parse(SCRIPT.read_text()).body
                      if isinstance(node, ast.FunctionDef) and node.name == 'daemon')
        caption = next(node for node in daemon.body
                       if isinstance(node, ast.ClassDef) and node.name == 'Caption')
        # The caption calls the small helpers daemon() defines ahead of it --
        # the stylesheet loader, the click gesture and the child walk -- so
        # they are compiled with it rather than reimplemented here.
        helpers = [node for node in daemon.body
                   if isinstance(node, ast.FunctionDef) and node.lineno < caption.lineno]
        display = Gdk.Display.get_default()
        namespace.update(Gtk=Gtk, Gdk=Gdk, GLib=GLib, Gio=Gio,
                         Gtk4LayerShell=Gtk4LayerShell, Pango=Pango,
                         display=display, retired=set())
        exec(compile(ast.Module(body=helpers + [caption], type_ignores=[]),
                     str(SCRIPT), 'exec'), namespace)
        cls.Caption = namespace['Caption']
        cls.shell = Gtk4LayerShell
        cls.reserve = namespace['decoration_reserve']
        cls.monitor = display.get_monitors().get_item(0)

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


    def test_the_caption_reserves_nothing_and_steps_back_over_its_band(self):
        """Reserving from the caption is exactly what made hovering resize
        windows: the zone travelled with focus, so crossing between a tiled and
        a floating terminal took the band away and gave it back. The caption
        now reserves nothing in either mode and only steps back over the band
        the reservation surface holds for it."""
        if os.environ.get(ISOLATION_MARKER) != '1':
            # The isolated child above runs this file whole; running the GTK
            # fixture twice in one session buys nothing.
            self.skipTest('covered by the isolated child run')
        shell = self.shell
        workspace = {'mode': 'workspace', 'edge': 'bottom', 'window_id': None,
                     'rect': {'x': 0, 'y': 0, 'width': 1440, 'height': 900}}
        caption = self.Caption(self.monitor, workspace, animate_entry=False)
        self.addCleanup(caption.destroy)
        self.assertEqual(shell.get_exclusive_zone(caption.window), 0)
        self.assertEqual(shell.get_margin(caption.window, shell.Edge.BOTTOM),
                         self.reserve.EDGE_MARGIN)
        caption.set_band(39)
        # The same row, expressed the only way GTK4 can express it. Stepping
        # back over the band is a negative margin, and gtk4-layer-shell cannot
        # carry one: the size it asks the compositor for collapses to zero and
        # the surface is given an arbitrary default instead. Declining every
        # reservation and stepping in from the raw edge puts the strip exactly
        # where the negative margin put it, because the band it steps over is
        # the only thing reserving that edge. It still reserves nothing: a zone
        # of -1 declines other reservations, it does not make one.
        self.assertEqual(shell.get_margin(caption.window, shell.Edge.BOTTOM),
                         self.reserve.EDGE_MARGIN)
        self.assertEqual(shell.get_exclusive_zone(caption.window), -1)

        attached = self.Caption(self.monitor, {
            'mode': 'window', 'edge': 'bottom', 'window_id': 3,
            'rect': {'x': 200, 'y': 160, 'width': 620, 'height': 360}}, animate_entry=False)
        self.addCleanup(attached.destroy)
        # An attached caption follows a window anywhere in the output, so it
        # needs the whole coordinate space and still reserves nothing.
        self.assertEqual(shell.get_exclusive_zone(attached.window), -1)
        attached.set_band(39)
        self.assertEqual(shell.get_margin(attached.window, shell.Edge.TOP), 0)


if __name__ == '__main__':
    result = unittest.main(exit=False).result
    sys.exit(77 if result.skipped else (0 if result.wasSuccessful() else 1))
