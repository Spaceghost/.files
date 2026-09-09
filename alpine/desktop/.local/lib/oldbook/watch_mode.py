"""Watch mode: park input off the desktop while the desktop stays live.

This is a **cat guard, not a lock**, and nothing here may ever be described as
security. It exists for one situation: a long job is running, the desktop is
worth looking at, and a cat would like to sit on the keyboard. Watch mode keeps
the cat's keys and paws away from the session while leaving every pixel of the
running desktop visible and moving. The real lock is `Super+Escape`; it is
untouched, and anyone who can reach the machine can leave watch mode.

How the input actually goes away, and why not the input inhibitor. The wlroots
input-inhibitor (`zwlr_input_inhibit_manager_v1`) would be the obvious tool and
is what swaylock-effects still falls back to, but this compositor does not
offer it: swayfx 0.6 / sway 1.12.0 on wlroots 0.20 advertises neither
`zwlr_input_inhibit_manager_v1` nor `zwlr_input_inhibitor_v1`, only
`ext_session_lock_manager_v1`, and a session lock blanks the desktop, which is
exactly what watch mode must not do. So watch mode takes input the other way,
with globals the compositor does advertise:

  * a fully transparent `zwlr_layer_shell_v1` OVERLAY surface on every output,
    covering it, with an input region over the whole surface, so every pointer
    motion, click, scroll and touchpad gesture lands on the guard and nothing
    below it is ever entered; and
  * `keyboard-interactivity: exclusive` on that surface, so the seat's keyboard
    focus is the guard and no other client receives a key. The compositor
    proves it by sending `wl_keyboard.enter`, which GTK reports as the window
    becoming active; watch mode waits for that before it claims anything. A
    seat with no keyboard at all never sends it, and there watch mode engages
    on the surface alone and records that it saw no keyboard, because there
    were no keystrokes to park in the first place; and
  * Sway's own `mode "watch"`, which is deliberately empty, so no compositor
    binding exists either. Without it a cat lying across the keyboard would
    still reach `Super+Shift+q` and kill a window.

Getting stuck is the thing this must never do, so the order is fixed. The guard
proves it holds the keyboard *before* Sway is put into the empty mode, so a
compositor that refuses the surface leaves the desktop exactly as it was and
says so loudly. The mode is restored before the surface is torn down, a
watchdog holding a pipe restores it if this process dies in any way at all
including SIGKILL, and the guard ends itself if it ever stops holding the
keyboard. Ending early is always safer than stranding the user.
"""
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time

NAMESPACE = 'oldbook-watch'
SWAY_MODE = 'watch'
# The chord is held, not tapped, and nothing else may be down: a cat lying on
# the keyboard is nearly always holding half the home row as well, and that is
# what the "clean" test below is really detecting.
RELEASE_HOLD_SECONDS = 1.0
# Two deadlines, because "GTK was slow to start" and "the compositor refused
# the keyboard" are different failures and the user deserves to be told which.
# The first covers getting a surface on screen at all; the second starts only
# once the surface is mapped. Missing either is a refusal, never a reason to
# carry on pretending input is parked.
MAP_DEADLINE_SECONDS = 20.0
FOCUS_DEADLINE_SECONDS = 5.0
# Losing the keyboard mid-session means something else took it; end rather than
# sit on a screen that no longer answers the release chord. Long enough to ride
# out a keyboard being unplugged and replugged, short enough to be honest.
FOCUS_LOSS_GRACE_SECONDS = 5.0
# Bar height plus the Ghost Observatory gap: the card sits under Waybar, clear
# of the caption strip, the OSD pill and Conky's lower-right corner.
INDICATOR_TOP_MARGIN = 52
GHOST_GLYPH = '\U000f02a0'
EYEBROW = f'{GHOST_GLYPH}  WATCH MODE · INPUT PARKED'
HOW_TO_LEAVE = 'Hold  Super + Shift + Escape  for a second to return'
NOT_A_LOCK = 'A cat guard, not a lock. The desktop below is live; Super + Escape still locks.'


