#!/usr/bin/env python3
"""Exercise production radio-owner components behind private fixture mounts.

The DHCP client, lease applier, resolver, owner IPC and CLI are real. WPA is a
Unix-datagram fixture; rfkill is simulated by a virtual veth link and private
JSON state. This proves neither physical radio blocking nor firewall policy.
"""
import argparse
import hashlib
import importlib.machinery
import importlib.util
import json
import math
import os
from pathlib import Path
import secrets
import select
import signal
import socket
import stat
import subprocess
import sys
import time
import traceback


SCRIPT = Path(__file__).resolve()
ROOT = SCRIPT.parent.parent / 'root'
PRIVATE = Path('/run/privacyctl-fixture')
RUNTIME = Path('/run/privacyctl')
CLI = '/usr/local/sbin/privacyctl'
IP = '/sbin/ip'
PYTHON = '/usr/bin/python3'
HOME_PROFILE = 'shmecklebucket'
HOTSPOT_PROFILE = 'iphone-hotspot'
# BusyBox clamps its internal lease timer to 30 seconds. The separate component
# fixture deliberately offers 16 seconds; native apply needs renewal time before
# that true expiry. Offer 32 here without changing the production expiry policy.
LEASE_SECONDS = 32
GUARD_TIMING = {'calls': 0, 'seconds': 0.0}


def load(path, name):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    return module


native = load(SCRIPT.with_name('verify_network_applier.py'), 'owner_private_applier')
guards = native.guards


def emit(value):
    print(json.dumps(value, sort_keys=True), flush=True)


def write_private(path, value):
    temporary = path.with_name('.' + path.name + '-' + secrets.token_hex(8))
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, sort_keys=True)
        stream.write('\n')
    os.replace(temporary, path)


def measured_guard(operation):
    def measured(*arguments):
        started = time.perf_counter()
        try:
            return operation(*arguments)
        finally:
            GUARD_TIMING['calls'] += 1
            GUARD_TIMING['seconds'] += time.perf_counter() - started
    return measured


@measured_guard
def fixture_guard(host, expected):
    guards.guard_private(host, expected)
    info = (PRIVATE / 'seal.json').lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
            or stat.S_IMODE(info.st_mode) != 0o600):
        raise RuntimeError('private fixture seal is not root-owned mode 0600')
    if json.loads((PRIVATE / 'seal.json').read_text()) != {'host': host, 'expected': expected}:
        raise RuntimeError('private fixture seal changed')
    mounts = {}
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        before, after = line.split(' - ', 1)
        mounts[before.split()[4]] = after.split()[:2]
    for target in ('/etc', '/run', '/dev', '/sys'):
        if mounts.get(target) != ['tmpfs', 'privacyctl-dhcp-fixture']:
            raise RuntimeError('host configuration or devices are not hidden')
    if Path('/dev/rfkill').exists() or Path('/sys/class/rfkill').exists():
        raise RuntimeError('real radio access is present in fixture')


class FakeSystem:
    """Radio simulation: only this fixture's veth wlan0 may be toggled."""
    def __init__(self, host, expected):
        self.host, self.expected = host, expected

    def state(self):
        fixture_guard(self.host, self.expected)
        return json.loads((PRIVATE / 'radios.json').read_text())

    def _set(self, blocked):
        state = self.state()
        if state['wifi_blocked'] != blocked:
            rows = json.loads(guards.checked([IP, '-j', '-d', 'link', 'show', 'dev', 'wlan0']).stdout)
            if len(rows) != 1 or rows[0].get('linkinfo', {}).get('info_kind') != 'veth':
                raise RuntimeError('simulated radio is not the private veth')
            fixture_guard(self.host, self.expected)
            guards.checked([IP, 'link', 'set', 'wlan0', 'down' if blocked else 'up'])
        state.update(wifi_blocked=blocked, bluetooth_blocked=True)
        write_private(PRIVATE / 'radios.json', state)

    def block_all(self):
        self._set(True)

    def unblock_wifi(self):
        self._set(False)

    def block_bluetooth(self):
        state = self.state()
        state['bluetooth_blocked'] = True
        write_private(PRIVATE / 'radios.json', state)

    def states(self, kind):
        return ['0' if self.state()[kind + '_blocked'] else '1']


