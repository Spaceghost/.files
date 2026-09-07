"""Read-only X11 keyboard/context and partial desktop configuration providers.

LXQt configuration follows lxqt-globalkeys daemon/core.cpp: groups are
shortcut[.id], with Enabled, Comment and Exec or DBus action fields.
https://github.com/lxqt/lxqt-globalkeys/blob/master/daemon/core.cpp
No command obtained from either configuration file is executed.
"""
from collections import deque
import configparser
from contextlib import contextmanager
import os
import json
from pathlib import Path
import re
import socket
import stat
import struct
import subprocess
import sys
import threading
import time
from urllib.parse import unquote
import xml.etree.ElementTree as ET

from .config import config_home
from .hold import HoldState, KEY_CAPSLOCK, KEY_LEFTMETA, KEY_RIGHTMETA, _set_bits
from .sources import ShortcutProvider, _clean


def display_identity(display):
    """Normalize local server aliases/screens for one singleton per X display."""
    if not isinstance(display, str) or not re.fullmatch(r'[^\s/]*:[0-9]+(?:\.[0-9]+)?', display):
        raise ValueError('DISPLAY must name an X11 display')
    host, number = display.rsplit(':', 1)
    number = str(int(number.split('.', 1)[0]))
    if host in ('', 'unix', 'localhost', socket.gethostname()):
        host = ''
    identity = {'backend': 'x11', 'server': f'{host}:{number}'}
    if not host:
        try:
            info = Path(f'/tmp/.X11-unix/X{number}').stat()
            identity.update(device=info.st_dev, inode=info.st_ino, created_ns=info.st_ctime_ns)
        except OSError:
            pass
    return identity


def _open_display(name):
    try:
        from Xlib.display import Display
    except ImportError as error:
        raise RuntimeError('the X11 backend requires python-Xlib') from error
    return Display(name)


