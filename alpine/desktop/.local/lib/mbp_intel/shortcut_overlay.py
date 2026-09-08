#!/usr/bin/env python3
"""Non-focusable shortcut overlay and per-Sway-session service lifecycle."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import stat
import struct
import subprocess
import sys
import time


IPC_HEADER = struct.Struct('=6sII')
IPC_GET_OUTPUTS = 3
IPC_GET_TREE = 4
IPC_SUBSCRIBE = 2
STATUS_VERSION = 1



# The overlay is a GTK layer surface, so the Qt platform theme never reaches it.
# These follow the same MBP Intel palette the rest of the desktop is built from.
DEFAULT_PALETTE = {'background': '#282828', 'background_hard': '#1d2021', 'surface': '#3c3836',
                   'foreground': '#ebdbb2', 'muted': '#928374', 'border': '#504945',
                   'accent': '#fabd2f'}


def theme_module():
    """Return the shared MBP Intel palette module, or None when installed alone."""
    try:
        import overlay_theme
        return overlay_theme
    except ImportError:
        shared = Path.home() / '.local/lib/mbp_intel'
        if shared.is_dir() and str(shared) not in sys.path:
            sys.path.append(str(shared))
        try:
            import overlay_theme
            return overlay_theme
        except ImportError:
            return None


def active_palette():
    module = theme_module()
    if module is None:
        return dict(DEFAULT_PALETTE)
    palette = module.read_palette()
    return {key: palette.get(key, fallback) for key, fallback in DEFAULT_PALETTE.items()}


def themed_css(template, palette):
    definitions = ''.join('@define-color theme_' + key + ' ' + value + ';\n'
                          for key, value in palette.items())
    return (definitions + template).encode()


class AlreadyRunning(RuntimeError):
    """The service already owns this Sway session."""


def _owned_private_directory(path, create=False):
    if create:
        path.mkdir(mode=0o700, exist_ok=True)
    try:
        info = path.stat(follow_symlinks=False)
    except OSError as error:
        raise RuntimeError(f'owned private directory is unavailable: {path}') from error
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise RuntimeError(f'expected an owned private directory: {path}')


def _owned_socket(path):
    try:
        info = path.stat(follow_symlinks=False)
    except OSError as error:
        raise RuntimeError(f'Sway socket is unavailable: {path}') from error
    if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
        raise RuntimeError(f'Sway socket must be an owned Unix socket: {path}')
    return info


def find_sway_socket(runtime, explicit=None):
    """Resolve and validate one session socket without consulting another UID."""
    configured = explicit or os.environ.get('SWAYSOCK')
    if configured:
        candidates = [Path(configured)]
    else:
        candidates = sorted(runtime.glob(f'sway-ipc.{os.getuid()}.*.sock'),
                            key=lambda item: item.stat().st_mtime, reverse=True)
    for candidate in candidates:
        try:
            _owned_socket(candidate)
            return candidate
        except RuntimeError:
            continue
    raise RuntimeError('no owned Sway session socket')


def _process_identity(pid):
    try:
        process = Path('/proc') / str(int(pid))
        if process.stat().st_uid != os.getuid():
            return None
        fields = process.joinpath('stat').read_text().rsplit(')', 1)[1].split()
        if fields[0] in ('Z', 'X'):
            return None
        return {
            'pid': int(pid),
            'start_time': fields[19],
            'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        }
    except (OSError, ValueError, IndexError):
        return None


def _socket_identity(path):
    info = _owned_socket(path)
    return {
        'socket': str(path),
        'device': info.st_dev,
        'inode': info.st_ino,
        'created_ns': info.st_ctime_ns,
    }


class SessionLease:
    """An advisory lock and status record keyed to one socket inode."""

    def __init__(self, runtime, sway_socket):
        self.runtime = Path(runtime)
        self.sway_socket = Path(sway_socket)
        identity = _socket_identity(self.sway_socket)
        material = json.dumps(identity, sort_keys=True).encode('utf-8')
        self.socket_id = hashlib.sha256(material).hexdigest()[:16]
        self.directory = self.runtime / 'mbp-intel-shortcuts'
        self.lock_path = self.directory / f'{self.socket_id}.lock'
        self.status_path = self.directory / f'{self.socket_id}.json'
        self._descriptor = None
        self._started_at = None

    def _write_status(self, state, **details):
        record = {
            'version': STATUS_VERSION,
            'state': state,
            'pid': os.getpid(),
            'process': _process_identity(os.getpid()),
            'sway_socket': str(self.sway_socket),
            'socket_id': self.socket_id,
            'started_at': self._started_at,
            'updated_at': time.time(),
        }
        record.update(details)
        temporary = self.status_path.with_name(
            f'.{self.status_path.name}.{os.getpid()}.{time.monotonic_ns()}.tmp')
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                             | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(descriptor, 'w') as stream:
                json.dump(record, stream, sort_keys=True)
                stream.write('\n')
            temporary.replace(self.status_path)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise

    def acquire(self):
        _owned_private_directory(self.runtime)
        _owned_socket(self.sway_socket)
        _owned_private_directory(self.directory, create=True)
        descriptor = os.open(self.lock_path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC
                             | os.O_NOFOLLOW, 0o600)
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600):
            os.close(descriptor)
            raise RuntimeError(f'unsafe service lock: {self.lock_path}')
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            os.close(descriptor)
            raise AlreadyRunning('shortcut service already runs for this Sway session') from error
        self._descriptor = descriptor
        self._started_at = time.time()
        try:
            self._write_status('starting', visible=False, device_count=0)
        except BaseException:
            fcntl.flock(self._descriptor, fcntl.LOCK_UN)
            os.close(self._descriptor)
            self._descriptor = None
            raise
        return self

    def update(self, state, **details):
        if self._descriptor is not None:
            self._write_status(state, **details)

    def close(self):
        if self._descriptor is None:
            return
        try:
            self._write_status('stopped', visible=False, device_count=0)
        finally:
            fcntl.flock(self._descriptor, fcntl.LOCK_UN)
            os.close(self._descriptor)
            self._descriptor = None


def screen_locked(runtime, wayland_socket):
    """Accept only the readiness record for this live compositor and process."""
    record = Path(runtime) / 'mbp-intel-screen-lock/ready.json'
    try:
        if record.is_symlink() or not record.is_file():
            return False
        saved = json.loads(record.read_text())
        process = saved['process']
        return (saved['compositor'] == _socket_identity(Path(wayland_socket))
                and process == _process_identity(process['pid']))
    except RuntimeError:
        # A readiness record plus a vanished compositor socket is ambiguous;
        # suppress the overlay until the session liveness path closes it.
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False


def _default_graphical_probe(runtime, wayland_socket):
    try:
        _owned_socket(wayland_socket)
    except RuntimeError:
        return False
    session_id = os.environ.get('XDG_SESSION_ID')
    if session_id:
        try:
            result = subprocess.run(
                ['loginctl', 'show-session', session_id, '--property=Active',
                 '--property=State', '--property=Type'],
                text=True, capture_output=True, timeout=.4, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return False
        values = dict(line.split('=', 1) for line in result.stdout.splitlines()
                      if '=' in line)
        return (result.returncode == 0 and values.get('Active') == 'yes'
                and values.get('State') == 'active' and values.get('Type') == 'wayland')
    virtual_terminal = os.environ.get('XDG_VTNR')
    if not virtual_terminal or os.environ.get('XDG_SESSION_TYPE') != 'wayland':
        return False
    try:
        active = Path('/sys/class/tty/tty0/active').read_text().strip()
    except OSError:
        return False
    return active == f'tty{virtual_terminal}'


class GraphicalSessionGuard:
    """Cheap lock checks plus a short-lived cached logind/VT activity probe."""

    def __init__(self, runtime, wayland_socket, activity_probe=None, lock_probe=None,
                 cache_seconds=.25):
        self.runtime = Path(runtime)
        self.wayland_socket = Path(wayland_socket)
        self.activity_probe = activity_probe or (
            lambda: _default_graphical_probe(self.runtime, self.wayland_socket))
        self.lock_probe = lock_probe or screen_locked
        self.cache_seconds = cache_seconds
        self._active = False
        self._checked_at = float('-inf')
        self._future = None
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix='mbp-intel-session-check')
        self.locked = False
        self.closed = False

    def allows_overlay(self, now):
        if self.closed:
            return False
        if self._future is not None and self._future.done():
            try:
                self._active = bool(self._future.result())
            except Exception:
                self._active = False
            self._checked_at = now
            self._future = None
        if (self._future is None
                and now - self._checked_at >= self.cache_seconds):
            self._future = self._executor.submit(self.activity_probe)
        self.locked = bool(self.lock_probe(self.runtime, self.wayland_socket))
        return self._active and not self.locked

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self._future is not None:
            self._future.cancel()
        self._executor.shutdown(wait=False, cancel_futures=True)


class SocketWatch:
    """A connected IPC socket whose peer lifetime can be polled without blocking."""

    def __init__(self, connection, path=None):
        self.connection = connection
        self.path = Path(path) if path is not None else None
        self.connection.setblocking(False)
        self.closed = False

    def alive(self):
        if self.closed:
            return False
        try:
            self.connection.recv(1, socket.MSG_PEEK)
        except BlockingIOError:
            return True
        except OSError:
            return False
        # This subscriber receives only shutdown events, so data and EOF both end it.
        return False

    def close(self):
        if not self.closed:
            self.connection.close()
            self.closed = True


def _send_ipc(connection, kind, payload=''):
    body = payload.encode('utf-8')
    connection.sendall(IPC_HEADER.pack(b'i3-ipc', len(body), kind) + body)


def _receive_exact(connection, size):
    chunks = bytearray()
    while len(chunks) < size:
        chunk = connection.recv(size - len(chunks))
        if not chunk:
            raise ConnectionError('Sway disconnected')
        chunks.extend(chunk)
    return bytes(chunks)


def _receive_ipc(connection):
    magic, length, kind = IPC_HEADER.unpack(_receive_exact(connection, IPC_HEADER.size))
    if magic != b'i3-ipc' or length > 32 * 1024 * 1024:
        raise ValueError('invalid Sway IPC frame')
    return kind, json.loads(_receive_exact(connection, length))


def connect_sway_watch(path):
    connection = socket.socket(socket.AF_UNIX)
    try:
        connection.settimeout(1)
        connection.connect(str(path))
        _send_ipc(connection, IPC_SUBSCRIBE, '["shutdown"]')
        kind, response = _receive_ipc(connection)
        if kind != IPC_SUBSCRIBE or not response.get('success'):
            raise RuntimeError('Sway rejected shutdown subscription')
        return SocketWatch(connection, path)
    except BaseException:
        connection.close()
        raise


def _ipc_request(path, kind):
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(1)
        connection.connect(str(path))
        _send_ipc(connection, kind)
        response_kind, response = _receive_ipc(connection)
        if response_kind != kind:
            raise ValueError('unexpected Sway IPC response')
        return response


def _output_rect(path, output_name):
    if not output_name:
        return None
    try:
        outputs = _ipc_request(path, IPC_GET_OUTPUTS)
        output = next(item for item in outputs if item.get('name') == output_name)
        rect = output.get('rect', {})
        return {key: int(rect[key]) for key in ('x', 'y', 'width', 'height')}
    except (ConnectionError, OSError, StopIteration, TypeError, ValueError, KeyError):
        return None


def _focused_output_context(path):
    tree = _ipc_request(path, IPC_GET_TREE)
    focused = None

    def visit(node, output, depth):
        nonlocal focused
        if not isinstance(node, dict):
            return
        if node.get('type') == 'output' and node.get('name') not in {'__i3', '__sway'}:
            output = node.get('name')
        if node.get('focused') is True and output:
            if focused is None or depth > focused[0]:
                focused = (depth, output)
        for collection in ('nodes', 'floating_nodes'):
            for child in node.get(collection, ()) if isinstance(
                    node.get(collection), list) else ():
                visit(child, output, depth + 1)

    visit(tree, None, 0)
    output = focused[1] if focused else None
    return {'output': output, '_output_rect': _output_rect(path, output)}


class ContextProvider:
    """Add focused-output geometry to provider data while still off the UI thread."""

    def __init__(self, provider, sway_socket):
        self.provider = provider
        self.sway_socket = Path(sway_socket)

    def snapshot(self):
        snapshot = self.provider.snapshot()
        snapshot['_output_rect'] = _output_rect(self.sway_socket, snapshot.get('output'))
        return snapshot


class ServiceController:
    """Drive input at UI cadence and collect context on disposable generations."""

    def __init__(self, monitor, provider, overlay, liveness, guard,
                 refresh_seconds=1.0, executor=None, loading_probe=None,
                 metadata_executor=None):
        self.monitor = monitor
        self.provider = provider
        self.overlay = overlay
        self.liveness = liveness
        self.guard = guard
        self.refresh_seconds = refresh_seconds
        # One bounded request may outlive a released hold. New generations
        # replace the single queued request instead of filling every worker
        # with context that can no longer be rendered.
        self.executor = executor or ThreadPoolExecutor(
            max_workers=1, thread_name_prefix='mbp-intel-shortcuts')
        self._owns_executor = executor is None
        socket_path = getattr(liveness, 'path', None)
        self.loading_probe = loading_probe or (
            (lambda: _focused_output_context(socket_path)) if socket_path else None)
        self.metadata_executor = metadata_executor or ThreadPoolExecutor(
            max_workers=1, thread_name_prefix='mbp-intel-output-check')
        self._owns_metadata_executor = metadata_executor is None
        self._metadata_future = None
        self._metadata_generation = None
        self._loading_context = None
        self._loading_shown = False
        self.loading_context_ready = False
        self._future = None
        self._future_generation = None
        self._generation = 0
        self._holding = False
        self._loaded_snapshot = None
        self._next_refresh = float('inf')
        self.snapshot_ready = False
        self.closed = False
        self.graphical_active = False

    @property
    def visible(self):
        return (self._holding and self.graphical_active
                and (self._loading_shown or self.snapshot_ready))

    @property
    def source_pending(self):
        return self._holding and self._future is not None

    def _submit_snapshot(self):
        if self._future is not None:
            return
        self.snapshot_ready = False
        self._future_generation = self._generation
        self._future = self.executor.submit(self.provider.snapshot)

    def _submit_loading_context(self):
        if self.loading_probe is not None and self._metadata_future is None:
            self._metadata_generation = self._generation
            self._metadata_future = self.metadata_executor.submit(self.loading_probe)

    def _collect_loading_context(self):
        if self._metadata_future is not None and self._metadata_future.done():
            generation = self._metadata_generation
            try:
                context = self._metadata_future.result()
                rect = context.get('_output_rect') if isinstance(context, dict) else None
                if (generation == self._generation and self._holding
                        and isinstance(context.get('output'), str)
                        and isinstance(rect, dict)):
                    self._loading_context = context
                    self.loading_context_ready = True
                    if not self.snapshot_ready and not self._loading_shown:
                        self.overlay.show_loading(context)
                        self._loading_shown = True
            except Exception:
                pass
            self._metadata_future = None
            self._metadata_generation = None
        if (self._holding and not self._loading_shown
                and not self.snapshot_ready and self._metadata_future is None):
            self._submit_loading_context()

    def _hide(self, cancel_hold=False):
        if cancel_hold:
            self.monitor.state.cancel()
        if self._holding or cancel_hold:
            self._generation += 1
            if self._future is not None and self._future.cancel():
                self._future = None
                self._future_generation = None
            self._loaded_snapshot = None
            self.snapshot_ready = False
            if (self._metadata_future is not None
                    and self._metadata_future.cancel()):
                self._metadata_future = None
                self._metadata_generation = None
            self._loading_context = None
            self._loading_shown = False
            self.loading_context_ready = False
            self._holding = False
            self.overlay.hide()

    def _collect_snapshot(self, now):
        if self._future is None or not self._future.done():
            return
        future = self._future
        generation = self._future_generation
        self._future = None
        self._future_generation = None
        if generation != self._generation or not self._holding:
            if self._holding:
                self._submit_snapshot()
            return
        try:
            snapshot = future.result()
        except Exception as error:
            snapshot = {
                'app': 'Unavailable',
                'output': None,
                'sections': [{
                    'title': 'Context',
                    'coverage': 'unavailable',
                    'rows': [{'key': '—', 'description': str(error)}],
                }],
            }
        if snapshot != self._loaded_snapshot:
            self.overlay.show(snapshot)
            self._loaded_snapshot = snapshot
        self.snapshot_ready = True
        self._next_refresh = now + self.refresh_seconds

    def tick(self, now):
        if self.closed:
            return False
        if not self.liveness.alive():
            self.close()
            return False
        try:
            requested = bool(self.monitor.poll(now))
        except (OSError, RuntimeError):
            self.close()
            return False
        try:
            self.graphical_active = self.guard.allows_overlay(now)
        except (OSError, RuntimeError):
            self.close()
            return False
        if not self.graphical_active:
            self._hide(cancel_hold=True)
            return True
        if not requested:
            self._hide()
            return True
        if not self._holding:
            self._holding = True
            self._loading_context = None
            self.loading_context_ready = False
            if self.loading_probe is None:
                self.overlay.show_loading(None)
                self._loading_shown = True
            else:
                self._submit_loading_context()
            self._submit_snapshot()
        self._collect_loading_context()
        self._collect_snapshot(now)
        if (self._holding and self._future is None
                and now >= self._next_refresh):
            self._submit_snapshot()
        return True

    def close(self):
        if self.closed:
            return
        self.closed = True
        self._generation += 1
        if self._future is not None:
            self._future.cancel()
            self._future = None
        if self._metadata_future is not None:
            self._metadata_future.cancel()
            self._metadata_future = None
        self.monitor.close()
        self.overlay.hide()
        self.overlay.close()
        self.liveness.close()
        close_guard = getattr(self.guard, 'close', None)
        if close_guard is not None:
            close_guard()
        if self._owns_executor:
            self.executor.shutdown(wait=False, cancel_futures=True)
        if self._owns_metadata_executor:
            self.metadata_executor.shutdown(wait=False, cancel_futures=True)


class GtkShortcutOverlay:
    """A compact, pointer-interactive layer surface with no keyboard focus."""

    CSS_TEMPLATE = '''
    #mbp-intel-shortcuts-window { background-color: transparent; }
    #mbp-intel-shortcuts-panel {
        background-color: alpha(@theme_background, 0.97);
        border: 2px solid @theme_border;
        border-radius: 18px;
        color: @theme_foreground;
        padding: 20px;
    }
    #mbp-intel-shortcuts-title { color: @theme_foreground; font-size: 22px; font-weight: bold; }
    #mbp-intel-shortcuts-hint { color: @theme_muted; font-size: 11px; }
    #mbp-intel-shortcuts-section {
        background-color: alpha(@theme_surface, 0.82);
        border-radius: 10px;
        padding: 12px;
    }
    #mbp-intel-shortcuts-section-title { color: @theme_accent; font-size: 15px; font-weight: bold; }
    #mbp-intel-shortcuts-coverage { color: @theme_muted; font-size: 10px; }
    #mbp-intel-shortcuts-key {
        background-color: @theme_surface;
        border: 1px solid @theme_border;
        border-radius: 5px;
        color: @theme_foreground;
        font-family: monospace;
        font-weight: bold;
        padding: 3px 7px;
    }
    #mbp-intel-shortcuts-description { color: @theme_foreground; }
    scrollbar slider { background-color: @theme_accent; min-width: 8px; min-height: 28px; }
    '''

    def __init__(self):
        import gi
        gi.require_version('Gtk', '3.0')
        gi.require_version('Gdk', '3.0')
        gi.require_version('GtkLayerShell', '0.1')
        from gi.repository import Gdk, Gtk, GtkLayerShell

        self.Gdk = Gdk
        self.Gtk = Gtk
        self.LayerShell = GtkLayerShell
        self.window = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        self.window.set_name('mbp-intel-shortcuts-window')
        self.window.set_decorated(False)
        self.window.set_resizable(False)
        self.window.set_accept_focus(False)
        self.window.set_focus_on_map(False)
        self.window.set_skip_taskbar_hint(True)
        self.window.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.window.connect('button-press-event', lambda *_arguments: True)
        GtkLayerShell.init_for_window(self.window)
        GtkLayerShell.set_namespace(self.window, 'mbp-intel-shortcuts')
        GtkLayerShell.set_layer(self.window, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_keyboard_mode(self.window, GtkLayerShell.KeyboardMode.NONE)
        GtkLayerShell.set_exclusive_zone(self.window, 0)
        GtkLayerShell.set_anchor(self.window, GtkLayerShell.Edge.TOP, True)
        GtkLayerShell.set_margin(self.window, GtkLayerShell.Edge.TOP, 46)

        self.css = Gtk.CssProvider()
        self.palette = active_palette()
        self.css.load_from_data(themed_css(self.CSS_TEMPLATE, self.palette))
        css = self.css
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.panel.set_name('mbp-intel-shortcuts-panel')
        self.window.add(self.panel)
        self._last_monitor = None

    def _clear(self):
        for child in self.panel.get_children():
            self.panel.remove(child)

    def _label(self, text, name, xalign=0):
        label = self.Gtk.Label(label=str(text))
        label.set_name(name)
        label.set_xalign(xalign)
        label.set_line_wrap(True)
        label.set_selectable(False)
        return label

    def _select_monitor(self, output_name=None, output_rect=None):
        display = self.Gdk.Display.get_default()
        if display is None:
            return None
        monitors = [display.get_monitor(index)
                    for index in range(display.get_n_monitors())]
        monitor = next((item for item in monitors
                        if output_name and output_name.lower() in ' '.join(filter(None, (
                            item.get_model(), item.get_manufacturer()))).lower()), None)
        if monitor is None and output_rect:
            monitor = next((item for item in monitors
                            if all(getattr(item.get_geometry(), key) == output_rect[key]
                                   for key in ('x', 'y', 'width', 'height'))), None)
        if monitor is None and monitors:
            monitor = display.get_primary_monitor() or monitors[0]
        if monitor is not None and monitor != self._last_monitor:
            self.LayerShell.set_monitor(self.window, monitor)
            self._last_monitor = monitor
        return monitor

    def _bound_window(self, monitor):
        if monitor is None:
            width, height = 900, 650
        else:
            geometry = monitor.get_geometry()
            width = min(960, max(440, geometry.width - 96))
            height = min(720, max(300, geometry.height - 96))
        self.window.set_size_request(width, height)

    def _header(self, title):
        heading = self.Gtk.Box(orientation=self.Gtk.Orientation.VERTICAL, spacing=3)
        heading.pack_start(self._label(title, 'mbp-intel-shortcuts-title'), False, False, 0)
        heading.pack_start(self._label(
            'Release Super to close  •  Scroll for more', 'mbp-intel-shortcuts-hint'),
            False, False, 0)
        self.panel.pack_start(heading, False, False, 0)

    def show_loading(self, context=None):
        self._clear()
        context = context if isinstance(context, dict) else {}
        self._select_monitor(context.get('output'), context.get('_output_rect'))
        self.window.set_size_request(540, 150)
        self.window.resize(540, 150)
        self._header('Keyboard shortcuts')
        self.panel.pack_start(self._label(
            'Loading the focused context…', 'mbp-intel-shortcuts-description'),
            False, False, 0)
        self.window.show_all()

    def show(self, snapshot):
        self._clear()
        monitor = self._select_monitor(snapshot.get('output'), snapshot.get('_output_rect'))
        self._bound_window(monitor)
        app = snapshot.get('app') or 'Current context'
        self._header(f'{app} shortcuts')
        scroll = self.Gtk.ScrolledWindow()
        scroll.set_policy(self.Gtk.PolicyType.NEVER, self.Gtk.PolicyType.AUTOMATIC)
        scroll.set_overlay_scrolling(False)
        content = self.Gtk.Box(orientation=self.Gtk.Orientation.VERTICAL, spacing=10)
        for section in snapshot.get('sections', []):
            card = self.Gtk.Box(orientation=self.Gtk.Orientation.VERTICAL, spacing=7)
            card.set_name('mbp-intel-shortcuts-section')
            section_header = self.Gtk.Box(orientation=self.Gtk.Orientation.HORIZONTAL,
                                          spacing=10)
            section_header.pack_start(self._label(
                section.get('title', 'Shortcuts'), 'mbp-intel-shortcuts-section-title'),
                True, True, 0)
            coverage = section.get('coverage', 'unknown')
            section_header.pack_end(self._label(
                coverage, 'mbp-intel-shortcuts-coverage', xalign=1), False, False, 0)
            card.pack_start(section_header, False, False, 0)
            for row in section.get('rows', []):
                line = self.Gtk.Box(orientation=self.Gtk.Orientation.HORIZONTAL,
                                    spacing=12)
                key = self._label(row.get('key', '—'), 'mbp-intel-shortcuts-key', xalign=.5)
                key.set_size_request(210, -1)
                description = self._label(
                    row.get('description', ''), 'mbp-intel-shortcuts-description')
                line.pack_start(key, False, False, 0)
                line.pack_start(description, True, True, 0)
                card.pack_start(line, False, False, 0)
            content.pack_start(card, False, False, 0)
        scroll.add(content)
        self.panel.pack_start(scroll, True, True, 0)
        self.window.show_all()

    def hide(self):
        self.window.hide()

    def close(self):
        self.window.destroy()


def _wayland_socket(runtime):
    display = os.environ.get('WAYLAND_DISPLAY')
    if not display:
        raise RuntimeError('WAYLAND_DISPLAY is required')
    path = Path(display)
    return path if path.is_absolute() else runtime / path


def _provider(socket_path, profiles_path=None, decorate=False):
    from mbp_intel.shortcut_sources import ShortcutProvider
    provider = ShortcutProvider(str(socket_path), profiles_path=profiles_path)
    return ContextProvider(provider, socket_path) if decorate else provider


def dump_snapshot(socket_path, profiles_path=None):
    print(json.dumps(_provider(socket_path, profiles_path).snapshot(),
                     ensure_ascii=False, indent=2))


def preview(socket_path, profiles_path=None, seconds=5.0):
    overlay = GtkShortcutOverlay()
    from gi.repository import GLib, Gtk
    snapshot = _provider(socket_path, profiles_path, decorate=True).snapshot()
    overlay.show(snapshot)
    GLib.timeout_add(max(1, int(seconds * 1000)), Gtk.main_quit)
    try:
        Gtk.main()
    finally:
        overlay.close()


def _run_daemon(runtime, socket_path, profiles_path=None):
    from mbp_intel.shortcut_hold import EvdevMonitor

    lease = SessionLease(runtime, socket_path)
    try:
        lease.acquire()
    except AlreadyRunning:
        return
    controller = None
    last_status = None
    try:
        watch = connect_sway_watch(socket_path)
        monitor = EvdevMonitor()
        overlay = GtkShortcutOverlay()
        from gi.repository import GLib, Gtk
        guard = GraphicalSessionGuard(runtime, _wayland_socket(runtime))
        provider = _provider(socket_path, profiles_path, decorate=True)
        controller = ServiceController(monitor, provider, overlay, watch, guard)

        def tick():
            nonlocal last_status
            running = controller.tick(time.monotonic())
            status = (controller.visible, controller.source_pending,
                      controller.graphical_active, monitor.device_count, guard.locked)
            if status != last_status:
                lease.update(
                    'visible' if controller.visible else 'running',
                    visible=controller.visible,
                    source_pending=controller.source_pending,
                    graphical_active=controller.graphical_active,
                    locked=guard.locked,
                    device_count=monitor.device_count)
                last_status = status
            if not running:
                Gtk.main_quit()
            return running

        GLib.timeout_add(25, tick)
        previous_handlers = {}
        for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            previous_handlers[signum] = signal.signal(
                signum, lambda _signum, _frame: GLib.idle_add(Gtk.main_quit))
        lease.update('running', visible=False, source_pending=False,
                     graphical_active=False, locked=False,
                     device_count=monitor.device_count)
        Gtk.main()
    finally:
        for signum, handler in locals().get('previous_handlers', {}).items():
            signal.signal(signum, handler)
        if controller is not None:
            controller.close()
        lease.close()


def print_status(runtime, socket_path):
    lease = SessionLease(runtime, socket_path)
    try:
        record = json.loads(lease.status_path.read_text())
    except (OSError, ValueError) as error:
        raise RuntimeError('no shortcut service status for this Sway session') from error
    process = record.get('process') if isinstance(record, dict) else None
    live = False
    if isinstance(process, dict):
        live = process == _process_identity(process.get('pid'))
    record['live'] = live and record.get('state') != 'stopped'
    if not record['live'] and record.get('state') != 'stopped':
        record['recorded_state'] = record.get('state')
        record['state'] = 'stale'
    print(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True))


def parse_args(arguments=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', nargs='?', choices=('daemon', 'dump', 'preview', 'status'))
    aliases = parser.add_mutually_exclusive_group()
    aliases.add_argument('--dump', action='store_true', help='print contextual shortcuts as JSON')
    aliases.add_argument('--preview', action='store_true', help='show the overlay without input monitoring')
    parser.add_argument('--seconds', type=float, default=5.0,
                        help='preview duration in seconds (default: 5)')
    parser.add_argument('--socket', help='Sway IPC socket (default: SWAYSOCK or owned runtime socket)')
    parser.add_argument('--profiles', help='optional local application profile file')
    args = parser.parse_args(arguments)
    if (args.dump or args.preview) and args.command:
        parser.error('choose either a command or a --dump/--preview alias')
    if args.seconds <= 0:
        parser.error('--seconds must be greater than zero')
    args.command = 'dump' if args.dump else 'preview' if args.preview else args.command or 'daemon'
    return args


def main(arguments=None):
    args = parse_args(arguments)
    runtime_name = os.environ.get('XDG_RUNTIME_DIR')
    if not runtime_name:
        raise RuntimeError('XDG_RUNTIME_DIR is required')
    runtime = Path(runtime_name)
    _owned_private_directory(runtime)
    socket_path = find_sway_socket(runtime, args.socket)
    if args.command == 'dump':
        dump_snapshot(socket_path, args.profiles)
    elif args.command == 'preview':
        preview(socket_path, args.profiles, args.seconds)
    elif args.command == 'status':
        print_status(runtime, socket_path)
    else:
        _run_daemon(runtime, socket_path, args.profiles)


if __name__ == '__main__':
    try:
        main()
    except (ConnectionError, OSError, RuntimeError, ValueError) as error:
        sys.exit(f'mbp-intel-shortcuts: {error}')
