#!/usr/bin/env python3
"""Asynchronous shortcut collection and per-display service lifecycle."""
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import stat
import struct
import subprocess
import time


IPC_HEADER = struct.Struct('=6sII')
IPC_GET_OUTPUTS = 3
IPC_GET_TREE = 4
IPC_SUBSCRIBE = 2
STATUS_VERSION = 1


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

    def __init__(self, runtime, sway_socket=None, display=None):
        self.runtime = Path(runtime)
        self.sway_socket = Path(sway_socket) if sway_socket is not None else None
        self.display = display
        if self.sway_socket is not None:
            identity = _socket_identity(self.sway_socket)
        else:
            from .x11 import display_identity
            identity = display_identity(display)
        material = json.dumps(identity, sort_keys=True).encode('utf-8')
        self.socket_id = hashlib.sha256(material).hexdigest()[:16]
        self.directory = self.runtime / 'hold-to-help'
        self.lock_path = self.directory / f'{self.socket_id}.lock'
        self.status_path = self.directory / f'{self.socket_id}.json'
        self._descriptor = None
        self._started_at = None
        self._details = {}

    def _write_status(self, state, **details):
        record = {
            'version': STATUS_VERSION,
            'state': state,
            'pid': os.getpid(),
            'process': _process_identity(os.getpid()),
            'backend': 'sway' if self.sway_socket is not None else 'x11',
            'sway_socket': str(self.sway_socket) if self.sway_socket is not None else None,
            'display': self.display,
            'socket_id': self.socket_id,
            'started_at': self._started_at,
            'updated_at': time.time(),
        }
        self._details.update(details)
        record.update(self._details)
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
        if self.sway_socket is not None:
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
            raise AlreadyRunning('shortcut service already runs for this display') from error
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
    record = Path(runtime) / 'oldbook-screen-lock/ready.json'
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


def _screensaver_status():
    """Query existing services, distinguishing absent and failed lock authorities."""
    if not os.environ.get('DBUS_SESSION_BUS_ADDRESS'):
        return {'locked': False, 'lock_authority': False}
    authority = False
    for service, path in (
            ('org.freedesktop.ScreenSaver', '/ScreenSaver'),
            ('org.freedesktop.ScreenSaver', '/org/freedesktop/ScreenSaver'),
            ('org.gnome.ScreenSaver', '/org/gnome/ScreenSaver')):
        try:
            owner = subprocess.run(
                ['dbus-send', '--session', '--print-reply', '--reply-timeout=250',
                 '--dest=org.freedesktop.DBus', '/org/freedesktop/DBus',
                 'org.freedesktop.DBus.GetNameOwner', f'string:{service}'],
                text=True, capture_output=True, timeout=.4, check=False)
            if owner.returncode:
                if any(message in owner.stderr for message in ('ServiceUnknown', 'NameHasNoOwner')):
                    continue
                return {'locked': True, 'lock_authority': authority}
            unique_name = re.search(r'string "(:[0-9]+\.[0-9]+)"', owner.stdout)
            if unique_name is None:
                return {'locked': True, 'lock_authority': authority}
            result = subprocess.run(
                ['dbus-send', '--session', '--print-reply', '--reply-timeout=250',
                 f'--dest={unique_name.group(1)}', path, f'{service}.GetActive'],
                text=True, capture_output=True, timeout=.4, check=False)
        except FileNotFoundError:
            return {'locked': True, 'lock_authority': False}
        except (OSError, subprocess.TimeoutExpired):
            return {'locked': True, 'lock_authority': authority}
        if result.returncode == 0:
            if 'boolean true' in result.stdout:
                return {'locked': True, 'lock_authority': True}
            if 'boolean false' not in result.stdout:
                return {'locked': True, 'lock_authority': authority}
            authority = True
        elif not any(message in result.stderr for message in (
                'ServiceUnknown', 'NameHasNoOwner', 'UnknownMethod', 'UnknownObject')):
            return {'locked': True, 'lock_authority': authority}
    return {'locked': False, 'lock_authority': authority}


def screensaver_locked():
    """Conservative compatibility predicate; never activate a locker."""
    return _screensaver_status()['locked']


