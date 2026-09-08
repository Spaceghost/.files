#!/usr/bin/env python3
"""Verify the actual lease applier in private PID, mount and network namespaces.

Only synthetic addresses are used. The worker hides host radios and resolver
state before making any mutation; the parent compares sanitized host snapshots.
Run as the desktop user with --output NEW_DIRECTORY and existing doas authority.
"""
import argparse
import hashlib
import importlib.util
from ipaddress import IPv6Address, IPv6Interface
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback


SCRIPT = Path(__file__).resolve()
LIBRARY = SCRIPT.parent.parent / 'root/usr/local/lib'
GUARDS = SCRIPT.with_name('verify_dhcp_network.py')
spec = importlib.util.spec_from_file_location('private_dhcp_guards', GUARDS)
guards = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guards)
IP = '/sbin/ip'
RESOLVCONF = '/usr/sbin/resolvconf'
INTERFACE = 'lease-test0'
GENERATION = 'a' * 32
CONFIG = '''resolv_conf=/etc/resolv.conf
state_dir=/run/resolvconf
libc_restart=:
dnsmasq=NO
named=NO
pdns_recursor=NO
pdnsd=NO
resolvectl=NO
systemd_resolved=NO
unbound=NO
'''


def emit(value):
    print(json.dumps(value, sort_keys=True), flush=True)


def snapshot_host(private_details=None):
    value = guards.host_snapshot()
    addresses = guards.normalized(json.loads(guards.checked([IP, '-j', 'address', 'show']).stdout))
    value['addresses_digest'] = hashlib.sha256(json.dumps(addresses, sort_keys=True).encode()).hexdigest()
    if private_details is not None:
        private_details['addresses'] = addresses
    routes = json.loads(guards.checked([IP, '-j', '-6', 'route', 'show', 'table', 'all']).stdout)
    value['ipv6_routes_digest'] = hashlib.sha256(json.dumps(
        guards.normalized(routes), sort_keys=True).encode()).hexdigest()
    return value


def changed_fields(before, after, path='$'):
    """Report JSON field positions only; never persist real host addresses."""
    if type(before) is not type(after):
        return [path]
    if isinstance(before, dict):
        return ([path + '.' + key for key in before.keys() ^ after.keys()]
                + [field for key in before.keys() & after.keys()
                   for field in changed_fields(before[key], after[key], path + '.' + key)])
    if isinstance(before, list):
        return (([path + '.length'] if len(before) != len(after) else [])
                + [field for index, (old, new) in enumerate(zip(before, after))
                   for field in changed_fields(old, new, path + f'[{index}]')])
    return [] if before == after else [path]


def prepare_private(host, patched_resolvconf=None):
    # Subscriber source contains code, not configuration or user resolver data.
    libc = Path('/usr/lib/resolvconf/libc').read_bytes()
    patched = None if patched_resolvconf is None else Path(patched_resolvconf).read_bytes()
    expected = guards.mount_private(host)
    emit({'phase': 'namespace_ready', 'namespaces': expected})
    guards.guard_private(host, expected)
    guards.checked(['/bin/mount', '-t', 'tmpfs', '-o', 'mode=0755',
                    'privacyctl-applier-subscribers', '/usr/lib/resolvconf'])
    Path('/usr/lib/resolvconf/libc').write_bytes(libc)
    Path('/usr/lib/resolvconf/libc').chmod(0o755)
    Path('/usr/lib/resolvconf/libc.d').mkdir()
    if patched is not None:
        fixture = Path('/run/private-resolvconf')
        fixture.write_bytes(patched)
        fixture.chmod(0o755)
        guards.guard_private(host, expected)
        guards.checked(['/bin/mount', '--bind', str(fixture), RESOLVCONF])
    Path('/etc/resolvconf.conf').write_text(CONFIG)
    guards.guard_private(host, expected)
    guards.checked([RESOLVCONF, '-u'])
    return expected


