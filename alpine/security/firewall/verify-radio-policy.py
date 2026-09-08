#!/usr/bin/env python3
"""Private DHCP/DNS/NDP packet proof with installed nft and OpenSnitch.

Run only after guard review and a coordinated native-fixture slot. No host
configuration, real rule files, GUI, radio device or uplink is used by workers.
This proves packet behavior under controlled rules, not trusted live profiles.
"""
import argparse
import ctypes
import errno
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import select
import selectors
import signal
import socket
import stat
import struct
import subprocess
import sys
import time
import traceback

SCRIPT = Path(__file__).resolve()
RADIO = SCRIPT.parents[1] / 'radio'
GUARD_FILE = RADIO / 'tests/verify_dhcp_network.py'
spec = importlib.util.spec_from_file_location('radio_packet_guards', GUARD_FILE)
guards = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guards)
LIBRARY = RADIO / 'root/usr/local/lib'
PYTHON, IP, NFT = '/usr/bin/python3', '/sbin/ip', '/usr/sbin/nft'
DAEMON = '/usr/bin/opensnitchd'
PRIVATE = Path('/run/radio-packet-proof')
CLIENT, PEER = 'policy-client', 'policy-server'
SERVER_IP, RESOLVER_A, RESOLVER_B = '192.0.2.1', '192.0.2.53', '192.0.2.54'
CLIENT_IP, SERVER_V6, CLIENT_V6 = '192.0.2.10', '2001:db8:1::1', '2001:db8:1::10'
ENV = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C'}
MAX_SECONDS = 120
SEALS = fcntl.F_SEAL_SEAL | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_GROW | fcntl.F_SEAL_WRITE


def emit(value):
    print(json.dumps(value, sort_keys=True), flush=True)


def bounded_tail(path, limit=16000):
    with path.open('rb') as stream:
        stream.seek(max(0, os.fstat(stream.fileno()).st_size - limit))
        return stream.read(limit).decode('utf-8', 'replace')


def verify_module_barrier(modules, log_path=None):
    info = modules.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != 0
            or stat.S_IMODE(info.st_mode) != 0o700 or any(modules.iterdir())):
        raise RuntimeError('private eBPF module directory is unsafe or nonempty')
    if log_path is None:
        return
    expected = str(modules / 'opensnitch-dns.o').encode()
    attempts, total = [], 0
    with log_path.open('rb') as stream:
        while line := stream.readline(8193):
            total += len(line)
            if len(line) > 8192 or total > 262144:
                raise RuntimeError('private module audit log exceeds its bound')
            if b'[eBPF] module loaded:' in line:
                raise RuntimeError('private daemon loaded an eBPF module')
            marker = b'[eBPF] trying to load '
            if marker in line:
                destination = line.split(marker, 1)[1].strip()
                if destination != expected:
                    raise RuntimeError('daemon attempted a nonprivate eBPF module path')
                attempts.append(destination.decode())
    if not attempts:
        raise RuntimeError('private module load attempt was not observed')
    return {'directory_root_private_and_empty': True, 'attempted_paths': attempts,
            'module_loaded': False, 'startup_listener_call_disabled': False}


def read_context(fd):
    if fcntl.fcntl(fd, fcntl.F_GET_SEALS) & SEALS != SEALS:
        raise RuntimeError('fixture context is not sealed')
    data = os.pread(fd, 8193, 0)
    if len(data) > 8192:
        raise RuntimeError('fixture context is oversized')
    value = json.loads(data)
    if (set(value) != {'host', 'parent', 'token'} or set(value['host']) != {'net', 'mnt', 'pid'}
            or not isinstance(value['token'], str) or len(value['token']) != 32):
        raise RuntimeError('invalid fixture context')
    return value


def private_guard(host, expected):
    guards.guard_private(host, expected)
    mounts = {}
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        before, after = line.split(' - ', 1)
        mounts[before.split()[4]] = after.split()[:2]
    for target in ('/tmp', '/etc', '/run', '/dev', '/sys', '/var'):
        if mounts.get(target) != ['tmpfs', 'privacyctl-dhcp-fixture']:
            raise RuntimeError('host configuration or device path is not hidden')
    if Path('/dev/rfkill').exists() or Path('/sys/class/rfkill').exists():
        raise RuntimeError('host radio device remains visible')
    seal = PRIVATE / 'seal.json'
    info = seal.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
            or stat.S_IMODE(info.st_mode) != 0o600):
        raise RuntimeError('unsafe private fixture seal')
    original = json.loads(seal.read_text())
    if original['host'] != host or any(original['worker'][key] != expected[key] for key in ('mnt', 'pid')):
        raise RuntimeError('private fixture seal changed')


def checked_private(host, expected, arguments, **kwargs):
    private_guard(host, expected)
    return guards.checked(arguments, env=ENV, **kwargs)


