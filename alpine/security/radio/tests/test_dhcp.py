"""Real private-process transport tests; no production DHCP or radio changes."""
import json
import os
from pathlib import Path
import select
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

LIBRARY = Path(__file__).parents[1] / 'root/usr/local/lib'
sys.path.insert(0, str(LIBRARY))
from privacyctl_runtime import dhcp
from privacyctl_runtime import launch


GENERATION = '0123456789abcdef0123456789abcdef'
FIELDS = {'interface': 'synthetic0', 'ip': '192.0.2.2', 'mask': '24',
          'lease': '30', 'serverid': '192.0.2.1', 'router': '192.0.2.1',
          'dns': '192.0.2.53'}


def executable(path, source):
    path.write_text('#!/usr/bin/python3 -I\n' + source)
    path.chmod(0o700)
    return str(path)


@unittest.skipUnless(os.geteuid() == 0, 'PID namespace transport tests require root')
class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='dhcp-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.runtime = self.root / 'run'
        bootstrap = 'import sys\nsys.path.insert(0, ' + repr(str(LIBRARY)) + ')\n'
        self.launcher = executable(self.root / 'launch', bootstrap +
                                  'from privacyctl_runtime.launch import main\nraise SystemExit(main())\n')
        self.hook = executable(self.root / 'hook', bootstrap +
                              'from privacyctl_runtime.hook import main\nraise SystemExit(main())\n')
        self.manager = None

    def manager_for(self, scenario='renew'):
        source = '''import json,os,signal,socket,subprocess,sys,time
fields=FIELDS
scenario=SCENARIO
hook=sys.argv[sys.argv.index('-s')+1]
def event(kind, values=None):
 env=dict(os.environ, **(fields if values is None else values))
 return subprocess.call([hook,kind],env=env)
def raw(packet, wait=True):
 peer=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET)
 peer.connect(os.environ['PRIVACYCTL_EVENT_SOCKET'])
 if packet is not None:peer.send(packet)
 if wait:time.sleep(30)
 peer.close()
event('deconfig',{'interface':'synthetic0'})
if scenario=='stall':
 raw(None)
elif scenario=='partial':
 raw(b'{"version":')
elif scenario=='oversized':
 raw(b'x'*20000)
elif scenario=='nested':
 raw(b'['*1500+b'0'+b']'*1500)
elif scenario=='detached':
 child=subprocess.Popen(['/usr/bin/python3','-I','-c','import time; time.sleep(30)'],start_new_session=True)
 Path=__import__('pathlib').Path
 Path(MARKER).write_text(str(child.pid))
elif scenario=='exit':
 raise SystemExit(4)
elif scenario=='acquire_timeout':
 pass
else:
 if scenario=='stale_then_bound':
  raw(json.dumps({'version':1,'generation':'f'*32,'event':'bound','fields':fields}).encode(),False)
 if event('bound')!=0:raise SystemExit(6)
 if scenario=='renew':event('renew')
 elif scenario in ('deconfig','nak','leasefail'):event(scenario,{'interface':'synthetic0'})
 elif scenario=='invalid':event('renew',dict(fields,ip='bad address'))
time.sleep(30)
'''
        source = source.replace('FIELDS', repr(FIELDS)).replace('SCENARIO', repr(scenario))
        source = source.replace('MARKER', repr(str(self.root / 'detached-pid')))
        client = executable(self.root / 'client', source)
        manager = dhcp.DHCPManager(self.runtime, launcher=self.launcher,
                                   hook=self.hook, udhcpc=client)
        self.manager = manager
        self.addCleanup(manager.stop)
        manager.start(GENERATION, 'synthetic0')
        return manager

    def next_event(self, kind, timeout=4):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for event in self.manager.poll(.03):
                if isinstance(event, kind):
                    return event
                self.fail('unexpected manager event: ' + repr(event))
        self.fail('manager event deadline')

    def test_initial_deconfig_then_bound_and_renew_keep_one_pid(self):
        manager = self.manager_for()
        first = self.next_event(dhcp.LeaseEvent)
        self.assertEqual(first.kind, 'bound')
        self.assertEqual(first.lease.interface, 'synthetic0')
        pid = manager.identity['client_pid']
        self.assertNotEqual(pid, 1)
        self.assertTrue(manager.reply(first.event_id, True))
        self.assertEqual(manager.phase, 'bound')
        self.assertEqual(manager.expiry, first.received_at + 30)
        second = self.next_event(dhcp.LeaseEvent)
        self.assertEqual(second.kind, 'renew')
        self.assertEqual(manager.identity['client_pid'], pid)
        self.assertTrue(manager.reply(second.event_id, True))
        self.assertEqual(manager.expiry, second.received_at + 30)

    def test_successful_application_delay_does_not_extend_lease(self):
        manager = self.manager_for()
        event = self.next_event(dhcp.LeaseEvent)
        with mock.patch.object(dhcp, 'boottime', return_value=event.received_at + 2):
            manager.reply(event.event_id, True)
        self.assertEqual(manager.expiry, event.received_at + 30)

    def test_post_bound_loss_events_report_failure_without_stopping_first(self):
        for scenario in ('deconfig', 'nak', 'leasefail', 'invalid'):
            with self.subTest(scenario=scenario):
                manager = self.manager_for(scenario)
                first = self.next_event(dhcp.LeaseEvent)
                manager.reply(first.event_id, True)
                failure = self.next_event(dhcp.Failure)
                self.assertTrue(failure.reason)
                self.assertEqual(manager.phase, 'failed')
                self.assertTrue(manager.active)
                manager.stop()

    def test_child_exit_reports_failure(self):
        self.manager_for('exit')
        failure = self.next_event(dhcp.Failure)
        self.assertIn('exit', failure.reason)

    def test_overlapping_start_and_other_manager_are_rejected(self):
        manager = self.manager_for('acquire_timeout')
        with self.assertRaises(dhcp.DHCPError):
            manager.start('1' * 32, 'synthetic0')
        another = dhcp.DHCPManager(self.runtime, launcher=self.launcher,
                                  hook=self.hook, udhcpc=str(self.root / 'client'))
        self.addCleanup(another.stop)
        with self.assertRaises(dhcp.DHCPError):
            another.start('2' * 32, 'synthetic0')

    def test_stale_or_host_namespace_frames_cannot_authorize_lease(self):
        manager = self.manager_for('acquire_timeout')
        deadline = time.monotonic() + 3
        while manager.phase == 'starting' and time.monotonic() < deadline:
            self.assertEqual(manager.poll(.03), [])
        for generation in ('f' * 32, GENERATION):
            with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as peer:
                peer.connect(manager.socket_path)
                peer.send(json.dumps({'version':1,'generation':generation,
                    'event':'bound','fields':FIELDS}).encode())
                self.assertEqual(manager.poll(.05), [])
        self.assertNotEqual(manager.phase, 'bound')

    def test_stale_generation_inside_client_namespace_is_discarded(self):
        manager = self.manager_for('stale_then_bound')
        event = self.next_event(dhcp.LeaseEvent)
        self.assertEqual(event.event_id, 1)
        self.assertEqual(event.kind, 'bound')
        self.assertTrue(manager.reply(event.event_id, True))

    def test_partial_and_oversized_packets_fail_without_hanging(self):
        for scenario in ('partial', 'oversized', 'nested'):
            with self.subTest(scenario=scenario):
                self.manager_for(scenario)
                self.assertIsInstance(self.next_event(dhcp.Failure), dhcp.Failure)
                self.manager.stop()

    def test_silent_hook_socket_has_finite_deadline(self):
        with mock.patch.object(dhcp, 'HOOK_TIMEOUT', .2):
            self.manager_for('stall')
            started = time.monotonic()
            failure = self.next_event(dhcp.Failure)
            self.assertIn('deadline', failure.reason)
            self.assertLess(time.monotonic() - started, 2)

    def test_acquisition_and_lease_expiry_are_independent_of_events(self):
        with mock.patch.object(dhcp, 'ACQUIRE_TIMEOUT', .3):
            self.manager_for('acquire_timeout')
            self.assertIn('acquisition', self.next_event(dhcp.Failure).reason)
        self.manager.stop()
        manager = self.manager_for('acquire_timeout')
        manager._expiry = dhcp.boottime() - 1
        manager.phase = 'bound'
        self.assertTrue(any('expired' in event.reason for event in manager.poll()
                            if isinstance(event, dhcp.Failure)))

    def test_unanswered_lease_hook_times_out_and_rejected_reply_cannot_bind(self):
        manager = self.manager_for()
        event = self.next_event(dhcp.LeaseEvent)
        with mock.patch.object(dhcp, 'boottime', return_value=event.received_at + 6):
            failures = manager.poll()
        self.assertTrue(any(isinstance(item, dhcp.Failure) for item in failures))
        self.assertFalse(manager.reply(event.event_id, True))
        manager.stop()
        manager = self.manager_for()
        event = self.next_event(dhcp.LeaseEvent)
        self.assertFalse(manager.reply(event.event_id, False))
        self.assertEqual(manager.phase, 'failed')

    def test_stop_kills_detached_hook_namespace_and_allows_new_generation(self):
        manager = self.manager_for('detached')
        deadline = time.monotonic() + 3
        marker = self.root / 'detached-pid'
        while not marker.exists() and time.monotonic() < deadline:
            self.assertEqual(manager.poll(.03), [])
        self.assertTrue(marker.exists())
        client_pid = manager.identity['client_pid']
        namespace = os.readlink('/proc/' + str(client_pid) + '/ns/pid')
        peer_pids = []
        for path in Path('/proc').glob('[0-9]*'):
            try:
                if os.readlink(path / 'ns/pid') == namespace:
                    peer_pids.append(os.pidfd_open(int(path.name)))
            except (FileNotFoundError, ProcessLookupError):
                pass
        self.assertGreaterEqual(len(peer_pids), 2)
        try:
            manager.stop()
            for fd in peer_pids:
                self.assertTrue(select.select([fd], [], [], 1)[0])
        finally:
            for fd in peer_pids:
                os.close(fd)
        self.assertFalse(manager.active)
        self.assertFalse(Path(manager.socket_path).exists())
        manager.start('1' * 32, 'synthetic0')

    def test_unsafe_runtime_and_invalid_generation_are_rejected(self):
        self.runtime.symlink_to(self.root, target_is_directory=True)
        manager = dhcp.DHCPManager(self.runtime, launcher=self.launcher,
                                   hook=self.hook, udhcpc='/bin/false')
        with self.assertRaises(dhcp.DHCPError):
            manager.start(GENERATION, 'synthetic0')
        self.runtime.unlink()
        for generation in ('../escape', 'a' * 31, 'A' * 32):
            with self.assertRaises(dhcp.DHCPError):
                manager.start(generation, 'synthetic0')

    def test_launch_context_is_sealed_and_plain_file_is_rejected(self):
        data = {'version':1,'generation':GENERATION,'interface':'synthetic0',
                'owner_pid':os.getpid(),'owner_start':launch.process_start(os.getpid()),
                'socket':str(self.root / 'events.sock'),'launcher':self.launcher,
                'hook':self.hook,'udhcpc':'/bin/false'}
        descriptor = launch.context_fd(data)
        try:
            self.assertEqual(launch.read_context(descriptor), data)
            with mock.patch.object(launch.json, 'loads', side_effect=RecursionError('synthetic nesting')):
                with self.assertRaises(ValueError):
                    launch.read_context(descriptor)
            with self.assertRaises(PermissionError):
                os.write(descriptor, b'changed')
        finally:
            os.close(descriptor)
        with tempfile.TemporaryFile(dir=self.root) as plain:
            plain.write(json.dumps(data).encode())
            plain.flush()
            with self.assertRaises((ValueError, OSError)):
                launch.read_context(plain.fileno())
        data['version'] = True
        descriptor = launch.context_fd(data)
        try:
            with self.assertRaises(ValueError):
                launch.read_context(descriptor)
        finally:
            os.close(descriptor)

    def test_readiness_handshake_shares_one_total_deadline(self):
        now = [100.0]
        timeouts = []
        class Peer:
            def __enter__(self): return self
            def __exit__(self, *_args): pass
            def settimeout(self, value): timeouts.append(value)
            def connect(self, _endpoint): now[0] += 2
            def getsockopt(self, *_args): return struct.pack('3i', 42, 0, 0)
            def sendall(self, _packet): now[0] += 2
            def recv(self, _size): return b'{"ok":true}'
        descriptor = os.open('/dev/null', os.O_RDONLY)
        data = {'socket':'/unused','generation':GENERATION,'interface':'synthetic0',
                'udhcpc':'/unused/client','hook':'/unused/hook'}
        with mock.patch.object(launch, 'clock', side_effect=lambda: now[0], create=True), mock.patch.object(
                launch.socket, 'socket', return_value=Peer()), mock.patch.object(
                launch.os, 'getpid', return_value=1), mock.patch.object(launch.os, 'execve'):
            launch.inner(descriptor, data)
        self.assertEqual(timeouts, [5, 3, 1])

    def test_launcher_rejects_mismatched_owner_before_namespace_exec(self):
        data = {'version':1,'generation':GENERATION,'interface':'synthetic0',
                'owner_pid':os.getpid()+1000000,'owner_start':1,
                'socket':str(self.root / 'absent.sock'),'launcher':self.launcher,
                'hook':self.hook,'udhcpc':'/bin/false'}
        descriptor = launch.context_fd(data)
        try:
            result = subprocess.run([self.launcher, 'outer', str(descriptor)],
                pass_fds=(descriptor,), capture_output=True, text=True, timeout=2)
            self.assertEqual(result.returncode, 1)
            self.assertIn('owner exited', result.stderr)
        finally:
            os.close(descriptor)

    def test_launcher_and_client_death_remove_detached_descendants(self):
        for identity_key in ('launcher_pid', 'client_pid'):
            with self.subTest(identity=identity_key):
                marker = self.root / 'detached-pid'
                marker.unlink(missing_ok=True)
                manager = self.manager_for('detached')
                deadline = time.monotonic() + 3
                while not marker.exists() and time.monotonic() < deadline:
                    manager.poll(.02)
                self.assertTrue(marker.exists())
                namespace = manager.identity['namespace']
                descriptors = []
                for path in Path('/proc').glob('[0-9]*'):
                    try:
                        if os.readlink(path / 'ns/pid') == namespace:
                            descriptors.append(os.pidfd_open(int(path.name)))
                    except (FileNotFoundError, ProcessLookupError):
                        pass
                target = os.pidfd_open(manager.identity[identity_key])
                try:
                    signal.pidfd_send_signal(target, signal.SIGKILL)
                    self.assertIsInstance(self.next_event(dhcp.Failure), dhcp.Failure)
                    for descriptor in descriptors:
                        self.assertTrue(select.select([descriptor], [], [], 2)[0])
                finally:
                    os.close(target)
                    for descriptor in descriptors:
                        os.close(descriptor)
                    manager.stop()

    def test_real_manager_owner_death_kills_client_and_detached_hooks(self):
        manager = self.manager_for('detached')
        manager.stop()
        identity_file = self.root / 'owner-identity.json'
        owner_code = ('import json,sys,time\nfrom pathlib import Path\n'
                      'sys.path.insert(0, ' + repr(str(LIBRARY)) + ')\n'
                      'from privacyctl_runtime.dhcp import DHCPManager\n'
                      'manager=DHCPManager(' + repr(str(self.runtime)) + ', launcher=' +
                      repr(self.launcher) + ', hook=' + repr(self.hook) + ', udhcpc=' +
                      repr(str(self.root / 'client')) + ')\n'
                      'manager.start(' + repr('9' * 32) + ', "synthetic0")\n'
                      'while "client_pid" not in manager.identity:\n manager.poll(.02)\n'
                      'Path(' + repr(str(identity_file)) + ').write_text(json.dumps(manager.identity))\n'
                      'while True:\n manager.poll(.02)\n')
        owner = subprocess.Popen([sys.executable, '-I', '-c', owner_code],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        owner_fd = os.pidfd_open(owner.pid)
        descriptors = []
        try:
            deadline = time.monotonic() + 4
            marker = self.root / 'detached-pid'
            while (not identity_file.exists() or not marker.exists()) and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue(identity_file.exists())
            self.assertTrue(marker.exists())
            identity = json.loads(identity_file.read_text())
            for path in Path('/proc').glob('[0-9]*'):
                try:
                    if (int(path.name) == identity['launcher_pid']
                            or os.readlink(path / 'ns/pid') == identity['namespace']):
                        descriptors.append(os.pidfd_open(int(path.name)))
                except (FileNotFoundError, ProcessLookupError):
                    pass
            self.assertGreaterEqual(len(descriptors), 3)
            signal.pidfd_send_signal(owner_fd, signal.SIGKILL)
            owner.wait(timeout=2)
            for descriptor in descriptors:
                self.assertTrue(select.select([descriptor], [], [], 2)[0])
        finally:
            for descriptor in [owner_fd, *descriptors]:
                try:
                    signal.pidfd_send_signal(descriptor, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                os.close(descriptor)
            owner.wait(timeout=2)


if __name__ == '__main__':
    unittest.main()
