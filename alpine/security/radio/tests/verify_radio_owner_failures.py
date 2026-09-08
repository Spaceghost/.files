#!/usr/bin/env python3
"""Combined owner fault tests confined to private net/mount/PID namespaces.

The production runner/guardian, CLI main/IPC/emergency routes, DHCP client and
lease applier are real. The CLI entrypoint, WPA and physical radio System are
guarded fixture substitutes. A real contained command pauses before resolver
publication, with the production command/check/deadline path intact. The optional
survivor case deliberately suppresses only its guarded native init parent-death
signal to exercise real new-observer recovery with detached and nested children.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import socket
import stat
import subprocess
import sys
import time
import traceback


SCRIPT = Path(__file__).resolve()
import importlib.util
spec = importlib.util.spec_from_file_location('owner_fault_base', SCRIPT.with_name('verify_radio_owner.py'))
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
guards, native = base.guards, base.native
PRIVATE, RUNTIME, ROOT = base.PRIVATE, base.RUNTIME, base.ROOT
FAULTS = PRIVATE / 'faults'
PYTHON, IP, CLI = base.PYTHON, base.IP, base.CLI
STATE = Path('/var/lib/privacyctl')
PRIOR_ALIAS = b'privacyctl fixture previous alias \xff'
_BASE_FIXTURE_GUARD = base.fixture_guard


def guard_private_var():
    mounts = {}
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        before, after = line.split(' - ', 1)
        mounts[before.split()[4]] = after.split()[:2]
    if (mounts.get('/var') != ['tmpfs', 'privacyctl-dhcp-fixture']
            or any(target.startswith('/var/') for target in mounts)):
        raise RuntimeError('host persistent state is not hidden by the private /var mount')


def fixture_guard(host, expected):
    _BASE_FIXTURE_GUARD(host, expected)
    guard_private_var()


# Base FakeSystem calls its own module global: wrap that too, so every inherited
# radio/owner guard in these processes also checks persistent-state isolation.
base.fixture_guard = fixture_guard


def snapshot_state_directory():
    """Read only the fixed journal subtree; emit a digest, never names/content."""
    digest = hashlib.sha256()
    counts = [0, 0]

    def visit(directory, depth):
        if depth > 4:
            raise RuntimeError('host journal snapshot exceeds depth bound')
        names = []
        with os.scandir(directory) as entries:
            for entry in entries:
                counts[0] += 1
                if counts[0] > 64:
                    raise RuntimeError('host journal snapshot exceeds entry bound')
                names.append(entry.name)
        for name in sorted(names):
            info = os.stat(name, dir_fd=directory, follow_symlinks=False)
            digest.update(os.fsencode(name) + b'\0')
            digest.update(repr((info.st_dev, info.st_ino, info.st_mode, info.st_uid,
                                info.st_gid, info.st_nlink, info.st_size, info.st_mtime_ns)).encode())
            if stat.S_ISDIR(info.st_mode):
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                dir_fd=directory)
                try:
                    visit(child, depth + 1)
                finally:
                    os.close(child)
            elif stat.S_ISREG(info.st_mode):
                if info.st_size > 65536 or counts[1] + info.st_size > 1048576:
                    raise RuntimeError('host journal snapshot exceeds byte bound')
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                             dir_fd=directory)
                with os.fdopen(fd, 'rb') as stream:
                    opened = os.fstat(stream.fileno())
                    if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                        raise RuntimeError('host journal snapshot identity changed')
                    content = stream.read(65537)
                    after = os.fstat(stream.fileno())
                unchanged = all(getattr(after, key) == getattr(opened, key) for key in
                                ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid',
                                 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))
                if len(content) > 65536 or not unchanged:
                    raise RuntimeError('host journal snapshot changed or exceeded bound')
                counts[1] += len(content)
                if counts[1] > 1048576:
                    raise RuntimeError('host journal snapshot exceeds byte bound')
                digest.update(content)
            elif stat.S_ISLNK(info.st_mode):
                digest.update(os.fsencode(os.readlink(name, dir_fd=directory)))

    try:
        info = STATE.lstat()
    except FileNotFoundError:
        return {'exists': False}
    digest.update(repr((info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
                        info.st_nlink, info.st_size, info.st_mtime_ns)).encode())
    if stat.S_ISDIR(info.st_mode):
        fd = os.open(STATE, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            opened = os.fstat(fd)
            if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                raise RuntimeError('host journal directory changed during snapshot')
            visit(fd, 0)
        finally:
            os.close(fd)
    elif stat.S_ISLNK(info.st_mode):
        digest.update(os.fsencode(os.readlink(STATE)))
    else:
        raise RuntimeError('host journal path is not a directory or symlink')
    return {'exists': True, 'sha256': digest.hexdigest()}


def append_event(kind, **fields):
    data = json.dumps({'kind': kind, 'pid': os.getpid(),
                       'at_boottime': time.clock_gettime(time.CLOCK_BOOTTIME), **fields}) + '\n'
    fd = os.open(FAULTS / 'events.jsonl', os.O_WRONLY | os.O_APPEND | os.O_CREAT |
                 os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        if len(data.encode()) > 8192 or os.write(fd, data.encode()) != len(data.encode()):
            raise RuntimeError('fixture event is too large or incomplete')
    finally:
        os.close(fd)


def read_json(path, default=None):
    try:
        with path.open() as stream:
            raw = stream.read(65537)
        if len(raw) > 65536:
            raise RuntimeError('fixture record exceeds its bound')
        return json.loads(raw)
    except FileNotFoundError:
        return default


def read_tail(path, limit):
    with path.open('rb') as stream:
        stream.seek(0, os.SEEK_END)
        stream.seek(max(0, stream.tell() - limit))
        return stream.read(limit).decode('utf-8', errors='replace')


def namespace_records(messages):
    """Normalize the single-record and accumulated-record helper messages."""
    result = []
    for message in messages:
        if message.get('phase') != 'namespace_ready':
            continue
        rows = message['namespaces']
        if isinstance(rows, dict):
            rows = [rows]
        if not isinstance(rows, list):
            raise ValueError('invalid namespace message shape')
        for row in rows:
            if (not isinstance(row, dict) or set(row) != {'net', 'mnt', 'pid'}
                    or any(not isinstance(value, str) for value in row.values())):
                raise ValueError('invalid namespace identity record')
            result.append(row)
    return result


def process_record(pid):
    value = guards.process_identity(pid)
    if value is None:
        raise RuntimeError('fixture process disappeared before its identity was captured')
    return {**value, 'namespaces': {kind: os.readlink(f'/proc/{pid}/ns/{kind}')
                                  for kind in ('net', 'mnt', 'pid')}}


class Handle:
    """Only a live process with the recorded private identity may be signalled."""
    def __init__(self, record, host, expected, *, moving_server=False):
        base.fixture_guard(host, expected)
        current = process_record(record['pid'])
        if (current['start_time'] != record['start_time']
                or (not moving_server and current['namespaces'] != record['namespaces'])
                or (not moving_server and current['namespaces']['net'] != expected['net'])
                or any(current['namespaces'][kind] == host[kind] for kind in host)):
            raise RuntimeError('refusing a changed or nonprivate process identity')
        if moving_server:
            # Only the direct server child may move from its inherited private
            # netns to another fresh netns during its readiness handshake.
            fields = Path(f"/proc/{record['pid']}/stat").read_text().rsplit(') ', 1)[1].split()
            if (int(fields[1]) != os.getpid()
                    or any(current['namespaces'][kind] != expected[kind] for kind in ('mnt', 'pid'))):
                raise RuntimeError('server is not our direct child in the expected private namespaces')
        self.fd = os.pidfd_open(record['pid'])
        self.record, self.host, self.expected = record, host, expected
        try:
            again = process_record(record['pid'])
            if (again['start_time'] != record['start_time']
                    or (not moving_server and again['namespaces'] != record['namespaces'])
                    or any(again['namespaces'][kind] == host[kind] for kind in host)):
                raise RuntimeError('process changed while opening its pidfd')
        except BaseException:
            os.close(self.fd)
            raise

    def dead(self):
        return bool(select.select([self.fd], [], [], 0)[0])

    def send(self, signum):
        base.fixture_guard(self.host, self.expected)
        signal.pidfd_send_signal(self.fd, signum)

    def wait(self, timeout=4):
        if not select.select([self.fd], [], [], timeout)[0]:
            raise RuntimeError('owned process remained alive beyond its deadline')

    def close(self):
        os.close(self.fd)


def fake_wpa(host, expected):
    base.fixture_guard(host, expected)
    selected, associated = None, False
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as server:
        server.bind('/run/wpa_supplicant/wlan0')
        server.settimeout(.025)
        base.write_private(FAULTS / 'wpa-ready.json', {'ready': True})
        while True:
            base.fixture_guard(host, expected)
            try:
                raw, peer = server.recvfrom(4096)
            except TimeoutError:
                continue
            command = raw.decode('ascii')
            fault = read_json(FAULTS / 'fault.json')
            response = 'OK\n'
            if command in ('DISCONNECT', 'DISABLE_NETWORK all'):
                associated = False
            elif command == 'SELECT_NETWORK 1':
                selected = 1
            elif command == 'RECONNECT':
                append_event('wpa_reconnect')
                associated = True
            elif command == 'LIST_NETWORKS':
                response = 'network id / ssid / bssid / flags\n1\tshmecklebucket\tany\t\n'
            elif command == 'STATUS':
                if fault['mode'] == 'wpa-unanswered':
                    base.write_private(FAULTS / 'wpa-unanswered.json', {'attempt': fault['attempt']})
                    continue
                blocked = read_json(PRIVATE / 'radios.json')['wifi_blocked']
                response = ('wpa_state=COMPLETED\nid=1\nssid=shmecklebucket\n'
                            if associated and selected and not blocked else 'wpa_state=DISCONNECTED\n')
            elif command not in ('ATTACH', 'ENABLE_NETWORK 1'):
                raise RuntimeError('unexpected synthetic WPA command')
            try:
                server.sendto(response.encode('ascii'), peer)
            except (FileNotFoundError, ConnectionRefusedError):
                # A cancelled owner closes this exact private endpoint.
                pass


# Executed ONLY through NativeNetwork's production contained-command launcher.
# Its original-proc fd and host-PID value are provided by the trusted handshake.
PAUSE_COMMAND = r'''import json,os,time
from pathlib import Path
root=Path('/run/privacyctl-fixture/faults')
fault=json.loads((root/'fault.json').read_text())
pid=int(os.environ['OPENRESOLV_HOST_PID'])
proc='/proc/self/fd/'+os.environ['OPENRESOLV_HOST_PROC_FD']
fields=Path(proc+'/'+str(pid)+'/stat').read_text().rsplit(') ',1)[1].split()
record={'pid':pid,'start_time':fields[19],
        'namespaces':{k:os.readlink('/proc/self/ns/'+k) for k in ('net','mnt','pid')},
        'attempt':fault['attempt'],'at_boottime':time.clock_gettime(time.CLOCK_BOOTTIME)}
fd=os.open(root/'pause-tmp.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as stream: json.dump(record,stream)
os.replace(root/'pause-tmp.json',root/'pause-ready.json')
while not (root/('release-'+fault['attempt'])).exists(): time.sleep(.005)
'''


def fixture_cli(host, expected, arguments):
    """Run the real CLI routes with the guardian's guarded radio substitute."""
    base.fixture_guard(host, expected)
    if type(arguments) is not list or arguments not in (['off'], ['connect', base.HOME_PROFILE]):
        raise RuntimeError('invalid fixed fixture CLI arguments')
    legacy = base.load(CLI, 'fault_cli_privacyctl')

    class CLISystem(base.FakeSystem):
        def __init__(self):
            base.fixture_guard(host, expected)
            super().__init__(host, expected)

        def block_all(self):
            super().block_all()
            append_event('cli_emergency_block')

    legacy.System = CLISystem
    return legacy.main(arguments)


