"""Card composition keeps device pixels, invalidates variants, and releases images."""
import gc
import math
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'desktop/.local/lib/mbp_intel'))
from carousel_view import Popup


class CardCache(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import gi
            for name in ('Gtk', 'Gdk', 'Gsk'):
                gi.require_version(name, '4.0')
            gi.require_version('Graphene', '1.0')
            from gi.repository import Gdk, GLib, Graphene, Gsk, Gtk
        except (ImportError, ValueError) as error:
            raise unittest.SkipTest(str(error))
        cls.native = SimpleNamespace(Gdk=Gdk, GLib=GLib, Graphene=Graphene, Gsk=Gsk, Gtk=Gtk)

    def setUp(self):
        self.view = view = Popup.__new__(Popup)
        for name, value in vars(self.native).items():
            setattr(view, name, value)
        self.scale = 2
        self.compositions = []
        self.texture_refs = []
        view.stage = SimpleNamespace(get_scale_factor=lambda: self.scale, queue_draw=lambda: None)
        display = SimpleNamespace(is_closed=lambda: True)
        view.window = SimpleNamespace(get_renderer=lambda: self, get_display=lambda: display,
                                      destroy=lambda: None)
        view.closed = False
        view._ids, view._textures, view._card_nodes = [1], {}, {}
        view._unavailable, view._layouts = set(), {}
        view._text = lambda *_args, **_kwargs: None
        color = self.native.Gdk.RGBA()
        color.parse('#76518e')
        view._color = lambda *_args: color
        self.candidate = {'id': 1, 'title': 'First title', 'application': 'Fixture'}
        view.set_preview(1, 1536, 960, bytes(1536 * 960 * 3))

    def render_texture(self, node, viewport):
        # Replace only GPU submission; native GSK nodes retain the real source.
        width, height = math.ceil(viewport.size.width), math.ceil(viewport.size.height)
        self.compositions.append((node.get_bounds(), viewport))
        texture = self.native.Gdk.MemoryTexture.new(width, height,
            self.native.Gdk.MemoryFormat.R8G8B8,
            self.native.GLib.Bytes.new(bytes(width * height * 3)), width * 3)
        self.texture_refs.append(texture.weak_ref())
        return texture

    def card(self, selected=False, hovered=False):
        return self.view._card_node(self.candidate, 120, 80, selected, hovered)

    def test_reuses_composed_card_at_device_scale_without_replacing_source(self):
        original = self.view._textures[1]
        first = self.card()
        self.assertIs(first, self.card())
        self.assertEqual(len(self.compositions), 1)
        rendered_bounds, viewport = self.compositions[0]
        logical = first.get_bounds()
        self.assertAlmostEqual(viewport.size.width, logical.size.width * 2, places=3)
        self.assertAlmostEqual(viewport.size.height, logical.size.height * 2, places=3)
        self.assertAlmostEqual(rendered_bounds.size.width, viewport.size.width, places=3)
        self.assertIs(self.view._textures[1], original)
        self.assertEqual((original.get_width(), original.get_height()), (1536, 960))

    def test_variant_reuse_and_scale_title_preview_invalidation(self):
        first = self.card()
        selected = self.card(True)
        hovered = self.card(False, True)
        self.assertIs(first, self.card())
        self.assertIs(selected, self.card(True))
        self.assertIs(hovered, self.card(False, True))
        self.assertEqual(len(self.compositions), 3)
        self.scale = 1
        self.assertIsNot(first, self.card())
        self.candidate['title'] = 'Changed title'
        self.card()
        self.view.set_preview(1, 1536, 960, bytes(1536 * 960 * 3))
        self.card()
        self.assertEqual(len(self.compositions), 6)

    def test_closing_releases_original_and_composed_native_textures(self):
        original = self.view._textures[1].weak_ref()
        self.card()
        self.assertEqual(len(self.texture_refs), 1)
        view = self.view
        view._keyboard_focus_epoch, view._keyboard_focus_handler = 0, None
        view._tick_id, view._deferred, view._theme_timer = None, [], 1
        view.GLib = SimpleNamespace(source_remove=lambda *_args: None)
        view.Gtk = SimpleNamespace(StyleContext=SimpleNamespace(
            remove_provider_for_display=lambda *_args: None))
        view.provider = None
        view.close()
        gc.collect()
        self.assertFalse(view._textures)
        self.assertFalse(view._card_nodes)
        self.assertIsNone(original())
        self.assertTrue(all(reference() is None for reference in self.texture_refs))


if __name__ == '__main__':
    unittest.main()
