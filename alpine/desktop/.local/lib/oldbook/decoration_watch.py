"""Keep decoration geometry current without spawning swaymsg while dragging."""

import json
import select
import socket
import struct
import threading
import time


_HEADER = struct.Struct('=6sII')
_MAGIC = b'i3-ipc'
_SUBSCRIBE = 2
_GET_TREE = 4
_MODE = (1 << 31) | 2
_SHUTDOWN = (1 << 31) | 6
_MAX_PAYLOAD = 32 * 1024 * 1024


def _send(connection, kind, payload=b''):
    connection.sendall(_HEADER.pack(_MAGIC, len(payload), kind) + payload)


def _receive_exact(connection, size):
    result = bytearray()
    while len(result) < size:
        part = connection.recv(size - len(result))
        if not part:
            raise ConnectionError('Sway IPC disconnected')
        result.extend(part)
    return bytes(result)


def _receive(connection):
    magic, size, kind = _HEADER.unpack(_receive_exact(connection, _HEADER.size))
    if magic != _MAGIC or size > _MAX_PAYLOAD:
        raise ValueError('invalid Sway IPC frame')
    return kind, _receive_exact(connection, size)


def _geometry(tree):
    """Ignore title churn when deciding whether floating geometry is moving."""
    rect = tree.get('rect', {})
    return (tree.get('id'), tuple(rect.get(key) for key in ('x', 'y', 'width', 'height')),
            tuple(_geometry(child) for child in tree.get('nodes', [])),
            tuple(_geometry(child) for child in tree.get('floating_nodes', [])))


class TreeWatch:
    """Deliver changed trees on one worker thread until close() or shutdown.

    Callers marshal ``deliver(tree)`` onto their UI thread. A persistent request
    socket handles geometry polling because Sway emits no move events during a
    floating drag; a second socket wakes the worker for semantic changes. An
    unchanged tree is never delivered twice, and only one request is in flight.
    """

    # Silent pointer drags still need polling: Sway sends no geometry events.
    # A quiet float is sampled within one 60 Hz frame; movement then keeps the
    # full 120 Hz budget until its brief settling tail has finished.
    ATTACHED_INTERVAL = 1 / 120
    QUIET_ATTACHED_INTERVAL = 1 / 60
    MOTION_GRACE = 0.250
    IDLE_INTERVAL = 0.750
    RECONNECT_DELAY = 0.250

    def __init__(self, path, deliver):
        self.path = str(path)
        self.deliver = deliver
        self._attached = False
        self._motion_until = 0
        self._stopped = threading.Event()
        self._lock = threading.Lock()
        self._connections = set()
        self._thread = None
        self._wake_read = None
        self._wake_write = None

    def start(self):
        with self._lock:
            if self._thread is not None or self._stopped.is_set():
                return
            self._wake_read, self._wake_write = socket.socketpair()
            self._wake_read.setblocking(False)
            self._wake_write.setblocking(False)
            self._thread = threading.Thread(
                target=self._run, name='oldbook-decoration-ipc', daemon=True)
            self._thread.start()

    def set_attached(self, attached):
        with self._lock:
            attached = bool(attached)
            if attached == self._attached:
                return
            self._attached = attached
            if attached:
                self._motion_until = time.monotonic() + self.MOTION_GRACE
            self._wake()

    def close(self):
        self._stopped.set()
        with self._lock:
            self._wake()
            connections = tuple(self._connections)
            thread = self._thread
        # Interrupt a blocked GET_TREE read as well as an idle select().
        for connection in connections:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2)

    def _wake(self):
        if self._wake_write is not None:
            try:
                self._wake_write.send(b'!')
            except (BlockingIOError, OSError):
                pass

    def _connect(self):
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.settimeout(1)
        with self._lock:
            if self._stopped.is_set():
                connection.close()
                raise ConnectionError('watch closed')
            self._connections.add(connection)
        try:
            connection.connect(self.path)
            return connection
        except OSError:
            self._disconnect(connection)
            raise

    def _disconnect(self, connection):
        if connection is None:
            return
        with self._lock:
            self._connections.discard(connection)
        connection.close()

    def _run(self):
        previous = None
        geometry = None
        try:
            while not self._stopped.is_set():
                request = subscriber = None
                try:
                    request = self._connect()
                    subscriber = self._connect()
                    _send(subscriber, _SUBSCRIBE,
                          b'["window","workspace","output","mode","shutdown"]')
                    kind, body = _receive(subscriber)
                    response = json.loads(body)
                    if (kind != _SUBSCRIBE or not isinstance(response, dict)
                            or not response.get('success')):
                        raise ValueError('Sway rejected decoration subscription')
                    next_refresh = 0
                    suspended = False
                    while not self._stopped.is_set():
                        if not suspended and time.monotonic() >= next_refresh:
                            started = time.monotonic()
                            _send(request, _GET_TREE)
                            kind, body = _receive(request)
                            if kind != _GET_TREE:
                                raise ValueError('unexpected Sway IPC response')
                            if body != previous:
                                tree = json.loads(body)
                                if not isinstance(tree, dict):
                                    raise ValueError('Sway tree is not an object')
                                latest_geometry = _geometry(tree)
                                if latest_geometry != geometry:
                                    geometry = latest_geometry
                                    with self._lock:
                                        self._motion_until = time.monotonic() + self.MOTION_GRACE
                                if not self._stopped.is_set():
                                    self.deliver(tree)
                                    previous = body
                            with self._lock:
                                interval = (self.ATTACHED_INTERVAL
                                            if time.monotonic() < self._motion_until
                                            else self.QUIET_ATTACHED_INTERVAL)
                                if not self._attached:
                                    interval = self.IDLE_INTERVAL
                            # Account for IPC/decoding work inside the budget.
                            # Late replies skip the wait, never queue catch-up
                            # requests or pay a second full interval afterward.
                            next_refresh = max(started + interval, time.monotonic())
                        if suspended:
                            # The carousel owns pointer and keyboard input; its
                            # covered captions cannot be dragged. Reserve this
                            # compositor time for the overlay until mode exit.
                            next_refresh = time.monotonic() + self.IDLE_INTERVAL
                        ready, _, _ = select.select(
                            [subscriber, self._wake_read], [], [],
                            max(0, next_refresh - time.monotonic()))
                        if self._wake_read in ready:
                            while True:
                                try:
                                    if not self._wake_read.recv(4096):
                                        break
                                except BlockingIOError:
                                    break
                            next_refresh = 0
                        if subscriber in ready:
                            # Drain bursts into one refresh, but never let an
                            # event flood starve the request socket.
                            for _ in range(64):
                                kind, body = _receive(subscriber)
                                if kind == _SHUTDOWN:
                                    self._stopped.set()
                                    break
                                if not kind & (1 << 31):
                                    raise ValueError('unexpected subscription frame')
                                if kind == _MODE:
                                    suspended = json.loads(body).get('change') == 'window-switcher'
                                    if not suspended:
                                        with self._lock:
                                            self._motion_until = time.monotonic() + self.MOTION_GRACE
                                if not select.select([subscriber], [], [], 0)[0]:
                                    break
                            next_refresh = 0
                except (OSError, ValueError):
                    # A compositor restart may temporarily leave a missing or
                    # disconnected socket. Retry without creating a busy loop.
                    pass
                finally:
                    self._disconnect(request)
                    self._disconnect(subscriber)
                self._stopped.wait(self.RECONNECT_DELAY)
        finally:
            self._stopped.set()
            with self._lock:
                for connection in (self._wake_read, self._wake_write):
                    if connection is not None:
                        connection.close()
                self._wake_read = self._wake_write = None