def survivor_guard(host, expected, *, require_init):
    """Accept only descendants of the sealed, device-masked native fixture."""
    import fcntl
    current = guards.guard_private(host)
    if (current['net'] != expected['net'] or current['pid'] == expected['pid']
            or current['mnt'] == expected['mnt'] or (require_init and os.getpid() != 1)
            or os.readlink('/proc/self') != str(os.getpid())
            or os.readlink('/proc/1/ns/pid') != current['pid']):
        raise RuntimeError('survivor is not in the expected private child namespaces')
    info = (PRIVATE / 'seal.json').lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
            or stat.S_IMODE(info.st_mode) != 0o600
            or read_json(PRIVATE / 'seal.json') != {'host': host, 'expected': expected}):
        raise RuntimeError('survivor private fixture seal changed')
    mounts = {}
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        before, after = line.split(' - ', 1)
        fields = before.split()
        if any(value.startswith('shared:') for value in fields[6:]):
            raise RuntimeError('survivor inherited a shared mount')
        mounts[fields[4]] = after.split()[:2]
    if (any(mounts.get(path) != ['tmpfs', 'privacyctl-dhcp-fixture']
            for path in ('/etc', '/run', '/var', '/dev', '/sys'))
            or any(path.startswith('/var/') for path in mounts)
            or Path('/dev/rfkill').exists() or Path('/sys/class/rfkill').exists()):
        raise RuntimeError('survivor host configuration or devices are not hidden')
    value = os.environ.get('OPENRESOLV_HOST_PROC_FD', '')
    if not value.isascii() or not value.isdigit() or not 3 <= int(value) <= 1048576:
        raise RuntimeError('survivor original proc descriptor is missing')
    descriptor = int(value)
    proc = f'/proc/self/fd/{descriptor}'
    if (not stat.S_ISDIR(os.fstat(descriptor).st_mode)
            or fcntl.fcntl(descriptor, fcntl.F_GETFL) & os.O_ACCMODE != os.O_RDONLY
            or os.readlink(proc + '/1/ns/pid') != expected['pid']
            or os.readlink(proc + '/self/ns/net') != expected['net']):
        raise RuntimeError('survivor original observer proc view changed')
    return descriptor, current


def allow_survival(host, expected):
    # Explicit fault injection after the production execution gate. Do not
    # alter the outer fixture init/timeout or any other process's signal state.
    descriptor, current = survivor_guard(host, expected, require_init=True)
    if os.readlink(f'/proc/self/fd/{descriptor}/self') != os.environ.get('OPENRESOLV_HOST_PID'):
        raise RuntimeError('survivor gate PID does not match its original observer identity')
    import ctypes
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, 0, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'survivor parent-death suppression failed')
    value = ctypes.c_int(-1)
    if libc.prctl(2, ctypes.byref(value), 0, 0, 0) != 0 or value.value != 0:
        raise OSError(ctypes.get_errno(), 'survivor parent-death suppression was not verified')
    return descriptor, current


def survivor_record(descriptor, pid=None):
    proc = f'/proc/self/fd/{descriptor}'
    if pid is None:
        pid = int(os.readlink(proc + '/self'))
    with open(proc + '/' + str(pid) + '/stat') as stream:
        value = stream.read(8193)
    if len(value) > 8192:
        raise RuntimeError('survivor stat exceeds bound')
    fields = value.rsplit(') ', 1)[1].split()
    return {'pid': pid, 'start_time': fields[19], 'session': int(fields[3]),
            'parent_pid': int(fields[1]),
            'namespaces': {kind: os.readlink(proc + '/' + str(pid) + '/ns/' + kind)
                           for kind in ('net', 'mnt', 'pid')}}