class Child:
    """A direct child stays unreaped until its pidfd is captured."""
    def __init__(self, host, expected, arguments, *, stdin=False, output=None):
        private_guard(host, expected)
        self.host, self.expected = host, expected
        self.process = subprocess.Popen(arguments, stdin=subprocess.PIPE if stdin else subprocess.DEVNULL,
            stdout=subprocess.PIPE if output is None else output, stderr=subprocess.PIPE,
            text=True, env=ENV, cwd='/', start_new_session=True)
        try:
            self.fd = os.pidfd_open(self.process.pid)
        except BaseException:
            self.process.kill()
            self.process.wait(timeout=3)
            raise

    def close(self):
        private_guard(self.host, self.expected)
        try:
            if self.process.poll() is None:
                signal.pidfd_send_signal(self.fd, signal.SIGKILL)
            self.process.wait(timeout=3)
            if not select.select([self.fd], [], [], 1)[0]:
                raise RuntimeError('private child survived cleanup')
        finally:
            os.close(self.fd)
            for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
                if stream is not None:
                    stream.close()


def packet_destination(ancillary, flags, expected_ifindex):
    # Linux in_pktinfo: native unsigned index, local address, header destination.
    # ipi_spec_dst can equal SERVER_IP for a broadcast; inspect ipi_addr instead.
    if flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC) or len(ancillary) != 1:
        raise RuntimeError('truncated or ambiguous DHCP packet metadata')
    level, kind, data = ancillary[0]
    if level != socket.IPPROTO_IP or kind != socket.IP_PKTINFO or len(data) != 12:
        raise RuntimeError('invalid DHCP IP_PKTINFO')
    index, _, destination = struct.unpack('=I4s4s', data)
    if index != expected_ifindex:
        raise RuntimeError('DHCP packet arrived on an unexpected interface')
    return socket.inet_ntoa(destination)


def server(host, inherited):
    private_guard(host, inherited)
    os.unshare(os.CLONE_NEWNET)
    expected = guards.guard_private(host, empty=True)
    private_guard(host, expected)
    emit({'ready': True, 'namespaces': expected})
    if json.loads(sys.stdin.readline()) != {'command': 'setup'}:
        raise RuntimeError('invalid server setup handshake')
    names = {row['ifname'] for row in json.loads(checked_private(
        host, expected, [IP, '-j', 'link', 'show']).stdout)}
    if names != {'lo', PEER}:
        raise RuntimeError('server links are not the private veth pair')
    for arguments in (['link', 'set', 'lo', 'up'], ['link', 'set', PEER, 'up'],
                      *(['address', 'add', address + '/24', 'dev', PEER]
                        for address in (SERVER_IP, RESOLVER_A, RESOLVER_B)),
                      ['-6', 'address', 'add', SERVER_V6 + '/64', 'dev', PEER]):
        checked_private(host, expected, [IP, *arguments])
    counters = {'discover': 0, 'select': 0, 'renew_unicast': 0, 'rebind_broadcast': 0,
                'dns_udp': 0, 'dns_tcp': 0}
    peer_index = socket.if_nametoindex(PEER)
    handles = []
    selector = selectors.DefaultSelector()
    try:
        for port, kind, address in ((67, socket.SOCK_DGRAM, '0.0.0.0'),
                                    (53, socket.SOCK_DGRAM, RESOLVER_A),
                                    (53, socket.SOCK_DGRAM, RESOLVER_B),
                                    (53, socket.SOCK_STREAM, '0.0.0.0')):
            sock = socket.socket(socket.AF_INET, kind)
            handles.append(sock)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if port == 67:
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_PKTINFO, 1)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, PEER.encode() + b'\0')
            # Bound UDP DNS replies retain the resolver address queried by the
            # connected client; a wildcard sendto would use SERVER_IP instead.
            sock.bind((address, port))
            if kind == socket.SOCK_STREAM:
                sock.listen(8)
            selector.register(sock, selectors.EVENT_READ, (port, kind))
        selector.register(sys.stdin, selectors.EVENT_READ, 'control')
        emit({'serving': True})
        while True:
            private_guard(host, expected)
            for key, _ in selector.select(.1):
                if key.data == 'control':
                    line = sys.stdin.readline()
                    if not line:
                        return
                    command = json.loads(line)
                    if command == {'command': 'report'}:
                        emit({'counters': counters})
                    elif command == {'command': 'stop'}:
                        emit({'stopped': True})
                        return
                    else:
                        raise RuntimeError('unsupported private server command')
                    continue
                port, kind = key.data
                if port == 67:
                    packet, ancillary, flags, peer = key.fileobj.recvmsg(4096, socket.CMSG_SPACE(12))
                    received_destination = packet_destination(ancillary, flags, peer_index)
                    if peer[1] != 68:
                        raise RuntimeError('DHCP request source port changed')
                    options = guards.decode_options(packet)
                    if not options or options.get(53) not in (b'\x01', b'\x03'):
                        continue
                    if options[53] == b'\x01':
                        counters['discover'] += 1
                        reply_type = 2
                    else:
                        if packet[12:16] == b'\0' * 4:
                            counters['select'] += 1
                        elif received_destination == SERVER_IP:
                            counters['renew_unicast'] += 1
                        elif received_destination in ('255.255.255.255', '192.0.2.255'):
                            counters['rebind_broadcast'] += 1
                        else:
                            raise RuntimeError('DHCP renewal destination changed')
                        reply_type = 5
                    # BusyBox's internal renewal floor is 30 seconds; 32 permits
                    # actual same-PID renewal before the accepted lease expires.
                    guards.LEASE_SECONDS = 32
                    destination = (peer[0], 68) if packet[12:16] != b'\0' * 4 else ('255.255.255.255', 68)
                    key.fileobj.sendto(guards.reply_packet(packet, reply_type), destination)
                elif kind == socket.SOCK_DGRAM:
                    packet, peer = key.fileobj.recvfrom(4096)
                    if len(packet) >= 12:
                        counters['dns_udp'] += 1
                        key.fileobj.sendto(packet[:2] + b'\x81\x80' + packet[4:], peer)
                else:
                    connection, _ = key.fileobj.accept()
                    with connection:
                        connection.settimeout(.3)
                        try:
                            packet = connection.recv(4096)
                            if len(packet) >= 14:
                                counters['dns_tcp'] += 1
                                connection.sendall(packet[:4] + b'\x81\x80' + packet[6:])
                        except (TimeoutError, OSError):
                            pass
    finally:
        selector.close()
        for sock in handles:
            sock.close()