def physical_trigger_codes(name):
    """Resolve XKB physical key names, even when Caps Lock maps to Escape."""
    display_identity(name)
    try:
        result = subprocess.run(['xkbcomp', '-xkb', name, '-'], stdin=subprocess.DEVNULL,
                                capture_output=True, text=True, timeout=1, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError('X11 physical triggers require a working xkbcomp') from error
    if result.returncode or len(result.stdout) > 1024 * 1024:
        raise RuntimeError('cannot read X11 physical key names with xkbcomp')
    section = re.search(r'\bxkb_keycodes\b[^{}]*\{(.*?)\};', result.stdout, re.DOTALL)
    if section is None:
        raise RuntimeError('XKB keycodes section is unavailable')
    names = {'CAPS': KEY_CAPSLOCK, 'LWIN': KEY_LEFTMETA, 'RWIN': KEY_RIGHTMETA}
    return {int(number): names[key] for key, number in
            re.findall(r'^\s*<(CAPS|LWIN|RWIN)>\s*=\s*([0-9]+)\s*;', section.group(1), re.MULTILINE)
            if 8 <= int(number) <= 255}


def raw_key_event(event, opcode):
    """Decode the fixed XI2 raw-key suffix after the GenericEvent header."""
    if event.type != 35 or event.extension != opcode or event.evtype not in (13, 14):
        return None
    if not isinstance(event.data, bytes) or len(event.data) < 22:
        raise RuntimeError('invalid XI2 raw key event')
    device, _timestamp, detail, source, _valuators, flags, _pad = struct.unpack_from('=HIIHHII', event.data)
    if not 8 <= detail <= 255:
        raise RuntimeError('invalid XI2 keycode')
    return detail, int(event.evtype == 13), source or device, bool(flags & (1 << 16))


def _interrupt_display(display):
    try:
        display.display.socket.shutdown(socket.SHUT_RDWR)
    except (AttributeError, OSError):
        pass


@contextmanager
def _display_connection(name):
    display = _open_display(name)
    # Context work is already off the UI thread. Bound stalled server replies
    # so a disappearing display cannot leave an executor alive indefinitely.
    timer = threading.Timer(.75, _interrupt_display, args=(display,))
    timer.daemon = True
    timer.start()
    try:
        yield display
    finally:
        timer.cancel()
        try:
            display.close()
        except Exception:
            pass


class X11Monitor:
    """Poll XQueryKeymap outside the GUI thread; never grab or remap keys."""

    def __init__(self, state=None, display=None, *, connection_factory=None,
                 interval=.02, stale_seconds=.25, start=True):
        self.state = state if state is not None else HoldState()
        self.display_name = display or os.environ.get('DISPLAY')
        display_identity(self.display_name)
        self._factory = connection_factory or _open_display
        self._interval = interval
        self._stale_seconds = stale_seconds
        self._frames = deque(maxlen=256)
        self._mutex = threading.Lock()
        self._stop = threading.Event()
        self._connection = None
        self._last_sample = None
        self._started_at = time.monotonic()
        self._pressed = None
        self._failed = False
        self.error = None
        self._overflow = False
        self.closed = False
        self.locked = True
        self.has_saver = False
        self._thread = threading.Thread(target=self._run, name='hold-to-help-x11-input', daemon=True)
        if start:
            self._thread.start()

    @property
    def device_count(self):
        return int(self._last_sample is not None and not self._failed and not self.closed)

    def _enqueue(self, pressed, now, locked=False, cancel=False):
        with self._mutex:
            self._overflow |= len(self._frames) == self._frames.maxlen
            self._frames.append((set(pressed), now, locked, cancel))
            self._last_sample = now

    def _run(self):
        display = None
        try:
            from Xlib.ext import xinput
            display = self._factory(self.display_name)
            self._connection = display
            trigger_codes = physical_trigger_codes(self.display_name)
            if not any(code in self.state.trigger_keys for code in trigger_codes.values()):
                raise RuntimeError('selected trigger has no X11 keycode')
            root = display.screen().root
            self.has_saver = display.has_extension('MIT-SCREEN-SAVER')
            if not display.has_extension('XInputExtension'):
                raise RuntimeError('X11 requires XI2 raw keys to observe short chords')
            opcode = display.display.get_extension_major('XInputExtension')
            version = xinput.XIQueryVersion(display=display.display, opcode=opcode,
                                           major_version=2, minor_version=2)
            if version.major_version < 2:
                raise RuntimeError('X11 requires XInput version 2 or newer')
            root.xinput_select_events([(xinput.AllMasterDevices,
                                        xinput.RawKeyPressMask | xinput.RawKeyReleaseMask)])
            display.sync()
            raw = _set_bits(display.query_keymap())
            sources = {}
            translated = lambda: {trigger_codes.get(code, 1024 + code) for code in raw}
            self._enqueue(translated(), time.monotonic(), locked=True)
            while not self._stop.is_set():
                current = _set_bits(display.query_keymap())
                locked = bool(root.screensaver_query_info().state) if self.has_saver else False
                # MappingNotify refreshes python-Xlib's mapping cache. Changing
                # the map invalidates this monitor so no old held key survives.
                consumed = 0
                while display.pending_events() and consumed < 256:
                    consumed += 1
                    event = display.next_event()
                    if event.type == 34:
                        if physical_trigger_codes(self.display_name) != trigger_codes:
                            raise RuntimeError('X11 physical keycodes changed; restart the service')
                        continue
                    edge = raw_key_event(event, opcode)
                    if edge is None:
                        continue
                    code, value, source, repeat = edge
                    if repeat:
                        continue
                    cancel = False
                    if value:
                        cancel = code in raw and source not in sources.get(code, ())
                        sources.setdefault(code, set()).add(source)
                        raw.add(code)
                    else:
                        sources.setdefault(code, set()).discard(source)
                        if not sources[code]:
                            raw.discard(code)
                    self._enqueue(translated(), time.monotonic(), locked, cancel=cancel)
                if display.pending_events():
                    raise RuntimeError('X11 raw input exceeded the bounded event queue')
                if not consumed and current != raw:
                    # Startup or a lost edge never creates a fresh hold.
                    raw = current
                    sources.clear()
                    self._enqueue(translated(), time.monotonic(), locked, cancel=True)
                else:
                    self._enqueue(translated(), time.monotonic(), locked)
                self._stop.wait(self._interval)
        except Exception as error:
            self.error = str(error) or type(error).__name__
            self._failed = True
        finally:
            if display is not None:
                try:
                    display.close()
                except Exception:
                    pass

    def alive(self):
        if self._last_sample is None and time.monotonic() - self._started_at > 2:
            self.error = 'X11 connection startup timed out'
            self._failed = True
        return not self.closed and not self._failed

    def poll(self, now):
        if self.closed or self._failed:
            self.state.cancel()
            return False
        with self._mutex:
            frames = list(self._frames)
            self._frames.clear()
            overflow, self._overflow = self._overflow, False
            last_sample = self._last_sample
        if overflow:
            self.state.cancel()
            self._pressed = None
        for pressed, sampled_at, locked, cancel in frames:
            self.locked = locked
            if self._pressed is None:
                self.state._resync_device('x11', pressed)
            else:
                # Apply presses first: a simultaneous trigger release/repress
                # with another key must not manufacture an eligible hold.
                for code in sorted(pressed - self._pressed):
                    self.state.update('x11', code, 1, sampled_at)
                for code in sorted(self._pressed - pressed):
                    self.state.update('x11', code, 0, sampled_at)
            self._pressed = pressed
            if locked or cancel:
                self.state.cancel()
        if last_sample is None or now - last_sample > self._stale_seconds:
            self.state.cancel()
            self._pressed = None
            return False
        return not self.locked and self.state.visible(now)

    def close(self):
        if self.closed:
            return
        self.closed = True
        self._stop.set()
        self.state.remove_device('x11')
        if self._connection is not None:
            _interrupt_display(self._connection)


def _read_config(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 256 * 1024:
            raise ValueError('configuration must be a regular file of at most 256 KiB')
        raw = stream.read(256 * 1024 + 1)
    if len(raw) > 256 * 1024:
        raise ValueError('configuration exceeds 256 KiB')
    return raw.decode('utf-8')


def _section(title, path, rows=None, error=None):
    return {'title': title,
            'coverage': (f'Unavailable: {error}' if error else 'Partial configured bindings') + f' — {path}',
            'rows': rows or []}


def openbox_section(path):
    """Read namespaced rc.xml keybinds, including key chains and action names."""
    try:
        raw = _read_config(path)
        if '<!DOCTYPE' in raw.upper() or '<!ENTITY' in raw.upper():
            raise ValueError('XML declarations are not supported')
        document = ET.fromstring(raw)
        rows = []

        def tag(element):
            return element.tag.rsplit('}', 1)[-1]

        def key_label(key):
            names = {'C': 'Ctrl', 'A': 'Alt', 'S': 'Shift', 'W': 'Super', 'Return': 'Enter'}
            return ' / '.join('+'.join(names.get(part, part) for part in item.split('-'))
                              for item in key.split())

        def visit(binding, chain=(), depth=0):
            if depth > 8 or len(rows) >= 100:
                return
            key = _clean(binding.get('key'), 80)
            if not key:
                return
            chain = (*chain, key_label(key))
            actions = []
            for child in binding:
                if tag(child) == 'action':
                    name = _clean(child.get('name'), 64)
                    if not name:
                        continue
                    details = [_clean(item.text, 120) for item in child
                               if tag(item) in {'command', 'to', 'direction', 'menu'} and item.text]
                    actions.append(name + (': ' + ', '.join(details) if details else ''))
                elif tag(child) == 'keybind':
                    visit(child, chain, depth + 1)
            if actions:
                rows.append({'key': ', '.join(chain), 'description': _clean('; '.join(actions), 180)})

        for keyboard in document:
            if tag(keyboard) == 'keyboard':
                for binding in keyboard:
                    if tag(binding) == 'keybind':
                        visit(binding)
        return _section('Openbox', path, rows)
    except (OSError, ValueError, ET.ParseError) as error:
        return _section('Openbox', path, error=str(error))


def lxqt_section(path):
    """Read genuine lxqt-globalkeys groups; unsupported entries stay absent."""
    try:
        parser = configparser.ConfigParser(interpolation=None, strict=True)
        parser.optionxform = str
        parser.read_string(_read_config(path))
        rows = []
        for group in parser.sections():
            if group == 'General' or len(rows) >= 100:
                continue
            entry = parser[group]
            if entry.get('Enabled', 'true').casefold() not in {'true', '1'}:
                continue
            key = _clean(unquote(group).split('.', 1)[0], 80)
            if not key or '%' in key or key == 'General':
                continue
            command = entry.get('Exec', '').strip()
            dbus_action = all(entry.get(field, '').strip()
                              for field in ('service', 'path', 'interface', 'method'))
            client_action = entry.get('path', '').startswith('/') and 'interface' not in entry
            if not (command or dbus_action or client_action):
                continue
            description = entry.get('Comment', '').strip().strip('"')
            if not description:
                description = (command or ('DBus: ' + entry['method'] if dbus_action
                                            else 'Registered client action'))
            rows.append({'key': key, 'description': _clean(description, 180)})
        return _section('LXQt global shortcuts', path, rows)
    except (OSError, ValueError, configparser.Error) as error:
        return _section('LXQt global shortcuts', path, error=str(error))


def _desktop_config(relative):
    candidates = [config_home() / relative]
    candidates.extend(Path(directory) / relative for directory in
                      os.environ.get('XDG_CONFIG_DIRS', '/etc/xdg').split(':')
                      if directory and Path(directory).is_absolute())
    return next((path for path in candidates if path.is_file()), candidates[0])


def _property(display, window, name):
    from Xlib import X
    reply = window.get_property(display.intern_atom(name), X.AnyPropertyType, 0, 256)
    return reply.value if reply is not None else None


def focused_context(display):
    """EWMH application identity/PID and output geometry, without window titles."""
    screen = display.screen()
    root = screen.root
    active = _property(display, root, '_NET_ACTIVE_WINDOW')
    window = display.create_resource_object('window', int(active[0])) if active is not None and len(active) and active[0] else None
    if window is None:
        focus = display.get_input_focus().focus
        window = focus if hasattr(focus, 'get_property') else None
    identity = None
    rect = {'x': 0, 'y': 0, 'width': screen.width_in_pixels, 'height': screen.height_in_pixels}
    for _ in range(8):
        if window is None or window.id == root.id:
            break
        wm_class = _property(display, window, 'WM_CLASS')
        if wm_class:
            classes = bytes(wm_class).decode('utf-8', 'replace').strip('\x00').split('\x00')
            pid = _property(display, window, '_NET_WM_PID')
            identity = {'app_id': _clean(classes[-1], 128),
                        'pid': int(pid[0]) if pid is not None and len(pid) else None}
            geometry = window.get_geometry()
            position = root.translate_coords(window, 0, 0)
            rect = {'x': position.x, 'y': position.y,
                    'width': geometry.width, 'height': geometry.height}
            break
        window = window.query_tree().parent
    output = f'X11 screen {display.get_default_screen()}'
    output_rect = {'x': 0, 'y': 0, 'width': screen.width_in_pixels, 'height': screen.height_in_pixels}
    if display.has_extension('RANDR'):
        try:
            monitors = root.xrandr_get_monitors().monitors
            center = (rect['x'] + rect['width'] // 2, rect['y'] + rect['height'] // 2)
            monitor = next((item for item in monitors if item.x <= center[0] < item.x + item.width
                            and item.y <= center[1] < item.y + item.height), None)
            if monitor is not None:
                output = _clean(display.get_atom_name(monitor.name), 128)
                output_rect = {key: int(getattr(monitor, key)) for key in ('x', 'y', 'width', 'height')}
        except (AttributeError, RuntimeError):
            pass
    return {'window': identity, 'output': output, '_output_rect': output_rect}


class X11ShortcutProvider(ShortcutProvider):
    def __init__(self, display=None, profiles_path=None, trigger_label='Super',
                 openbox_path=None, lxqt_path=None):
        super().__init__('', profiles_path, trigger_label)
        self.display_name = display or os.environ.get('DISPLAY')
        display_identity(self.display_name)
        self.openbox_path = Path(openbox_path) if openbox_path else _desktop_config('openbox/rc.xml')
        self.lxqt_path = Path(lxqt_path) if lxqt_path else _desktop_config('lxqt/globalkeyshortcuts.conf')
        self._last_context = None

    def context(self):
        # A fixed helper process bounds even Display()'s authentication/setup
        # handshake; no global timeout changes or unkillable executor threads.
        try:
            module_path = str(Path(__file__).resolve().parent.parent)
            python_path = os.pathsep.join(filter(None, (module_path, os.environ.get('PYTHONPATH'))))
            result = subprocess.run(
                [sys.executable, '-P', '-m', 'hold_to_help.x11', '--context', self.display_name],
                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=1.5,
                env=dict(os.environ, PYTHONPATH=python_path), check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise RuntimeError('X11 context connection timed out or failed') from error
        if result.returncode or len(result.stdout) > 65536:
            raise RuntimeError('X11 context is unavailable')
        return json.loads(result.stdout)

    def _context(self):
        self._last_context = self.context()
        return self._last_context['window'], self._last_context['output']

    def _desktop_sections(self):
        return [openbox_section(self.openbox_path), lxqt_section(self.lxqt_path)]

    def snapshot(self):
        snapshot = super().snapshot()
        snapshot['_output_rect'] = self._last_context['_output_rect']
        return snapshot


if __name__ == '__main__':
    if len(sys.argv) != 3 or sys.argv[1] != '--context':
        raise SystemExit('internal X11 context helper requires --context DISPLAY')
    display_identity(sys.argv[2])
    try:
        with _display_connection(sys.argv[2]) as connection:
            print(json.dumps(focused_context(connection)))
    except Exception as error:
        raise SystemExit(f'X11 context unavailable: {error}')
