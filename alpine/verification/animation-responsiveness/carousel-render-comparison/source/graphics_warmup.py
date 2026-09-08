"""Keep GTK's GPU device and shader pools alive without mapping a window."""


class GraphicsKeeper:
    def __init__(self, window, node, texture):
        self.window, self.node, self.texture = window, node, texture

    def close(self):
        window, self.window = self.window, None
        self.node = self.texture = None
        if window is not None:
            window.destroy()


def warm_graphics():
    """Compile shared animation primitives using only small synthetic pixels."""
    from showdesktop import preload_layer_shell
    preload_layer_shell()
    import gi
    for namespace in ('Gtk', 'Gdk', 'Gsk'):
        gi.require_version(namespace, '4.0')
    gi.require_version('Graphene', '1.0')
    from gi.repository import Gdk, GLib, Graphene, Gsk, Gtk, Pango
    Gtk.init()
    window = Gtk.Window(title='Oldbook graphics warmup')
    window.set_default_size(320, 180)
    drawing_area = Gtk.Box()
    window.set_child(drawing_area)

    def color(value):
        result = Gdk.RGBA()
        result.parse(value)
        return result

    def rectangle(x, y, width, height):
        return Graphene.Rect().init(x, y, width, height)

    try:
        # Realization creates the rendering context. No present(), mapping,
        # layer-shell role, keyboard controller, or desktop capture is used.
        window.realize()
        renderer = window.get_renderer()
        if renderer is None:
            raise RuntimeError('GTK did not create a renderer for graphics warmup')
        row = (b'\x72\x48\x98' * 8 + b'\xbb\xa7\xd1' * 8) * 8
        pixels = row * 128
        texture = Gdk.MemoryTexture.new(128, 128, Gdk.MemoryFormat.R8G8B8,
                                        GLib.Bytes.new(pixels), 128 * 3)
        card = Gtk.Snapshot.new()
        bounds = rectangle(0, 0, 96, 64)
        rounded = Gsk.RoundedRect().init_from_rect(bounds, 10)
        card.append_outset_shadow(rounded, color('rgba(24, 16, 32, .8)'), 0, 8, 0, 12)
        card.push_rounded_clip(rounded)
        card.append_color(color('#30213f'), bounds)
        card.append_scaled_texture(texture, Gsk.ScalingFilter.TRILINEAR, bounds)
        layout = drawing_area.create_pango_layout('Aa 0123')
        font = Pango.FontDescription.from_string('sans-serif bold 12')
        layout.set_font_description(font)
        card.append_layout(layout, color('#f1e8fa'))
        card.pop()
        card_node = card.to_node()
        scene = Gtk.Snapshot.new()
        scene.save()
        scene.translate(Graphene.Point().init(35, 45))
        scene.perspective(400)
        scene.rotate_3d(35, Graphene.Vec3().init(0, 1, 0))
        scene.push_opacity(.85)
        scene.append_node(card_node)
        scene.pop()
        scene.restore()
        scene.save()
        scene.translate(Graphene.Point().init(170, 45))
        scene.push_blur(4)
        scene.append_node(card_node)
        scene.pop()
        scene.restore()
        node = scene.to_node()
        rendered = renderer.render_texture(node, rectangle(0, 0, 320, 180))
        if window.get_mapped():
            raise RuntimeError('graphics warmup must remain unmapped')
        return GraphicsKeeper(window, node, rendered)
    except BaseException:
        window.destroy()
        raise
