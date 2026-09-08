#!/usr/bin/python3 -I
"""Private-namespace udhcpc hook; never use as a host network hook."""
import ipaddress
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time


def guard():
    for kind in ('net', 'mnt', 'pid'):
        current = os.readlink(f'/proc/self/ns/{kind}')
        if current != os.environ[f'PRIVATE_DHCP_{kind.upper()}']:
            raise RuntimeError('fixture namespace identity changed')
        if current == os.environ[f'PRIVATE_DHCP_HOST_{kind.upper()}']:
            raise RuntimeError('fixture refuses host namespace')
    if os.environ.get('interface') != 'dhcp-client':
        raise RuntimeError('fixture refuses an unexpected interface')
    if Path('/dev/rfkill').exists() or Path('/sys/class/rfkill').exists():
        raise RuntimeError('fixture can still reach host radio interfaces')


def command(*arguments):
    guard()
    subprocess.run(['/sbin/ip', *arguments], check=True, timeout=3,
                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)


def main():
    guard()
    if len(sys.argv) != 2:
        raise RuntimeError('expected one DHCP event')
    event = sys.argv[1]
    if event not in {'bound', 'renew', 'deconfig', 'nak', 'leasefail'}:
        raise RuntimeError('unexpected DHCP event')
    payload = {key: os.environ[key] for key in
               ('interface', 'ip', 'subnet', 'mask', 'router', 'dns', 'lease', 'serverid')
               if key in os.environ}
    if event in {'bound', 'renew'}:
        address = ipaddress.IPv4Interface(payload['ip'] + '/' + payload['mask'])
        if str(address) != '192.0.2.10/24':
            raise RuntimeError('unexpected synthetic lease')
        if payload.get('router', '').strip() != '192.0.2.1':
            raise RuntimeError('unexpected synthetic router')
        command('-4', 'address', 'replace', str(address), 'dev', 'dhcp-client')
        command('-4', 'route', 'replace', 'default', 'via', '192.0.2.1',
                'dev', 'dhcp-client')
    elif event == 'deconfig':
        command('-4', 'address', 'flush', 'dev', 'dhcp-client', 'scope', 'global')
    record = {'event': event, 'monotonic': time.monotonic(), 'hook_pid': os.getpid(),
              'client_pid': os.getppid(), 'payload': payload,
              'generation': os.environ['PRIVACYCTL_GENERATION'],
              'net_namespace': os.readlink('/proc/self/ns/net')}
    target = Path(os.environ['PRIVATE_DHCP_EVENTS'])
    info = target.parent.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
        raise RuntimeError('unsafe private event directory')
    descriptor = os.open(target, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW,
                         0o600)
    with os.fdopen(descriptor, 'a') as stream:
        stream.write(json.dumps(record, separators=(',', ':')) + '\n')
        stream.flush()
    # Deliberately no default.script, DNS write, scan, WPA or rfkill action.


if __name__ == '__main__':
    main()