def probe_session(backend, runtime, wayland_socket=None):
    """Background activity/lock check; failed available authorities deny."""
    if backend == 'sway':
        try:
            _owned_socket(Path(wayland_socket))
        except (RuntimeError, TypeError):
            return {'active': False, 'locked': True, 'lock_authority': False}
    saver = _screensaver_status()
    locked = saver['locked']
    authority = saver['lock_authority']
    session_id = os.environ.get('XDG_SESSION_ID')
    if session_id:
        try:
            result = subprocess.run(
                ['loginctl', 'show-session', session_id, '--property=Active',
                 '--property=State', '--property=Type', '--property=LockedHint'],
                text=True, capture_output=True, timeout=.4, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return {'active': False, 'locked': True, 'lock_authority': False}
        values = dict(line.split('=', 1) for line in result.stdout.splitlines()
                      if '=' in line)
        active = (result.returncode == 0 and values.get('Active') == 'yes'
                  and values.get('State') == 'active'
                  and values.get('Type') == ('wayland' if backend == 'sway' else 'x11'))
        hint_known = (result.returncode == 0
                      and values.get('Type') == ('wayland' if backend == 'sway' else 'x11')
                      and values.get('LockedHint') in ('yes', 'no'))
        return {'active': active,
                'locked': locked or not hint_known or values.get('LockedHint') != 'no',
                'lock_authority': authority or hint_known}
    virtual_terminal = os.environ.get('XDG_VTNR')
    if virtual_terminal:
        try:
            active = Path('/sys/class/tty/tty0/active').read_text().strip() == f'tty{virtual_terminal}'
        except OSError:
            active = False
    else:
        # Standalone X servers have no logind/VT authority; X11Monitor also
        # requires fresh connection and MIT-SCREEN-SAVER state each poll.
        active = backend == 'x11' and bool(os.environ.get('DISPLAY'))
    return {'active': active, 'locked': locked, 'lock_authority': authority}


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
        self._session_locked = False
        self.lock_authority = False
        self._checked_at = float('-inf')
        self._future = None
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix='oldbook-session-check')
        self.locked = False
        self.closed = False

    def allows_overlay(self, now):
        if self.closed:
            return False
        if self._future is not None and self._future.done():
            try:
                result = self._future.result()
                self._active = bool(result.get('active')) if isinstance(result, dict) else bool(result)
                self._session_locked = bool(result.get('locked')) if isinstance(result, dict) else False
                self.lock_authority = (bool(result.get('lock_authority'))
                                       if isinstance(result, dict) else False)
            except Exception:
                self._active = False
                self.lock_authority = False
            self._checked_at = now
            self._future = None
        if (self._future is None
                and now - self._checked_at >= self.cache_seconds):
            self._future = self._executor.submit(self.activity_probe)
        self.locked = self._session_locked or bool(self.lock_probe(self.runtime, self.wayland_socket))
        return (self._active and not self.locked
                and now - self._checked_at <= max(1.0, self.cache_seconds * 4))

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
            max_workers=1, thread_name_prefix='oldbook-shortcuts')
        self._owns_executor = executor is None
        socket_path = getattr(liveness, 'path', None)
        self.loading_probe = loading_probe or (
            (lambda: _focused_output_context(socket_path)) if socket_path else None)
        self.metadata_executor = metadata_executor or ThreadPoolExecutor(
            max_workers=1, thread_name_prefix='oldbook-output-check')
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



def print_status(runtime, socket_path=None, display=None):
    lease = SessionLease(runtime, socket_path, display=display)
    try:
        record = json.loads(lease.status_path.read_text())
    except (OSError, ValueError) as error:
        raise RuntimeError('no shortcut service status for this display') from error
    process = record.get('process') if isinstance(record, dict) else None
    live = False
    if isinstance(process, dict):
        live = process == _process_identity(process.get('pid'))
    record['live'] = live and record.get('state') != 'stopped'
    if not record['live'] and record.get('state') != 'stopped':
        record['recorded_state'] = record.get('state')
        record['state'] = 'stale'
    print(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True))
