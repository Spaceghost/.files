"""Authenticate gated PID-namespace init writers and prove their completion.

No executable names, PID files, or numeric-PID signals confer authority here.
Callers own radio blocking, exclusive locks, and durable journal transitions.
The process-pidfd completion proof is documented in ORPHAN-RECOVERY.md against
Linux v6.12 pid_namespace.c:zap_pid_ns_processes, exit.c:exit_notify, and
pidfs.c:pidfd_poll. Deployment still requires the isolated kernel fault proof.
"""
from pathlib import Path
import errno
import math
import os
import re
import select
import signal
import time

_PROC = Path('/proc')
_TAG = re.compile(r'[a-z][a-z-]{0,63}', re.ASCII)
_BOOT = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', re.ASCII)


class WriterError(RuntimeError):
    """Identity or completion is unproved; the caller must retain ownership."""


def _namespace_valid(value):
    return (type(value) is dict and set(value) == {'dev', 'ino'}
            and type(value['dev']) is int and 1 <= value['dev'] < 1 << 63
            and type(value['ino']) is int and 1 <= value['ino'] < 1 << 63)


def validate_writer(record):
    """Reject non-JSON types, extra authority, and contradictory init records."""
    if (type(record) is not dict
            or set(record) != {'pid', 'start_time', 'pidns', 'nspid', 'operation'}
            or type(record['pid']) is not int or not 2 <= record['pid'] < 1 << 63
            or type(record['start_time']) is not int or not 1 <= record['start_time'] < 1 << 63
            or not _namespace_valid(record['pidns'])
            or type(record['nspid']) is not int or record['nspid'] != 1
            or type(record['operation']) is not str or not _TAG.fullmatch(record['operation'])):
        raise WriterError('invalid writer identity record')


def namespace_id(path):
    """Use nsfs device/inode identity, following its kernel namespace link."""
    info = os.stat(path)
    return {'dev': info.st_dev, 'ino': info.st_ino}


def _read(path, limit, *, dir_fd=None):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=dir_fd)
    with os.fdopen(descriptor, 'rb') as stream:
        content = stream.read(limit + 1)
    if len(content) > limit:
        raise WriterError('writer metadata exceeds size limit')
    try:
        return content.decode('ascii')
    except UnicodeDecodeError:
        raise WriterError('invalid writer metadata encoding') from None


def current_context():
    """Reject a /proc mount exposing numeric PIDs from an ancestor namespace."""
    try:
        observer = namespace_id(_PROC / 'self/ns/pid')
        if (os.readlink(_PROC / 'self') != str(os.getpid())
                or namespace_id(_PROC / '1/ns/pid') != observer):
            raise WriterError('inconsistent observer proc PID view')
        boot = _read(_PROC / 'sys/kernel/random/boot_id', 64).strip()
        if not _BOOT.fullmatch(boot):
            raise WriterError('invalid boot identity')
        return {'boot_id': boot, 'observer_pidns': observer,
                'target_netns': namespace_id(_PROC / 'self/ns/net')}
    except OSError as error:
        raise WriterError('cannot establish observer process context') from error


def _start_time(directory, pid):
    content = _read('stat', 8192, dir_fd=directory)
    prefix, separator, rest = content.rpartition(') ')
    fields = rest.split()
    if (not separator or not prefix.startswith(str(pid) + ' (') or len(fields) < 20
            or not re.fullmatch(r'[0-9]+', fields[19]) or int(fields[19]) <= 0):
        raise WriterError('invalid writer start time metadata')
    return int(fields[19])


def _init_identity(directory, pid):
    status = _read('status', 65536, dir_fd=directory)
    lines = [line for line in status.splitlines() if line.startswith('NSpid:')]
    if len(lines) != 1:
        raise WriterError('missing or ambiguous writer NSpid')
    fields = lines[0].split()[1:]
    if (len(fields) < 2 or any(not re.fullmatch(r'[1-9][0-9]*', item) for item in fields)
            or int(fields[0]) != pid or int(fields[-1]) != 1):
        raise WriterError('writer is not an observed private namespace init')
    result = {}
    for name in ('pid', 'net'):
        info = os.stat('ns/' + name, dir_fd=directory)
        result[name] = {'dev': info.st_dev, 'ino': info.st_ino}
    return result