def worker(host, patched_resolvconf=None):
    expected = prepare_private(host, patched_resolvconf)
    for arguments in (['link', 'set', 'lo', 'up'],
                      ['link', 'add', INTERFACE, 'type', 'dummy'],
                      ['link', 'set', INTERFACE, 'up'],
                      ['-4', 'address', 'add', '203.0.113.17/24', 'dev', INTERFACE,
                       'proto', '99', 'noprefixroute'],
                      ['-4', 'route', 'add', '203.0.113.0/24', 'dev', INTERFACE,
                       'proto', '99', 'metric', '900', 'src', '203.0.113.17']):
        guards.guard_private(host, expected)
        guards.checked([IP, *arguments])
    guards.guard_private(host, expected)
    guards.checked([RESOLVCONF, '-a', 'other0'], input='nameserver 198.51.100.53\n')
    sys.path.insert(0, str(LIBRARY))
    from privacyctl_runtime.lease import Lease
    from privacyctl_runtime.network import IPv6Profile, LeaseApplier, NativeNetwork, PROTOCOL

    backend = NativeNetwork()
    applier = LeaseApplier(GENERATION, INTERFACE, backend=backend,
                           check=lambda: guards.guard_private(host, expected))
    cases = []

    def lease(**changes):
        fields = {'interface': INTERFACE, 'ip': '192.0.2.17', 'mask': '24',
                  'router': '192.0.2.1', 'dns': '192.0.2.53', 'lease': '60',
                  'serverid': '192.0.2.2'}
        fields.update(changes)
        return Lease.from_event(fields, expected_interface=INTERFACE)

    def kernel():
        return backend.snapshot(INTERFACE, deadline=time.monotonic() + 3,
                                check=lambda: guards.guard_private(host, expected))

    def dns():
        return backend.resolver(deadline=time.monotonic() + 3,
                                check=lambda: guards.guard_private(host, expected))

    def record(name, started, owned=None):
        snapshot = kernel()
        case = {'name': name, 'elapsed_seconds': time.monotonic() - started,
                'owned': None if owned is None else owned.to_dict(),
                'addresses': sorted(value.cidr for value in snapshot.addresses),
                'dns': dns()}
        cases.append(case)
        emit({'phase': 'case', **case})
        return snapshot

    initial = kernel()
    start = time.monotonic()
    owned = applier.apply(lease())
    first = record('initial_ipv4_and_native_dns', start, owned)
    assert set(owned.addresses).issubset(first.addresses)
    assert set(owned.routes).issubset(first.routes)
    assert initial.addresses.issubset(first.addresses)
    assert initial.routes.issubset(first.routes)
    assert set(dns()) == {'192.0.2.53', '198.51.100.53'}
    rows = json.loads(guards.checked([IP, '-j', '-N', 'address', 'show', 'dev', INTERFACE]).stdout)
    address = next(value for value in rows[0]['addr_info'] if value['local'] == '192.0.2.17')
    assert address['broadcast'] == '192.0.2.255'
    assert 55 <= address['valid_life_time'] <= 60
    start = time.monotonic()
    old = owned
    owned = applier.apply(lease(lease='120'), owned)
    renewed = record('same_address_renewal', start, owned)
    assert set(old.addresses) == set(owned.addresses)
    assert first.addresses == renewed.addresses
    rows = json.loads(guards.checked([IP, '-j', '-N', 'address', 'show', 'dev', INTERFACE]).stdout)
    address = next(value for value in rows[0]['addr_info'] if value['local'] == '192.0.2.17')
    assert 115 <= address['valid_life_time'] <= 120
    home = IPv6Profile((IPv6Interface('2001:db8:1::17/64'),), (IPv6Address('fe80::1'),))
    start = time.monotonic()
    owned = applier.apply(lease(), owned, ipv6=home)
    first_home = record('home_static_ipv6', start, owned)
    assert any(value.cidr == '2001:db8:1::17/64' for value in first_home.addresses)
    assert not set(owned.addresses).intersection(first_home.tentative | first_home.failed)
    start = time.monotonic()
    owned = applier.apply(lease(ip='198.51.100.17', router='198.51.100.1',
                                dns='198.51.100.53'), owned)
    hotspot = record('hotspot_removes_only_owned_ipv6', start, owned)
    assert not any(value.family == 6 and value.protocol == PROTOCOL for value in hotspot.addresses)
    assert {value for value in first_home.addresses if value.family == 6 and value.protocol != PROTOCOL}.issubset(hotspot.addresses)
    start = time.monotonic()
    owned = applier.apply(lease(), owned, ipv6=home)
    restored = record('home_restores_static_ipv6', start, owned)
    assert any(value.cidr == '2001:db8:1::17/64' for value in restored.addresses)
    start = time.monotonic()
    applier.remove(owned)
    removed = record('removal_preserves_other_address_routes_and_dns', start)
    assert not any(value.protocol == PROTOCOL for value in removed.addresses | removed.routes)
    assert initial.addresses.issubset(removed.addresses)
    assert initial.routes.issubset(removed.routes)
    assert dns() == ('198.51.100.53',)
    assert not list(Path('/run/resolvconf/keys').glob('privacyctl.*'))
    assert Path('/run/resolvconf/keys/other0').read_text() == 'nameserver 198.51.100.53\n'
    start = time.monotonic()
    owned = applier.apply(lease(ip='192.0.2.17', mask='32'))
    host_lease = record('host_lease_off_prefix_gateway', start, owned)
    assert any(value.destination == '192.0.2.1/32' and value.gateway is None
               for value in host_lease.routes)
    assert any(value.destination == 'default' and value.gateway == '192.0.2.1'
               for value in host_lease.routes)
    applier.remove(owned)
    final = kernel()
    assert not any(value.protocol == PROTOCOL for value in final.addresses | final.routes)
    assert dns() == ('198.51.100.53',)
    emit({'phase': 'complete', 'cases': cases})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--worker')
    parser.add_argument('--resolvconf', type=Path,
                        help='trusted patched script, mounted only inside the private worker')
    args = parser.parse_args()
    if args.worker:
        try:
            worker(json.loads(args.worker), args.resolvconf)
        except BaseException:
            emit({'phase': 'failed', 'traceback': traceback.format_exc()})
            raise
        return
    if args.output is None or args.output.exists():
        parser.error('--output must name a new directory')
    paths = [SCRIPT, GUARDS, *(LIBRARY / 'privacyctl_runtime' / name
                              for name in ('network.py', 'lease.py'))]
    if args.resolvconf is not None:
        args.resolvconf = args.resolvconf.resolve(strict=True)
        paths.append(args.resolvconf)
    source_hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    private_before, private_after = {}, {}
    before = snapshot_host(private_before)
    privilege = [] if os.geteuid() == 0 else ['doas', '-n']
    started = time.monotonic()
    command = [*privilege, '/usr/bin/timeout', '-k', '3', '45',
        '/usr/bin/unshare', '--net', '--mount', '--pid', '--fork', '--kill-child=KILL',
        '--propagation', 'unchanged', '/usr/bin/python3', '-I', str(SCRIPT),
        '--worker', json.dumps(before['namespaces'])]
    if args.resolvconf is not None:
        command += ['--resolvconf', str(args.resolvconf)]
    process = subprocess.run(command, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, timeout=50)
    after = snapshot_host(private_after)
    messages = [json.loads(line) for line in process.stdout.splitlines()]
    namespaces = next((item['namespaces'] for item in messages
                       if item.get('phase') == 'namespace_ready'), {})
    cleanup = json.loads(guards.checked([*privilege, '/usr/bin/python3', '-I', str(GUARDS),
        '--audit-cleanup', json.dumps(list(namespaces.values()))]).stdout)
    hashes_after = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    completed = next((item for item in messages if item.get('phase') == 'complete'), None)
    evidence = {'schema_version': 1, 'source_sha256': source_hashes,
                'source_unchanged': source_hashes == hashes_after,
                'host_checks': {key: before[key] == after[key] for key in before},
                'host_state_unchanged': before == after,
                'host_address_changed_fields': changed_fields(private_before, private_after),
                'elapsed_seconds': time.monotonic() - started,
                'verified_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                'namespaces': namespaces, 'cleanup': cleanup,
                'worker_exit_status': process.returncode, 'messages': messages,
                'worker_stderr': process.stderr}
    evidence['status'] = 'passed' if (process.returncode == 0 and completed and namespaces
        and before == after and source_hashes == hashes_after
        and not cleanup['remaining_namespace_members']) else 'failed'
    args.output.mkdir(mode=0o700, parents=True)
    (args.output / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    emit({'status': evidence['status'], 'evidence': str(args.output / 'evidence.json'),
          'elapsed_seconds': evidence['elapsed_seconds']})
    if evidence['status'] != 'passed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
