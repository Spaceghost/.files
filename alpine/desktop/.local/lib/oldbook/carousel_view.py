"""A themed GTK4 coverflow surface; geometry remains usable without GTK."""
import math

from overlay_theme import read_palette
from window_switching import key_action, modifier_release_commits


def spring_step(value, velocity, target, seconds, frequency=40.0):
    """Exact critically damped motion, independent of the display refresh rate."""
    seconds = max(0.0, seconds)
    offset = value - target
    combined = velocity + frequency * offset
    decay = math.exp(-frequency * seconds)
    return (target + (offset + combined * seconds) * decay,
            (velocity - frequency * combined * seconds) * decay)


def cyclic_delta(index, position, count):
    delta = (index - position) % count
    return delta - count if delta > count / 2 else delta


def letterbox(pixel_width, pixel_height, width, height):
    scale = min(width / max(1, pixel_width), height / max(1, pixel_height))
    fitted_width, fitted_height = pixel_width * scale, pixel_height * scale
    return ((width - fitted_width) / 2, (height - fitted_height) / 2,
            fitted_width, fitted_height)


def card_layout(count, position, width, height):
    """Back-to-front projected cards, with at most three neighbors per side."""
    if count <= 0 or width <= 0 or height <= 0:
        return []
    card_width = min(760.0, width * .52)
    card_height = min(440.0, height * .49)
    nearby = sorted(range(count), key=lambda index: abs(cyclic_delta(index, position, count)))[:7]
    cards = []
    perspective = 1400.0
    for index in nearby:
        delta = cyclic_delta(index, position, count)
        distance = abs(delta)
        angle = -56.0 * max(-1.0, min(1.0, delta))
        scale = 1.0 / (1.0 + .10 * distance)
        depth = -110.0 * distance
        x = width / 2 + card_width * (.29 * delta + .36 * math.tanh(delta * 1.4))
        y = height * .47 + min(distance, 3) * 7
        sine, cosine = math.sin(math.radians(angle)), math.cos(math.radians(angle))
        corners = []
        for local_x, local_y in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            horizontal = local_x * card_width * scale / 2
            vertical = local_y * card_height * scale / 2
            ratio = perspective / (perspective - (depth - horizontal * sine))
            corners.append((x + horizontal * cosine * ratio, y + vertical * ratio))
        cards.append({'index': index, 'delta': delta, 'x': x, 'y': y,
                      'width': card_width, 'height': card_height, 'scale': scale,
                      'angle': angle, 'depth': depth, 'perspective': perspective,
                      'opacity': 1.0 / (1.0 + .15 * distance), 'corners': corners})
    return sorted(cards, key=lambda card: abs(card['delta']), reverse=True)


def hit_card(cards, x, y):
    for card in reversed(cards):
        corners = card['corners']
        crosses = []
        for start, end in zip(corners, corners[1:] + corners[:1]):
            crosses.append((end[0] - start[0]) * (y - start[1])
                           - (end[1] - start[1]) * (x - start[0]))
        if all(value >= 0 for value in crosses) or all(value <= 0 for value in crosses):
            return card['index']
    return None


