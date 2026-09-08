"""Shared GTK4 layer-shell scaffolding for the Launchpad and Mission Control grids.

Both overlays are the same object at heart: one full-output surface on the
overlay layer, the current painting blurred behind it, a short frame-clock fade
that scales the content in from slightly too large, keyboard interactivity only
while the surface is mapped, and a single owner per compositor session. What
differs is what each one draws and what its keys mean, so the subclass supplies
`render`, `key_pressed` and the pointer handlers and nothing else.

GTK 4 with gtk4-layer-shell is deliberate: the newest overlays on this desktop
(the window carousel and the show-desktop slide) already use it, its Gsk
snapshot API gives rounded clips, textures and shadows without a cairo context
per frame, and `preload_layer_shell` already exists to interpose the library.
"""
import fcntl
import hashlib
import os
from pathlib import Path
import runpy
import socket
import stat
import sys

from overlay_theme import read_palette

REVEAL_MS = 190.0
SCALE_FROM = 1.03
# A compositor that never returns a frame callback would otherwise leave the
# surface stuck part-way through its fade: invisible, and still holding the
# keyboard. Twice the fade plus a margin is long enough that a healthy frame
# clock always finishes first.
WATCHDOG_MS = 420


def smoothstep(value):
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def load_ipc():
    return runpy.run_path(str(Path(__file__).resolve().parents[2] / 'bin/oldbook-workspaces'))


def cache_directory(name):
    base = Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache')) / 'oldbook' / name
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = base.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise RuntimeError(f'overlay cache must be an owned private directory: {base}')
    return base