def survivor_child(host, expected, role):
    if role not in ('detached', 'nested-launcher', 'nested-init'):
        raise RuntimeError('invalid fixed survivor child role')
    descriptor, _ = survivor_guard(host, expected, require_init=role == 'nested-init')
    attempt = read_json(FAULTS / 'fault.json')['attempt']
    if role == 'nested-launcher':
        os.set_inheritable(descriptor, True)
        os.execv('/usr/bin/unshare', ['/usr/bin/unshare', '--mount', '--propagation', 'private',
            '--pid', '--fork', '--kill-child=KILL', '--mount-proc', PYTHON, '-I', str(SCRIPT),
            '--survivor-child', json.dumps(host), json.dumps(expected), 'nested-init'])
    record = survivor_record(descriptor)
    if role == 'nested-init':
        # unshare changed the launcher's mount namespace before this fork;
        # capture its final identity now, not the bootstrap's pre-exec view.
        base.write_private(FAULTS / 'survivor-nested-launcher.json',
                           {'attempt': attempt, 'record': survivor_record(descriptor, record['parent_pid'])})
    base.write_private(FAULTS / ('survivor-' + role + '.json'),
                       {'attempt': attempt, 'record': record})
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        time.sleep(.025)
    raise RuntimeError('survivor child outlived its bounded proof window')


def survivor_payload(host, expected):
    descriptor, _ = allow_survival(host, expected)
    record = survivor_record(descriptor)
    if str(record['pid']) != os.environ.get('OPENRESOLV_HOST_PID'):
        raise RuntimeError('survivor gate PID does not match its original observer identity')
    if os.fork() == 0:
        try:
            os.setsid()
            survivor_child(host, expected, 'detached')
        finally:
            os._exit(113)
    nested = subprocess.Popen([PYTHON, '-I', str(SCRIPT), '--survivor-child',
        json.dumps(host), json.dumps(expected), 'nested-launcher'], pass_fds=(descriptor,),
        stdin=subprocess.DEVNULL)
    # The original init owns both branches. Parent-namespace init completion
    # must tear down even setsid and the nested PID namespace before readiness.
    attempt = read_json(FAULTS / 'fault.json')['attempt']
    deadline = time.monotonic() + 30
    children = []
    while time.monotonic() < deadline:
        if not children:
            rows = [read_json(FAULTS / ('survivor-' + role + '.json'), {})
                    for role in ('detached', 'nested-launcher', 'nested-init')]
            if all(row.get('attempt') == attempt for row in rows):
                children = [row['record'] for row in rows]
                if (children[0]['session'] != children[0]['pid']
                        or children[0]['namespaces']['pid'] != record['namespaces']['pid']
                        or children[2]['namespaces']['pid'] == record['namespaces']['pid']
                        or children[0]['parent_pid'] != record['pid']
                        or children[1]['parent_pid'] != record['pid']
                        or children[2]['parent_pid'] != children[1]['pid']):
                    raise RuntimeError('survivor descendant topology changed')
                base.write_private(FAULTS / 'survivor-ready.json',
                                   {'attempt': attempt, 'init': record, 'descendants': children,
                                    'at_boottime': time.clock_gettime(time.CLOCK_BOOTTIME)})
        if nested.poll() is not None:
            raise RuntimeError('nested survivor launcher exited early')
        time.sleep(.005)
    raise RuntimeError('survivor init outlived its bounded proof window')


class SurvivorBarrier:
    """Observe the real drain; never substitute process completion or signals."""
    def __init__(self, proof, host, expected, invocation):
        base.fixture_guard(host, expected)
        self.proof, self.invocation = proof, invocation
        self.handles, self.drained = [], False
        self.observer = process_record(os.getpid())
        if ((self.observer['pid'], self.observer['start_time']) ==
                (proof['old_owner']['pid'], proof['old_owner']['start_time'])):
            raise RuntimeError('survivor proof requires a new observer')
        if len(proof['descendants']) != 3:
            raise RuntimeError('survivor proof needs exactly three descendant handles')
        if (proof['init']['pid'] != proof['writer']['pid']
                or len({row['pid'] for row in (proof['init'], *proof['descendants'])}) != 4):
            raise RuntimeError('survivor proof requires four distinct original identities')
        try:
            for record in (proof['init'], *proof['descendants']):
                self.handles.append(Handle(record, host, expected))
            if any(handle.dead() for handle in self.handles):
                raise RuntimeError('all survivor processes must be alive at new observer entry')
            from privacyctl_runtime.writers import capture_writer
            captured = capture_writer(proof['writer']['pid'], self.handles[0].fd,
                                      proof['writer']['operation'])
            if captured != proof['writer']:
                raise RuntimeError('survivor no longer matches the durable writer record')
            append_event('surviving_writer_recovery_entry', invocation=invocation,
                         observer=self.observer, writer=proof['writer'], descendants=proof['descendants'],
                         all_original_pidfds_live=True)
        except BaseException:
            self.close()
            raise

    def drain(self, record, actual, **kwargs):
        if record != self.proof['writer']:
            return actual(record, **kwargs)
        if any(handle.dead() for handle in self.handles):
            raise RuntimeError('survivor died before real drain entry')
        outcome = actual(record, **kwargs)
        if outcome != 'killed' or any(not handle.dead() for handle in self.handles):
            raise RuntimeError('real drain did not kill init and complete every descendant')
        self.drained = True
        append_event('surviving_writer_drained', invocation=self.invocation,
                     observer=self.observer, outcome=outcome, all_original_pidfds_ready=True)
        return outcome

    def require_drained(self):
        if not self.drained or any(not handle.dead() for handle in self.handles):
            raise RuntimeError('native cleanup attempted before survivor namespace completion')

    def close(self):
        for handle in self.handles:
            handle.close()
        self.handles = []


def measure_call(counter, callback, *args, **kwargs):
    """Keep bounded aggregate timings, including failed calls, only in memory."""
    started = time.monotonic()
    counter['writes' if 'writes' in counter else 'calls'] += 1
    try:
        return callback(*args, **kwargs)
    except BaseException:
        counter['failures'] += 1
        raise
    finally:
        elapsed = time.monotonic() - started
        counter['total_seconds'] += elapsed
        counter['max_seconds'] = max(counter['max_seconds'], elapsed)


