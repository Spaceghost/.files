"""Bounded root-only owner transport; caller drives every lifecycle operation."""
from collections import OrderedDict
from dataclasses import dataclass
import errno
import fcntl
import json
import math
import os
from pathlib import Path
import re
import secrets
import socket
import stat
import struct
import time

DEFAULT_RUNTIME = Path('/run/privacyctl')
MAX_REQUEST = 8192
MAX_RESPONSE = 131072
MAX_PEERS = 8
MAX_ACCEPTS = 8
INITIAL_TIMEOUT = 3
MAX_RECENT_NONCES = 1024
_NONCE = re.compile(r'[0-9a-f]{32}\Z')
_PROFILES = frozenset(('shmecklebucket', 'iphone-hotspot'))


class IPCError(RuntimeError):
    pass


class Unavailable(IPCError):
    pass


def _directory(path, *, create=False):
    if not path.is_absolute():
        raise IPCError('owner runtime directory must be absolute')
    for parent in path.parents:
        info = parent.lstat()
        sticky_root = info.st_uid == 0 and bool(info.st_mode & stat.S_ISVTX)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != 0
                or (info.st_mode & 0o022 and not sticky_root)):
            raise IPCError('unsafe owner runtime ancestor')
    if create:
        path.mkdir(mode=0o700, exist_ok=True)
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    info = os.fstat(descriptor)
    if info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o700:
        os.close(descriptor)
        raise IPCError('owner runtime directory must be root-owned mode 0700')
    return descriptor


