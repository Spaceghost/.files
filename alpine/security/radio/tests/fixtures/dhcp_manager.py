#!/usr/bin/env python3
"""Production manager integration worker; invoked only by the guarded harness."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import secrets
import sys
import time
from types import SimpleNamespace


HARNESS = Path(__file__).resolve().parents[1] / 'verify_dhcp_network.py'
spec = importlib.util.spec_from_file_location('private_dhcp_harness', HARNESS)
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)
LIBRARY = HARNESS.parent.parent / 'root/usr/local/lib'
sys.path.insert(0, str(LIBRARY))
from privacyctl_runtime import dhcp


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    parser.add_argument('--expected', required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--server-input', type=int, required=True)
    parser.add_argument('--server-output', type=int, required=True)
    parser.add_argument('--exercise-cleanup', action='store_true')
    args = parser.parse_args()
    host, expected = json.loads(args.host), json.loads(args.expected)
    harness.guard_private(host, expected)
    if os.getpid() <= 1:
        raise RuntimeError('manager owner must be a child of the private namespace init')
    if Path('/dev/rfkill').exists() or Path('/sys/class/rfkill').exists():
        raise RuntimeError('host radio paths must be hidden')
    daemon = SimpleNamespace(stdin=os.fdopen(args.server_input, 'w'),
                             stdout=os.fdopen(args.server_output, 'r'))
    root = args.root
    if root.stat().st_uid != 0 or root.stat().st_mode & 0o077:
        raise RuntimeError('manager fixture directory must be private and root-owned')
    wrappers = {}
    for name, module in (('launch', 'launch'), ('hook', 'hook')):
        path = root / ('manager-' + name)
        path.write_text('#!/usr/bin/python3 -I\nimport sys\nsys.path.insert(0, '
                        + repr(str(LIBRARY)) + ')\nfrom privacyctl_runtime.'
                        + module + ' import main\nraise SystemExit(main())\n')
        path.chmod(0o700)
        wrappers[name] = str(path)
    runtime = root / 'manager-runtime'
    evidence = []
    manager = None

    def mode(value):
        result = harness.server_command(daemon, {'command': 'mode', 'mode': value})
        if result != {'mode': value}:
            raise RuntimeError('private server mode mismatch')

    def clear_private_address():
        harness.guard_private(host, expected)
        harness.checked([harness.IP, '-4', 'address', 'flush', 'dev', 'dhcp-client', 'scope', 'global'])

    def start():
        nonlocal manager
        clear_private_address()
        harness.guard_private(host, expected)
        manager = dhcp.DHCPManager(runtime, launcher=wrappers['launch'],
                                   hook=wrappers['hook'], udhcpc=harness.CLIENT)
        manager.start(secrets.token_hex(16), 'dhcp-client')

    def next_event(timeout=25):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            values = manager.poll(.05)
            if values:
                if len(values) != 1:
                    raise RuntimeError('unexpected overlapping manager events')
                return values[0]
        raise RuntimeError('production manager event timeout')

    def accept(event, kind):
        if not isinstance(event, dhcp.LeaseEvent) or event.kind != kind:
            raise RuntimeError('unexpected production manager event: ' + repr(event))
        lease = event.lease
        if (str(lease.address) != harness.CLIENT_ADDRESS + '/24'
                or tuple(map(str, lease.routers)) != (harness.SERVER_ADDRESS,)
                or tuple(map(str, lease.dns)) != ('192.0.2.53',)
                or lease.lease_seconds != harness.LEASE_SECONDS):
            raise RuntimeError('production lease parser changed synthetic values')
        # This fixture applies only its private test address/route. Production
        # LeaseApplier is verified separately; the real production hook stays
        # unchanged and must never call Alpine's default network script.
        for command in (
                ['-4', 'address', 'replace', str(lease.address), 'dev', 'dhcp-client'],
                ['-4', 'route', 'replace', 'default', 'via', harness.SERVER_ADDRESS,
                 'dev', 'dhcp-client']):
            harness.guard_private(host, expected)
            harness.checked([harness.IP, *command])
        if not manager.reply(event.event_id, True):
            raise RuntimeError('production manager rejected timely lease application')
        if kind == 'bound':
            harness.emit({'phase': 'manager_namespace',
                          'namespace': dict(expected, pid=manager.identity['namespace'])})
        harness.emit({'phase': 'manager_event', 'event': kind})
        return {'kind': event.kind, 'received_at': event.received_at,
                'lease': lease.to_dict(), 'expiry': manager.expiry}

    def stop():
        if manager is None:
            return
        identity = manager.identity
        endpoint = manager.socket_path
        harness.guard_private(host, expected)
        manager.stop()
        current = harness.process_identity(identity.get('client_pid', -1))
        if current is not None and current['state'] != 'Z':
            raise RuntimeError('production manager left its private client alive')
        if manager.active or manager.phase != 'idle' or Path(endpoint).exists():
            raise RuntimeError('production manager did not release owned resources')
        clear_private_address()

    try:
        print('Private production manager: bound, same-PID renewal and NAK', file=sys.stderr, flush=True)
        mode('ack')
        start()
        first = next_event()
        bound = accept(first, 'bound')
        identity = manager.identity
        if args.exercise_cleanup:
            harness.emit({'phase': 'intentional_failure', 'after_bound': True,
                          'private_client_alive': manager.active})
            raise RuntimeError('intentional production manager cleanup failure')
        renewed = accept(next_event(), 'renew')
        if manager.identity != identity:
            raise RuntimeError('renewal replaced the production DHCP client')
        mode('nak')
        failure = next_event()
        if not isinstance(failure, dhcp.Failure) or 'nak' not in failure.reason:
            raise RuntimeError('NAK did not revoke manager authorization: ' + repr(failure))
        if not manager.active or manager.phase != 'failed':
            raise RuntimeError('failure must preserve handles until owner cleanup')
        stop()
        evidence.append({'name': 'manager_persistent_renewal_and_nak', 'same_client_identity': True,
                         'events': [bound, renewed], 'failure': failure.reason,
                         'client_and_socket_removed': True})

        print('Private production manager: independent lease expiry', file=sys.stderr, flush=True)
        mode('ack')
        start()
        event = next_event()
        bound = accept(event, 'bound')
        mode('silent')
        failure = next_event()
        elapsed = dhcp.boottime() - event.received_at
        if not isinstance(failure, dhcp.Failure) or failure.reason != 'DHCP lease expired':
            raise RuntimeError('owner did not independently enforce lease expiry: ' + repr(failure))
        if not harness.LEASE_SECONDS <= elapsed < harness.LEASE_SECONDS + 1:
            raise RuntimeError('owner expiry exceeded its lease deadline tolerance')
        stop()
        evidence.append({'name': 'manager_silence_expiry_deadline', 'event': bound,
                         'failure': failure.reason, 'expiry_delay_seconds': elapsed,
                         'client_and_socket_removed': True})

        print('Private production manager: no initial offer', file=sys.stderr, flush=True)
        mode('silent')
        start()
        started = dhcp.boottime()
        failure = next_event()
        elapsed = dhcp.boottime() - started
        if not isinstance(failure, dhcp.Failure) or elapsed > dhcp.ACQUIRE_TIMEOUT + 1:
            raise RuntimeError('no-offer acquisition was not bounded: ' + repr(failure))
        stop()
        evidence.append({'name': 'manager_no_initial_offer', 'failure': failure.reason,
                         'failure_delay_seconds': elapsed, 'client_and_socket_removed': True})
        harness.emit({'phase': 'manager_complete', 'cases': evidence})
    finally:
        stop()
        daemon.stdin.close()
        daemon.stdout.close()


if __name__ == '__main__':
    main()