def guardian(host, expected, invocation, journal_delay_ms=0):
    base.fixture_guard(host, expected)
    if len(invocation) != 32 or any(value not in '0123456789abcdef' for value in invocation):
        raise RuntimeError('invalid fixture guardian invocation')
    if type(journal_delay_ms) is not int or journal_delay_ms not in (0, 50):
        raise RuntimeError('invalid fixed journal delay')
    sys.path.insert(0, '/usr/local/lib')
    from privacyctl_runtime import runner, adapter, journal, network, recovery
    from privacyctl_runtime.adapter import NativeAdapter
    from privacyctl_runtime.network import NativeNetwork
    from privacyctl_runtime.dhcp import DHCPManager
    from privacyctl_runtime.service import Owner
    legacy = base.load(CLI, 'fault_native_privacyctl')
    active_owner = [None]
    timing = {'journal_delay_ms': journal_delay_ms, 'journal_backing': 'private-tmpfs'}
    for name in ('journal_write', 'native_command', 'snapshot', 'apply', 'remove', 'remove_recovered',
                 'startup_recovery', 'wrapper_prepare', 'wrapper_remove'):
        timing[name] = {'writes' if name == 'journal_write' else 'calls': 0,
                        'failures': 0, 'total_seconds': 0.0, 'max_seconds': 0.0}

    class ObservedJournal(journal.Journal):
        def write(self, record):
            write = super().write

            def delayed_write():
                if journal_delay_ms == 50:
                    time.sleep(.05)
                return write(record)

            return measure_call(timing['journal_write'], delayed_write)

    class ObservedApplier(network.LeaseApplier):
        def apply(self, *args, **kwargs):
            return measure_call(timing['apply'], super().apply, *args, **kwargs)

        def remove(self, *args, **kwargs):
            return measure_call(timing['remove'], super().remove, *args, **kwargs)

        def remove_recovered(self, *args, **kwargs):
            return measure_call(timing['remove_recovered'], super().remove_recovered, *args, **kwargs)

    class ObservedWrapper(adapter.JournaledApplier):
        def prepare(self):
            return measure_call(timing['wrapper_prepare'], super().prepare)

        def remove(self, owned):
            return measure_call(timing['wrapper_remove'], super().remove, owned)

    def export(owner):
        pending = []
        for peer in owner.dhcp._pending.values():
            try:
                pending.append(process_record(peer.pid))
            except (OSError, RuntimeError):
                pending.append({'pid': peer.pid, 'already_exited': True})
        value = {'invocation': invocation, 'phase': owner.phase, 'generation': owner.generation,
                 'profile': owner.profile, 'error': owner._error, 'client': owner.dhcp.identity,
                 'dhcp_phase': owner.dhcp.phase, 'expiry': owner.dhcp.expiry,
                 'dirty': (RUNTIME / 'lease-dirty').exists(), 'hooks': pending,
                 'owned': None if owner.owned is None else owner.owned.to_dict(), 'timing': timing,
                 'first_latch_timing': owner._first_latch_timing}
        base.write_private(FAULTS / ('state-' + invocation + '.json'), value)

    class ObservedSystem(base.FakeSystem):
        def block_all(self):
            super().block_all()
            append_event('blocked', invocation=invocation)

    class PausedNetwork(NativeNetwork):
        survivor_barrier = None

        def _run(self, *args, **kwargs):
            if self.survivor_barrier is not None:
                self.survivor_barrier.require_drained()
            return measure_call(timing['native_command'], super()._run, *args, **kwargs)

        def snapshot(self, *args, **kwargs):
            return measure_call(timing['snapshot'], super().snapshot, *args, **kwargs)

        @staticmethod
        def _stop_command(process, descriptors):
            try:
                append_event('native_command_stop', invocation=invocation, child_pid=process.pid)
            finally:
                NativeNetwork._stop_command(process, descriptors)

        def set_provider(self, key, content, **options):
            fault = read_json(FAULTS / 'fault.json')
            if fault['mode'] == 'apply-paused':
                base.fixture_guard(host, expected)
                export(active_owner[0])
                self._run([PYTHON, '-I', '-S', '-c', PAUSE_COMMAND], **options)
            elif fault['mode'] == 'apply-survivor-paused':
                base.fixture_guard(host, expected)
                export(active_owner[0])
                self._run([PYTHON, '-I', str(SCRIPT), '--survivor',
                           json.dumps(host), json.dumps(expected)], operation='native-survivor', **options)
            return super().set_provider(key, content, **options)

    class ObservedRecovery(recovery.RecoveryJournal):
        def recover(self, **options):
            if read_json(FAULTS / 'fault.json')['mode'] != 'survivor-recovery':
                return super().recover(**options)
            proof = read_json(FAULTS / 'survivor-proof.json')
            record = self.store.read()
            if (record is None or record['generation'] != proof['generation']
                    or record['writers']['native'] != proof['writer']):
                raise RuntimeError('survivor proof does not match the actual durable journal')
            barrier = SurvivorBarrier(proof, host, expected, invocation)
            actual = self._drain
            self._drain = lambda record, **kwargs: barrier.drain(record, actual, **kwargs)
            self.backend.survivor_barrier = barrier
            try:
                result = super().recover(**options)
                barrier.require_drained()
                append_event('surviving_writer_cleanup_complete', invocation=invocation,
                             observer=barrier.observer, result=result)
                return result
            finally:
                self._drain = actual
                self.backend.survivor_barrier = None
                barrier.close()

    class ObservedManager(DHCPManager):
        def stop(self):
            try:
                append_event('dhcp_stop', invocation=invocation)
            finally:
                super().stop()

    class FixtureAdapter(NativeAdapter):
        def __init__(self, legacy):
            super().__init__(legacy, system=ObservedSystem(host, expected),
                             backend=PausedNetwork(), state=STATE)

        def prepare_recovery(self, *args, **kwargs):
            return measure_call(timing['startup_recovery'], super().prepare_recovery, *args, **kwargs)

        def check_generation(self, generation):
            base.fixture_guard(host, expected)
            return super().check_generation(generation)

    class ObservedOwner(Owner):
        def __init__(self, **arguments):
            super().__init__(**arguments)
            self._first_latch_timing = None
            active_owner[0] = self
            base.write_private(FAULTS / ('owner-' + invocation + '.json'), process_record(os.getpid()))
            append_event('owner_created', invocation=invocation)

        def start(self):
            try:
                return super().start()
            finally:
                export(self)

        def step(self):
            super().step()
            export(self)

        def _latch(self, reason):
            if self._first_latch_timing is None:
                self._first_latch_timing = json.loads(json.dumps(timing))
            append_event('latched', invocation=invocation, reason=str(reason)[:2048])
            try:
                return super()._latch(reason)
            finally:
                export(self)

        def shutdown(self):
            try:
                return super().shutdown()
            finally:
                export(self)
                append_event('owner_shutdown', invocation=invocation)

    journal.Journal = ObservedJournal
    adapter.LeaseApplier = network.LeaseApplier = ObservedApplier
    adapter.JournaledApplier = ObservedWrapper
    recovery.RecoveryJournal = ObservedRecovery
    runner.NativeAdapter, runner.Owner, runner.DHCPManager = FixtureAdapter, ObservedOwner, ObservedManager
    try:
        runner.run(legacy)
    except BaseException as error:
        append_event('guardian_exit_error', invocation=invocation, error=type(error).__name__)
        raise