PROBE = r'''import json,os,socket,struct,sys
uid=int(sys.argv[1]);protocol=sys.argv[2];host=sys.argv[3];port=int(sys.argv[4])
if uid:
 os.setgroups([]);os.setgid(uid);os.setuid(uid)
packet=struct.pack('!HHHHHH',0x6378,0x0100,1,0,0,0)+b'\x05probe\x07invalid\0'+struct.pack('!HH',1,1)
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM if protocol=='udp' else socket.SOCK_STREAM)
s.settimeout(.7)
try:
 s.connect((host,port));s.sendall(packet if protocol=='udp' else struct.pack('!H',len(packet))+packet)
 data=s.recv(4096)
 if protocol=='tcp':data=data[2:]
 ok=len(data)>=12 and data[:2]==packet[:2] and data[2]&0x80!=0
except (OSError,TimeoutError):ok=False
finally:s.close()
print(json.dumps({'ok':ok,'uid':os.getuid(),'executable':os.readlink('/proc/self/exe'),'pid_namespace':os.readlink('/proc/self/ns/pid')}))
sys.exit(0 if ok else 2)
'''


def nft_counts(host, expected):
    data = json.loads(checked_private(host, expected, [NFT, '-j', 'list', 'table', 'inet', 'policy_observe']).stdout)
    return {row['rule']['comment']: next(value['counter']['packets'] for value in row['rule']['expr']
            if 'counter' in value) for row in data['nftables'] if 'rule' in row and 'comment' in row['rule']}