def fake_wpa(host, expected):
    fixture_guard(host, expected)
    endpoint = Path('/run/wpa_supplicant/wlan0')
    selected, associated, scan_id = None, False, 40
    pending = None
    trace = {'commands': [], 'wrong_scan_ids': [], 'completed_scan_ids': [],
             'results_before_completion': False}
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as server:
        server.bind(str(endpoint))
        server.settimeout(.025)
        write_private(PRIVATE / 'wpa-ready.json', {'ready': True})
        while True:
            fixture_guard(host, expected)
            if pending and time.monotonic() >= pending[0]:
                _when, peer, current = pending
                server.sendto(f'<3>CTRL-EVENT-SCAN-RESULTS id={current}\n'.encode(), peer)
                trace['completed_scan_ids'].append(current)
                pending = None
                write_private(PRIVATE / 'wpa-trace.json', trace)
            try:
                raw, peer = server.recvfrom(4096)
            except TimeoutError:
                continue
            command = raw.decode('ascii')
            trace['commands'].append(command)
            response = 'OK\n'
            if command in ('DISCONNECT', 'DISABLE_NETWORK all'):
                associated = False
            elif command.startswith('SELECT_NETWORK '):
                selected = int(command.split()[-1])
                if selected not in (1, 2):
                    raise RuntimeError('fixture received unexpected network ID')
            elif command == 'RECONNECT':
                associated = True
            elif command == 'LIST_NETWORKS':
                response = ('network id / ssid / bssid / flags\n'
                            '1\tshmecklebucket\tany\t\n'
                            '2\tprivacyctl-fixture-hotspot\tany\t\n')
            elif command == 'STATUS':
                blocked = json.loads((PRIVATE / 'radios.json').read_text())['wifi_blocked']
                if associated and selected and not blocked:
                    ssid = 'shmecklebucket' if selected == 1 else 'privacyctl-fixture-hotspot'
                    response = f'wpa_state=COMPLETED\nid={selected}\nssid={ssid}\n'
                else:
                    response = 'wpa_state=DISCONNECTED\n'
            elif command == 'SCAN use_id=1':
                scan_id += 1
                wrong = scan_id + 9000
                server.sendto(f'<3>CTRL-EVENT-SCAN-RESULTS id={wrong}\n'.encode(), peer)
                trace['wrong_scan_ids'].append(wrong)
                response = str(scan_id) + '\n'
                pending = time.monotonic() + .15, peer, scan_id
            elif command == 'SCAN_RESULTS':
                if pending:
                    trace['results_before_completion'] = True
                response = ('bssid / frequency / signal level / flags / ssid\n'
                            '02:00:00:00:00:01\t2412\t-40\t[ESS]\tprivacyctl-fixture-scan\n')
            elif command not in ('ATTACH', 'ENABLE_NETWORK 1', 'ENABLE_NETWORK 2'):
                raise RuntimeError('unexpected fixture WPA command')
            server.sendto(response.encode('ascii'), peer)
            write_private(PRIVATE / 'wpa-trace.json', trace)


def dhcp_server(host, expected):
    fixture_guard(host, expected)
    guards.LEASE_SECONDS = LEASE_SECONDS
    original_reply, replies = guards.reply_packet, []
    def observed_reply(request, message_type):
        result = original_reply(request, message_type)
        replies.append({'type': message_type, 'at_boottime': time.clock_gettime(time.CLOCK_BOOTTIME)})
        write_private(PRIVATE / 'dhcp-replies.json', replies)
        return result
    guards.reply_packet = observed_reply
    guards.server(host, expected)


