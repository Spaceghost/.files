#!/usr/bin/env python3
"""Exercise real udhcpc against a synthetic server in private namespaces.

Run as the desktop user: python3 verify_dhcp_network.py --output DIRECTORY.
Requires installed Python3, iproute2, util-linux unshare/mount, BusyBox udhcpc,
and existing noninteractive doas authority. No DHCP-server package is needed.
Only the isolated worker is privileged. Evidence contains synthetic addresses.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import selectors
import secrets
import signal
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import time


SCRIPT = Path(__file__).resolve()
HOOK = SCRIPT.parent / 'fixtures/dhcp_event.py'
MANAGER = SCRIPT.parent / 'fixtures/dhcp_manager.py'
IP = '/sbin/ip'
PYTHON = '/usr/bin/python3'
CLIENT = '/sbin/udhcpc'
SERVER_ADDRESS = '192.0.2.1'
CLIENT_ADDRESS = '192.0.2.10'
LEASE_SECONDS = 16
PACKET = struct.Struct('!BBBBIHH4s4s4s4s16s64s128s')
COOKIE = b'\x63\x82\x53\x63'


def identities():
    return {kind: os.readlink(f'/proc/self/ns/{kind}') for kind in ('net', 'mnt', 'pid')}


def process_identity(pid):
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(') ', 1)[1].split()
        return {'pid': pid, 'state': fields[0], 'start_time': fields[19]}
    except (OSError, IndexError):
        return None


def checked(arguments, **kwargs):
    return subprocess.run(arguments, check=True, capture_output=True, text=True,
                          timeout=5, **kwargs)


def guard_private(host, expected=None, empty=False):
    current = identities()
    if os.geteuid() != 0 or any(current[k] == host[k] for k in current):
        raise RuntimeError('refusing mutation in a host namespace')
    if expected is not None and current != expected:
        raise RuntimeError('private namespace identity changed')
    if empty:
        links = json.loads(checked([IP, '-j', 'link', 'show']).stdout)
        if {link['ifname'] for link in links} != {'lo'}:
            raise RuntimeError('new network namespace was not empty')
    return current


def mount_private(host):
    expected = guard_private(host, empty=True)
    if os.getpid() != 1:
        raise RuntimeError('worker must be init of a fresh PID namespace')
    # Unshare was told to leave propagation unchanged: this explicit guard runs
    # before the first mount or interface mutation.
    checked(['/bin/mount', '--make-rprivate', '/'])
    guard_private(host, expected)
    checked(['/bin/mount', '-t', 'proc', 'proc', '/proc'])
    for target in ('/tmp', '/run', '/etc', '/dev', '/sys'):
        guard_private(host, expected)
        checked(['/bin/mount', '-t', 'tmpfs', '-o', 'mode=0755',
                 'privacyctl-dhcp-fixture', target])
    os.mknod('/dev/null', stat.S_IFCHR | 0o666, os.makedev(1, 3))
    Path('/etc/resolv.conf').write_text('# private DHCP verification; never host DNS\n')
    if Path('/dev/rfkill').exists() or Path('/sys/class/rfkill').exists():
        raise RuntimeError('host radio access survived the fixture mounts')
    return expected


def decode_options(data):
    if len(data) < 240 or data[236:240] != COOKIE:
        return None
    options = {}
    offset = 240
    while offset < len(data):
        code = data[offset]
        offset += 1
        if code == 255:
            return options
        if code == 0:
            continue
        if offset >= len(data):
            return None
        length = data[offset]
        offset += 1
        if offset + length > len(data):
            return None
        options[code] = data[offset:offset + length]
        offset += length
    return options


def reply_packet(request, message_type):
    header = list(PACKET.unpack(request[:236]))
    if header[:3] != [1, 1, 6]:
        raise RuntimeError('unexpected synthetic client hardware header')
    header[0] = 2
    header[6] = 0x8000
    header[8] = socket.inet_aton(CLIENT_ADDRESS) if message_type != 6 else b'\0' * 4
    header[9] = socket.inet_aton(SERVER_ADDRESS)
    payload = PACKET.pack(*header) + COOKIE
    options = [(53, bytes([message_type])), (54, socket.inet_aton(SERVER_ADDRESS))]
    if message_type != 6:
        options += [(51, struct.pack('!I', LEASE_SECONDS)),
                    (1, socket.inet_aton('255.255.255.0')),
                    (3, socket.inet_aton(SERVER_ADDRESS)),
                    (6, socket.inet_aton('192.0.2.53'))]
    for key, value in options:
        payload += bytes([key, len(value)]) + value
    return (payload + b'\xff').ljust(300, b'\0')


def emit(value):
    print(json.dumps(value, separators=(',', ':')), flush=True)


def server(host, client_namespace):
    guard_private(host, client_namespace)
    os.unshare(os.CLONE_NEWNET)
    expected = guard_private(host, empty=True)
    if expected['net'] == client_namespace['net']:
        raise RuntimeError('server did not enter its own network namespace')
    emit({'ready': True, 'identity': process_identity(os.getpid()), 'namespaces': expected})
    setup = json.loads(sys.stdin.readline())
    if setup != {'command': 'setup'}:
        raise RuntimeError('invalid private server handshake')
    guard_private(host, expected)
    names = {x['ifname'] for x in json.loads(checked([IP, '-j', 'link', 'show']).stdout)}
    if names != {'lo', 'dhcp-server'}:
        raise RuntimeError('unexpected server interface set')
    for arguments in (['link', 'set', 'lo', 'up'],
                      ['address', 'add', SERVER_ADDRESS + '/24', 'dev', 'dhcp-server'],
                      ['link', 'set', 'dhcp-server', 'up']):
        guard_private(host, expected)
        checked([IP, *arguments])
    mode = 'ack'
    packets = []
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
        udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        udp.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, b'dhcp-server\0')
        udp.bind(('0.0.0.0', 67))
        selector = selectors.DefaultSelector()
        selector.register(udp, selectors.EVENT_READ, 'packet')
        selector.register(sys.stdin, selectors.EVENT_READ, 'control')
        emit({'serving': True})
        control_data = b''
        try:
            while True:
                for key, _mask in selector.select(timeout=1):
                    if key.data == 'control':
                        chunk = os.read(sys.stdin.fileno(), 4096)
                        if not chunk:
                            return
                        control_data += chunk
                        while b'\n' in control_data:
                            line, control_data = control_data.split(b'\n', 1)
                            command = json.loads(line)
                            if command.get('command') == 'mode' and command.get('mode') in {'ack', 'nak', 'silent'}:
                                mode = command['mode']
                                emit({'mode': mode})
                            elif command == {'command': 'report'}:
                                emit({'packets': packets})
                            elif command == {'command': 'stop'}:
                                emit({'stopped': True})
                                return
                            else:
                                raise RuntimeError('invalid private server command')
                        continue
                    request, _peer = udp.recvfrom(4096)
                    options = decode_options(request)
                    if not options or len(options.get(53, b'')) != 1:
                        continue
                    message_type = options[53][0]
                    packets.append({'type': message_type, 'mode': mode,
                                    'monotonic': time.monotonic()})
                    if mode == 'silent' or message_type not in {1, 3}:
                        continue
                    response_type = 2 if message_type == 1 else (6 if mode == 'nak' else 5)
                    guard_private(host, expected)
                    udp.sendto(reply_packet(request, response_type), ('255.255.255.255', 68))
        finally:
            selector.close()


def read_message(process, timeout=5):
    if not select.select([process.stdout], [], [], timeout)[0]:
        raise RuntimeError('private server control deadline exceeded')
    line = process.stdout.readline()
    if not line:
        raise RuntimeError('private server exited before its reply')
    return json.loads(line)


def server_command(process, message):
    process.stdin.write(json.dumps(message) + '\n')
    process.stdin.flush()
    return read_message(process)


def events(path):
    if not path.exists():
        return []
    result = []
    for line in path.read_text().splitlines():
        try:
            result.append(json.loads(line))
        except json.JSONDecodeError:
            # A hook may currently be completing its single append.
            continue
    return result


def await_event(path, name, timeout, after=0, process=None):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        found = [x for x in events(path) if x['event'] == name and x['monotonic'] > after]
        if found:
            return found[-1]
        if process is not None and process.poll() is not None:
            raise RuntimeError(f'udhcpc exited before {name}')
        time.sleep(.05)
    raise RuntimeError(f'DHCP event deadline exceeded: {name}')


def stop_owned(process, identity, host, expected):
    if process is None or process.poll() is not None:
        return
    guard_private(host, expected)
    current = process_identity(process.pid)
    if current is None or current['start_time'] != identity['start_time']:
        raise RuntimeError('refusing to signal a changed private process identity')
    if os.readlink(f'/proc/{process.pid}/ns/pid') != expected['pid']:
        raise RuntimeError('refusing to signal a process outside the private PID namespace')
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        current = process_identity(process.pid)
        if current is not None and current['start_time'] == identity['start_time']:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=2)


def production_cases(root, daemon, host, expected, processes, namespaces, exercise_cleanup):
    log_path = root / 'production-manager.log'
    arguments = [PYTHON, '-I', str(MANAGER), '--host', json.dumps(host),
                 '--expected', json.dumps(expected), '--root', str(root),
                 '--server-input', str(daemon.stdin.fileno()),
                 '--server-output', str(daemon.stdout.fileno())]
    if exercise_cleanup:
        arguments.append('--exercise-cleanup')
    with log_path.open('w') as log:
        guard_private(host, expected)
        process = subprocess.Popen(arguments, stdout=subprocess.PIPE, stderr=log,
                                   text=True, start_new_session=True,
                                   pass_fds=(daemon.stdin.fileno(), daemon.stdout.fileno()))
    processes.append((process, process_identity(process.pid)))
    while True:
        message = read_message(process, timeout=40)
        if message.get('phase') == 'manager_namespace':
            namespaces.append(message['namespace'])
            emit({'phase': 'namespace_ready', 'namespaces': namespaces})
        elif message.get('phase') == 'manager_complete':
            process.wait(timeout=5)
            if process.returncode:
                raise RuntimeError('production manager worker failed after its report')
            return message['cases']
        elif message.get('phase') == 'intentional_failure':
            emit(message)
            process.wait(timeout=5)
            raise RuntimeError('intentional production manager cleanup case completed')
        else:
            emit(message)


def worker(host, exercise_cleanup=False, production_manager=False):
    # Exercise rejection inside an already verified private namespace, never
    # by deliberately running a potentially regressed guard against the host.
    initial = guard_private(host, empty=True)
    try:
        guard_private(initial)
    except RuntimeError:
        namespace_rejection = True
    else:
        raise RuntimeError('same-namespace rejection guard failed')
    expected = mount_private(host)
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(RuntimeError('fixture deadline expired')))
    namespaces = [expected]
    emit({'phase': 'namespace_ready', 'namespaces': namespaces})
    cases = []
    processes = []
    with tempfile.TemporaryDirectory(prefix='private-dhcp-', dir='/tmp') as temporary:
        root = Path(temporary)
        os.chmod(root, 0o700)
        hook = root / 'event-hook'
        hook.write_bytes(HOOK.read_bytes())
        hook.chmod(0o700)
        server_log = (root / 'server.log').open('w')
        daemon = subprocess.Popen([PYTHON, '-I', str(SCRIPT), '--server',
                                   json.dumps(host), json.dumps(expected)],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=server_log, text=True, start_new_session=True)
        daemon_identity = process_identity(daemon.pid)
        processes.append((daemon, daemon_identity))
        try:
            greeting = read_message(daemon)
            if (not greeting.get('ready') or any(
                    greeting.get('identity', {}).get(key) != daemon_identity[key]
                    for key in ('pid', 'start_time'))):
                raise RuntimeError('server identity handshake failed')
            server_ns = greeting['namespaces']
            namespaces.append(server_ns)
            emit({'phase': 'namespace_ready', 'namespaces': namespaces})
            if os.readlink(f'/proc/{daemon.pid}/ns/net') != server_ns['net']:
                raise RuntimeError('server network namespace changed before veth transfer')
            guard_private(host, expected)
            checked([IP, 'link', 'add', 'dhcp-client', 'type', 'veth', 'peer', 'name', 'dhcp-server'])
            if process_identity(daemon.pid)['start_time'] != daemon_identity['start_time']:
                raise RuntimeError('server PID changed before veth transfer')
            guard_private(host, expected)
            checked([IP, 'link', 'set', 'dhcp-server', 'netns', str(daemon.pid)])
            for interface in ('lo', 'dhcp-client'):
                guard_private(host, expected)
                checked([IP, 'link', 'set', interface, 'up'])
            if server_command(daemon, {'command': 'setup'}) != {'serving': True}:
                raise RuntimeError('synthetic DHCP server did not start')

            def launch(name, one_shot=False):
                event_path = root / (name + '.events')
                log_path = root / (name + '.log')
                environment = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LC_ALL': 'C',
                               'PRIVATE_DHCP_EVENTS': str(event_path),
                               'PRIVACYCTL_GENERATION': secrets.token_hex(16)}
                for kind in expected:
                    environment['PRIVATE_DHCP_' + kind.upper()] = expected[kind]
                    environment['PRIVATE_DHCP_HOST_' + kind.upper()] = host[kind]
                arguments = [CLIENT, '-f', '-n', '-t', '3', '-T', '1',
                             '-i', 'dhcp-client', '-s', str(hook),
                             '-p', str(root / (name + '.pid'))]
                if one_shot:
                    arguments.append('-q')
                log = log_path.open('w')
                try:
                    guard_private(host, expected)
                    process = subprocess.Popen(arguments, env=environment,
                                               stdin=subprocess.DEVNULL, stdout=log,
                                               stderr=log, start_new_session=True)
                finally:
                    log.close()
                identity = process_identity(process.pid)
                processes.append((process, identity))
                return process, identity, event_path, log_path

            if production_manager:
                cases = production_cases(root, daemon, host, expected, processes, namespaces, exercise_cleanup)
            else:
                print('Private DHCP: one-shot negative control', file=sys.stderr, flush=True)
                client, identity, path, log = launch('one-shot', one_shot=True)
                await_event(path, 'bound', 8, process=client)
                client.wait(timeout=3)
                assert client.returncode == 0
                cases.append({'name': 'one_shot_negative_control', 'bound': True,
                              'client_exited': True, 'renewal_capable': False,
                              'events': events(path), 'client_log': log.read_text()})

                print('Private DHCP: timed renewal and NAK', file=sys.stderr, flush=True)
                client, identity, path, log = launch('persistent')
                bound = await_event(path, 'bound', 8, process=client)
                if exercise_cleanup:
                    emit({'phase': 'intentional_failure', 'after_bound': True,
                          'private_client_alive': client.poll() is None})
                    raise RuntimeError('intentional failure with live private DHCP owners')
                renewed = await_event(path, 'renew', 25, after=bound['monotonic'], process=client)
                assert client.poll() is None
                assert process_identity(client.pid)['start_time'] == identity['start_time']
                assert bound['client_pid'] == renewed['client_pid'] == client.pid
                server_command(daemon, {'command': 'mode', 'mode': 'nak'})
                nak = await_event(path, 'nak', 25, after=renewed['monotonic'], process=client)
                deconfig = await_event(path, 'deconfig', 4, after=nak['monotonic'])
                stop_owned(client, identity, host, expected)
                cases.append({'name': 'persistent_renewal_and_nak', 'same_client_pid': True,
                              'renewal_delay_seconds': renewed['monotonic'] - bound['monotonic'],
                              'nak_followed_by_deconfig': deconfig['monotonic'] >= nak['monotonic'],
                              'events': events(path), 'client_log': log.read_text()})

                print('Private DHCP: server silence through lease expiry', file=sys.stderr, flush=True)
                server_command(daemon, {'command': 'mode', 'mode': 'ack'})
                client, identity, path, log = launch('expiry')
                bound = await_event(path, 'bound', 8, process=client)
                server_command(daemon, {'command': 'mode', 'mode': 'silent'})
                expired = await_event(path, 'deconfig', 35, after=bound['monotonic'])
                assert not [x for x in events(path) if x['event'] == 'renew']
                stop_owned(client, identity, host, expected)
                cases.append({'name': 'server_silence_expires_lease',
                              'expiry_delay_seconds': expired['monotonic'] - bound['monotonic'],
                              'events': events(path), 'client_log': log.read_text()})

                print('Private DHCP: no initial offer', file=sys.stderr, flush=True)
                client, identity, path, log = launch('no-offer')
                await_event(path, 'leasefail', 8)
                client.wait(timeout=3)
                assert client.returncode != 0
                assert not [x for x in events(path) if x['event'] in {'bound', 'renew'}]
                cases.append({'name': 'no_initial_offer', 'nonzero_client_exit': True,
                              'events': events(path), 'client_log': log.read_text()})
            packets = server_command(daemon, {'command': 'report'})['packets']
            server_command(daemon, {'command': 'stop'})
            daemon.wait(timeout=3)
            assert daemon.returncode == 0
            result = {'schema_version': 1, 'namespaces': namespaces,
                      'lease_seconds_offered': LEASE_SECONDS, 'cases': cases,
                      'server_packets': packets,
                      'same_namespace_guard_rejects': namespace_rejection,
                      'host_radio_and_config_paths_hidden': True,
                      'alpine_default_hook_invoked': False}
        except BaseException:
            for log_path in sorted(root.glob('*.log')):
                print(log_path.name + ': ' + log_path.read_text()[-6000:], file=sys.stderr)
            raise
        finally:
            for process, identity in reversed(processes):
                stop_owned(process, identity, host, expected)
            server_log.close()
            # Reap orphaned fixture grandchildren while this PID namespace
            # still exists. Kernel teardown also kills all remaining members.
            while True:
                try:
                    pid, _status = os.waitpid(-1, os.WNOHANG)
                    if pid == 0:
                        break
                except ChildProcessError:
                    break
        result['owned_processes_exited'] = all(p.poll() is not None for p, _ in processes)
        emit(result)


def normalized(value):
    if isinstance(value, dict):
        return {k: normalized(v) for k, v in value.items()
                if k not in {'expires', 'valid_life_time', 'preferred_life_time'}}
    if isinstance(value, list):
        return [normalized(v) for v in value]
    return value


def host_snapshot():
    def digest(value):
        return hashlib.sha256(json.dumps(normalized(value), sort_keys=True).encode()).hexdigest()
    clients = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            if (proc / 'comm').read_text().strip() == 'udhcpc':
                identity = process_identity(int(proc.name))
                if identity:
                    clients.append({key: identity[key] for key in ('pid', 'start_time')})
        except OSError:
            continue
    return {'namespaces': identities(),
            'addresses_digest': digest(json.loads(checked([IP, '-j', 'address', 'show']).stdout)),
            'routes_digest': digest(json.loads(checked([IP, '-j', 'route', 'show', 'table', 'all']).stdout)),
            'dns_digest': hashlib.sha256(Path('/etc/resolv.conf').read_bytes()).hexdigest(),
            'radio_states': {p.name: [(p / name).read_text().strip() for name in ('soft', 'hard')]
                             for p in Path('/sys/class/rfkill').glob('rfkill*')},
            'dhcp_clients': sorted(clients, key=lambda p: p['pid'])}


def audit_cleanup(namespace_ids):
    if os.geteuid() != 0:
        raise RuntimeError('cleanup audit requires read-only root proc access')
    matches = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        for kind in ('net', 'mnt', 'pid'):
            try:
                if os.readlink(proc / 'ns' / kind) in namespace_ids:
                    matches.append({'pid': int(proc.name), 'kind': kind})
            except OSError:
                continue
    emit({'remaining_namespace_members': matches})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--worker', metavar='HOST_IDENTITIES')
    parser.add_argument('--server', nargs=2, metavar=('HOST_IDENTITIES', 'CLIENT_IDENTITIES'))
    parser.add_argument('--audit-cleanup', metavar='NAMESPACE_IDS')
    parser.add_argument('--exercise-cleanup', action='store_true',
                        help='inject a failure after real acquisition and verify cleanup')
    parser.add_argument('--production-manager', action='store_true',
                        help='exercise the staged production DHCP manager and event hook')
    args = parser.parse_args()
    if args.worker:
        worker(json.loads(args.worker), args.exercise_cleanup, args.production_manager)
        return
    if args.server:
        server(*(json.loads(value) for value in args.server))
        return
    if args.audit_cleanup:
        audit_cleanup(json.loads(args.audit_cleanup))
        return
    if not args.output:
        parser.error('--output is required')
    if args.output.exists():
        parser.error('output directory already exists; choose a fresh evidence directory')
    before = host_snapshot()
    sources = [SCRIPT, HOOK]
    if args.production_manager:
        library = SCRIPT.parent.parent / 'root/usr/local/lib/privacyctl_runtime'
        sources += [MANAGER, *(library / name for name in
                              ('__init__.py', 'dhcp.py', 'launch.py', 'hook.py', 'lease.py'))]
    source_hashes = {str(path.relative_to(SCRIPT.parent.parent)):
                     hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
    privilege = [] if os.geteuid() == 0 else ['doas', '-n']
    command = [*privilege, '/usr/bin/timeout', '-k', '3', '120',
               '/usr/bin/unshare', '--net', '--mount', '--pid', '--fork',
               '--kill-child', '--propagation', 'unchanged', PYTHON, '-I',
               str(SCRIPT), '--worker', json.dumps(before['namespaces'])]
    if args.exercise_cleanup:
        command.append('--exercise-cleanup')
    if args.production_manager:
        command.append('--production-manager')
    started = time.monotonic()
    completed = subprocess.run(command, stdout=subprocess.PIPE, text=True, timeout=130)
    after = host_snapshot()
    messages = [json.loads(line) for line in completed.stdout.splitlines()]
    namespaces = next((message['namespaces'] for message in reversed(messages)
                       if message.get('phase') == 'namespace_ready'), [])
    namespace_ids = sorted({value for identity in namespaces for value in identity.values()})
    if not namespace_ids:
        raise RuntimeError(f'worker failed before namespace report ({completed.returncode}); host unchanged={before == after}')
    cleanup = checked([*privilege, PYTHON, '-I', str(SCRIPT),
                       '--audit-cleanup', json.dumps(namespace_ids)])
    cleanup = json.loads(cleanup.stdout)
    if args.exercise_cleanup:
        if completed.returncode == 0:
            raise RuntimeError('intentional worker failure did not occur')
        assert any(message.get('phase') == 'intentional_failure'
                   and message.get('after_bound') and message.get('private_client_alive')
                   for message in messages), 'worker failed before reaching the intended cleanup case'
        result = {'schema_version': 1, 'namespaces': namespaces,
                  'expected_failure_exercised': True, 'worker_exit_status': completed.returncode,
                  'cases': [{'name': 'failure_with_live_private_owners'}]}
    elif completed.returncode:
        raise RuntimeError(f'isolated worker failed ({completed.returncode}); host unchanged={before == after}; cleanup={cleanup}')
    else:
        result = messages[-1]
        assert result['owned_processes_exited']
    result['cleanup'] = cleanup
    result['host_state_unchanged'] = before == after
    result['host_checks'] = {key: before[key] == after[key] for key in before}
    result['elapsed_seconds'] = time.monotonic() - started
    result['verified_at_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    assert source_hashes == {str(path.relative_to(SCRIPT.parent.parent)):
                             hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
    result['source_sha256'] = source_hashes
    assert result['host_state_unchanged'], 'host changed during verification; do not claim isolation proof'
    assert not result['cleanup']['remaining_namespace_members']
    args.output.mkdir(mode=0o700, parents=True)
    (args.output / 'evidence.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': 'passed', 'cases': [case['name'] for case in result['cases']],
                      'elapsed_seconds': result['elapsed_seconds'],
                      'evidence': str(args.output / 'evidence.json')}, indent=2))


if __name__ == '__main__':
    main()