def worker(host, journal_delay_ms=0, case_selection='baseline'):
    # Prepare/verify private net, mount, PID and resolver/device masks first.
    expected = native.prepare_private(host)
    guards.guard_private(host, expected)
    guards.checked(['/bin/mount', '-t', 'tmpfs', '-o', 'mode=0755',
                    'privacyctl-dhcp-fixture', '/var'])
    guard_private_var()
    Path('/var/lib').mkdir(mode=0o755)
    PRIVATE.mkdir(mode=0o700)
    base.write_private(PRIVATE / 'seal.json', {'host': host, 'expected': expected})
    base.fixture_guard(host, expected)
    FAULTS.mkdir(mode=0o700)
    for prefix in ('lib', 'libexec', 'sbin'):
        base.fixture_guard(host, expected)
        guards.checked(['/bin/mount', '-t', 'tmpfs', '-o', 'mode=0755',
                        'privacyctl-owner-code', '/usr/local/' + prefix])
    for relative in ('usr/local/lib/privacyctl_runtime', 'usr/local/libexec', 'usr/local/sbin'):
        destination = Path('/') / relative
        destination.mkdir(mode=0o755, parents=True, exist_ok=True)
        for path in (ROOT / relative).iterdir():
            if path.is_file() and (path.suffix == '.py' or path.name in
                                  ('privacyctl', 'privacyctl-dhcp-launch', 'privacyctl-dhcp-event')):
                target = destination / path.name
                target.write_bytes(path.read_bytes())
                target.chmod(0o755 if relative.endswith(('libexec', 'sbin')) else 0o644)
    Path('/etc/privacyctl').mkdir(mode=0o700)
    profiles = Path('/etc/privacyctl/profiles')
    profiles.write_text('profile|shmecklebucket|1|shmecklebucket\n')
    profiles.chmod(0o600)
    base.write_private(Path('/etc/privacyctl/ipv6.json'), {'version': 1, 'profiles': {
        base.HOME_PROFILE: {'addresses': ['2001:db8:1::17/64'], 'routers': ['fe80::1']}}})
    Path('/run/wpa_supplicant').mkdir(mode=0o700)
    base.write_private(PRIVATE / 'radios.json', {'wifi_blocked': False, 'bluetooth_blocked': True})
    processes, handles, streams, namespaces, cases = [], [], [], [expected], []
    base.emit({'phase': 'namespace_ready', 'namespaces': namespaces})

    def fault(mode):
        value = {'mode': mode, 'attempt': base.secrets.token_hex(16)}
        base.write_private(FAULTS / 'fault.json', value)
        return value['attempt']

    def spawn(arguments, name, control=False, moving_server=False):
        base.fixture_guard(host, expected)
        stream = (FAULTS / (name + '.log')).open('w')
        streams.append(stream)
        process = subprocess.Popen(arguments, stdin=subprocess.PIPE if control else subprocess.DEVNULL,
            stdout=subprocess.PIPE if control else stream, stderr=stream, text=True, start_new_session=True,
            env={'PATH': '/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C'})
        record = process_record(process.pid)
        handle = Handle(record, host, expected, moving_server=moving_server)
        handles.append(handle)
        processes.append((process, handle))
        return process, handle

    def capture(record):
        handle = Handle(record, host, expected)
        handles.append(handle)
        namespaces.append(record['namespaces'])
        base.emit({'phase': 'namespace_ready', 'namespaces': namespaces})
        return handle

    def state(invocation):
        return read_json(FAULTS / ('state-' + invocation + '.json'), {})

    def start_guardian(*, recovering=False):
        invocation = base.secrets.token_hex(16)
        process, handle = spawn([PYTHON, '-I', str(SCRIPT), '--guardian', json.dumps(host),
                                json.dumps(expected), invocation, '--journal-delay-ms',
                                str(journal_delay_ms)], 'guardian-' + invocation)
        base.wait_for(lambda: state(invocation).get('phase') == 'idle', 18 if recovering else 4,
                      'real guarded owner readiness', (process,))
        owner = capture(read_json(FAULTS / ('owner-' + invocation + '.json')))
        return invocation, process, handle, owner

    def cli(name, *arguments):
        return spawn([PYTHON, '-I', str(SCRIPT), '--cli', json.dumps(host),
                      json.dumps(expected), json.dumps(list(arguments))], name)

    def finish_cli(process, expected_ok):
        # Observe the production CLI's 50-second request result, including its
        # exit overhead; this changes no owner, hook or network deadline.
        status = process.wait(timeout=52)
        if (status == 0) != expected_ok:
            raise RuntimeError('CLI result did not match the expected cancellation outcome')

    def link_alias():
        base.fixture_guard(host, expected)
        sys.path.insert(0, '/usr/local/lib')
        from privacyctl_runtime.link import read_link
        return read_link('wlan0', deadline=time.monotonic() + 1,
                         check=lambda: base.fixture_guard(host, expected)).alias

    def network_clean():
        base.fixture_guard(host, expected)
        rows = json.loads(guards.checked([IP, '-j', '-N', 'address', 'show', 'dev', 'wlan0']).stdout)
        values = list(rows[0].get('addr_info', []))
        for family in ('-4', '-6'):
            values += json.loads(guards.checked([IP, '-j', '-N', family, 'route',
                                                'show', 'dev', 'wlan0']).stdout)
        return (not any(int(str(value.get('protocol', 0)), 0) == 196 for value in values)
                and not list(Path('/run/resolvconf/keys').glob('privacyctl.*'))
                and not (STATE / 'lease.json').exists()
                and link_alias() == PRIOR_ALIAS
                and not (RUNTIME / 'lease-dirty').exists()
                and not (RUNTIME / 'session.json').exists()
                and read_json(PRIVATE / 'radios.json')['wifi_blocked'])

    def clean(invocation):
        current = state(invocation)
        return (current.get('phase') == 'idle' and current.get('generation') is None
                and current.get('dhcp_phase') == 'idle' and network_clean())

    def client_handles(current):
        identity = current['client']
        result = []
        for kind in ('launcher', 'client'):
            record = process_record(identity[kind + '_pid'])
            if record['start_time'] != str(identity[kind + '_start']):
                raise RuntimeError('DHCP process no longer matches owner evidence')
            result.append(capture(record))
        return result

    def record(name, started, **details):
        value = {'name': name, 'elapsed_seconds': time.monotonic() - started, **details}
        cases.append(value)
        base.emit({'phase': 'case', **value})

    def events_since(started, invocation, kind):
        with (FAULTS / 'events.jsonl').open() as stream:
            raw = stream.read(65537)
        if len(raw) > 65536:
            raise RuntimeError('fixture event log exceeds its bound')
        return [row for line in raw.splitlines() if (row := json.loads(line))['kind'] == kind
                and row.get('invocation') == invocation and row['at_boottime'] >= started]

    def reconnect_count():
        path = FAULTS / 'events.jsonl'
        if not path.exists():
            return 0
        with path.open() as stream:
            text = stream.read(65537)
        if len(text.encode()) > 65536:
            raise RuntimeError('fixture event log exceeds its bound')
        return sum(json.loads(line)['kind'] == 'wpa_reconnect' for line in text.splitlines())

    def assert_idle_without_reconnect(invocation, process, previous_reconnects):
        deadline = time.monotonic() + .2
        while time.monotonic() < deadline:
            base.fixture_guard(host, expected)
            if process.poll() is not None or not clean(invocation) or state(invocation).get('client'):
                raise RuntimeError('recovered owner did not remain clean and blocked')
            if reconnect_count() != previous_reconnects:
                raise RuntimeError('owner reconnected without a fresh CLI request')
            time.sleep(.025)
        assert Path('/run/resolvconf/keys/unrelated0').read_text() == 'nameserver 198.51.100.53\n'
        resolver = Path('/etc/resolv.conf').read_text()
        assert 'nameserver 198.51.100.53\n' in resolver
        assert 'nameserver 192.0.2.53\n' not in resolver
        assert link_alias() == PRIOR_ALIAS

    def fresh_connect_off(invocation, process, label, old_generation):
        fault('none')
        request, _ = cli(label + '-connect', 'connect', base.HOME_PROFILE)
        finish_cli(request, True)
        current = base.wait_for(lambda: (row if (row := state(invocation)).get('phase') == 'bound' else None),
                               3, 'fresh post-recovery bound state', (process,))
        assert current['generation'] != old_generation and current['client']
        off, _ = cli(label + '-off', 'off')
        finish_cli(off, True)
        base.wait_for(lambda: clean(invocation), 15, 'fresh post-recovery off cleanup', (process,))
        return current['generation']

    def surviving_case(invocation, guard_process, guard_handle, owner_handle):
        started = time.monotonic()
        attempt = fault('apply-survivor-paused')
        request, _ = cli('surviving-writer-connect-' + attempt, 'connect', base.HOME_PROFILE)
        ready = base.wait_for(lambda: (row if (row := read_json(FAULTS / 'survivor-ready.json', {}))
                                      .get('attempt') == attempt else None),
                             15, 'guarded surviving native writer readiness', (guard_process, request))
        original = [capture(ready['init']), *[capture(row) for row in ready['descendants']]]
        current = state(invocation)
        old_dhcp = client_handles(current)
        hook = capture(current['hooks'][0])
        orphan = read_json(STATE / 'lease.json')
        writer = orphan['writers']['native']
        assert (writer['pid'] == ready['init']['pid']
                and str(writer['start_time']) == ready['init']['start_time']
                and writer['operation'] == 'native-survivor' and writer['nspid'] == 1)
        assert all(not handle.dead() for handle in original)
        base.write_private(FAULTS / 'survivor-proof.json',
                           {'attempt': attempt, 'generation': orphan['generation'], 'writer': writer,
                            'init': ready['init'], 'descendants': ready['descendants'],
                            'old_owner': owner_handle.record})
        owner_handle.send(signal.SIGKILL)
        owner_handle.wait()
        if not guard_handle.dead():
            guard_handle.send(signal.SIGKILL)
        assert guard_process.wait(timeout=5) != 0
        finish_cli(request, False)
        for handle in [hook, *old_dhcp]:
            handle.wait()
        assert all(not handle.dead() for handle in original)
        reconnects = reconnect_count()
        fault('survivor-recovery')
        replacement, process, _, new_owner = start_guardian(recovering=True)
        assert (new_owner.record['pid'], new_owner.record['start_time']) != (
            owner_handle.record['pid'], owner_handle.record['start_time'])
        entries = events_since(ready['at_boottime'], replacement, 'surviving_writer_recovery_entry')
        drained = events_since(ready['at_boottime'], replacement, 'surviving_writer_drained')
        completed = events_since(ready['at_boottime'], replacement, 'surviving_writer_cleanup_complete')
        assert len(entries) == len(drained) == len(completed) == 1
        assert (entries[0]['all_original_pidfds_live'] and drained[0]['outcome'] == 'killed'
                and drained[0]['all_original_pidfds_ready']
                and entries[0]['observer']['pid'] == new_owner.record['pid'])
        assert all(handle.dead() for handle in original)
        assert_idle_without_reconnect(replacement, process, reconnects)
        fresh_connect_off(replacement, process, 'surviving-writer-recovered', orphan['generation'])
        record('new_observer_drains_induced_surviving_writer_and_descendants', started,
               survival_induced_by_fixture_pdeath_suppression=True,
               all_original_processes_live_at_new_observer=True,
               original_init_detached_child_and_nested_namespace_completed=True,
               real_drain_outcome='killed', cleanup_guarded_by_all_original_pidfds=True,
               old_owner_and_guardian_dead=True, previous_alias_and_unrelated_provider_preserved=True,
               no_automatic_reconnect=True, fresh_connect_and_off_succeeded=True)

    def complete():
        base.emit({'phase': 'complete', 'cases': cases, 'guardian_is_production': True,
                   'cli_main_ipc_emergency_are_production': True,
                   'cli_entrypoint_and_physical_system_substituted': True,
                   'baseline_owner_harness_changed': True, 'historical_fault_case_count': 7,
                   'case_count': len(cases), 'case_selection': case_selection,
                   'first_six_fault_cases_preserved': True,
                   'first_six_fault_cases_exercised': case_selection != 'survivor',
                   'integrated_recovery_cases': 1 if case_selection == 'survivor' else (
                       4 if case_selection == 'all' else 3)})

    try:
        fault('none')
        server, server_handle = spawn([PYTHON, '-I', str(base.SCRIPT), '--dhcp-server',
                                      json.dumps(host), json.dumps(expected)], 'server', True, True)
        greeting = guards.read_message(server)
        if (not greeting.get('ready') or greeting['identity']['pid'] != server.pid
                or greeting['identity']['start_time'] != server_handle.record['start_time']):
            raise RuntimeError('private server handshake changed')
        server_ns = greeting['namespaces']
        if os.readlink(f'/proc/{server.pid}/ns/net') != server_ns['net']:
            raise RuntimeError('server namespace changed before veth transfer')
        namespaces.append(server_ns)
        base.emit({'phase': 'namespace_ready', 'namespaces': namespaces})
        base.fixture_guard(host, expected)
        guards.checked([IP, 'link', 'add', 'wlan0', 'type', 'veth', 'peer', 'name', 'dhcp-server'])
        if process_record(server.pid)['start_time'] != server_handle.record['start_time']:
            raise RuntimeError('server PID changed before veth transfer')
        base.fixture_guard(host, expected)
        guards.checked([IP, 'link', 'set', 'dhcp-server', 'netns', str(server.pid)])
        for interface in ('lo', 'wlan0'):
            base.fixture_guard(host, expected)
            guards.checked([IP, 'link', 'set', interface, 'up'])
        assert guards.server_command(server, {'command': 'setup'}) == {'serving': True}
        base.fixture_guard(host, expected)
        guards.checked([IP, 'link', 'set', 'dev', 'wlan0', 'alias', os.fsdecode(PRIOR_ALIAS)])
        assert link_alias() == PRIOR_ALIAS
        base.fixture_guard(host, expected)
        guards.checked([native.RESOLVCONF, '-a', 'unrelated0'], input='nameserver 198.51.100.53\n')
        wpa, _ = spawn([PYTHON, '-I', str(SCRIPT), '--fake-wpa', json.dumps(host), json.dumps(expected)], 'wpa')
        base.wait_for(lambda: read_json(FAULTS / 'wpa-ready.json'), 3, 'fake WPA readiness', (wpa,))
        invocation, guard_process, guard_handle, owner_handle = start_guardian()
        if case_selection == 'survivor':
            surviving_case(invocation, guard_process, guard_handle, owner_handle)
            complete()
            return

        for kill_requester in (False, True):
            started = time.monotonic()
            case_boottime = time.clock_gettime(time.CLOCK_BOOTTIME)
            attempt = fault('wpa-unanswered')
            request, request_handle = cli('wpa-connect-' + attempt, 'connect', base.HOME_PROFILE)
            base.wait_for(lambda: read_json(FAULTS / 'wpa-unanswered.json', {}).get('attempt') == attempt,
                          3, 'unanswered WPA command', (guard_process, request))
            if kill_requester:
                request_handle.send(signal.SIGKILL)
                finish_cli(request, False)
            else:
                off, _ = cli('wpa-off-' + attempt, 'off')
                finish_cli(off, True)
                finish_cli(request, False)
            base.wait_for(lambda: clean(invocation), 15, 'WPA cancellation cleanup', (guard_process,))
            assert not state(invocation)['client']
            reason = 'requesting client disconnected' if kill_requester else 'radio authorization cancelled'
            assert any(row['reason'] == reason for row in events_since(case_boottime, invocation, 'latched'))
            record('requester_death_before_commit' if kill_requester else 'off_during_unanswered_wpa', started,
                   observed_reason=reason)

        for kill_hook in (False, True):
            started = time.monotonic()
            case_boottime = time.clock_gettime(time.CLOCK_BOOTTIME)
            attempt = fault('apply-paused')
            request, _ = cli('apply-connect-' + attempt, 'connect', base.HOME_PROFILE)
            ready = base.wait_for(lambda: (row if (row := read_json(FAULTS / 'pause-ready.json', {}))
                                          .get('attempt') == attempt else None),
                                 15, 'real contained application command readiness', (guard_process, request))
            command_handle = capture(ready)
            current = state(invocation)
            dhcp_handles = client_handles(current)
            assert current['dirty'] and current['hooks'] and not current['expiry']
            hook_handle = capture(current['hooks'][0])
            if kill_hook:
                hook_handle.send(signal.SIGKILL)
            else:
                off, _ = cli('apply-off-' + attempt, 'off')
                finish_cli(off, True)
            finish_cli(request, False)
            base.wait_for(lambda: clean(invocation), 15, 'blocked hook/application cleanup', (guard_process,))
            for handle in [command_handle, hook_handle, *dhcp_handles]:
                handle.wait()
            blocked = events_since(case_boottime, invocation, 'blocked')
            command_stops = events_since(case_boottime, invocation, 'native_command_stop')
            dhcp_stops = events_since(case_boottime, invocation, 'dhcp_stop')
            assert blocked and command_stops and dhcp_stops
            # Ignore _begin's initial block: cancellation must block again after
            # the real command published readiness and before either teardown.
            cancelled_blocks = [row for row in blocked if row['at_boottime'] >= ready['at_boottime']]
            assert cancelled_blocks
            assert min(row['at_boottime'] for row in cancelled_blocks) < min(
                row['at_boottime'] for row in command_stops + dhcp_stops)
            reason = ('DHCP hook exited or sent extra data before acknowledgment'
                      if kill_hook else 'radio authorization cancelled')
            assert any(row['reason'] == reason
                       for row in events_since(ready['at_boottime'], invocation, 'latched'))
            record('hook_death_during_native_apply' if kill_hook else 'off_during_native_apply', started,
                   real_command_and_hook_dead=True, native_partial_state_removed=True,
                   blocked_before_command_and_dhcp_teardown=True, observed_reason=reason)

        fault('none')
        request, _ = cli('bound-before-guardian-death', 'connect', base.HOME_PROFILE)
        finish_cli(request, True)
        current = base.wait_for(lambda: (row if (row := state(invocation)).get('phase') == 'bound' else None),
                               3, 'real guarded bound state', (guard_process,))
        dhcp_handles = client_handles(current)
        started = time.monotonic()
        other_invocation = base.secrets.token_hex(16)
        other, _ = spawn([PYTHON, '-I', str(SCRIPT), '--guardian', json.dumps(host),
                          json.dumps(expected), other_invocation, '--journal-delay-ms',
                          str(journal_delay_ms)], 'second-guardian')
        assert other.wait(timeout=3) != 0
        assert not (FAULTS / ('owner-' + other_invocation + '.json')).exists()
        assert not owner_handle.dead() and all(not handle.dead() for handle in dhcp_handles)
        assert state(invocation)['client'] == current['client']
        record('second_guardian_cannot_create_overlapping_owner_or_client', started)

        started = time.monotonic()
        death_boottime = time.clock_gettime(time.CLOCK_BOOTTIME)
        guard_handle.send(signal.SIGKILL)
        guard_process.wait(timeout=3)
        owner_handle.wait(timeout=30)
        for handle in dhcp_handles:
            handle.wait()
        base.wait_for(network_clean, 15, 'guardian death cleanup')
        assert state(invocation)['phase'] == 'stopped'
        assert any(row['pid'] == owner_handle.record['pid']
                   for row in events_since(death_boottime, invocation, 'blocked'))
        assert events_since(death_boottime, invocation, 'owner_shutdown')
        record('guardian_sigkill_causes_owner_pdeath_cleanup', started,
               owner_and_dhcp_dead=True, dirty_marker_removed=True)

        invocation, guard_process, guard_handle, owner_handle = start_guardian()
        request, _ = cli('bound-before-owner-death', 'connect', base.HOME_PROFILE)
        finish_cli(request, True)
        current = base.wait_for(lambda: (row if (row := state(invocation)).get('phase') == 'bound' else None),
                               3, 'replacement guarded bound state', (guard_process,))
        dhcp_handles = client_handles(current)
        generation = current['generation']
        started = time.monotonic()
        death_boottime = time.clock_gettime(time.CLOCK_BOOTTIME)
        owner_handle.send(signal.SIGKILL)
        owner_handle.wait()
        assert guard_process.wait(timeout=5) != 0
        for handle in dhcp_handles:
            handle.wait()
        assert read_json(PRIVATE / 'radios.json')['wifi_blocked']
        assert any(row['pid'] == guard_process.pid
                   for row in events_since(death_boottime, invocation, 'blocked'))
        assert (RUNTIME / 'lease-dirty').read_text() == generation + '\n'
        assert not (RUNTIME / 'session.json').exists()
        orphan = read_json(STATE / 'lease.json')
        assert orphan['generation'] == generation and orphan['phase'] == 'active'
        assert link_alias() == ('privacyctl:' + generation).encode('ascii')
        reconnects = reconnect_count()
        invocation, guard_process, guard_handle, owner_handle = start_guardian(recovering=True)
        assert_idle_without_reconnect(invocation, guard_process, reconnects)
        fresh_connect_off(invocation, guard_process, 'recovered-owner', generation)
        record('owner_sigkill_recovers_on_blocked_startup', started,
               previous_dhcp_dead=True, orphan_journal_and_marker_removed=True,
               previous_alias_restored=True, unrelated_provider_preserved=True,
               no_reconnect_before_fresh_cli=True, fresh_connect_and_off_succeeded=True)

        started = time.monotonic()
        for _ in range(2):
            reconnects = reconnect_count()
            guard_handle.send(signal.SIGTERM)
            assert guard_process.wait(timeout=30) == 0
            owner_handle.wait()
            assert network_clean()
            invocation, guard_process, guard_handle, owner_handle = start_guardian(recovering=True)
            assert_idle_without_reconnect(invocation, guard_process, reconnects)
        record('repeated_clean_startup_is_idempotent', started, clean_restarts=2,
               no_automatic_reconnect=True, previous_alias_and_unrelated_provider_preserved=True)

        # Capture a real native init while it is alive behind the fixed pause.
        # The production parent-death chain may drain it before replacement;
        # this case deliberately does not claim survival until recovery starts.
        started = time.monotonic()
        attempt = fault('apply-paused')
        request, _ = cli('native-orphan-connect-' + attempt, 'connect', base.HOME_PROFILE)
        ready = base.wait_for(lambda: (row if (row := read_json(FAULTS / 'pause-ready.json', {}))
                                      .get('attempt') == attempt else None),
                             15, 'native writer alive before owner death', (guard_process, request))
        command_handle = capture(ready)
        current = state(invocation)
        dhcp_handles = client_handles(current)
        hook_handle = capture(current['hooks'][0])
        orphan = read_json(STATE / 'lease.json')
        writer = orphan['writers']['native']
        assert (writer['pid'] == ready['pid'] and str(writer['start_time']) == ready['start_time']
                and writer['nspid'] == 1 and not command_handle.dead())
        generation = orphan['generation']
        owner_handle.send(signal.SIGKILL)
        owner_handle.wait()
        finish_cli(request, False)
        assert guard_process.wait(timeout=5) != 0
        for handle in [command_handle, hook_handle, *dhcp_handles]:
            handle.wait()
        writer_death_proved_at = time.clock_gettime(time.CLOCK_BOOTTIME)
        assert read_json(PRIVATE / 'radios.json')['wifi_blocked']
        assert read_json(STATE / 'lease.json')['writers']['native'] == writer
        reconnects = reconnect_count()
        fault('none')
        invocation, guard_process, guard_handle, owner_handle = start_guardian(recovering=True)
        assert_idle_without_reconnect(invocation, guard_process, reconnects)
        fresh_connect_off(invocation, guard_process, 'recovered-native', generation)
        record('owner_sigkill_during_live_native_apply_recovers', started,
               native_init_live_at_kill=True, original_init_pidfd_completed_before_restart=True,
               writer_death_proved_at_boottime=writer_death_proved_at,
               native_writer_survival_until_replacement_claimed=False,
               orphan_journal_and_marker_removed=True, previous_alias_restored=True,
               unrelated_provider_preserved=True, fresh_connect_and_off_succeeded=True)
        if case_selection == 'all':
            surviving_case(invocation, guard_process, guard_handle, owner_handle)
        complete()
    except BaseException:
        diagnostic = {'phase': 'failure_diagnostics'}
        for path in sorted(FAULTS.glob('*.json')):
            try:
                diagnostic[path.name] = read_json(path)
            except Exception as error:
                diagnostic[path.name] = {'unavailable': type(error).__name__}
        base.emit(diagnostic)
        raise
    finally:
        # Held pidfds remain authoritative even after a guardian dies/reparents
        # its owner. No numeric PID or global service cleanup is used here.
        for process, handle in reversed(processes):
            if process.poll() is None:
                if not handle.dead():
                    handle.send(signal.SIGTERM)
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    if not handle.dead():
                        handle.send(signal.SIGKILL)
                    process.wait(timeout=3)
            for stream in (process.stdin, process.stdout):
                if stream is not None:
                    stream.close()
        for handle in reversed(handles):
            try:
                if not handle.dead():
                    handle.send(signal.SIGKILL)
                handle.wait(timeout=3)
            finally:
                handle.close()
        for stream in streams:
            stream.close()
        state_paths = sorted(FAULTS.glob('state-*.json'))
        if len(state_paths) > 32:
            raise RuntimeError('fixture timing state count exceeds bound')
        for path in state_paths:
            value = read_json(path)
            base.emit({'phase': 'fixture_timing', 'invocation': value['invocation'],
                       'timing': value.get('timing', {}),
                       'first_latch_timing': value.get('first_latch_timing')})
        if (FAULTS / 'events.jsonl').exists():
            base.emit({'phase': 'fixture_events', 'text': read_tail(FAULTS / 'events.jsonl', 65536)})
        for path in sorted(FAULTS.glob('*.log')):
            if path.stat().st_size:
                base.emit({'phase': 'fixture_log', 'name': path.name, 'text': read_tail(path, 8192)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--worker')
    parser.add_argument('--host-state-snapshot', action='store_true')
    parser.add_argument('--guardian', nargs=3)
    parser.add_argument('--fake-wpa', nargs=2)
    parser.add_argument('--cli', nargs=3)
    parser.add_argument('--survivor', nargs=2)
    parser.add_argument('--survivor-child', nargs=3)
    parser.add_argument('--case', choices=('baseline', 'survivor', 'all'), default='baseline')
    parser.add_argument('--journal-delay-ms', type=int, choices=(0, 50), default=0)
    args = parser.parse_args()
    if args.host_state_snapshot:
        if (args.worker or args.guardian or args.fake_wpa or args.cli or args.survivor
                or args.survivor_child or args.output is not None or args.journal_delay_ms
                or args.case != 'baseline'):
            parser.error('host state snapshot is a standalone read-only mode')
        base.emit(snapshot_state_directory())
        return
    if args.cli:
        if (args.worker or args.guardian or args.fake_wpa or args.survivor or args.survivor_child
                or args.output is not None or args.journal_delay_ms or args.case != 'baseline'):
            parser.error('fixture CLI is a standalone private mode')
        raise SystemExit(fixture_cli(*(json.loads(value) for value in args.cli)))
    if args.survivor or args.survivor_child:
        if (args.worker or args.guardian or args.fake_wpa or args.output is not None
                or args.journal_delay_ms or args.case != 'baseline'
                or (args.survivor and args.survivor_child)):
            parser.error('survivor payload is a standalone private mode')
        if args.survivor:
            survivor_payload(*(json.loads(value) for value in args.survivor))
        else:
            survivor_child(json.loads(args.survivor_child[0]),
                           json.loads(args.survivor_child[1]), args.survivor_child[2])
        return
    if args.guardian:
        guardian(json.loads(args.guardian[0]), json.loads(args.guardian[1]), args.guardian[2],
                 args.journal_delay_ms)
        return
    if args.fake_wpa:
        fake_wpa(*(json.loads(value) for value in args.fake_wpa))
        return
    if args.worker:
        try:
            worker(json.loads(args.worker), args.journal_delay_ms, args.case)
        except BaseException:
            base.emit({'phase': 'failed', 'traceback': traceback.format_exc()})
            raise
        return
    if args.output is None or args.output.exists():
        parser.error('--output must name a new evidence directory')
    paths = [SCRIPT, base.SCRIPT, Path(native.__file__), guards.SCRIPT,
             ROOT / 'usr/local/sbin/privacyctl', ROOT / 'usr/local/libexec/privacyctl-dhcp-launch',
             ROOT / 'usr/local/libexec/privacyctl-dhcp-event', Path(native.RESOLVCONF),
             Path('/usr/lib/resolvconf/libc'), *sorted((ROOT / 'usr/local/lib/privacyctl_runtime').glob('*.py'))]
    hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    private_before, private_after = {}, {}
    privilege = [] if os.geteuid() == 0 else ['doas', '-n']

    def snapshot_host():
        return json.loads(guards.checked([*privilege, PYTHON, '-I', str(SCRIPT),
                                           '--host-state-snapshot']).stdout)

    before = native.snapshot_host(private_before)
    before['persistent_state'] = snapshot_host()
    started = time.monotonic()
    result = subprocess.run([*privilege, '/usr/bin/timeout', '-k', '3', '240', '/usr/bin/unshare',
        '--net', '--mount', '--pid', '--fork', '--kill-child=KILL', '--propagation', 'unchanged',
        PYTHON, '-I', str(SCRIPT), '--worker', json.dumps(before['namespaces']),
        '--journal-delay-ms', str(args.journal_delay_ms), '--case', args.case],
        capture_output=True, text=True, timeout=248)
    args.output.mkdir(mode=0o700, parents=True)
    base.write_private(args.output / 'worker-result.json', {
        'exit_status': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr,
        'source_sha256': hashes, 'host_before': before})
    after = native.snapshot_host(private_after)
    after['persistent_state'] = snapshot_host()
    base.write_private(args.output / 'snapshot-comparison.json', {
        'host_checks': {key: before[key] == after[key] for key in before},
        'host_after': after})
    messages = [json.loads(line) for line in result.stdout.splitlines()]
    namespaces = namespace_records(messages)
    namespace_ids = sorted({value for row in namespaces for value in row.values()})
    cleanup = json.loads(guards.checked([*privilege, PYTHON, '-I', str(guards.SCRIPT),
        '--audit-cleanup', json.dumps(namespace_ids)]).stdout)
    stable = hashes == {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    complete = any(row.get('phase') == 'complete' for row in messages)
    passed = (not result.returncode and complete and namespace_ids and before == after
              and stable and not cleanup['remaining_namespace_members'])
    evidence = {'schema_version': 1, 'status': 'passed' if passed else 'failed',
        'journal_delay_ms': args.journal_delay_ms,
        'case_selection': args.case,
        'source_sha256': hashes, 'source_unchanged': stable,
        'host_checks': {key: before[key] == after[key] for key in before},
        'host_state_unchanged': before == after,
        'host_address_changed_fields': native.changed_fields(private_before, private_after),
        'namespaces': namespaces, 'cleanup': cleanup, 'worker_exit_status': result.returncode,
        'messages': messages, 'worker_stderr': result.stderr,
        'elapsed_seconds': time.monotonic() - started,
        'verified_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'limitations': ['WPA is a synthetic Unix-datagram responder; rfkill is simulated by a private veth.',
            'CLI main, IPC and emergency-off routes are real; its entrypoint and physical System use the guarded fixture substitute.',
            'Journal timing uses private tmpfs with the selected fixed artificial delay, not real-disk latency.',
            'The native-apply pause is a fixed synthetic command run through the production contained runner.',
            'No physical radio, real trusted association, packet gate, OpenSnitch or OpenRC startup is exercised.',
            'Owner SIGKILL recovery uses a private /var journal and real runner; historical refusal proof is retained separately.',
            'Baseline case nine only proves the native writer alive at owner kill; it does not establish survival at new-observer entry. The optional survivor case requires that stronger proof separately.']}
    evidence['limitations'].append(
        'The optional survivor case deliberately clears only its guarded native init parent-death signal; '
        'survival is induced, and outer private PID namespace/timeout/pidfd containment remains intact.')
    base.write_private(args.output / 'evidence.json', evidence)
    base.emit({'status': evidence['status'], 'evidence': str(args.output / 'evidence.json'),
               'elapsed_seconds': evidence['elapsed_seconds']})
    if not passed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