def owner_process(host, expected):
    fixture_guard(host, expected)
    if os.getpid() == 1:
        raise RuntimeError('the owner must be a child of the private namespace init')
    sys.path.insert(0, '/usr/local/lib')
    from privacyctl_runtime.adapter import NativeAdapter
    from privacyctl_runtime.dhcp import DHCPManager, LeaseEvent
    from privacyctl_runtime.ipc import Server
    from privacyctl_runtime.network import LeaseApplier, NativeNetwork
    from privacyctl_runtime.service import Owner
    legacy = load(CLI, 'fixture_native_privacyctl')
    adapter = NativeAdapter(legacy, system=FakeSystem(host, expected))
    original_check = adapter.check_generation
    stopped = [False]
    def stop(*_arguments):
        stopped[0] = True
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, stop)
    def check(generation):
        fixture_guard(host, expected)
        if stopped[0]:
            adapter.block_all()
            raise RuntimeError('fixture owner stopping')
        original_check(generation)
    adapter.check_generation = check
    manager = DHCPManager(RUNTIME)
    lease_events, original_poll = [], manager.poll
    def observed_poll(*arguments, **options):
        result = original_poll(*arguments, **options)
        for event in result:
            if isinstance(event, LeaseEvent):
                lease_events.append({'kind': event.kind, 'received_at': event.received_at,
                                     'lease_seconds': event.lease.lease_seconds})
        return result
    manager.poll = observed_poll
    server = Server()
    server.open()
    owner = Owner(server=server, adapter=adapter, dhcp=manager, applier_factory=adapter.applier)
    # Keep observations in memory throughout each apply so timing does not add
    # per-command I/O or change any production checkpoint/command behavior.
    checkpoint_timing = {'calls': 0, 'seconds': 0.0}
    current_timing, apply_timings = [None], []
    original_checkpoint = owner.checkpoint
    def observed_checkpoint():
        started = time.perf_counter()
        try:
            return original_checkpoint()
        finally:
            checkpoint_timing['calls'] += 1
            checkpoint_timing['seconds'] += time.perf_counter() - started
    owner.checkpoint = observed_checkpoint
    original_run = NativeNetwork._run
    def observed_run(backend, arguments, **options):
        started = time.perf_counter()
        try:
            return original_run(backend, arguments, **options)
        finally:
            if current_timing[0] is not None:
                current_timing[0]['commands'].append({'arguments': list(arguments),
                    'elapsed_seconds': time.perf_counter() - started})
    NativeNetwork._run = observed_run
    original_snapshot = NativeNetwork.snapshot
    def observed_snapshot(backend, *arguments, **options):
        result = original_snapshot(backend, *arguments, **options)
        if current_timing[0] is not None:
            current_timing[0]['snapshots'].append({
                'at_seconds': time.perf_counter() - current_timing[0]['started'],
                'tentative_addresses': len(result.tentative), 'failed_addresses': len(result.failed),
                'owned_ipv6_tentative': sum(value.family == 6 and value.protocol == 196
                                            for value in result.tentative)})
        return result
    NativeNetwork.snapshot = observed_snapshot
    original_apply = LeaseApplier.apply
    def observed_apply(applier, *arguments, **options):
        started = time.perf_counter()
        guard_before, checkpoints_before = dict(GUARD_TIMING), dict(checkpoint_timing)
        record = {'started': started, 'commands': [], 'snapshots': [], 'succeeded': False}
        current_timing[0] = record
        try:
            result = original_apply(applier, *arguments, **options)
            record['succeeded'] = True
            return result
        finally:
            record.update(elapsed_seconds=time.perf_counter() - started,
                remaining_deadline_seconds=applier._deadline - time.monotonic(),
                fixture_guards={key: GUARD_TIMING[key] - guard_before[key] for key in GUARD_TIMING},
                owner_checkpoints={key: checkpoint_timing[key] - checkpoints_before[key]
                                   for key in checkpoint_timing})
            record.pop('started')
            current_timing[0] = None
            apply_timings.append(record)
            del apply_timings[:-16]
            write_private(PRIVATE / 'owner-timing.json', apply_timings)
    LeaseApplier.apply = observed_apply
    original_latch = owner._latch
    latch_events = []
    def observe_latch(reason):
        # Observation only: preserve the cause that successful cleanup clears.
        # All fields belong to this synthetic fixture; call production unchanged.
        try:
            error = sys.exception()
            latch_events.append({'reason': str(reason)[:4096], 'phase': owner.phase,
                'dhcp_phase': manager.phase, 'at_boottime': time.clock_gettime(time.CLOCK_BOOTTIME),
                'exception_chain': ''.join(traceback.format_exception(error))[-8192:]
                    if error is not None else ''})
            del latch_events[:-32]
            write_private(PRIVATE / 'owner-latch.json', latch_events)
        finally:
            original_latch(reason)
    owner._latch = observe_latch
    previous = None
    try:
        owner.start()
        while not stopped[0]:
            owner.step()
            value = {'phase': owner.phase, 'profile': owner.profile, 'generation': owner.generation,
                     'dhcp_phase': manager.phase, 'client': manager.identity,
                     'expiry': manager.expiry, 'error': owner._error,
                     'lease_events': list(lease_events),
                     'owned': None if owner.owned is None else owner.owned.to_dict(),
                     'dirty': (RUNTIME / 'lease-dirty').exists()}
            if value != previous:
                write_private(PRIVATE / 'owner-state.json', value)
                previous = value
            time.sleep(.015)
    finally:
        try:
            owner.shutdown()
        finally:
            server.close()