class ReleaseChord:
    """Decide when a person asked to leave, and a cat did not.

    Two things have to be true at once for a full second: the modifiers are
    exactly Super and Shift, and Escape is the only non-modifier key down. The
    hold defeats a paw that lands and lifts; the "only key down" test defeats a
    cat that settles across the keyboard, because a settled cat holds a handful
    of neighbouring keys and never just one. Autorepeat is not a second press,
    so leaning on the chord does not restart the clock.
    """

    KEY = 'Escape'
    MODIFIERS = frozenset({'super', 'shift'})
    MODIFIER_KEYS = frozenset({
        'Shift_L', 'Shift_R', 'Control_L', 'Control_R', 'Alt_L', 'Alt_R',
        'Meta_L', 'Meta_R', 'Super_L', 'Super_R', 'Hyper_L', 'Hyper_R',
        'Caps_Lock', 'Num_Lock', 'ISO_Level3_Shift', 'ISO_Level5_Shift', 'Mode_switch'})

    def __init__(self, hold_seconds=RELEASE_HOLD_SECONDS):
        self.hold_seconds = hold_seconds
        self._down = {}
        self._armed_at = None

    def press(self, keycode, name, modifiers, now):
        if keycode in self._down:
            return  # Autorepeat: the key never came up, so nothing changed.
        self._down[keycode] = name
        self._settle(modifiers, now)

    def release(self, keycode, modifiers, now):
        self._down.pop(keycode, None)
        self._settle(modifiers, now)

    def _settle(self, modifiers, now):
        held = [name for name in self._down.values() if name not in self.MODIFIER_KEYS]
        clean = frozenset(modifiers) == self.MODIFIERS and held == [self.KEY]
        if not clean:
            self._armed_at = None
        elif self._armed_at is None:
            self._armed_at = now

    @property
    def armed(self):
        return self._armed_at is not None

    @property
    def armed_at(self):
        """When this hold began, or None. Stable across autorepeat, which is
        what lets the guard schedule one timer for a hold instead of resetting
        it twenty-five times a second while the key is leaned on."""
        return self._armed_at

    def ready(self, now):
        return self._armed_at is not None and now - self._armed_at >= self.hold_seconds


def private_directory(path):
    """The same owned-and-private rule the lock helper applies to its runtime."""
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise RuntimeError(f'Watch mode runtime must be an owned private directory: {path}')
    return path


def runtime_directory(runtime=None):
    runtime = runtime or os.environ.get('XDG_RUNTIME_DIR')
    if not runtime:
        raise RuntimeError('XDG_RUNTIME_DIR is required for watch mode')
    return private_directory(Path(runtime) / 'oldbook')


