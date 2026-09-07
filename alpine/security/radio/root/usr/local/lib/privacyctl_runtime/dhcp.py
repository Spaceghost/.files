"""One foreground DHCP client with authenticated, bounded hook transport.

Only the owner calls this object, from the persistent thread that creates it.
Failures are returned to that owner so it can block radios BEFORE stop().
This module never configures interfaces, routes, resolvers or firewall rules.
"""
from collections import deque
from dataclasses import dataclass
import fcntl
import json
import os
from pathlib import Path
import select
import selectors
import signal
import socket
import stat
import struct
import subprocess
import threading
import time

from .lease import Lease
from .launch import GENERATION, INTERFACE, context_fd, executable, process_start

LAUNCHER = '/usr/local/libexec/privacyctl-dhcp-launch'
HOOK = '/usr/local/libexec/privacyctl-dhcp-event'
UDHCPC = '/sbin/udhcpc'
ACQUIRE_TIMEOUT = 20
HOOK_TIMEOUT = 12
READY_TIMEOUT = 5
STOP_TIMEOUT = 3
MAX_FRAME = 8192
MAX_PEERS = 8
YES = b'{"ok":true}'
NO = b'{"ok":false}'


def boottime():
    return time.clock_gettime(time.CLOCK_BOOTTIME)


class DHCPError(RuntimeError):
    pass


@dataclass(frozen=True)
class LeaseEvent:
    event_id: int
    kind: str
    received_at: float
    lease: Lease


@dataclass(frozen=True)
class Failure:
    reason: str


@dataclass
class _Peer:
    socket: socket.socket
    pid: int
    deadline: float
    event: LeaseEvent | None = None


def _private_directory(path):
    path = Path(path)
    if not path.is_absolute():
        raise DHCPError('DHCP runtime directory must be absolute')
    # Runtime ancestors must not let another user replace the private tree.
    for parent in path.parents:
        info = parent.lstat()
        sticky_root = info.st_uid == 0 and bool(info.st_mode & stat.S_ISVTX)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != 0
                or (info.st_mode & 0o022 and not sticky_root)):
            raise DHCPError('unsafe DHCP runtime ancestor')
    path.mkdir(mode=0o700, exist_ok=True)
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    info = os.fstat(descriptor)
    if info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o700:
        os.close(descriptor)
        raise DHCPError('DHCP runtime directory must be root-owned mode 0700')
    return descriptor