def _root_peer(connection):
    _pid, uid, _gid = struct.unpack('3i', connection.getsockopt(
        socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i')))
    return uid == 0


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise IPCError('duplicate JSON field')
        result[key] = value
    return result


def _invalid_constant(value):
    raise IPCError('invalid JSON constant')


def _decode(frame):
    try:
        value = json.loads(frame.decode('utf-8'), object_pairs_hook=_pairs,
                           parse_constant=_invalid_constant)
    except (UnicodeError, ValueError, RecursionError) as error:
        raise IPCError('invalid JSON frame') from error
    if not isinstance(value, dict):
        raise IPCError('JSON frame must be an object')
    return value


def _validate_command(command, profile):
    if not isinstance(command, str):
        raise IPCError('invalid command')
    if command == 'connect':
        if not isinstance(profile, str) or profile not in _PROFILES:
            raise IPCError('invalid connection profile')
    elif command not in ('off', 'scan') or profile is not None:
        raise IPCError('invalid command or profile')


def _decode_request(frame):
    value = _decode(frame)
    expected = {'version', 'command', 'nonce'}
    if value.get('command') in ('scan', 'connect'):
        expected.add('fence')
    if value.get('command') == 'connect':
        expected.add('profile')
    if set(value) != expected or type(value.get('version')) is not int or value['version'] != 1:
        raise IPCError('invalid request fields or version')
    nonce = value['nonce']
    if not isinstance(nonce, str) or not _NONCE.fullmatch(nonce):
        raise IPCError('invalid request nonce')
    _validate_command(value['command'], value.get('profile'))
    fence = value.get('fence')
    if fence is not None and (not isinstance(fence, str) or not _NONCE.fullmatch(fence)):
        raise IPCError('invalid off fence')
    return value


class Request:
    def __init__(self, peer, fields, release):
        self.command = fields['command']
        self.profile = fields.get('profile')
        self.nonce = fields['nonce']
        self.fence = fields.get('fence')
        self._peer = peer
        self._release = release

    def alive(self):
        if self._peer is None:
            return False
        try:
            self._peer.recv(1, socket.MSG_PEEK | socket.MSG_DONTWAIT)
        except BlockingIOError:
            return True
        except OSError:
            pass
        # EOF and any additional packet both revoke this one-shot request.
        self.close()
        return False

    def respond(self, ok, result='', error=''):
        if not self.alive():
            return False
        try:
            if type(ok) is not bool or not isinstance(result, str) or not isinstance(error, str):
                return False
            frame = json.dumps(dict(version=1, nonce=self.nonce, ok=ok,
                                    result=result, error=error),
                               ensure_ascii=True, separators=(',', ':')).encode('ascii')
            if len(frame) > MAX_RESPONSE:
                return False
            return self._peer.send(frame, socket.MSG_DONTWAIT | socket.MSG_NOSIGNAL) == len(frame)
        except (OSError, ValueError):
            return False
        finally:
            self.close()

    def close(self):
        peer, self._peer = self._peer, None
        if peer is not None:
            self._release(peer)


@dataclass
class _Peer:
    socket: socket.socket
    deadline: float
    request: Request | None = None


class Server:
    def __init__(self, runtime=DEFAULT_RUNTIME):
        self.runtime = Path(runtime)
        self._directory = None
        self._lock = None
        self._listener = None
        self._socket_identity = None
        self._peers = {}
        self._nonces = OrderedDict()

    def acquire(self):
        """Hold owner exclusivity without publishing command readiness."""
        if self._lock is not None:
            return
        if os.geteuid() != 0:
            raise IPCError('owner transport requires root')
        path = str(self.runtime / 'owner.sock')
        if len(os.fsencode(path)) > 107:
            raise IPCError('owner socket path is too long')
        try:
            self._directory = _directory(self.runtime, create=True)
            self._lock = os.open('owner.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW |
                                 os.O_CLOEXEC | os.O_NONBLOCK, 0o600, dir_fd=self._directory)
            info = os.fstat(self._lock)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
                raise IPCError('unsafe owner lock')
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, ValueError, IPCError) as error:
            self.close()
            raise IPCError('cannot acquire owner transport: ' + str(error)) from error

    def listen(self):
        """Publish only after the caller completes blocked startup recovery."""
        if self._lock is None:
            raise IPCError('owner transport requires acquired ownership')
        if self._listener is not None:
            raise IPCError('owner server already listening')
        path = str(self.runtime / 'owner.sock')
        try:
            self._remove_stale(path)
            self._listener = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
            self._listener.setblocking(False)
            self._listener.bind(path)
            info = os.stat('owner.sock', dir_fd=self._directory, follow_symlinks=False)
            self._socket_identity = (info.st_dev, info.st_ino)
            os.chmod('owner.sock', 0o600, dir_fd=self._directory, follow_symlinks=False)
            self._listener.listen(MAX_PEERS)
        except (OSError, ValueError, IPCError) as error:
            self.close()
            raise IPCError('cannot open owner transport: ' + str(error)) from error

    def open(self):
        """Compatibility entrypoint for callers without a recovery phase."""
        self.acquire()
        self.listen()

    def _remove_stale(self, path):
        try:
            info = os.stat('owner.sock', dir_fd=self._directory, follow_symlinks=False)
        except FileNotFoundError:
            return
        if (not stat.S_ISSOCK(info.st_mode) or info.st_uid != 0
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
            raise IPCError('unsafe existing owner socket')
        with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as probe:
            probe.setblocking(False)
            try:
                probe.connect(path)
            except OSError as error:
                if error.errno != errno.ECONNREFUSED:
                    raise IPCError('existing owner socket is not safely stale') from error
            else:
                raise IPCError('existing owner socket is live')
        current = os.stat('owner.sock', dir_fd=self._directory, follow_symlinks=False)
        if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
            raise IPCError('owner socket changed during stale check')
        os.unlink('owner.sock', dir_fd=self._directory)

    def _drop(self, connection):
        peer = self._peers.pop(connection.fileno(), None)
        if peer is not None and peer.request is not None:
            peer.request._peer = None
        connection.close()

    def poll(self):
        if self._listener is None:
            return []
        now = time.monotonic()
        # Reap before accepting so disconnected request objects cannot fill capacity.
        for peer in list(self._peers.values()):
            if peer.request is not None:
                peer.request.alive()
            elif now >= peer.deadline:
                self._drop(peer.socket)
        for _ in range(MAX_ACCEPTS):
            try:
                connection, _address = self._listener.accept()
            except BlockingIOError:
                break
            except OSError as error:
                raise IPCError('owner accept failed') from error
            connection.setblocking(False)
            try:
                allowed = _root_peer(connection)
            except OSError:
                allowed = False
            if not allowed or len(self._peers) >= MAX_PEERS:
                connection.close()
                continue
            self._peers[connection.fileno()] = _Peer(connection, now + INITIAL_TIMEOUT)
        result = []
        for peer in list(self._peers.values()):
            if peer.request is not None:
                continue
            try:
                frame, _ancillary, flags, _address = peer.socket.recvmsg(MAX_REQUEST)
                if not frame or flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC):
                    raise IPCError('empty or truncated request')
                fields = _decode_request(frame)
                nonce = fields['nonce']
                if nonce in self._nonces:
                    raise IPCError('replayed request nonce')
                self._nonces[nonce] = None
                if len(self._nonces) > MAX_RECENT_NONCES:
                    self._nonces.popitem(last=False)
                peer.request = Request(peer.socket, fields, self._drop)
                if peer.request.alive():
                    result.append(peer.request)
            except BlockingIOError:
                continue
            except (OSError, IPCError):
                self._drop(peer.socket)
        return result

    def close(self):
        for peer in list(self._peers.values()):
            self._drop(peer.socket)
        if self._listener is not None:
            self._listener.close()
            self._listener = None
        if self._directory is not None:
            try:
                info = os.stat('owner.sock', dir_fd=self._directory, follow_symlinks=False)
                if (info.st_dev, info.st_ino) == self._socket_identity:
                    os.unlink('owner.sock', dir_fd=self._directory)
            except OSError:
                pass
            os.close(self._directory)
            self._directory = None
        self._socket_identity = None
        if self._lock is not None:
            os.close(self._lock)
            self._lock = None


def request(command, profile=None, *, runtime=DEFAULT_RUNTIME, timeout=50):
    """Send one operation and return its text, with one deadline for all I/O."""
    _validate_command(command, profile)
    if os.geteuid() != 0:
        raise IPCError('owner transport requires root')
    if (type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0):
        raise IPCError('invalid owner request timeout')
    runtime = Path(runtime)
    path = str(runtime / 'owner.sock')
    if len(os.fsencode(path)) > 107:
        raise IPCError('owner socket path is too long')
    nonce = secrets.token_hex(16)
    fields = dict(version=1, command=command, nonce=nonce)
    if profile is not None:
        fields['profile'] = profile
    deadline = time.monotonic() + timeout

    def remaining():
        duration = deadline - time.monotonic()
        if duration <= 0:
            raise IPCError('owner request timed out')
        return duration

    try:
        directory = _directory(runtime)
        try:
            info = os.stat('owner.sock', dir_fd=directory, follow_symlinks=False)
            if (not stat.S_ISSOCK(info.st_mode) or info.st_uid != 0
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
                raise IPCError('unsafe owner socket')
        finally:
            os.close(directory)
        if command in ('scan', 'connect'):
            from .adapter import Fence
            try:
                fields['fence'] = Fence(runtime).read()
            except RuntimeError as error:
                raise IPCError('cannot read emergency-off fence') from error
        frame = json.dumps(fields, separators=(',', ':')).encode('ascii')
        with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as connection:
            connection.settimeout(remaining())
            connection.connect(path)
            if not _root_peer(connection):
                raise IPCError('owner peer is not root')
            connection.settimeout(remaining())
            if connection.send(frame, socket.MSG_NOSIGNAL) != len(frame):
                raise IPCError('incomplete owner request')
            connection.settimeout(remaining())
            reply, _ancillary, flags, _address = connection.recvmsg(MAX_RESPONSE)
            if not reply or flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC):
                raise IPCError('empty or truncated owner response')
        value = _decode(reply)
        if (set(value) != {'version', 'nonce', 'ok', 'result', 'error'}
                or type(value.get('version')) is not int or value['version'] != 1
                or value.get('nonce') != nonce or type(value.get('ok')) is not bool
                or not isinstance(value.get('result'), str)
                or not isinstance(value.get('error'), str)):
            raise IPCError('invalid owner response fields')
        if not value['ok']:
            raise IPCError(value['error'] or 'owner request failed')
        return value['result']
    except (FileNotFoundError, ConnectionRefusedError) as error:
        raise Unavailable('owner service is unavailable') from error
    except (OSError, ValueError) as error:
        raise IPCError('owner request failed: ' + str(error)) from error