def run_cases(host, expected, config_source, gate_source):
    sys.path.insert(0, '/usr/local/lib')
    from privacyctl_runtime.dhcp import DHCPManager, Failure, LeaseEvent
    children, log_streams, cases = [], [], []
    manager = None
    def command(arguments, **kwargs):
        return checked_private(host, expected, arguments, **kwargs)
    def record(name, **values):
        cases.append({'name': name, **values})
        emit({'phase': 'case', **cases[-1]})
    def probe(executable, protocol, address=RESOLVER_A, uid=65534, allowed=False, nested=False, port=53):
        argv = [executable, '-I', '-c', PROBE, str(uid), protocol, address, str(port)]
        if nested:
            argv = ['/usr/bin/unshare', '--pid', '--fork', '--kill-child=KILL', *argv]
        child = Child(host, expected, argv)
        try:
            stdout, stderr = child.process.communicate(timeout=3)
            if child.process.returncode not in (0, 2) or stderr:
                raise RuntimeError('private DNS probe failed: ' + stderr[:1000])
            value = json.loads(stdout)
            if value['ok'] != allowed:
                private_guard(host, expected)
                emit({'phase': 'probe_failure', 'probe': value,
                      'server_counters': guards.server_command(peer.process, {'command': 'report'})['counters']})
                raise RuntimeError('unexpected private DNS verdict: ' + json.dumps(value))
            if value['uid'] != uid or value['executable'] != executable:
                raise RuntimeError('probe executable or UID changed')
            if nested and value['pid_namespace'] == expected['pid']:
                raise RuntimeError('nested probe did not enter a different PID namespace')
            return value
        finally:
            child.close()
    try:
        peer = Child(host, expected, [PYTHON, '-I', str(SCRIPT), '--server', json.dumps(host), json.dumps(expected)], stdin=True)
        children.append(peer)
        ready = guards.read_message(peer.process)
        peer_expected = ready['namespaces']
        if peer_expected['net'] in (host['net'], expected['net']):
            raise RuntimeError('server namespace is not separate')
        emit({'phase': 'server_namespace', 'namespaces': peer_expected})
        for arguments in (['link', 'set', 'lo', 'up'],
                          ['link', 'add', CLIENT, 'type', 'veth', 'peer', 'name', PEER],
                          ['link', 'set', PEER, 'netns', str(peer.process.pid)],
                          ['link', 'set', CLIENT, 'up']):
            command([IP, *arguments])
        if guards.server_command(peer.process, {'command': 'setup'}) != {'serving': True}:
            raise RuntimeError('private server did not become ready')
        rules = PRIVATE / 'rules'
        rules.mkdir(mode=0o700)
        executable, alternate = str(PRIVATE / 'probe-python'), str(PRIVATE / 'other-python')
        binary = Path(PYTHON).resolve().read_bytes()
        for path in (executable, alternate):
            Path(path).write_bytes(binary)
            Path(path).chmod(0o755)
        command([NFT, '-f', '-'], input=gate_source)
        observer = '''table inet policy_observe {
chain before { type filter hook output priority -151; policy accept;
udp sport 68 udp dport 67 counter comment "dhcp_before"
icmpv6 type nd-neighbor-solicit ip6 hoplimit 255 counter comment "ns255_before"
icmpv6 type nd-neighbor-solicit ip6 hoplimit 254 counter comment "ns254_before"
}
chain after { type filter hook output priority -148; policy accept;
udp sport 68 udp dport 67 counter comment "dhcp_after"
icmpv6 type nd-neighbor-solicit ip6 hoplimit 255 counter comment "ns255_after"
icmpv6 type nd-neighbor-solicit ip6 hoplimit 254 counter comment "ns254_after"
}
}
'''
        command([NFT, '-f', '-'], input=observer)
        before = nft_counts(host, expected)
        manager = DHCPManager(PRIVATE / 'dhcp')
        manager.start(secrets.token_hex(16), CLIENT)
        start, bound, renewal, first_identity, bound_counts = time.monotonic(), False, False, None, None
        while time.monotonic() - start < 36:
            private_guard(host, expected)
            for event in manager.poll(.025):
                if isinstance(event, Failure):
                    raise RuntimeError(event.reason)
                if not isinstance(event, LeaseEvent):
                    raise RuntimeError('unexpected DHCP event')
                if event.kind == 'bound':
                    if bound:
                        raise RuntimeError('second bound event instead of renewal')
                    command([IP, 'address', 'add', str(event.lease.address), 'dev', CLIENT])
                    bound_counts = nft_counts(host, expected)
                    first_identity = manager.identity
                    bound = True
                elif event.kind == 'renew':
                    if not bound or manager.identity != first_identity:
                        raise RuntimeError('DHCP renewal changed client identity')
                    renewal = True
                if not manager.reply(event.event_id, True):
                    raise RuntimeError('private DHCP acknowledgment failed')
            if renewal:
                break
        if not bound or not renewal:
            raise RuntimeError('actual DHCP acquisition/renewal did not complete')
        after = nft_counts(host, expected)
        packets = guards.server_command(peer.process, {'command': 'report'})['counters']
        if (packets['discover'] < 1 or packets['select'] < 1 or packets['renew_unicast'] < 1
                or packets['rebind_broadcast'] != 0
                or bound_counts['dhcp_before'] != before['dhcp_before']
                or after['dhcp_before'] <= bound_counts['dhcp_before']
                or after['dhcp_after'] <= bound_counts['dhcp_after']):
            raise RuntimeError('DHCP raw/kernel path counters did not match')
        client_path = os.readlink('/proc/' + str(first_identity['client_pid']) + '/exe')
        if client_path != str(Path('/sbin/udhcpc').resolve()):
            raise RuntimeError('DHCP client is not installed BusyBox')
        record('raw_acquisition_and_same_client_unicast_renewal_without_daemon',
               server_packets=packets, before=before, after_bound=bound_counts, after_renewal=after,
               executable=client_path, same_client=True,
               receive_destination_evidence='IP_PKTINFO ipi_addr', unicast_ack_accepted=True)
        manager.stop()
        manager = None
        # The private fixture keeps the synthetic address for DNS probes only.
        for protocol in ('udp', 'tcp'):
            probe(executable, protocol)
        record('fresh_dns_denied_without_queue_consumer')
        v6_before = nft_counts(host, expected)
        if int(Path('/proc/sys/net/ipv6/conf/' + CLIENT + '/accept_dad').read_text()) < 1:
            raise RuntimeError('DAD is disabled on the private veth')
        command([IP, '-6', 'address', 'add', CLIENT_V6 + '/64', 'dev', CLIENT])
        tentative_seen = False
        end = time.monotonic() + 5
        while True:
            rows = json.loads(command([IP, '-j', '-6', 'address', 'show', 'dev', CLIENT]).stdout)
            value = next((a for a in rows[0]['addr_info'] if a['local'] == CLIENT_V6), None)
            if value is None or value.get('dadfailed'):
                raise RuntimeError('private DAD failed')
            tentative_seen |= bool(value.get('tentative'))
            if not value.get('tentative'):
                break
            if time.monotonic() >= end:
                raise RuntimeError('private DAD timed out')
            time.sleep(.025)
        dad_after = nft_counts(host, expected)
        if not tentative_seen or dad_after['ns255_after'] <= v6_before['ns255_after']:
            raise RuntimeError('real DAD did not traverse the hoplimit-255 exception')
        send_outcomes = []
        for hop in (255, 254):
            private_guard(host, expected)
            with socket.socket(socket.AF_INET6, socket.SOCK_RAW, socket.IPPROTO_ICMPV6) as sock:
                sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_UNICAST_HOPS, hop)
                sock.bind((CLIENT_V6, 0))
                packet = struct.pack('!BBHI16s', 135, 0, 0, 0, socket.inet_pton(socket.AF_INET6, SERVER_V6))
                try:
                    sent = sock.sendto(packet, (SERVER_V6, 0))
                    if sent != len(packet):
                        raise RuntimeError('short private NDP send')
                    send_outcomes.append({'hoplimit': hop, 'send_succeeded': True, 'errno': None})
                except OSError as caught:
                    if hop != 254 or caught.errno != errno.EPERM:
                        raise
                    send_outcomes.append({'hoplimit': hop, 'send_succeeded': False, 'errno': caught.errno})
            time.sleep(.1)
        ndp_after = nft_counts(host, expected)
        if (ndp_after['ns255_after'] <= dad_after['ns255_after']
                or ndp_after['ns254_before'] <= dad_after['ns254_before']
                or ndp_after['ns254_after'] != dad_after['ns254_after']):
            raise RuntimeError('NDP exception/non-exempt counters did not match')
        record('dad_and_ndp_exception_with_no_daemon', tentative_observed=tentative_seen,
               dad_counters=dad_after, ndp_counters=ndp_after, send_outcomes=send_outcomes,
               non255_is_not_universally_denied_with_other_application_rules=True)
        config = json.loads(config_source)
        config['Server']['Address'] = 'unix://' + str(PRIVATE / 'absent-gui.sock')
        config['Server']['LogFile'] = str(PRIVATE / 'daemon.log')
        config['Rules']['Path'] = str(rules)
        config['ProcMonitorMethod'] = 'proc'
        modules = PRIVATE / 'empty-ebpf'
        modules.mkdir(mode=0o700)
        config['Ebpf']['ModulesPath'] = str(modules)
        config['DefaultAction'], config['InterceptUnknown'], config['LogLevel'] = 'deny', True, 0
        config['FwOptions']['ConfigPath'] = str(PRIVATE / 'system-fw.json')
        (PRIVATE / 'system-fw.json').write_text('{"Enabled":false,"Version":1,"SystemRules":[]}\n')
        (PRIVATE / 'config.json').write_text(json.dumps(config))
        log = (PRIVATE / 'stdio.log').open('w')
        log_streams.append(log)
        # Child's environment is a fixed allowlist, extended only for this ABI.
        private_guard(host, expected)
        verify_module_barrier(modules)
        daemon = subprocess.Popen([DAEMON, '-config-file', str(PRIVATE / 'config.json')],
            stdin=subprocess.DEVNULL, stdout=log, stderr=log, cwd='/', start_new_session=True,
            env={**ENV, 'OPENSNITCH_EXTERNAL_OUTPUT_QUEUE': '1'})
        try:
            daemon_fd = os.pidfd_open(daemon.pid)
        except BaseException:
            daemon.kill()  # Still our unreaped direct child.
            daemon.wait(timeout=3)
            raise
        try:
            end = time.monotonic() + 5
            queue_path = Path('/proc/net/netfilter/nfnetlink_queue')
            while not queue_path.exists() or not queue_path.read_text().strip():
                if daemon.poll() is not None or time.monotonic() >= end:
                    raise RuntimeError('private OpenSnitch did not bind queue')
                time.sleep(.025)
            time.sleep(.3)
            for protocol in ('udp', 'tcp'):
                probe(executable, protocol)
            record('fresh_dns_denied_by_empty_opensnitch_policy')
            rule = {'name': 'allow-exact-dns', 'description': 'synthetic fixture only',
                    'created': '2026-09-07T00:00:00Z', 'updated': '2026-09-07T00:00:00Z',
                    'enabled': True, 'precedence': False, 'action': 'allow', 'duration': 'always',
                    'operator': {'type': 'list', 'operand': 'list', 'list': [
                        {'type': 'simple', 'operand': 'process.path', 'data': executable, 'sensitive': True},
                        {'type': 'simple', 'operand': 'user.id', 'data': '65534'},
                        {'type': 'regexp', 'operand': 'protocol', 'data': '^(tcp|udp)6?$'},
                        {'type': 'simple', 'operand': 'dest.port', 'data': '53'},
                        {'type': 'simple', 'operand': 'dest.ip', 'data': RESOLVER_A}]}}
            (rules / 'allow-exact-dns.json').write_text(json.dumps(rule))
            (rules / 'allow-exact-dns.json').chmod(0o600)
            time.sleep(.8)
            accepted = []
            for protocol in ('udp', 'tcp'):
                accepted.append(probe(executable, protocol, allowed=True))
                probe(executable, protocol, address=RESOLVER_B)
                probe(alternate, protocol)
                probe(executable, protocol, uid=0)
                # This server does not listen on 54: queue counters/daemon logs
                # are required before interpreting port mismatch as policy.
                accepted.append(probe(executable, protocol, allowed=True, nested=True))
            record('exact_dns_rule_allows_only_selected_executable_uid_resolver',
                   accepted=accepted, tested_transports=['udp', 'tcp'],
                   wrong_resolver_and_executable_and_uid_denied=True,
                   nested_pid_namespace_identity_matches=True)
            ruleset = json.loads(command([NFT, '-j', 'list', 'ruleset']).stdout)
            queues = [e['queue'] for row in ruleset['nftables'] for e in row.get('rule', {}).get('expr', []) if 'queue' in e]
            if len(queues) != 3 or any(q.get('num') != 0 or q.get('flags') for q in queues):
                raise RuntimeError('private queue number/bypass changed')
            signal.pidfd_send_signal(daemon_fd, signal.SIGKILL)
            daemon.wait(timeout=3)
            if queue_path.exists() and queue_path.read_text().strip():
                raise RuntimeError('private NFQUEUE consumer survived daemon death')
            for protocol in ('udp', 'tcp'):
                probe(executable, protocol)
            record('daemon_death_denies_fresh_dns', queue_count=len(queues), bypass=False,
                   remaining_queue_consumers=0)
        finally:
            if daemon.poll() is None:
                signal.pidfd_send_signal(daemon_fd, signal.SIGKILL)
                daemon.wait(timeout=3)
            os.close(daemon_fd)
            private_guard(host, expected)
            emit({'phase': 'module_barrier', **verify_module_barrier(modules, PRIVATE / 'daemon.log')})
        emit({'phase': 'complete', 'cases': cases,
              'actual_host_rule_files_used': False, 'host_packet_capture': False,
              'dhcp_applier_scope': 'synthetic fixture addresses only; separate owner proof required'})
    finally:
        if manager is not None:
            manager.stop()
        for child in reversed(children):
            child.close()
        for stream in log_streams:
            stream.close()
        for name in ('daemon.log', 'stdio.log'):
            path = PRIVATE / name
            if path.exists():
                emit({'phase': 'private_daemon_log', 'name': name, 'text': bounded_tail(path)})