def _ready(pidfd):
    return bool(select.select([pidfd], [], [], 0)[0])


def capture_writer(pid, pidfd, operation):
    """Capture an init while its caller-owned process pidfd and gate are held.

    The caller must have opened this flags=0 pidfd for pid and keep the execution
    gate closed until the returned record is durable. Never close that pidfd.
    """
    if (type(pid) is not int or pid <= 1 or type(pidfd) is not int or pidfd < 0
            or type(operation) is not str or not _TAG.fullmatch(operation)):
        raise WriterError('invalid writer capture arguments')
    context = current_context()
    directory = None
    try:
        if _ready(pidfd):
            raise WriterError('writer exited before registration')
        directory = os.open(_PROC / str(pid), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        start = _start_time(directory, pid)
        identity = _init_identity(directory, pid)
        if (identity['pid'] == context['observer_pidns']
                or identity['net'] != context['target_netns'] or _ready(pidfd)):
            raise WriterError('writer namespace identity changed during registration')
        record = {'pid': pid, 'start_time': start, 'pidns': identity['pid'],
                  'nspid': 1, 'operation': operation}
        validate_writer(record)
        return record
    except OSError as error:
        raise WriterError('cannot capture writer identity') from error
    finally:
        if directory is not None:
            os.close(directory)


def _checkpoint(deadline, check):
    check()
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise WriterError('writer drain deadline expired')
    return remaining


def drain_writer(record, *, boot_id, observer_pidns, target_netns, deadline,
                 check=lambda: None):
    """Return absent/reused/dead/killed only after original init completion.

    Open a process pidfd first (flags=0, never PIDFD_THREAD). In the verified
    observer PID view, readiness proves the original init completed: the handle
    either names that init, or names a replacement whose existence already
    proves the original PID was recycled after init teardown. The same reasoning
    makes ESRCH from pidfd_open and a verified changed start time sufficient.
    Missing /proc metadata alone is never a completion proof.

    A matching live init is killed only through this owned pidfd. Kernel init
    teardown precedes pidfd readiness, including detached/nested descendants.
    Wait in at most 25ms intervals and never waitpid an unrelated process.
    """
    validate_writer(record)
    if (type(boot_id) is not str or not _BOOT.fullmatch(boot_id)
            or not _namespace_valid(observer_pidns) or not _namespace_valid(target_netns)
            or type(deadline) not in (int, float) or not math.isfinite(deadline)):
        raise WriterError('invalid writer recovery context')
    expected = {'boot_id': boot_id, 'observer_pidns': observer_pidns,
                'target_netns': target_netns}
    if current_context() != expected:
        raise WriterError('writer recovery boot or namespace context changed')
    if record['pidns'] == observer_pidns:
        raise WriterError('recorded writer is not in a private PID namespace')
    _checkpoint(deadline, check)
    pidfd = directory = None
    try:
        try:
            pidfd = os.pidfd_open(record['pid'], 0)
        except OverflowError as error:
            raise WriterError('writer PID is outside the kernel PID range') from error
        except OSError as error:
            if error.errno == errno.ESRCH:
                return 'absent'
            raise
        if _ready(pidfd):
            return 'dead'
        try:
            directory = os.open(_PROC / str(record['pid']),
                                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
            start = _start_time(directory, record['pid'])
            if start != record['start_time']:
                return 'reused'
            identity = _init_identity(directory, record['pid'])
        except OSError:
            if _ready(pidfd):
                return 'dead'
            raise
        if identity['pid'] != record['pidns'] or identity['net'] != target_netns:
            raise WriterError('matching writer start time has contradictory namespace identity')
        _checkpoint(deadline, check)
        if _ready(pidfd):
            return 'dead'
        try:
            signal.pidfd_send_signal(pidfd, signal.SIGKILL, None, 0)
        except OSError:
            if _ready(pidfd):
                return 'dead'
            raise
        while True:
            remaining = _checkpoint(deadline, check)
            if select.select([pidfd], [], [], min(remaining, 0.025))[0]:
                return 'killed'
    except OSError as error:
        raise WriterError('cannot prove writer completion') from error
    finally:
        try:
            if directory is not None:
                os.close(directory)
        finally:
            if pidfd is not None:
                os.close(pidfd)