def session_locked(runtime=None):
    """True while oldbook-lock holds a live session lock.

    Pressing an engraved overview key behind the lock must not map an overlay:
    the lock surface covers it, so it would sit there invisible while holding a
    keyboard grab. The lock helper records the locker's process identity when it
    reaches readiness, so a stale record from a crashed locker never counts.
    """
    import json
    runtime = Path(runtime or os.environ.get('XDG_RUNTIME_DIR', '/run/user/%d' % os.getuid()))
    record = runtime / 'oldbook-screen-lock' / 'ready.json'
    try:
        saved = json.loads(record.read_text())
        pid = int(saved['process']['pid'])
        started = str(saved['process']['start_time'])
    except (OSError, ValueError, KeyError, TypeError):
        return False
    try:
        fields = (Path('/proc') / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()
    except (OSError, IndexError):
        return False
    return fields[19] == started


def focused_output(ipc, sway):
    """Connector name and logical size of the output the user is looking at."""
    try:
        outputs = ipc['request'](sway, 3)
    except Exception:
        return None, 1440.0, 900.0
    for output in sorted(outputs, key=lambda item: not item.get('focused')):
        rect = output.get('rect') or {}
        if output.get('active') and rect.get('width'):
            return output.get('name'), float(rect['width']), float(rect['height'])
    return None, 1440.0, 900.0


def background_texture(Gdk, palette, cache_name):
    """The current painting, blurred and darkened, as a texture; None without one."""
    try:
        import lock_scene
        painting = lock_scene.current_painting()
        if painting is None:
            return None
        geometry = lock_scene.output_geometry()
        path = lock_scene.render_background(painting, geometry, palette,
                                            cache=cache_directory(cache_name))
        return Gdk.Texture.new_from_filename(str(path))
    except Exception:
        return None


class Overlay:
    """One animated, full-output layer-shell surface with a single owner."""

    NAMESPACE = 'oldbook-overlay'
    TITLE = 'Oldbook overlay'
    CACHE = 'overlay'

    def __init__(self, ipc, sway, control):
        from showdesktop import preload_layer_shell
        preload_layer_shell()
        import gi
        gi.require_version('Gtk', '4.0')
        gi.require_version('Gdk', '4.0')
        gi.require_version('Gsk', '4.0')
        gi.require_version('Graphene', '1.0')
        gi.require_version('Gtk4LayerShell', '1.0')
        from gi.repository import Gdk, GLib, Graphene, Gsk, Gtk, Gtk4LayerShell, Pango, PangoCairo
        Gtk.init()
        self.Gdk, self.GLib, self.Graphene = Gdk, GLib, Graphene
        self.Gsk, self.Gtk, self.Pango, self.PangoCairo = Gsk, Gtk, Pango, PangoCairo
        self.ipc, self.sway, self.control = ipc, sway, control
        self.palette = read_palette()
        self._colors = {}
        self._layouts = {}
        self.closing = False
        self.reveal = 0.0
        self._tick_id = None
        self._last_frame = None
        self._watchdog = None
        self.loop = GLib.MainLoop()
        self.output_name, self.width, self.height = focused_output(ipc, sway)
        self.background = background_texture(Gdk, self.palette, self.CACHE)
        overlay = self

        class Stage(Gtk.Widget):
            def do_snapshot(self, snapshot):
                overlay._snapshot(snapshot, self.get_width(), self.get_height())

        self.stage = Stage()
        self.stage.set_focusable(True)
        self.stage.set_hexpand(True)
        self.stage.set_vexpand(True)
        self.window = Gtk.Window(title=self.TITLE)
        self.window.set_name(self.NAMESPACE)
        self.window.set_decorated(False)
        self.window.set_child(self.stage)
        Gtk4LayerShell.init_for_window(self.window)
        if not Gtk4LayerShell.is_layer_window(self.window):
            self.window.destroy()
            raise RuntimeError(f'{self.NAMESPACE} requires GTK4 layer-shell')
        Gtk4LayerShell.set_namespace(self.window, self.NAMESPACE)
        Gtk4LayerShell.set_layer(self.window, Gtk4LayerShell.Layer.OVERLAY)
        Gtk4LayerShell.set_keyboard_mode(self.window, Gtk4LayerShell.KeyboardMode.EXCLUSIVE)
        Gtk4LayerShell.set_exclusive_zone(self.window, -1)
        for edge in (Gtk4LayerShell.Edge.TOP, Gtk4LayerShell.Edge.BOTTOM,
                     Gtk4LayerShell.Edge.LEFT, Gtk4LayerShell.Edge.RIGHT):
            Gtk4LayerShell.set_anchor(self.window, edge, True)
        for monitor in self.window.get_display().get_monitors():
            if monitor.get_connector() == self.output_name:
                Gtk4LayerShell.set_monitor(self.window, monitor)
                break
        self.provider = Gtk.CssProvider()
        self.provider.load_from_string(
            '#' + self.NAMESPACE + ' { background: transparent; box-shadow: none; }')
        Gtk.StyleContext.add_provider_for_display(self.window.get_display(), self.provider,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        keyboard = Gtk.EventControllerKey.new()
        keyboard.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keyboard.connect('key-pressed', self._key_pressed)
        self.window.add_controller(keyboard)
        click = Gtk.GestureClick.new()
        click.set_button(1)
        click.connect('pressed', self._pressed)
        click.connect('released', self._released)
        self.stage.add_controller(click)
        motion = Gtk.EventControllerMotion.new()
        motion.connect('motion', self._motion)
        self.stage.add_controller(motion)
        scroll = Gtk.EventControllerScroll.new(
            Gtk.EventControllerScrollFlags.VERTICAL | Gtk.EventControllerScrollFlags.DISCRETE)
        scroll.connect('scroll', self._scroll)
        self.stage.add_controller(scroll)
        self._watch = GLib.io_add_watch(control.fileno(), GLib.IO_IN, self._message)

    # Lifecycle -----------------------------------------------------------

    def run(self):
        self.window.present()
        self.stage.grab_focus()
        self._animate()
        self.loop.run()

    def _message(self, *_args):
        try:
            data = self.control.recv(64)
        except OSError as error:
            self.debug('control read failed: %s' % error)
            return True
        self.debug('control message %r' % data)
        if data.strip() in (b'close', b'toggle'):
            self.request_close()
        return True

    def debug(self, message):
        if os.environ.get('OLDBOOK_GRID_DEBUG'):
            print(f'{self.NAMESPACE}: {message}', file=sys.stderr, flush=True)

    def request_close(self):
        self.debug('close requested')
        if not self.closing:
            self.closing = True
            self._animate()

    def _finish(self):
        self._cancel_watchdog()
        if self._tick_id is not None:
            self.stage.remove_tick_callback(self._tick_id)
            self._tick_id = None
        self.GLib.source_remove(self._watch)
        display = self.window.get_display()
        self.Gtk.StyleContext.remove_provider_for_display(display, self.provider)
        self.window.destroy()
        # Complete the Wayland teardown before any focus request travels over
        # the separate Sway IPC socket, so the keyboard grab is already gone.
        if not display.is_closed():
            display.sync()
        self.loop.quit()

    def _animate(self):
        self.stage.queue_draw()
        if self._tick_id is None:
            self._last_frame = self.GLib.get_monotonic_time()
            self._tick_id = self.stage.add_tick_callback(self._tick)
        self._arm_watchdog()

    def _arm_watchdog(self):
        self._cancel_watchdog()
        self._watchdog = self.GLib.timeout_add(WATCHDOG_MS, self._watchdog_fired)

    def _cancel_watchdog(self):
        if self._watchdog is not None:
            self.GLib.source_remove(self._watchdog)
            self._watchdog = None

    def _watchdog_fired(self):
        """Finish without animating when no frame callback ever arrives."""
        self._watchdog = None
        target = 0.0 if self.closing else 1.0
        if abs(self.reveal - target) <= 0.0005:
            return False
        self.debug('frame clock stalled at %.3f; settling immediately' % self.reveal)
        self.reveal = target
        if self._tick_id is not None:
            self.stage.remove_tick_callback(self._tick_id)
            self._tick_id = None
        self.stage.queue_draw()
        if self.closing:
            self._finish()
        return False

    def _tick(self, _widget, clock):
        stamp = clock.get_frame_time()
        seconds = max(0.0, (stamp - self._last_frame) / 1000000)
        self._last_frame = stamp
        target = 0.0 if self.closing else 1.0
        step = seconds * 1000.0 / REVEAL_MS
        if self.reveal < target:
            self.reveal = min(target, self.reveal + step)
        else:
            self.reveal = max(target, self.reveal - step)
        self.stage.queue_draw()
        if abs(self.reveal - target) > 0.0005:
            return True
        # Exact settling: the last frame lands on the target, then the clock
        # callback is dropped so an idle overlay costs nothing.
        self.reveal = target
        self._tick_id = None
        self._cancel_watchdog()
        if self.closing:
            self.GLib.idle_add(self._finish)
        return False

    # Drawing helpers -----------------------------------------------------

    def color(self, name, opacity=1.0):
        key = (name, round(opacity, 3))
        if key not in self._colors:
            value = self.Gdk.RGBA()
            value.parse(self.palette.get(name, self.palette['foreground']))
            value.alpha = opacity
            self._colors[key] = value
        return self._colors[key]

    def rectangle(self, x, y, width, height):
        return self.Graphene.Rect().init(x, y, max(0.0, width), max(0.0, height))

    def rounded(self, x, y, width, height, radius):
        return self.Gsk.RoundedRect().init_from_rect(
            self.rectangle(x, y, width, height), radius)

    def text(self, snapshot, content, x, y, width, size, color,
             bold=False, centered=True, height=None):
        key = (content, round(width), round(size, 1), bold, centered)
        layout = self._layouts.get(key)
        if layout is None:
            layout = self.stage.create_pango_layout(content)
            font = self.Pango.FontDescription()
            font.set_family('Inter,JetBrainsMono Nerd Font,sans-serif')
            font.set_absolute_size(size * self.Pango.SCALE)
            font.set_weight(self.Pango.Weight.SEMIBOLD if bold else self.Pango.Weight.NORMAL)
            layout.set_font_description(font)
            layout.set_width(max(1, round(width)) * self.Pango.SCALE)
            layout.set_ellipsize(self.Pango.EllipsizeMode.END)
            layout.set_single_paragraph_mode(True)
            layout.set_alignment(self.Pango.Alignment.CENTER if centered
                                 else self.Pango.Alignment.LEFT)
            if len(self._layouts) > 512:
                self._layouts.clear()
            self._layouts[key] = layout
        _, extents = layout.get_pixel_extents()
        offset = 0.0 if height is None else max(0.0, (height - extents.height) / 2)
        snapshot.save()
        snapshot.translate(self.Graphene.Point().init(x, y + offset))
        snapshot.append_layout(layout, color)
        snapshot.restore()
        return extents.height

    def _snapshot(self, snapshot, width, height):
        eased = smoothstep(self.reveal)
        if self.background is not None:
            snapshot.push_opacity(eased)
            snapshot.append_texture(self.background, self.rectangle(0, 0, width, height))
            snapshot.pop()
        # The painting arrives already blurred and darkened by the lock scene, so
        # this scrim only has to lift text off it, not hide it.
        snapshot.append_color(self.color('background_hard', 0.32 * eased),
                              self.rectangle(0, 0, width, height))
        if eased <= 0.001:
            return
        scale = SCALE_FROM + (1.0 - SCALE_FROM) * eased
        snapshot.push_opacity(eased)
        snapshot.save()
        snapshot.translate(self.Graphene.Point().init(width / 2, height / 2))
        snapshot.scale(scale, scale)
        snapshot.translate(self.Graphene.Point().init(-width / 2, -height / 2))
        self.render(snapshot, width, height)
        snapshot.restore()
        snapshot.pop()

    # Subclass surface ----------------------------------------------------

    def render(self, snapshot, width, height):
        raise NotImplementedError

    def key_pressed(self, keyval, state):
        return False

    def pressed(self, x, y, presses):
        return False

    def released(self, x, y, presses):
        return False

    def moved(self, x, y):
        return False

    def scrolled(self, dx, dy):
        return False

    # Controller adapters -------------------------------------------------

    def _key_pressed(self, _controller, keyval, _code, state):
        from gi.repository import Gdk
        if keyval in (Gdk.KEY_Escape,):
            self.request_close()
            return True
        return bool(self.key_pressed(keyval, state))

    def _pressed(self, gesture, presses, x, y):
        if self.pressed(x, y, presses):
            gesture.set_state(self.Gtk.EventSequenceState.CLAIMED)

    def _released(self, gesture, presses, x, y):
        if self.released(x, y, presses):
            gesture.set_state(self.Gtk.EventSequenceState.CLAIMED)

    def _motion(self, _controller, x, y):
        if self.moved(x, y):
            self.stage.queue_draw()

    def _scroll(self, _controller, dx, dy):
        return bool(self.scrolled(dx, dy))


def serve(build, action, name):
    """Run one overlay per compositor session; a second call toggles the first."""
    ipc = load_ipc()
    runtime = Path(os.environ['XDG_RUNTIME_DIR'])
    sway = ipc['find_socket'](runtime)
    directory = ipc['prepare_directory'](runtime).parent
    identity = hashlib.sha256(str(sway).encode()).hexdigest()[:12]
    address = directory / f'{name}-{identity}.sock'
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
        try:
            client.sendto(action.encode(), str(address))
            return
        except (FileNotFoundError, ConnectionRefusedError):
            if action == 'close':
                return
    with (directory / f'{name}-{identity}.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        if session_locked(runtime):
            return
        address.unlink(missing_ok=True)
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as control:
            control.bind(str(address))
            control.setblocking(False)
            try:
                build(ipc, sway, control).run()
            finally:
                address.unlink(missing_ok=True)