def worker(fd):
    context = read_context(fd)
    host = context['host']
    expected = guards.guard_private(host, empty=True)
    if os.getpid() != 1:
        raise RuntimeError('packet worker must be a fresh namespace init')
    emit({'phase': 'guard_ready', 'namespaces': expected, 'token': context['token']})
    if not select.select([sys.stdin], [], [], 5)[0]:
        raise RuntimeError('controller did not release private worker')
    if json.loads(sys.stdin.readline()) != {'release': context['token']}:
        raise RuntimeError('private worker release token changed')
    # Read only public staged code/config before hiding /etc,/run,/tmp,/dev,/sys.
    config = (SCRIPT.parent / 'default-config.json').read_text()
    gate = (SCRIPT.parent / 'mbp-intel.nft').read_text()
    expected = guards.mount_private(host)
    # Also hide daemon cache/pid/log defaults, even though configured output is /run.
    guards.guard_private(host, expected)
    guards.checked(['/bin/mount', '-t', 'tmpfs', '-o', 'mode=0755',
                    'privacyctl-dhcp-fixture', '/var'], env=ENV)
    PRIVATE.mkdir(mode=0o755)
    seal = PRIVATE / 'seal.json'
    seal.write_text(json.dumps({'host': host, 'worker': expected}))
    seal.chmod(0o600)
    private_guard(host, expected)
    # Helpers use fixed /usr/local/lib imports and require root-owned ancestors.
    # Copy only code into private mounts, as the existing owner fixture does.
    for prefix in ('lib', 'libexec'):
        checked_private(host, expected, ['/bin/mount', '-t', 'tmpfs', '-o', 'mode=0755',
                                        'privacyctl-packet-code', '/usr/local/' + prefix])
    destination = Path('/usr/local/lib/privacyctl_runtime')
    destination.mkdir(mode=0o755)
    for path in (LIBRARY / 'privacyctl_runtime').glob('*.py'):
        target = destination / path.name
        target.write_bytes(path.read_bytes())
        target.chmod(0o644)
    for name in ('privacyctl-dhcp-launch', 'privacyctl-dhcp-event'):
        target = Path('/usr/local/libexec') / name
        target.write_bytes((RADIO / 'root/usr/local/libexec' / name).read_bytes())
        target.chmod(0o755)
    os.close(fd)
    emit({'phase': 'namespace_ready', 'namespaces': expected})
    # Production DHCP deliberately rejects PID1 as its owner. Keep this fresh
    # namespace init as supervisor; only its direct child owns DHCP and probes.
    private_guard(host, expected)
    driver = os.fork()
    if driver == 0:
        if os.getpid() <= 1:
            raise RuntimeError('case driver must not be namespace init')
        emit({'phase': 'case_driver_ready', 'pid': os.getpid(), 'namespaces': expected})
        run_cases(host, expected, config, gate)
        os._exit(0)
    try:
        driver_fd = os.pidfd_open(driver)
    except BaseException:
        os.kill(driver, signal.SIGKILL)  # Unreaped direct child; SIGCHLD is DFL.
        os.waitpid(driver, 0)
        raise
    reaped = False
    try:
        if not select.select([driver_fd], [], [], MAX_SECONDS - 5)[0]:
            raise RuntimeError('private case driver exceeded its deadline')
        _, status = os.waitpid(driver, 0)
        reaped = True
        if not os.WIFEXITED(status) or os.WEXITSTATUS(status) != 0:
            raise RuntimeError('private case driver failed')
    finally:
        private_guard(host, expected)
        try:
            if not reaped:
                try:
                    signal.pidfd_send_signal(driver_fd, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                os.waitpid(driver, 0)
        finally:
            os.close(driver_fd)


def launch(fd):
    context = read_context(fd)
    parent = context['parent']
    if os.getppid() != parent['pid'] or guards.process_identity(parent['pid'])['start_time'] != parent['start_time']:
        raise RuntimeError('fixture controller changed before launch')
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'fixture launcher parent-death setup failed')
    if os.getppid() != parent['pid']:
        raise RuntimeError('fixture controller died during launch')
    os.set_inheritable(fd, True)
    os.execve('/usr/bin/unshare', ['/usr/bin/unshare', '--net', '--mount', '--pid', '--fork',
        '--kill-child=KILL', '--propagation', 'unchanged', PYTHON, '-I', str(SCRIPT),
        '--worker-fd', str(fd)], ENV)