class Popup:
    """Real window textures and input for one frozen switching gesture."""

    def __init__(self, state, modifier, on_command, on_map, output_name=None):
        from showdesktop import preload_layer_shell
        preload_layer_shell()
        import gi
        gi.require_version('Gtk', '4.0')
        gi.require_version('Gdk', '4.0')
        gi.require_version('Gsk', '4.0')
        gi.require_version('Graphene', '1.0')
        gi.require_version('Gtk4LayerShell', '1.0')
        from gi.repository import Gdk, GLib, Graphene, Gsk, Gtk, Gtk4LayerShell, Pango
        Gtk.init()
        self.Gdk, self.GLib, self.Graphene = Gdk, GLib, Graphene
        self.Gsk, self.Gtk, self.Pango = Gsk, Gtk, Pango
        self.state, self.modifier = state, modifier
        self.on_command, self.on_map = on_command, on_map
        self.closed = False
        self.frames, self.frame_times = 0, []
        self._tick_id, self._last_frame = None, None
        self._deferred = set()
        self._keyboard_ready_callback = None
        self._keyboard_focus_handler = None
        self._keyboard_ready_source = None
        self._keyboard_focus_epoch = 0
        self._position = self._target = float(state.index or 0)
        self._velocity, self._reveal, self._reveal_velocity = 0.0, 0.0, 0.0
        self._ids = [candidate['id'] for candidate in state.candidates]
        self._textures, self._layouts = {}, {}
        self._card_nodes = {}
        self._unavailable = set()
        self._hovered = None
        self._last_scroll = 0
        self.palette = read_palette()
        self._colors = {}
        popup = self

        class Stage(Gtk.Widget):
            def do_snapshot(self, snapshot):
                popup._snapshot(snapshot, self.get_width(), self.get_height())

        self.stage = Stage()
        self.stage.set_focusable(True)
        self.stage.set_hexpand(True)
        self.stage.set_vexpand(True)
        self.window = Gtk.Window(title='Window carousel')
        self.window.set_name('oldbook-carousel')
        self.window.set_decorated(False)
        self.window.set_child(self.stage)
        Gtk4LayerShell.init_for_window(self.window)
        if not Gtk4LayerShell.is_layer_window(self.window):
            self.window.destroy()
            raise RuntimeError('window carousel requires GTK4 layer-shell')
        Gtk4LayerShell.set_namespace(self.window, 'oldbook-carousel')
        Gtk4LayerShell.set_layer(self.window, Gtk4LayerShell.Layer.OVERLAY)
        Gtk4LayerShell.set_keyboard_mode(self.window, Gtk4LayerShell.KeyboardMode.EXCLUSIVE)
        Gtk4LayerShell.set_exclusive_zone(self.window, -1)
        for edge in (Gtk4LayerShell.Edge.TOP, Gtk4LayerShell.Edge.BOTTOM,
                     Gtk4LayerShell.Edge.LEFT, Gtk4LayerShell.Edge.RIGHT):
            Gtk4LayerShell.set_anchor(self.window, edge, True)
        for monitor in self.window.get_display().get_monitors():
            if monitor.get_connector() == output_name:
                Gtk4LayerShell.set_monitor(self.window, monitor)
                break
        self.provider = Gtk.CssProvider()
        self.provider.load_from_string('#oldbook-carousel { background: transparent; box-shadow: none; }')
        Gtk.StyleContext.add_provider_for_display(self.window.get_display(), self.provider,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.window.connect('map', self._mapped)
        self.window.connect('close-request', self._close_requested)
        keyboard = Gtk.EventControllerKey.new()
        keyboard.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keyboard.connect('key-pressed', self._key_pressed)
        keyboard.connect('key-released', self._key_released)
        self.window.add_controller(keyboard)
        click = Gtk.GestureClick.new()
        click.set_button(1)
        click.connect('released', self._clicked)
        self.stage.add_controller(click)
        motion = Gtk.EventControllerMotion.new()
        motion.connect('motion', self._motion)
        motion.connect('leave', self._leave)
        self.stage.add_controller(motion)
        scroll = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL
            | Gtk.EventControllerScrollFlags.HORIZONTAL | Gtk.EventControllerScrollFlags.DISCRETE)
        scroll.connect('scroll', self._scroll)
        self.stage.add_controller(scroll)
        self._theme_timer = GLib.timeout_add_seconds(1, self._refresh_theme)

    def present(self):
        if not self.closed:
            self.window.present()
            self.stage.grab_focus()
            self._animate()

    def close(self):
        if self.closed:
            return
        self.closed = True
        self._keyboard_ready_callback = None
        self._keyboard_focus_epoch += 1
        self._keyboard_ready_source = None
        if self._keyboard_focus_handler is not None:
            self.window.disconnect(self._keyboard_focus_handler)
            self._keyboard_focus_handler = None
        if self._tick_id is not None:
            self.stage.remove_tick_callback(self._tick_id)
            self._tick_id = None
        self.GLib.source_remove(self._theme_timer)
        for source in self._deferred:
            self.GLib.source_remove(source)
        self._deferred.clear()
        display = self.window.get_display()
        self.Gtk.StyleContext.remove_provider_for_display(display, self.provider)
        self.window.destroy()
        # Focus travels over a separate Sway IPC socket. Complete the Wayland
        # destruction first so the keyboard grab is gone before that request.
        if not display.is_closed():
            display.sync()
        self._textures.clear()
        self._card_nodes.clear()
        self._unavailable.clear()
        self._layouts.clear()

    def update(self, state):
        if self.closed:
            return
        self.state = state
        ids = [candidate['id'] for candidate in state.candidates]
        index = float(state.index or 0)
        if ids != self._ids:
            self._position = self._target = index
            self._velocity = 0.0
            self._ids = ids
            self._textures = {identity: texture for identity, texture in self._textures.items()
                              if identity in ids}
            self._unavailable.intersection_update(ids)
            self._card_nodes = {identity: cached for identity, cached in self._card_nodes.items()
                                if identity in ids}
        elif ids:
            self._target += cyclic_delta(index, self._target, len(ids))
        self._layouts.clear()
        self._animate()

    def set_preview(self, identity, width, height, pixels):
        if self.closed or identity not in self._ids:
            return False
        if width <= 0 or height <= 0 or len(pixels) != width * height * 3:
            raise ValueError('preview must be tightly packed positive-size RGB8 pixels')
        texture = self.Gdk.MemoryTexture.new(width, height, self.Gdk.MemoryFormat.R8G8B8,
                                              self.GLib.Bytes.new(bytes(pixels)), width * 3)
        self._textures[identity] = texture
        self._card_nodes.pop(identity, None)
        self._unavailable.discard(identity)
        self.stage.queue_draw()
        return True

    def set_preview_unavailable(self, identity):
        if self.closed or identity not in self._ids:
            return False
        self._unavailable.add(identity)
        self._card_nodes.pop(identity, None)
        self.stage.queue_draw()
        return True

    def when_keyboard_ready(self, callback):
        self._keyboard_ready_callback = callback
        self._keyboard_focus_handler = self.window.connect(
            'notify::is-active', self._keyboard_focus_changed)
        self._keyboard_focus_changed()

    def _keyboard_focus_changed(self, *_args):
        self._keyboard_focus_epoch += 1
        if self._keyboard_ready_source is not None:
            self.GLib.source_remove(self._keyboard_ready_source)
            self._deferred.discard(self._keyboard_ready_source)
            self._keyboard_ready_source = None
        if not self.closed and self._keyboard_ready_callback and self.window.is_active():
            self._queue_keyboard_ready(self._keyboard_focus_epoch, False)

    def _queue_keyboard_ready(self, epoch, synchronized):
        source = self.GLib.idle_add(self._keyboard_ready, epoch, synchronized)
        self._keyboard_ready_source = source
        self._deferred.add(source)

    def _keyboard_ready(self, epoch, synchronized):
        self._deferred.discard(self._keyboard_ready_source)
        self._keyboard_ready_source = None
        if self.closed or epoch != self._keyboard_focus_epoch or not self.window.is_active():
            return False
        if not synchronized:
            display = self.window.get_display()
            if display.is_closed():
                return False
            # is-active follows Wayland keyboard enter. A roundtrip delivers
            # the modifiers that the protocol requires after that enter,
            # including an unchanged zero mask for a quick released hotkey.
            display.sync()
            if not self.closed and epoch == self._keyboard_focus_epoch:
                # GDK queues focus events: let a queued focus-out run before
                # deciding that the synchronized zero mask means release.
                self._queue_keyboard_ready(epoch, True)
            return False
        callback, self._keyboard_ready_callback = self._keyboard_ready_callback, None
        if self._keyboard_focus_handler is not None:
            self.window.disconnect(self._keyboard_focus_handler)
            self._keyboard_focus_handler = None
        if callback:
            callback()
        return False

    def current_modifiers(self):
        seat = self.window.get_display().get_default_seat()
        keyboard = seat.get_keyboard() if seat else None
        mask = keyboard.get_modifier_state() if keyboard else 0
        return self._modifier_names(mask)

    def _modifier_names(self, mask):
        return {name for name, flag in (
            ('Shift', self.Gdk.ModifierType.SHIFT_MASK),
            ('Mod4', self.Gdk.ModifierType.SUPER_MASK),
            ('Mod1', self.Gdk.ModifierType.ALT_MASK)) if mask & flag}

    def _mapped(self, *_args):
        if not self.closed:
            self.on_map()

    def _close_requested(self, *_args):
        if not self.closed:
            self.on_command('cancel')
        return True

    def _key_pressed(self, _controller, keyval, _keycode, modifiers):
        name = self.Gdk.keyval_name(keyval)
        action = key_action(name, self._modifier_names(modifiers))
        if name in ('Left', 'Up'):
            action = 'previous'
        elif name in ('Right', 'Down'):
            action = 'next'
        if action and not self.closed:
            self.on_command(action)
            return True
        return False

    def _key_released(self, _controller, keyval, _keycode, _modifiers):
        name = self.Gdk.keyval_name(keyval)
        if self.modifier is None or name not in ('Alt_L', 'Alt_R', 'Super_L', 'Super_R'):
            return

        def after_release():
            self._deferred.discard(source)
            if not self.closed and modifier_release_commits(self.modifier, name, self.current_modifiers()):
                self.on_command('commit')
            return False

        source = self.GLib.idle_add(after_release)
        self._deferred.add(source)

    def _cards(self):
        return card_layout(len(self.state.candidates), self._position,
                           self.stage.get_width(), self.stage.get_height())

    def _clicked(self, _gesture, _presses, x, y):
        if self.closed:
            return
        index = hit_card(self._cards(), x, y)
        if index is None:
            self.on_command('cancel')
        else:
            self.state.index = index
            self.on_command('commit')

    def _motion(self, _controller, x, y):
        hovered = hit_card(self._cards(), x, y)
        if hovered != self._hovered:
            self._hovered = hovered
            self.stage.set_cursor_from_name('pointer' if hovered is not None else 'default')
            self.stage.queue_draw()

    def _leave(self, _controller):
        self._hovered = None
        self.stage.queue_draw()

    def _scroll(self, _controller, dx, dy):
        delta = dx if abs(dx) > abs(dy) else dy
        now = self.GLib.get_monotonic_time()
        if delta and not self.closed and now - self._last_scroll >= 80000:
            self._last_scroll = now
            self.on_command('next' if delta > 0 else 'previous')
        return True

    def _refresh_theme(self):
        if self.closed:
            return False
        palette = read_palette()
        if palette != self.palette:
            self.palette = palette
            self._colors.clear()
            self._card_nodes.clear()
            self.stage.queue_draw()
        return True

    def _animate(self):
        self.stage.queue_draw()
        if self._tick_id is None:
            # Frame-clock timestamps share GLib's monotonic time base. Start
            # at the input request so the first frame already shows movement.
            self._last_frame = self.GLib.get_monotonic_time()
            self._tick_id = self.stage.add_tick_callback(self._tick)

    def _tick(self, _widget, clock):
        if self.closed:
            self._tick_id = None
            return False
        stamp = clock.get_frame_time()
        # The exact spring stays stable across delayed frames: use all elapsed
        # time instead of turning one missed frame into prolonged slow motion.
        seconds = max(0.0, (stamp - self._last_frame) / 1000000)
        self._last_frame = stamp
        self.frames += 1
        self.frame_times.append(stamp)
        del self.frame_times[:-240]
        self._position, self._velocity = spring_step(self._position, self._velocity, self._target, seconds)
        self._reveal, self._reveal_velocity = spring_step(
            self._reveal, self._reveal_velocity, 1.0, seconds, frequency=60.0)
        settled = (abs(self._position - self._target) < .0005 and abs(self._velocity) < .01
                   and abs(self._reveal - 1.0) < .0005 and abs(self._reveal_velocity) < .01)
        if settled:
            self._position, self._velocity = self._target, 0.0
            self._reveal, self._reveal_velocity = 1.0, 0.0
            self._tick_id = None
        self.stage.queue_draw()
        return not settled

    def _color(self, name, opacity=1.0):
        key = name, opacity
        if key not in self._colors:
            color = self.Gdk.RGBA()
            color.parse(self.palette[name])
            color.alpha = opacity
            self._colors[key] = color
        return self._colors[key]

    def _rectangle(self, x, y, width, height):
        return self.Graphene.Rect().init(x, y, max(0, width), max(0, height))

    def _text(self, snapshot, text, x, y, width, size, color, bold=False, centered=False):
        key = str(text), round(width), size, bold, centered
        layout = self._layouts.get(key)
        if layout is None:
            layout = self.stage.create_pango_layout(str(text))
            font = self.Pango.FontDescription()
            font.set_family('sans-serif')
            font.set_absolute_size(size * self.Pango.SCALE)
            font.set_weight(self.Pango.Weight.BOLD if bold else self.Pango.Weight.NORMAL)
            layout.set_font_description(font)
            layout.set_width(max(1, round(width)) * self.Pango.SCALE)
            layout.set_ellipsize(self.Pango.EllipsizeMode.END)
            layout.set_single_paragraph_mode(True)
            layout.set_alignment(self.Pango.Alignment.CENTER if centered else self.Pango.Alignment.LEFT)
            self._layouts[key] = layout
        snapshot.save()
        snapshot.translate(self.Graphene.Point().init(x, y))
        snapshot.append_layout(layout, self._color(color))
        snapshot.restore()

    def _snapshot(self, snapshot, width, height):
        if self.closed or width <= 0 or height <= 0:
            return
        snapshot.append_color(self._color('background_hard', .92 * self._reveal),
                              self._rectangle(0, 0, width, height))
        snapshot.push_opacity(self._reveal)
        self._text(snapshot, 'YOUR WINDOWS, WITH ROOM TO BREATHE', width * .1,
                   height * .105, width * .8, 13, 'muted', centered=True)
        for card in self._cards():
            self._draw_card(snapshot, card)
        selected = self.state.selected
        if selected is not None:
            title_y = height * .47 + min(440.0, height * .49) / 2 + 34
            self._text(snapshot, selected.get('title') or selected.get('application') or 'Window',
                       width * .14, title_y, width * .72, 25, 'foreground', True, True)
            application = selected.get('application') or selected.get('app_id') or 'Window'
            detail = application + '  ·  ' + (selected.get('workspace') or 'Workspace')
            self._text(snapshot, detail, width * .14, title_y + 36, width * .72, 14, 'muted', centered=True)
            self._text(snapshot, f'{self.state.index + 1} / {len(self.state.candidates)}',
                       width * .4, title_y + 66, width * .2, 12, 'accent', True, True)
        release = {'alt': 'Release Alt to arrive', 'super': 'Release Super to arrive'}.get(
            self.modifier, 'Enter or click to arrive')
        self._text(snapshot, 'Tab / Shift+Tab or arrows to browse  ·  ' + release + '  ·  Esc to stay',
                   width * .08, height - 60, width * .84, 13, 'muted', centered=True)
        snapshot.pop()

    def _draw_card(self, snapshot, card):
        candidate = self.state.candidates[card['index']]
        width, height = card['width'], card['height']
        selected = card['index'] == self.state.index
        snapshot.save()
        snapshot.translate(self.Graphene.Point().init(card['x'], card['y'] + 24 * (1 - self._reveal)))
        snapshot.perspective(card['perspective'])
        snapshot.translate_3d(self.Graphene.Point3D().init(0, 0, card['depth']))
        snapshot.rotate_3d(card['angle'], self.Graphene.Vec3().init(0, 1, 0))
        snapshot.scale(card['scale'], card['scale'])
        snapshot.translate(self.Graphene.Point().init(-width / 2, -height / 2))
        hovered = card['index'] == self._hovered
        snapshot.push_opacity(1.0 if hovered else card['opacity'])
        snapshot.append_node(self._card_node(candidate, width, height, selected, hovered))
        snapshot.pop()
        snapshot.restore()

    def _card_node(self, candidate, width, height, selected, hovered):
        # Compose static clips/shadows once: the legacy GL renderer otherwise
        # rasterizes these vector operations again under every changing 3D pose.
        identity = candidate['id']
        texture = self._textures.get(identity)
        title = candidate.get('title') or candidate.get('application') or 'Window'
        application = candidate.get('application') or candidate.get('app_id') or 'Window'
        scale = self.stage.get_scale_factor()
        signature = (width, height, scale, title, application, texture, identity in self._unavailable)
        cached = self._card_nodes.get(identity)
        if cached is None or cached[0] != signature:
            cached = (signature, {})
            self._card_nodes[identity] = cached
        variants = cached[1]
        variant = selected, hovered
        if variant in variants:
            return variants[variant][1]
        # At most four selection/hover variants are retained per candidate.
        snapshot = self.Gtk.Snapshot.new()
        bounds = self._rectangle(0, 0, width, height)
        rounded = self.Gsk.RoundedRect().init_from_rect(bounds, 18)
        snapshot.append_outset_shadow(rounded, self._color('background_hard', .8), 0, 18, 0, 38)
        if selected or hovered:
            snapshot.append_outset_shadow(rounded, self._color('accent', .18), 0, 5, 0, 30)
        snapshot.push_rounded_clip(rounded)
        snapshot.append_color(self._color('surface'), bounds)
        snapshot.append_color(self._color('accent', .09 if selected else .025), bounds)
        self._text(snapshot, title, 18, 12, width - 36, 12, 'foreground', bold=selected)
        preview_bounds = self._rectangle(12, 38, width - 24, height - 50)
        preview_round = self.Gsk.RoundedRect().init_from_rect(preview_bounds, 10)
        snapshot.push_rounded_clip(preview_round)
        snapshot.append_color(self._color('background_hard'), preview_bounds)
        if texture is not None:
            x, y, fitted_width, fitted_height = letterbox(texture.get_width(), texture.get_height(),
                                                          width - 24, height - 50)
            snapshot.append_scaled_texture(texture, self.Gsk.ScalingFilter.TRILINEAR,
                self._rectangle(12 + x, 38 + y, fitted_width, fitted_height))
        else:
            self._text(snapshot, application, 30, height / 2 - 10, width - 60,
                       21, 'foreground', True, True)
            message = ('Preview unavailable · Enter still takes you there'
                       if candidate['id'] in self._unavailable else 'Bringing the view into focus…')
            self._text(snapshot, message, 30, height / 2 + 28,
                       width - 60, 12, 'muted', centered=True)
        snapshot.pop()
        snapshot.pop()
        node = snapshot.to_node()
        # Include the entire shadow bounds at output device scale. Keep the
        # original vector node and full provider texture for invalidation; no
        # reduced preview replaces the source. Close clears both cache levels.
        bounds = node.get_bounds()
        device_bounds = self._rectangle(bounds.origin.x * scale, bounds.origin.y * scale,
                                         bounds.size.width * scale, bounds.size.height * scale)
        composed = self.Gtk.Snapshot.new()
        composed.scale(scale, scale)
        composed.append_node(node)
        rendered = self.window.get_renderer().render_texture(composed.to_node(), device_bounds)
        composed = self.Gtk.Snapshot.new()
        composed.append_scaled_texture(rendered, self.Gsk.ScalingFilter.TRILINEAR, bounds)
        result = composed.to_node()
        variants[variant] = (node, result)
        return result