def process_identity(pid):
    """PID reuse and zombies must not authenticate a stale watch record."""
    try:
        process = Path('/proc') / str(int(pid))
        if process.stat().st_uid != os.getuid():
            return None
        fields = (process / 'stat').read_text().rsplit(')', 1)[1].split()
        if fields[0] in ('Z', 'X'):
            return None
        return {'pid': int(pid), 'start_time': fields[19],
                'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
    except (OSError, ValueError, IndexError):
        return None


def state_path(runtime=None):
    return runtime_directory(runtime) / 'watch.json'


def engaged(runtime=None):
    """The live guard's record, or None. A stale record never counts."""
    try:
        path = state_path(runtime)
        if path.is_symlink():
            return None
        record = json.loads(path.read_text())
        if record.get('process') != process_identity(record['process']['pid']):
            return None
        return record
    except (OSError, ValueError, KeyError, TypeError, RuntimeError):
        return None


def publish(record, runtime=None):
    path = state_path(runtime)
    temporary = path.with_name(f'{path.name}.{os.getpid()}.tmp')
    temporary.write_text(json.dumps(record, indent=2) + '\n')
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def sway(*commands, kind=None, environment=None, timeout=4):
    """One swaymsg call, raising on anything but a clean success."""
    invocation = ['swaymsg', '-r'] + (['-t', kind] if kind else []) + list(commands)
    result = subprocess.run(invocation, capture_output=True, text=True,
                            timeout=timeout, env=environment)
    if result.returncode != 0:
        raise RuntimeError(f'swaymsg {" ".join(commands) or kind} failed: '
                           f'{result.stderr.strip() or result.returncode}')
    data = json.loads(result.stdout)
    if not kind and not all(item.get('success') for item in data):
        raise RuntimeError(f'Sway rejected {commands}: {data}')
    return data


def mode_watchdog(environment=None):
    """Restore the default mode if this process dies in any way at all.

    Same shape as the lock helper's power-key inhibitor: a detached shell holds
    the read end of a pipe and blocks on it, so the moment this process and
    every child of it are gone — including SIGKILL, including a crash — the
    write end closes, the read returns, and Sway is put back into its default
    mode. The caller keeps the returned descriptor open for exactly as long as
    watch mode should last. A watchdog that cannot start is fatal: an empty
    mode with no way out is the one outcome worse than not starting.
    """
    read_fd, write_fd = os.pipe()
    try:
        subprocess.Popen(['sh', '-c', 'IFS= read -r _ignored; exec swaymsg mode default'],
                         stdin=read_fd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True, env=environment)
        return write_fd
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        os.close(write_fd)
        raise RuntimeError(f'Watch mode cannot arm its mode watchdog: {error}') from error
    finally:
        os.close(read_fd)


def announce(summary, body, urgent=True):
    """Say it out loud. Watch mode never fails quietly, because the whole point
    is that the user walks away trusting what they were told."""
    print(f'oldbook-watch: {summary} — {body}', file=sys.stderr)
    try:
        subprocess.Popen(['notify-send', '-a', 'Oldbook',
                          '-u', 'critical' if urgent else 'normal', summary, body],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except OSError:
        pass


def cue(name):
    """A cue is never load-bearing; every failure here is silence."""
    try:
        subprocess.Popen([str(Path(__file__).resolve().parents[1] / 'bin/oldbook-sound'), name],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        pass


def indicator_style(palette, translucent=True):
    """The card's CSS in the active palette; nothing here moves on its own."""
    def color(name, fallback='#ebdbb2'):
        return palette.get(name, fallback)

    ground = color('background_hard', '#1d2021')
    alpha = '0.82' if translucent else '1.0'
    red, green, blue = (int(ground.lstrip('#')[index:index + 2], 16) for index in (0, 2, 4))
    return f'''
    window#{NAMESPACE} {{ background: transparent; box-shadow: none; }}
    #watch-card {{
        background: rgba({red}, {green}, {blue}, {alpha});
        border-radius: 16px;
        padding: 13px 22px 15px 22px;
    }}
    #watch-eyebrow {{
        color: {color('accent', '#fabd2f')};
        font-family: "JetBrainsMono Nerd Font", monospace;
        font-size: 9pt; font-weight: 600; letter-spacing: 2px;
    }}
    #watch-how {{ color: {color('foreground')}; font-family: Inter, sans-serif; font-size: 12pt; }}
    #watch-note {{ color: {color('muted', '#928374')}; font-family: Inter, sans-serif; font-size: 9pt; }}
    '''


def modifier_names(state, Gdk):
    """The Gdk modifier mask as the plain names ReleaseChord reasons about.

    Lock and the numeric-keypad modifier are ignored on purpose: Caps Lock is
    Escape on this keyboard and Num Lock is not something the user is choosing.
    """
    names = set()
    for name, flag in (('shift', Gdk.ModifierType.SHIFT_MASK),
                       ('ctrl', Gdk.ModifierType.CONTROL_MASK),
                       ('alt', Gdk.ModifierType.ALT_MASK),
                       ('super', Gdk.ModifierType.SUPER_MASK)):
        if state & flag:
            names.add(name)
    return names


class Guard:
    """Transparent, input-eating layer surfaces; one per output.

    Only the first window asks for the keyboard. Keyboard focus belongs to the
    seat rather than to an output, so one exclusive surface covers every
    keyboard on the machine, and having exactly one avoids two surfaces
    arguing over which of them the compositor last focused.
    """

    def __init__(self, palette, on_release, on_keyboard, on_keyboard_lost,
                 on_mapped=None, translucent=True):
        from showdesktop import preload_layer_shell
        preload_layer_shell()
        import gi
        gi.require_version('Gtk', '4.0')
        gi.require_version('Gdk', '4.0')
        gi.require_version('Gtk4LayerShell', '1.0')
        from gi.repository import Gdk, GLib, Gtk, Gtk4LayerShell
        self.Gdk, self.GLib, self.Gtk, self.Shell = Gdk, GLib, Gtk, Gtk4LayerShell
        Gtk.init()
        self.chord = ReleaseChord()
        self.on_release, self.on_keyboard, self.on_keyboard_lost = on_release, on_keyboard, on_keyboard_lost
        self.on_mapped = on_mapped or (lambda: None)
        self.mapped = False
        self.windows = []
        self.closed = False
        self._had_keyboard = False
        self._loss_timer = None
        self._hold_timer = None
        self._timed_hold = None
        display = Gdk.Display.get_default()
        if display is None:
            raise RuntimeError('watch mode needs a Wayland display')
        self.provider = Gtk.CssProvider()
        self.provider.load_from_string(indicator_style(palette, translucent))
        Gtk.StyleContext.add_provider_for_display(display, self.provider,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        monitors = list(display.get_monitors()) or [None]
        for index, monitor in enumerate(monitors):
            self.windows.append(self._build(monitor, primary=index == 0))

    def _build(self, monitor, primary):
        Gtk, Shell = self.Gtk, self.Shell
        window = Gtk.Window(title='Oldbook watch mode')
        window.set_name(NAMESPACE)
        window.set_decorated(False)
        Shell.init_for_window(window)
        if not Shell.is_layer_window(window):
            window.destroy()
            raise RuntimeError('watch mode requires GTK4 layer-shell')
        Shell.set_namespace(window, NAMESPACE)
        Shell.set_layer(window, Shell.Layer.OVERLAY)
        Shell.set_keyboard_mode(window, Shell.KeyboardMode.EXCLUSIVE if primary
                                else Shell.KeyboardMode.NONE)
        Shell.set_exclusive_zone(window, -1)
        for edge in (Shell.Edge.TOP, Shell.Edge.BOTTOM, Shell.Edge.LEFT, Shell.Edge.RIGHT):
            Shell.set_anchor(window, edge, True)
        if monitor is not None:
            Shell.set_monitor(window, monitor)
        window.set_child(self._card() if primary else Gtk.Box())
        # Every pointer class is consumed here rather than below: a paw on the
        # trackpad must not cross a window, scroll a document or click a thing.
        for controller in (Gtk.GestureClick.new(), Gtk.EventControllerMotion.new(),
                           Gtk.EventControllerScroll.new(
                               Gtk.EventControllerScrollFlags.VERTICAL
                               | Gtk.EventControllerScrollFlags.HORIZONTAL)):
            if isinstance(controller, Gtk.GestureClick):
                controller.set_button(0)
            window.add_controller(controller)
        if primary:
            keyboard = Gtk.EventControllerKey.new()
            keyboard.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            keyboard.connect('key-pressed', self._pressed)
            keyboard.connect('key-released', self._released)
            window.add_controller(keyboard)
            window.connect('notify::is-active', self._focus_changed)
            window.connect('map', self._mapped)
        window.connect('close-request', lambda *_: True)
        return window

    def _card(self):
        Gtk = self.Gtk
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        card.set_name('watch-card')
        card.set_halign(Gtk.Align.CENTER)
        card.set_valign(Gtk.Align.START)
        card.set_margin_top(INDICATOR_TOP_MARGIN)
        for name, text in (('watch-eyebrow', EYEBROW), ('watch-how', HOW_TO_LEAVE),
                           ('watch-note', NOT_A_LOCK)):
            label = Gtk.Label(label=text)
            label.set_name(name)
            label.set_halign(Gtk.Align.CENTER)
            card.append(label)
        return card

    def present(self):
        for window in self.windows:
            window.present()

    def keyboard_capable(self):
        """Does this seat have a keyboard for the guard to be holding?"""
        seat = self.Gdk.Display.get_default().get_default_seat()
        return bool(seat) and bool(seat.get_capabilities() & self.Gdk.SeatCapabilities.KEYBOARD)

    def _mapped(self, *_args):
        if self.mapped or self.closed:
            return
        self.mapped = True
        self.on_mapped()
        if not self.keyboard_capable():
            # Nothing on this seat can type, so there is no keyboard focus to
            # wait for and nothing to park. Say so rather than wait forever.
            self.on_keyboard(proven=False)

    def _focus_changed(self, window, *_args):
        if self.closed:
            return
        if window.is_active():
            self._had_keyboard = True
            if self._loss_timer is not None:
                self.GLib.source_remove(self._loss_timer)
                self._loss_timer = None
            self.on_keyboard(proven=True)
        elif self._had_keyboard and self._loss_timer is None:
            self._loss_timer = self.GLib.timeout_add(
                int(FOCUS_LOSS_GRACE_SECONDS * 1000), self._keyboard_lost)

    def _keyboard_lost(self):
        """Only a keyboard that exists and is elsewhere ends watch mode.

        A seat that lost its keyboard outright has nothing left to park, so the
        guard stays up and keeps eating the pointer; a keyboard that is present
        and pointed at something else means the guard is no longer doing what
        it says, and ending is the honest answer.
        """
        self._loss_timer = None
        if not self.closed and self.keyboard_capable() and not self.windows[0].is_active():
            self.on_keyboard_lost()
        return False

    def _pressed(self, _controller, keyval, keycode, state):
        self.chord.press(keycode, self.Gdk.keyval_name(keyval) or '',
                         modifier_names(state, self.Gdk), time.monotonic())
        self._reschedule()
        return True  # Nothing below the guard ever sees a key.

    def _released(self, _controller, keyval, keycode, state):
        self.chord.release(keycode, modifier_names(state, self.Gdk), time.monotonic())
        self._reschedule()

    def _reschedule(self):
        """One timer per hold, so holding still is enough to leave.

        A held key autorepeats about twenty-five times a second, and each
        repeat arrives as another key-pressed. Restarting the timer on every
        one of them means it never expires and the chord never releases, which
        is exactly the bug this guards against: the timer is only touched when
        the hold itself started or ended.
        """
        armed_at = self.chord.armed_at
        if armed_at == self._timed_hold and self._hold_timer is not None:
            return
        self._timed_hold = armed_at
        if self._hold_timer is not None:
            self.GLib.source_remove(self._hold_timer)
            self._hold_timer = None
        if armed_at is not None and not self.closed:
            self._hold_timer = self.GLib.timeout_add(
                int(RELEASE_HOLD_SECONDS * 1000) + 20, self._hold_elapsed)

    def _hold_elapsed(self):
        self._hold_timer = self._timed_hold = None
        if not self.closed and self.chord.ready(time.monotonic()):
            self.on_release()
        return False

    def close(self):
        if self.closed:
            return
        self.closed = True
        for timer in (self._loss_timer, self._hold_timer):
            if timer is not None:
                self.GLib.source_remove(timer)
        self._loss_timer = self._hold_timer = None
        for window in self.windows:
            window.destroy()