def host_fingerprint():
    value = guards.host_snapshot()
    for family in ('-4', '-6'):
        rows = json.loads(guards.checked([IP, '-j', family, 'route', 'show', 'table', 'all']).stdout)
        value[family + '_routes_digest'] = hashlib.sha256(json.dumps(guards.normalized(rows), sort_keys=True).encode()).hexdigest()
    rules = json.loads(guards.checked([NFT, '-j', 'list', 'ruleset']).stdout)
    def stable(x):
        if isinstance(x, dict):
            return {k: stable(v) for k, v in x.items() if k not in ('counter', 'metainfo')}
        if isinstance(x, list):
            return [stable(v) for v in x if not isinstance(v, dict) or set(v) not in ({'counter'}, {'metainfo'})]
        return x
    value['firewall_digest'] = hashlib.sha256(json.dumps(stable(rules), sort_keys=True).encode()).hexdigest()
    value['private_rules_digest'] = hashlib.sha256(b''.join(hashlib.sha256(p.read_bytes()).digest()
        for p in sorted(Path('/etc/opensnitchd/rules').glob('*.json')))).hexdigest()
    return value


def controller(output):
    if os.geteuid() != 0 or not output.is_absolute() or output.exists():
        raise RuntimeError('controller requires root and a new absolute output directory')
    source_paths = [SCRIPT, GUARD_FILE, *(SCRIPT.parent / name for name in ('mbp-intel.nft', 'default-config.json', 'system-fw.json')),
                    Path(DAEMON), Path(NFT), Path('/bin/busybox'),
                    *(LIBRARY / 'privacyctl_runtime' / name for name in ('__init__.py', 'dhcp.py', 'lease.py', 'launch.py', 'hook.py')),
                    RADIO / 'root/usr/local/libexec/privacyctl-dhcp-launch', RADIO / 'root/usr/local/libexec/privacyctl-dhcp-event']
    hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
    before = host_fingerprint()
    output.mkdir(mode=0o700)
    path = output / 'evidence.json'
    context = {'host': before['namespaces'], 'parent': guards.process_identity(os.getpid()), 'token': secrets.token_hex(16)}
    fd = os.memfd_create('radio-packet-context', os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    os.write(fd, json.dumps(context).encode())
    fcntl.fcntl(fd, fcntl.F_ADD_SEALS, SEALS)
    old_sigchld = signal.signal(signal.SIGCHLD, signal.SIG_DFL)
    process, launcher_fd, worker_fd = None, None, None
    messages, namespace_ids, error = [], set(), ''
    raw = {'stdout': bytearray(), 'stderr': bytearray()}

    def persist(evidence):
        with path.open('w') as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(evidence, stream, indent=2)
            stream.write('\n')
    started = time.monotonic()
    try:
        process = subprocess.Popen([PYTHON, '-I', str(SCRIPT), '--launch-fd', str(fd)], pass_fds=(fd,),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd='/', env=ENV, start_new_session=True)
        launcher_fd = os.pidfd_open(process.pid)
        selector = selectors.DefaultSelector()
        buffers = {'stdout': b'', 'stderr': b''}
        total = 0
        for name in buffers:
            stream = getattr(process, name)
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, name)
        try:
            while selector.get_map():
                if time.monotonic() - started >= MAX_SECONDS:
                    raise RuntimeError('packet proof watchdog deadline exceeded')
                for key, _ in selector.select(.05):
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    raw[key.data].extend(chunk[:max(0, 1048576 - total)])
                    total += len(chunk)
                    if total > 1048576:
                        raise RuntimeError('packet proof output exceeded bound')
                    buffers[key.data] += chunk
                    if key.data == 'stderr':
                        continue
                    while b'\n' in buffers['stdout']:
                        line, buffers['stdout'] = buffers['stdout'].split(b'\n', 1)
                        message = json.loads(line)
                        messages.append(message)
                        if 'namespaces' in message:
                            namespace_ids.update(message['namespaces'].values())
                        if message.get('phase') == 'guard_ready':
                            if worker_fd is not None or message['token'] != context['token']:
                                raise RuntimeError('worker handshake repeated or token changed')
                            children = Path(f'/proc/{process.pid}/task/{process.pid}/children').read_text().split()
                            if len(children) != 1:
                                raise RuntimeError('worker init identity is ambiguous')
                            worker_pid = int(children[0])
                            worker_fd = os.pidfd_open(worker_pid)
                            actual = {k: os.readlink(f'/proc/{worker_pid}/ns/{k}') for k in ('net', 'mnt', 'pid')}
                            if actual != message['namespaces'] or any(actual[k] == before['namespaces'][k] for k in actual):
                                raise RuntimeError('worker is not in three private namespaces')
                            process.stdin.write(json.dumps({'release': context['token']}).encode() + b'\n')
                            process.stdin.flush()
            process.wait(timeout=3)
        finally:
            selector.close()
    except BaseException as caught:
        error = type(caught).__name__ + ': ' + str(caught)
    finally:
        try:
            if process is not None:
                for handle in (worker_fd, launcher_fd):
                    if handle is not None:
                        try:
                            signal.pidfd_send_signal(handle, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                if launcher_fd is None and process.poll() is None:
                    process.kill()  # Direct child remains unreaped; SIGCHLD is DFL.
                try:
                    process.wait(timeout=3)
                    for handle in (worker_fd, launcher_fd):
                        if handle is not None and not select.select([handle], [], [], 3)[0]:
                            raise RuntimeError('fixture process did not exit')
                finally:
                    for stream in (process.stdin, process.stdout, process.stderr):
                        if stream is not None:
                            stream.close()
        except BaseException as caught:
            error += ('; ' if error else '') + 'cleanup ' + type(caught).__name__ + ': ' + str(caught)
        finally:
            for handle in (worker_fd, launcher_fd, fd):
                if handle is not None:
                    try:
                        os.close(handle)
                    except OSError as caught:
                        error += '; close: ' + str(caught)
            signal.signal(signal.SIGCHLD, old_sigchld)
            evidence = {'status': 'failed', 'source_sha256': hashes,
                'error': error, 'messages': messages,
                'worker_stdout_raw': raw['stdout'].decode('utf-8', 'replace'),
                'worker_stderr': raw['stderr'].decode('utf-8', 'replace'),
                'elapsed_seconds': time.monotonic() - started,
                'verified_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
            persist(evidence)
    passed = False
    try:
        after = host_fingerprint()
        remaining = []
        for proc in Path('/proc').glob('[0-9]*'):
            for kind in ('net', 'mnt', 'pid'):
                try:
                    if os.readlink(proc / 'ns' / kind) in namespace_ids:
                        remaining.append({'pid': int(proc.name), 'kind': kind})
                except OSError:
                    pass
        stable = hashes == {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
        complete = any(m.get('phase') == 'complete' for m in messages)
        passed = bool(process is not None and process.returncode == 0 and complete and namespace_ids
                      and not error and before == after and stable and not remaining)
        evidence.update(status='passed' if passed else 'failed', source_unchanged=stable,
            host_state_unchanged=before == after,
            host_checks={key: before[key] == after[key] for key in before},
            remaining_namespace_members=remaining)
    except BaseException as caught:
        evidence['error'] += ('; ' if evidence['error'] else '') + 'aggregation ' + type(caught).__name__ + ': ' + str(caught)
    persist(evidence)
    emit({'status': evidence['status'], 'evidence': str(path)})
    if not passed:
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--output', type=Path)
    modes.add_argument('--worker-fd', type=int)
    modes.add_argument('--launch-fd', type=int)
    modes.add_argument('--server', nargs=2)
    args = parser.parse_args()
    if args.output is not None:
        if os.geteuid() != 0:
            raise SystemExit(subprocess.run(['doas', '-n', PYTHON, '-I', str(SCRIPT), '--output',
                                            str(args.output.absolute())], env=ENV).returncode)
        controller(args.output)
    elif args.launch_fd is not None:
        launch(args.launch_fd)
    elif args.worker_fd is not None:
        try:
            worker(args.worker_fd)
        except BaseException as caught:
            diagnostic = {'phase': 'failed', 'traceback': traceback.format_exc()}
            if isinstance(caught, subprocess.CalledProcessError):
                diagnostic['command_stderr'] = (caught.stderr or '')[-16000:]
            emit(diagnostic)
            raise
    else:
        server(*(json.loads(value) for value in args.server))


if __name__ == '__main__':
    main()