def wait_for(predicate, timeout, description, processes=()):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for process in processes:
            if process.poll() is not None:
                raise RuntimeError(description + ': owned fixture process exited')
        value = predicate()
        if value:
            return value
        time.sleep(.025)
    raise RuntimeError(description + ': deadline exceeded')


def worker(host):
    # The shared helper checks root, fresh PID1, all namespace identities and an
    # empty network namespace BEFORE its first mount or network mutation.
    expected = native.prepare_private(host)
    guards.guard_private(host, expected)
    PRIVATE.mkdir(mode=0o700)
    write_private(PRIVATE / 'seal.json', {'host': host, 'expected': expected})
    fixture_guard(host, expected)
    for prefix in ('lib', 'libexec', 'sbin'):
        fixture_guard(host, expected)
        guards.checked(['/bin/mount', '-t', 'tmpfs', '-o', 'mode=0755',
                        'privacyctl-owner-code', '/usr/local/' + prefix])
    # All implementation copies are root-owned and confined to private mounts.
    for relative in ('usr/local/lib/privacyctl_runtime', 'usr/local/libexec', 'usr/local/sbin'):
        source = ROOT / relative
        destination = Path('/') / relative
        destination.mkdir(mode=0o755, parents=True, exist_ok=True)
        for path in source.iterdir():
            if path.is_file() and (path.suffix == '.py' or path.name in
                                  ('privacyctl', 'privacyctl-dhcp-launch', 'privacyctl-dhcp-event')):
                target = destination / path.name
                target.write_bytes(path.read_bytes())
                target.chmod(0o755 if relative.endswith(('libexec', 'sbin')) else 0o644)
    Path('/etc/privacyctl').mkdir(mode=0o700)
    profiles = Path('/etc/privacyctl/profiles')
    profiles.write_text('profile|shmecklebucket|1|shmecklebucket\n'
                        'profile|iphone-hotspot|2|privacyctl-fixture-hotspot\n')
    profiles.chmod(0o600)
    write_private(Path('/etc/privacyctl/ipv6.json'), {'version': 1, 'profiles': {
        HOME_PROFILE: {'addresses': ['2001:db8:1::17/64'], 'routers': ['fe80::1']},
        HOTSPOT_PROFILE: {'addresses': [], 'routers': []}}})
    Path('/run/wpa_supplicant').mkdir(mode=0o700)
    write_private(PRIVATE / 'radios.json', {'wifi_blocked': False, 'bluetooth_blocked': True})
    processes, logs, namespaces, cases = [], [], [expected], []
    emit({'phase': 'namespace_ready', 'namespaces': namespaces})
    def spawn(arguments, name, control=False):
        fixture_guard(host, expected)
        log = (PRIVATE / (name + '.log')).open('w')
        logs.append(log)
        process = subprocess.Popen(arguments, stdin=subprocess.PIPE if control else subprocess.DEVNULL,
            stdout=subprocess.PIPE if control else log, stderr=log, text=True, start_new_session=True)
        processes.append((process, guards.process_identity(process.pid)))
        return process
    def cli(*arguments):
        fixture_guard(host, expected)
        result = subprocess.run([CLI, *arguments], capture_output=True, text=True, timeout=22,
            env={'PATH': '/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C'})
        if result.returncode:
            raise RuntimeError('staged CLI failed: ' + result.stderr.strip())
        return result.stdout
    def state():
        path = PRIVATE / 'owner-state.json'
        return json.loads(path.read_text()) if path.exists() else {}
    def bound(profile, *, after_generation=None, after_expiry=None):
        # A CLI reply can precede the next status export; inspect one coherent
        # record and require the requested profile/new generation when switching.
        current = state()
        if current.get('phase') != 'bound' or current.get('profile') != profile:
            return None
        expiry = current.get('expiry')
        if not isinstance(expiry, (float, int)) or not math.isfinite(expiry) or current.get('error'):
            raise RuntimeError('bound state has invalid expiry or an owner error')
        if (not current.get('lease_events')
                or current['lease_events'][-1]['lease_seconds'] != LEASE_SECONDS
                or expiry != current['lease_events'][-1]['received_at'] + LEASE_SECONDS):
            raise RuntimeError('bound state does not preserve the offered lease deadline')
        if after_generation is not None and current.get('generation') == after_generation:
            return None
        if after_expiry is not None and (current.get('expiry') or 0) <= after_expiry:
            return None
        return current
    def record(name, started, **details):
        value = {'name': name, 'elapsed_seconds': time.monotonic() - started, **details}
        cases.append(value)
        emit({'phase': 'case', **value})
    def clean():
        current = state()
        if current.get('phase') != 'idle' or current.get('generation') is not None or current.get('dirty'):
            return False
        rows = json.loads(guards.checked([IP, '-j', '-N', 'address', 'show', 'dev', 'wlan0']).stdout)
        addresses = rows[0].get('addr_info', [])
        routes = [route for family in ('-4', '-6') for route in json.loads(guards.checked(
            [IP, '-j', '-N', family, 'route', 'show', 'dev', 'wlan0']).stdout)]
        protocol = lambda value: int(str(value.get('protocol', 0)), 0)
        return (not any(protocol(value) == 196 for value in addresses + routes)
                and not list(Path('/run/resolvconf/keys').glob('privacyctl.*'))
                and not (RUNTIME / 'lease-dirty').exists()
                and not (RUNTIME / 'session.json').exists()
                and json.loads((PRIVATE / 'radios.json').read_text())['wifi_blocked'])
    server = None
    try:
        server = spawn([PYTHON, '-I', str(SCRIPT), '--dhcp-server', json.dumps(host),
                        json.dumps(expected)], 'dhcp-server', control=True)
        greeting = guards.read_message(server)
        identity = processes[-1][1]
        if not greeting.get('ready') or any(greeting['identity'][key] != identity[key]
                                          for key in ('pid', 'start_time')):
            raise RuntimeError('private DHCP server identity handshake failed')
        server_namespace = greeting['namespaces']
        namespaces.append(server_namespace)
        emit({'phase': 'namespace_ready', 'namespaces': namespaces})
        if os.readlink(f'/proc/{server.pid}/ns/net') != server_namespace['net']:
            raise RuntimeError('server namespace changed before veth transfer')
        fixture_guard(host, expected)
        guards.checked([IP, 'link', 'add', 'wlan0', 'type', 'veth', 'peer', 'name', 'dhcp-server'])
        if guards.process_identity(server.pid)['start_time'] != identity['start_time']:
            raise RuntimeError('server PID changed before veth transfer')
        fixture_guard(host, expected)
        guards.checked([IP, 'link', 'set', 'dhcp-server', 'netns', str(server.pid)])
        for interface in ('lo', 'wlan0'):
            fixture_guard(host, expected)
            guards.checked([IP, 'link', 'set', interface, 'up'])
        if guards.server_command(server, {'command': 'setup'}) != {'serving': True}:
            raise RuntimeError('private DHCP server setup failed')
        fixture_guard(host, expected)
        guards.checked([native.RESOLVCONF, '-a', 'unrelated0'], input='nameserver 198.51.100.53\n')
        wpa = spawn([PYTHON, '-I', str(SCRIPT), '--fake-wpa', json.dumps(host), json.dumps(expected)], 'wpa')
        wait_for(lambda: (PRIVATE / 'wpa-ready.json').exists(), 3, 'fake WPA readiness', (wpa,))
        owner = spawn([PYTHON, '-I', str(SCRIPT), '--owner', json.dumps(host), json.dumps(expected)], 'owner')
        wait_for(lambda: state().get('phase') == 'idle', 3, 'native owner readiness', (owner, wpa))

        started = time.monotonic()
        cli('connect', HOME_PROFILE)
        first = wait_for(lambda: bound(HOME_PROFILE), 3,
                         'initial bound state', (owner, wpa))
        assert first['dirty'] and first['owned'] and first['expiry']
        assert any(value['cidr'] == '2001:db8:1::17/64' for value in first['owned']['addresses'])
        first_apply = json.loads((PRIVATE / 'owner-timing.json').read_text())[0]
        assert first_apply['succeeded'] and first_apply['snapshots']
        assert any(value['owned_ipv6_tentative'] > 0 for value in first_apply['snapshots'])
        assert first_apply['snapshots'][-1]['owned_ipv6_tentative'] == 0
        renewed = wait_for(lambda: bound(HOME_PROFILE, after_expiry=first['expiry'] + 2),
                          23, 'same-client renewal', (owner, wpa))
        assert renewed['client'] == first['client']
        assert renewed['generation'] == first['generation']
        assert renewed['owned']['revision'] > first['owned']['revision']
        record('real_bound_and_same_client_renewal', started, client=first['client'],
               initial_expiry=first['expiry'], renewed_expiry=renewed['expiry'])

        old_fence = (RUNTIME / 'off-fence').read_text().strip() if (RUNTIME / 'off-fence').exists() else None
        started = time.monotonic()
        cli('off')
        wait_for(clean, 4, 'normal off cleanup', (owner, wpa))
        assert Path('/run/resolvconf/keys/unrelated0').read_text() == 'nameserver 198.51.100.53\n'
        record('cli_off_removes_owned_state_and_dirty_marker', started)

        started = time.monotonic()
        with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as connection:
            connection.settimeout(4)
            connection.connect('/run/privacyctl/owner.sock')
            nonce = secrets.token_hex(16)
            connection.send(json.dumps({'version': 1, 'command': 'connect', 'profile': HOME_PROFILE,
                                        'fence': old_fence, 'nonce': nonce}).encode())
            response = json.loads(connection.recv(131072))
        assert response['nonce'] == nonce and response['ok'] is False
        assert 'cancelled' in response['error']
        wait_for(clean, 3, 'old fence remained blocked', (owner, wpa))
        record('captured_pre_off_fence_rejected', started)

        started = time.monotonic()
        result = cli('scan')
        trace = json.loads((PRIVATE / 'wpa-trace.json').read_text())
        assert 'privacyctl-fixture-scan' in result and trace['wrong_scan_ids']
        assert trace['completed_scan_ids'] and not trace['results_before_completion']
        wait_for(clean, 3, 'scan cleanup', (owner, wpa))
        record('scan_ignores_wrong_id_and_accepts_exact_completion', started,
               wrong_ids=trace['wrong_scan_ids'], completed_ids=trace['completed_scan_ids'])

        started = time.monotonic()
        cli('connect', HOME_PROFILE)
        home = wait_for(lambda: bound(HOME_PROFILE, after_generation=first['generation']),
                        3, 'home bound', (owner, wpa))
        cli('connect', HOTSPOT_PROFILE)
        hotspot = wait_for(lambda: bound(HOTSPOT_PROFILE, after_generation=home['generation']),
                           3, 'hotspot bound', (owner, wpa))
        assert not any(value['family'] == 6 for value in hotspot['owned']['addresses'])
        cli('connect', HOME_PROFILE)
        restored = wait_for(lambda: bound(HOME_PROFILE, after_generation=hotspot['generation']),
                            3, 'restored home bound', (owner, wpa))
        assert any(value['cidr'] == '2001:db8:1::17/64' for value in restored['owned']['addresses'])
        assert len({item['generation'] for item in (home, hotspot, restored)}) == 3
        record('owner_home_hotspot_home_restores_ipv6', started)

        started = time.monotonic()
        assert guards.server_command(server, {'command': 'mode', 'mode': 'nak'}) == {'mode': 'nak'}
        wait_for(clean, 25, 'NAK removes authorization and lease', (owner, wpa))
        packets = guards.server_command(server, {'command': 'report'})['packets']
        assert any(value['mode'] == 'nak' and value['type'] == 3 for value in packets)
        record('real_renewal_nak_cleans_owner', started)

        assert guards.server_command(server, {'command': 'mode', 'mode': 'ack'}) == {'mode': 'ack'}
        cli('connect', HOME_PROFILE)
        silence_bound = wait_for(lambda: bound(HOME_PROFILE, after_generation=restored['generation']),
                                 3, 'silence-case bound', (owner, wpa))
        started = time.monotonic()
        silence_started = time.clock_gettime(time.CLOCK_BOOTTIME)
        assert guards.server_command(server, {'command': 'mode', 'mode': 'silent'}) == {'mode': 'silent'}
        wait_for(clean, 36, 'silent server authorization cleanup', (owner, wpa))
        signals = [value for value in json.loads((PRIVATE / 'owner-latch.json').read_text())
                   if value['at_boottime'] >= silence_started and value['reason'] in
                   ('DHCP authorization lost: deconfig', 'DHCP lease expired')]
        assert signals, 'silence cleanup had no observed deconfig or lease expiry'
        first_signal = min(signals, key=lambda value: value['at_boottime'])
        replies = json.loads((PRIVATE / 'dhcp-replies.json').read_text())
        assert not [value for value in replies if value['at_boottime'] >= silence_started
                    and value['type'] == 5], 'silent server constructed a DHCP ACK'
        assert state()['lease_events'] == silence_bound['lease_events'], 'silence delivered a new lease'
        packets = guards.server_command(server, {'command': 'report'})['packets']
        assert any(value['mode'] == 'silent' and value['type'] == 3 for value in packets)
        record('real_server_silence_removes_authorization', started,
               lease_expiry=silence_bound['expiry'], observed_failure_time=first_signal['at_boottime'],
               observed_reason=first_signal['reason'],
               early_signal=first_signal['at_boottime'] < silence_bound['expiry'],
               expiry_reached_at_signal=first_signal['at_boottime'] >= silence_bound['expiry'],
               ack_after_silence=False, lease_events_after_silence=False)
        emit({'phase': 'complete', 'cases': cases, 'simulated_radio': True,
              'fake_wpa': True, 'packet_gate_tested': False, 'opensnitch_tested': False,
              'lease_seconds_offered': LEASE_SECONDS,
              'apply_timings': json.loads((PRIVATE / 'owner-timing.json').read_text())})
    except BaseException:
        diagnostic = {'phase': 'failure_diagnostics'}
        for name in ('owner-state', 'owner-latch', 'owner-timing', 'wpa-trace', 'radios', 'dhcp-replies'):
            try:
                with (PRIVATE / (name + '.json')).open() as stream:
                    raw = stream.read(65537)
                diagnostic[name] = json.loads(raw) if len(raw) <= 65536 else {'oversized': True}
            except (OSError, ValueError) as error:
                diagnostic[name] = {'unavailable': type(error).__name__}
        if server is not None and server.poll() is None:
            try:
                server.stdin.write('{"command":"report"}\n')
                server.stdin.flush()
                diagnostic['dhcp_server'] = guards.read_message(server, timeout=1)
            except Exception as error:
                diagnostic['dhcp_server'] = {'unavailable': type(error).__name__}
        emit(diagnostic)
        raise
    finally:
        for process, identity in reversed(processes):
            try:
                guards.stop_owned(process, identity, host, expected)
            finally:
                for stream in (process.stdin, process.stdout):
                    if stream:
                        stream.close()
        for log in logs:
            log.close()
        for name in ('owner', 'wpa', 'dhcp-server'):
            path = PRIVATE / (name + '.log')
            if path.exists() and path.stat().st_size:
                emit({'phase': 'fixture_log', 'name': name, 'text': path.read_text()[-16384:]})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--worker')
    parser.add_argument('--owner', nargs=2)
    parser.add_argument('--fake-wpa', nargs=2)
    parser.add_argument('--dhcp-server', nargs=2)
    args = parser.parse_args()
    for operation, values in ((owner_process, args.owner), (fake_wpa, args.fake_wpa),
                              (dhcp_server, args.dhcp_server)):
        if values:
            operation(*(json.loads(value) for value in values))
            return
    if args.worker:
        try:
            worker(json.loads(args.worker))
        except BaseException:
            emit({'phase': 'failed', 'traceback': traceback.format_exc()})
            raise
        return
    if args.output is None or args.output.exists():
        parser.error('--output must name a new evidence directory')
    paths = [SCRIPT, Path(native.__file__), guards.SCRIPT,
             ROOT / 'usr/local/sbin/privacyctl', ROOT / 'usr/local/libexec/privacyctl-dhcp-launch',
             ROOT / 'usr/local/libexec/privacyctl-dhcp-event', Path(native.RESOLVCONF),
             Path('/usr/lib/resolvconf/libc'),
             *sorted((ROOT / 'usr/local/lib/privacyctl_runtime').glob('*.py'))]
    hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    private_before, private_after = {}, {}
    before = native.snapshot_host(private_before)
    privilege = [] if os.geteuid() == 0 else ['doas', '-n']
    started = time.monotonic()
    command = [*privilege, '/usr/bin/timeout', '-k', '3', '120', '/usr/bin/unshare',
               '--net', '--mount', '--pid', '--fork', '--kill-child=KILL',
               '--propagation', 'unchanged', PYTHON, '-I', str(SCRIPT),
               '--worker', json.dumps(before['namespaces'])]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, timeout=128)
    after = native.snapshot_host(private_after)
    messages = [json.loads(line) for line in result.stdout.splitlines()]
    namespace_rows = [row['namespaces'] for row in messages if row.get('phase') == 'namespace_ready']
    namespaces = []
    for row in namespace_rows:
        namespaces.extend([row] if isinstance(row, dict) else row)
    namespace_ids = sorted({value for row in namespaces for value in row.values()})
    cleanup = json.loads(guards.checked([*privilege, PYTHON, '-I', str(guards.SCRIPT),
        '--audit-cleanup', json.dumps(namespace_ids)]).stdout)
    hashes_after = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    completed = any(row.get('phase') == 'complete' for row in messages)
    evidence = {'schema_version': 1, 'source_sha256': hashes,
                'lease_seconds_offered': LEASE_SECONDS,
                'source_unchanged': hashes == hashes_after,
                'host_checks': {key: before[key] == after[key] for key in before},
                'host_state_unchanged': before == after,
                'host_address_changed_fields': native.changed_fields(private_before, private_after),
                'namespaces': namespaces, 'cleanup': cleanup,
                'worker_exit_status': result.returncode, 'messages': messages,
                'worker_stderr': result.stderr, 'elapsed_seconds': time.monotonic() - started,
                'verified_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                'limitations': ['WPA is a synthetic Unix-datagram server.',
                    'Radio blocking is simulated using only virtual wlan0 and private state.',
                    'This test does not exercise physical radios, real trusted SSIDs, packet gates or OpenSnitch.',
                    'Server silence may revoke authorization early through deconfig; independent lease expiry is a separate manager component test.',
                    'The Owner is launched directly; OpenRC service startup and the reciprocal guardian are separate checks.']}
    evidence['status'] = 'passed' if (not result.returncode and completed and namespace_ids
        and before == after and hashes == hashes_after and not cleanup['remaining_namespace_members']) else 'failed'
    args.output.mkdir(mode=0o700, parents=True)
    write_private(args.output / 'evidence.json', evidence)
    emit({'status': evidence['status'], 'evidence': str(args.output / 'evidence.json'),
          'elapsed_seconds': evidence['elapsed_seconds']})
    if evidence['status'] != 'passed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
