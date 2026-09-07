"""Bounded DHCP event forwarding; this hook never applies network state."""
import json
import os
from pathlib import Path
import re
import socket
import stat
import struct
import sys
import time

FIELDS = frozenset(('interface', 'ip', 'subnet', 'mask', 'router', 'dns', 'lease', 'serverid'))
EVENTS = frozenset(('bound', 'renew', 'deconfig', 'nak', 'leasefail'))
MAX_FRAME = 8192
# Includes the ten-second lease application plus authentication and reply time.
TIMEOUT = 12


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    try:
        started = time.clock_gettime(time.CLOCK_BOOTTIME)
        if os.geteuid() != 0 or len(args) != 1 or args[0] not in EVENTS:
            raise ValueError('unsupported private DHCP event')
        generation = os.environ.get('PRIVACYCTL_GENERATION', '')
        endpoint = os.environ.get('PRIVACYCTL_EVENT_SOCKET', '')
        if not re.fullmatch(r'[0-9a-f]{32}', generation) or not endpoint.startswith('/'):
            raise ValueError('missing owner event context')
        parent = Path(endpoint).parent.lstat()
        info = Path(endpoint).lstat()
        if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != 0
                or stat.S_IMODE(parent.st_mode) != 0o700
                or not stat.S_ISSOCK(info.st_mode) or info.st_uid != 0
                or info.st_mode & 0o077):
            raise ValueError('unsafe owner event socket')
        frame = {'version': 1, 'generation': generation, 'event': args[0],
                 'fields': {key: os.environ[key] for key in FIELDS if key in os.environ}}
        data = json.dumps(frame, separators=(',', ':')).encode()
        if len(data) > MAX_FRAME:
            raise ValueError('DHCP event exceeds transport bound')
        with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as peer:
            for operation in (lambda: peer.connect(endpoint), lambda: peer.sendall(data)):
                remaining = TIMEOUT - (time.clock_gettime(time.CLOCK_BOOTTIME) - started)
                if remaining <= 0:
                    raise TimeoutError('event deadline exceeded')
                peer.settimeout(remaining)
                operation()
                _pid, uid, _gid = struct.unpack('3i', peer.getsockopt(
                    socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                if uid != 0:
                    raise ValueError('owner credentials are not root')
            remaining = TIMEOUT - (time.clock_gettime(time.CLOCK_BOOTTIME) - started)
            if remaining <= 0:
                raise TimeoutError('event deadline exceeded')
            peer.settimeout(remaining)
            if peer.recv(128) != b'{"ok":true}':
                raise ValueError('DHCP event was rejected')
        return 0
    except (OSError, ValueError, UnicodeError) as error:
        print('privacyctl DHCP event: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
