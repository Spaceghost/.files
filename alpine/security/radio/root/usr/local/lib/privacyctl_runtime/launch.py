"""Private PID-namespace launcher. Never accepts executable paths from CLI/env."""
import ctypes
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import socket
import stat
import struct
import sys
import time

UNSHARE = '/usr/bin/unshare'
SEALS = fcntl.F_SEAL_SEAL | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_GROW | fcntl.F_SEAL_WRITE
GENERATION = re.compile(r'[0-9a-f]{32}')
INTERFACE = re.compile(r'[A-Za-z0-9_.-]{1,15}')


def process_start(pid):
    text = Path('/proc/' + str(pid) + '/stat').read_text()
    return int(text.rsplit(')', 1)[1].split()[19])


def executable(path):
    """The constructor supplies trusted paths; require immutable root files."""
    path = Path(path)
    if not path.is_absolute():
        raise ValueError('implementation path must be absolute')
    resolved = path.resolve(strict=True)
    for original in (path, resolved):
        for parent in original.parents:
            info = parent.lstat()
            sticky_root = info.st_uid == 0 and bool(info.st_mode & stat.S_ISVTX)
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != 0
                    or (info.st_mode & 0o022 and not sticky_root)):
                raise ValueError('unsafe implementation path ancestor')
    info = resolved.stat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
            or info.st_mode & 0o022 or not info.st_mode & 0o111):
        raise ValueError('implementation file must be root-owned and executable')
    return str(path)


def context_fd(values):
    descriptor = os.memfd_create('privacyctl-dhcp-launch', os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    try:
        os.fchmod(descriptor, 0o600)
        data = json.dumps(values, separators=(',', ':')).encode()
        if len(data) > 16384 or os.write(descriptor, data) != len(data):
            raise ValueError('invalid launch context size')
        fcntl.fcntl(descriptor, fcntl.F_ADD_SEALS, SEALS)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def read_context(descriptor):
    info = os.fstat(descriptor)
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
            or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 16384
            or fcntl.fcntl(descriptor, fcntl.F_GET_SEALS) & SEALS != SEALS):
        raise ValueError('launch context must be sealed, root-owned and private')
    try:
        data = json.loads(os.pread(descriptor, 16385, 0))
    except RecursionError as error:
        raise ValueError('launch context exceeds JSON nesting bound') from error
    expected = {'version', 'generation', 'interface', 'owner_pid', 'owner_start',
                'socket', 'launcher', 'hook', 'udhcpc'}
    if (not isinstance(data, dict) or set(data) != expected
            or type(data['version']) is not int or data['version'] != 1
            or not isinstance(data['generation'], str)
            or not GENERATION.fullmatch(data['generation'])
            or not isinstance(data['interface'], str)
            or not INTERFACE.fullmatch(data['interface'])
            or type(data['owner_pid']) is not int or data['owner_pid'] <= 1
            or type(data['owner_start']) is not int or data['owner_start'] <= 0
            or not isinstance(data['socket'], str) or not data['socket'].startswith('/')):
        raise ValueError('invalid launch context')
    for key in ('launcher', 'hook', 'udhcpc'):
        executable(data[key])
    return data


def outer(descriptor, data):
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0:  # PR_SET_PDEATHSIG
        raise OSError(ctypes.get_errno(), 'cannot arm owner-death protection')
    if (os.getppid() != data['owner_pid']
            or process_start(data['owner_pid']) != data['owner_start']):
        raise ValueError('owner exited before launch protection was armed')
    os.set_inheritable(descriptor, True)
    os.execv(UNSHARE, [UNSHARE, '--pid', '--fork', '--kill-child=KILL', '--',
                      data['launcher'], 'inner', str(descriptor)])


def clock():
    return time.clock_gettime(time.CLOCK_BOOTTIME)


def inner(descriptor, data):
    if os.getpid() != 1:
        raise ValueError('DHCP client must be the private namespace init')
    deadline = clock() + 5
    with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as peer:
        def remaining():
            value = deadline - clock()
            if value <= 0:
                raise TimeoutError('readiness handshake deadline exceeded')
            peer.settimeout(value)
        remaining()
        peer.connect(data['socket'])
        _pid, uid, _gid = struct.unpack('3i', peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        if uid != 0:
            raise ValueError('owner credentials are not root')
        frame = {'version': 1, 'generation': data['generation'], 'event': 'ready',
                 'fields': {'interface': data['interface']}}
        remaining()
        peer.sendall(json.dumps(frame, separators=(',', ':')).encode())
        remaining()
        if peer.recv(128) != b'{"ok":true}':
            raise ValueError('owner rejected DHCP readiness')
    os.close(descriptor)
    environment = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C',
                   'PRIVACYCTL_EVENT_SOCKET': data['socket'],
                   'PRIVACYCTL_GENERATION': data['generation']}
    os.execve(data['udhcpc'], [data['udhcpc'], '-f', '-n', '-t', '5', '-T', '3',
                             '-i', data['interface'], '-s', data['hook']], environment)


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    try:
        if os.geteuid() != 0 or len(args) != 2 or args[0] not in ('outer', 'inner'):
            raise ValueError('private root launcher requires its inherited context')
        descriptor = int(args[1])
        if descriptor < 3:
            raise ValueError('invalid inherited context descriptor')
        data = read_context(descriptor)
        (outer if args[0] == 'outer' else inner)(descriptor, data)
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print('privacyctl DHCP launcher: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