class DHCPManager:
    def __init__(self, runtime, *, launcher=LAUNCHER, hook=HOOK, udhcpc=UDHCPC,
                 journal=None):
        """Explicit implementation paths are for trusted Python test harnesses.

        Neither service requests nor environment variables supply these values.
        The production service uses the fixed installed defaults.
        """
        self.runtime = Path(runtime)
        self.launcher, self.hook, self.udhcpc = launcher, hook, udhcpc
        self.journal = journal
        self._journal_writer = False
        self._lifetime = False
        self._closed = False
        self.phase = 'idle'
        self.socket_path = ''
        self._identity = {}
        self._process = None
        self._launcher_fd = None
        self._client_fd = None
        self._directory = None
        self._lock = None
        self._listener = None
        self._socket_identity = None
        self._selector = selectors.DefaultSelector()
        self._peers = {}
        self._pending = {}
        self._output = deque()
        self._expiry = None
        self._acquire_deadline = None
        self._ready_deadline = None
        self._event_id = 0
        self._generation = None
        self._interface = None
        self._thread = None

    @property
    def active(self):
        return self._process is not None

    @property
    def identity(self):
        return dict(self._identity)

    @property
    def expiry(self):
        return self._expiry

    def _same_thread(self):
        if self._closed:
            raise DHCPError('DHCP manager is closed')
        if self._thread is not None and self._thread != threading.get_ident():
            raise DHCPError('DHCP manager must remain on its persistent owner thread')

    def _acquire(self):
        self._same_thread()
        if os.geteuid() != 0:
            raise DHCPError('DHCP ownership requires root')
        if self._lock is not None:
            return
        directory = lock = None
        try:
            directory = _private_directory(self.runtime)
            lock = os.open('dhcp.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW |
                           os.O_NONBLOCK | os.O_CLOEXEC,
                           0o600, dir_fd=directory)
            info = os.fstat(lock)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
                raise DHCPError('unsafe DHCP owner lock')
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._directory, self._lock = directory, lock
            directory = lock = None
            self._thread = threading.get_ident()
        except OSError as error:
            raise DHCPError('DHCP ownership acquisition failed: ' + str(error)) from error
        finally:
            if lock is not None:
                os.close(lock)
            if directory is not None:
                os.close(directory)

    def acquire(self):
        """Idempotently hold ownership until close(), without exposing readiness.

        Production acquires guardian, owner, then DHCP ownership before orphan
        recovery. stop() retains this explicit lifetime lock across generations.
        """
        self._acquire()
        self._lifetime = True

    def _release_ownership(self):
        for name in ('_lock', '_directory'):
            descriptor = getattr(self, name)
            if descriptor is not None:
                os.close(descriptor)
                setattr(self, name, None)

    def close(self):
        """Terminal, idempotent close; failed stop retains handles and ownership."""
        if self._closed:
            return
        self.stop()
        self._selector.close()
        self._release_ownership()
        self._lifetime = False
        self._closed = True

    def start(self, generation, interface):
        self._same_thread()
        if (self.active or self._listener is not None or self._client_fd is not None
                or self._launcher_fd is not None or self._journal_writer):
            raise DHCPError('a DHCP generation is already active')
        if os.geteuid() != 0:
            raise DHCPError('DHCP ownership requires root')
        if (not isinstance(generation, str) or not GENERATION.fullmatch(generation)
                or not isinstance(interface, str) or not INTERFACE.fullmatch(interface)):
            raise DHCPError('invalid DHCP generation or interface')
        self._thread = threading.get_ident()
        self._generation, self._interface = generation, interface
        self._output.clear()
        self._identity = {}
        self._expiry = None
        self.socket_path = str(self.runtime / ('dhcp-' + generation + '.sock'))
        if len(os.fsencode(self.socket_path)) > 107:
            raise DHCPError('DHCP event socket path is too long')
        context = None
        try:
            for path in (self.launcher, self.hook, self.udhcpc):
                executable(path)
            self._acquire()
            self._listener = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
            self._listener.bind(self.socket_path)  # Exclusive; never unlink another owner.
            os.chmod(self.socket_path, 0o600)
            info = os.lstat(self.socket_path)
            self._socket_identity = (info.st_dev, info.st_ino)
            self._listener.listen(MAX_PEERS)
            self._listener.setblocking(False)
            self._selector.register(self._listener, selectors.EVENT_READ, 'listener')
            now = boottime()
            self._acquire_deadline = now + ACQUIRE_TIMEOUT
            self._ready_deadline = now + READY_TIMEOUT
            self.phase = 'starting'
            context = context_fd({'version': 1, 'generation': generation, 'interface': interface,
                                  'owner_pid': os.getpid(), 'owner_start': process_start(os.getpid()),
                                  'socket': self.socket_path, 'launcher': str(self.launcher),
                                  'hook': str(self.hook), 'udhcpc': str(self.udhcpc)})
            self._process = subprocess.Popen([str(self.launcher), 'outer', str(context)],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                pass_fds=(context,), start_new_session=True, cwd='/',
                env={'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C'})
            self._launcher_fd = os.pidfd_open(self._process.pid, 0)
            self._identity = {'launcher_pid': self._process.pid,
                              'launcher_start': process_start(self._process.pid),
                              'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
            self._selector.register(self._launcher_fd, selectors.EVENT_READ, 'launcher')
        except (OSError, ValueError, DHCPError) as error:
            self.stop()
            raise DHCPError('DHCP launch failed: ' + str(error)) from error
        finally:
            if context is not None:
                os.close(context)

    def _drop(self, peer):
        descriptor = peer.socket.fileno()
        try:
            self._selector.unregister(peer.socket)
        except (KeyError, ValueError):
            pass
        self._peers.pop(descriptor, None)
        if peer.event is not None:
            self._pending.pop(peer.event.event_id, None)
        peer.socket.close()

    def _fail(self, reason):
        if self.phase == 'failed':
            return
        self.phase = 'failed'
        self._expiry = None
        self._output.clear()
        self._output.append(Failure(reason))
        for peer in list(self._peers.values()):
            self._drop(peer)

    def _peer_allowed(self, pid):
        try:
            namespace = os.readlink('/proc/' + str(pid) + '/ns/pid')
            if self.phase == 'starting':
                fields = Path('/proc/' + str(pid) + '/stat').read_text().rsplit(')', 1)[1].split()
                return (int(fields[1]) == self._process.pid and namespace == os.readlink(
                    '/proc/' + str(self._process.pid) + '/ns/pid_for_children'))
            return namespace == self._identity.get('namespace')
        except (OSError, ValueError, IndexError):
            return False

    def _accept(self):
        for _ in range(MAX_PEERS):
            try:
                connection, _address = self._listener.accept()
            except BlockingIOError:
                return
            connection.setblocking(False)
            pid, uid, _gid = struct.unpack('3i', connection.getsockopt(
                socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i')))
            if uid != 0 or not self._peer_allowed(pid) or len(self._peers) >= MAX_PEERS:
                connection.close()
                continue
            peer = _Peer(connection, pid, boottime() + HOOK_TIMEOUT)
            self._peers[connection.fileno()] = peer
            self._selector.register(connection, selectors.EVENT_READ, peer)

    def _ready(self, peer, fields):
        if fields != {'interface': self._interface} or self._client_fd is not None:
            raise ValueError('invalid client readiness fields')
        descriptor = os.pidfd_open(peer.pid, 0)
        try:
            status = Path('/proc/' + str(peer.pid) + '/status').read_text()
            nspid = next(line for line in status.splitlines() if line.startswith('NSpid:')).split()[1:]
            namespace = os.readlink('/proc/' + str(peer.pid) + '/ns/pid')
            if (int(nspid[-1]) != 1 or namespace == os.readlink('/proc/self/ns/pid')
                    or not self._peer_allowed(peer.pid)
                    or select.select([descriptor], [], [], 0)[0]):
                raise ValueError('invalid namespace init identity')
            self._identity.update(client_pid=peer.pid, client_start=process_start(peer.pid),
                                  namespace=namespace)
            self._client_fd = descriptor
            descriptor = None
            self._selector.register(self._client_fd, selectors.EVENT_READ, 'client')
            # Capture all identity handles before allowing PID1 to exec udhcpc.
            if self.journal is not None:
                # A failed fsync may follow a successful rename. Keep the handle
                # and attempted slot until death and durable completion reconcile it.
                self._journal_writer = True
                try:
                    self.journal.writer_started('dhcp', peer.pid, self._client_fd, 'dhcp-client')
                except Exception as error:
                    raise DHCPError('DHCP writer registration failed: ' + str(error)) from error
            if peer.socket.send(YES) != len(YES):
                raise OSError('short readiness acknowledgment')
            self.phase = 'acquiring'
            self._drop(peer)
        finally:
            if descriptor is not None:
                os.close(descriptor)

    def _receive(self, peer):
        try:
            packet, _ancillary, flags, _address = peer.socket.recvmsg(MAX_FRAME)
        except BlockingIOError:
            return
        except OSError:
            self._fail('DHCP hook transport failed')
            return
        if peer.event is not None:
            self._fail('DHCP hook exited or sent extra data before acknowledgment')
            return
        try:
            if not packet or flags & socket.MSG_TRUNC:
                raise ValueError('missing or oversized event packet')
            frame = json.loads(packet)
            if (not isinstance(frame, dict) or set(frame) != {'version', 'generation', 'event', 'fields'}
                    or type(frame['version']) is not int or frame['version'] != 1
                    or not isinstance(frame['event'], str) or not isinstance(frame['fields'], dict)):
                raise ValueError('invalid event envelope')
            if frame['generation'] != self._generation:
                self._drop(peer)
                return
            kind, fields = frame['event'], frame['fields']
            if self.phase == 'starting':
                if kind != 'ready':
                    raise ValueError('expected readiness before DHCP events')
                self._ready(peer, fields)
                return
            if kind == 'deconfig' and self.phase == 'acquiring':
                if fields != {'interface': self._interface}:
                    raise ValueError('invalid initial deconfiguration')
                if peer.socket.send(YES) != len(YES):
                    raise OSError('short startup event acknowledgment')
                self._drop(peer)
                return
            if kind in ('deconfig', 'nak', 'leasefail'):
                self._fail('DHCP authorization lost: ' + kind)
                return
            if (kind, self.phase) not in (('bound', 'acquiring'), ('renew', 'bound')) or self._pending:
                raise ValueError('unexpected lease event transition')
            lease = Lease.from_event(fields, expected_interface=self._interface)
            self._event_id += 1
            event = LeaseEvent(self._event_id, kind, boottime(), lease)
            peer.event = event
            self._pending[event.event_id] = peer
            self._output.append(event)
        except (OSError, ValueError, UnicodeError, KeyError, TypeError, StopIteration,
                RecursionError, DHCPError) as error:
            self._fail('invalid DHCP event: ' + str(error))

    def _deadlines(self):
        now = boottime()
        if self.phase == 'failed' or not self.active:
            return
        if self._expiry is not None and now >= self._expiry:
            self._fail('DHCP lease expired')
        elif self.phase in ('starting', 'acquiring') and now >= self._acquire_deadline:
            self._fail('DHCP acquisition deadline exceeded')
        elif self.phase == 'starting' and now >= self._ready_deadline:
            self._fail('DHCP readiness deadline exceeded')
        elif any(now >= peer.deadline for peer in self._peers.values()):
            self._fail('DHCP hook deadline exceeded')

    def poll(self, timeout=0):
        self._same_thread()
        if not isinstance(timeout, (int, float)) or not 0 <= timeout <= 20:
            raise DHCPError('invalid poll timeout')
        self._deadlines()
        if self.active and self.phase != 'failed':
            deadlines = [peer.deadline for peer in self._peers.values()]
            if self.phase in ('starting', 'acquiring'):
                deadlines.append(self._acquire_deadline)
            if self.phase == 'starting':
                deadlines.append(self._ready_deadline)
            if self._expiry is not None:
                deadlines.append(self._expiry)
            delay = min(timeout, max(0, min(deadlines) - boottime())) if deadlines else timeout
            try:
                ready = self._selector.select(0 if self._output else delay)
                # Death takes priority over applying queued hook events.
                if any(key.data in ('launcher', 'client') for key, _mask in ready):
                    self._fail('DHCP client or launcher exited')
                else:
                    for key, _mask in ready:
                        if self.phase == 'failed':
                            break
                        if key.data == 'listener':
                            self._accept()
                        elif isinstance(key.data, _Peer) and key.data.socket.fileno() >= 0:
                            self._receive(key.data)
            except (OSError, ValueError) as error:
                self._fail('DHCP event polling failed: ' + str(error))
            self._deadlines()
        result = list(self._output)
        self._output.clear()
        return result

    def reply(self, event_id, accepted):
        self._same_thread()
        self._deadlines()
        peer = self._pending.get(event_id)
        if peer is None or self.phase == 'failed':
            return False
        if accepted is not True:
            self._fail('DHCP lease application rejected')
            return False
        event = peer.event
        if boottime() >= event.received_at + event.lease.lease_seconds:
            self._fail('DHCP lease expired during application')
            return False
        try:
            if peer.socket.send(YES) != len(YES):
                raise OSError('short lease acknowledgment')
        except OSError:
            self._fail('DHCP hook acknowledgment failed')
            return False
        self._expiry = event.received_at + event.lease.lease_seconds
        self.phase = 'bound'
        self._drop(peer)
        return True

    def stop(self):
        """Owner must block first. Retain handles/lock if teardown cannot finish."""
        self._same_thread()
        self._generation = None
        for descriptor in (self._launcher_fd, self._client_fd):
            if descriptor is not None:
                try:
                    signal.pidfd_send_signal(descriptor, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        if self._process is not None and self._launcher_fd is None:
            # A just-created direct child remains unreaped, so its PID is reserved.
            self._process.kill()
        deadline = time.monotonic() + STOP_TIMEOUT
        for descriptor in (self._launcher_fd, self._client_fd):
            if descriptor is not None and not select.select(
                    [descriptor], [], [], max(0, deadline - time.monotonic()))[0]:
                self.phase = 'failed'
                raise DHCPError('DHCP namespace termination deadline exceeded')
        if self._process is not None:
            try:
                self._process.wait(timeout=max(.01, deadline - time.monotonic()))
            except subprocess.TimeoutExpired as error:
                self.phase = 'failed'
                raise DHCPError('DHCP launcher reaping deadline exceeded') from error
        if self._journal_writer:
            if self._client_fd is None:
                self.phase = 'failed'
                raise DHCPError('DHCP writer has no retained init completion handle')
            try:
                self.journal.writer_finished('dhcp')
            except Exception as error:
                self.phase = 'failed'
                raise DHCPError('DHCP writer completion failed: ' + str(error)) from error
            self._journal_writer = False
        for peer in list(self._peers.values()):
            self._drop(peer)
        self._selector.close()
        self._selector = selectors.DefaultSelector()
        if self._listener is not None:
            self._listener.close()
            self._listener = None
        if self._socket_identity is not None:
            try:
                info = os.lstat(self.socket_path)
                if (info.st_dev, info.st_ino) == self._socket_identity:
                    os.unlink(self.socket_path)
            except FileNotFoundError:
                pass
        for name in ('_launcher_fd', '_client_fd'):
            descriptor = getattr(self, name)
            if descriptor is not None:
                os.close(descriptor)
                setattr(self, name, None)
        if not self._lifetime:
            self._release_ownership()
        self._socket_identity = None
        self._process = None
        self._output.clear()
        self._pending.clear()
        self._expiry = None
        self.phase = 'idle'
