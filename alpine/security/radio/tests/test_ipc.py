"""Root-private local IPC tests; never touch production runtime or radios."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest

LIBRARY = Path(__file__).parents[1] / 'root/usr/local/lib'
sys.path.insert(0, str(LIBRARY))
NONCE = '0123456789abcdef0123456789abcdef'


@unittest.skipUnless(os.geteuid() == 0, 'real private IPC requires root')
class IPCFixture(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('privacyctl_runtime.ipc'),
                             'IPC implementation is missing')
        from privacyctl_runtime import ipc
        self.ipc = ipc
        temporary = tempfile.TemporaryDirectory(prefix='owner-ipc-', dir='/tmp')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.runtime = self.root / 'run'
        self.server = ipc.Server(self.runtime)
        self.addCleanup(self.server.close)

    def start(self):
        self.server.open()

    def peer(self, packet=None):
        peer = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.addCleanup(peer.close)
        peer.settimeout(0.5)
        peer.connect(str(self.runtime / 'owner.sock'))
        if packet is not None:
            peer.send(packet)
        return peer

    def frame(self, **changes):
        fields = dict(version=1, command='scan', nonce=NONCE)
        if changes.get('command', 'scan') in ('scan', 'connect'):
            fields['fence'] = None
        fields.update(changes)
        return json.dumps(fields).encode()

    def next_requests(self):
        requests = []
        for _ in range(10):
            requests += self.server.poll()
            if requests:
                break
            time.sleep(0.001)
        return requests

    def assert_closed(self, peer):
        try:
            self.assertEqual(peer.recv(131072), b'')
        except ConnectionResetError:
            pass

class ServerTests(IPCFixture):
    def test_round_trip_and_exactly_once_delivery(self):
        self.start()
        peer = self.peer(self.frame())
        requests = self.next_requests()
        self.assertEqual(len(requests), 1)
        request = requests[0]
        self.assertEqual((request.command, request.profile, request.nonce),
                         ('scan', None, NONCE))
        self.assertEqual(self.server.poll(), [])
        self.assertTrue(request.alive())
        self.assertTrue(request.respond(True, result='network list'))
        self.assertEqual(json.loads(peer.recv(131072)), {
            'version': 1, 'nonce': NONCE, 'ok': True,
            'result': 'network list', 'error': ''})
        self.assertFalse(request.alive())
        self.assertFalse(request.respond(True))
        self.assert_closed(peer)

    def test_fence_required_for_scan_connect_and_forbidden_for_off(self):
        self.start()
        invalid = [self.frame(fence=True), self.frame(fence='A' * 32),
                   self.frame(fence='a' * 31), self.frame(fence=[]),
                   self.frame(command='off', fence=None)]
        for command, profile in [('scan', None), ('connect', 'iphone-hotspot')]:
            fields = dict(version=1, command=command, nonce=NONCE)
            if profile is not None:
                fields['profile'] = profile
            invalid.append(json.dumps(fields).encode())
        for frame in invalid:
            peer = self.peer(frame)
            self.assertEqual(self.next_requests(), [])
            self.assert_closed(peer)
        peer = self.peer(self.frame(fence='b' * 32))
        request, = self.next_requests()
        self.assertEqual(request.fence, 'b' * 32)
        request.close()
        self.assert_closed(peer)

    def test_owner_lock_is_exclusive_and_reusable(self):
        self.start()
        competitor = self.ipc.Server(self.runtime)
        self.addCleanup(competitor.close)
        with self.assertRaises(self.ipc.IPCError):
            competitor.open()
        peer = self.peer(self.frame())
        self.assertEqual(len(self.next_requests()), 1)
        self.server.close()
        self.assert_closed(peer)
        competitor.open()
        self.assertTrue((self.runtime / 'owner.sock').is_socket())
        self.assertEqual((self.runtime / 'owner.lock').stat().st_mode & 0o777, 0o600)

    def test_malformed_frames_never_dispatch(self):
        self.start()
        invalid = [b'\xff', b'{', b'[]', b'[' * 2000 + b'0' + b']' * 2000,
                   b'x' * 8193, self.frame(version=True), self.frame(version=2),
                   self.frame(command='status'), self.frame(command=['off']),
                   self.frame(nonce='A' * 32), self.frame(nonce='a' * 31),
                   self.frame(profile=None), self.frame(generation='a' * 32),
                   self.frame(path='/bin/true'), self.frame(executable='/bin/true'),
                   self.frame(env={'PATH': '/tmp'}), self.frame(command='connect'),
                   self.frame(command='connect', profile='arbitrary'),
                   self.frame(command='connect', profile=['iphone-hotspot']),
                   self.frame().replace(b'"version": 1', b'"version": 1, "version": 1'),
                   self.frame().replace(b'"version": 1', b'"version": NaN')]
        for frame in invalid:
            with self.subTest(frame=frame[:100]):
                peer = self.peer(frame)
                self.assertEqual(self.next_requests(), [])
                self.assert_closed(peer)

    def test_allowed_commands_and_profiles(self):
        self.start()
        for index, (command, profile) in enumerate([
                ('off', None), ('scan', None),
                ('connect', 'shmecklebucket'), ('connect', 'iphone-hotspot')]):
            fields = dict(command=command, nonce=format(index, '032x'))
            if profile is not None:
                fields['profile'] = profile
            peer = self.peer(self.frame(**fields))
            request, = self.next_requests()
            self.assertEqual((request.command, request.profile), (command, profile))
            self.assertTrue(request.respond(False, error='controlled failure'))
            self.assertEqual(json.loads(peer.recv(131072))['error'], 'controlled failure')

    def test_disconnect_and_extra_packet_cancel_requests(self):
        self.start()
        peer = self.peer(self.frame())
        request, = self.next_requests()
        peer.close()
        self.server.poll()
        self.assertFalse(request.alive())
        self.assertFalse(request.respond(True))
        peer = self.peer(self.frame(nonce='a' * 32))
        request, = self.next_requests()
        peer.send(b'additional frame')
        self.server.poll()
        self.assertFalse(request.alive())
        self.assert_closed(peer)

    def test_duplicate_nonce_rejected_after_completed_request(self):
        self.start()
        first = self.peer(self.frame())
        request, = self.next_requests()
        request.respond(True)
        first.recv(131072)
        duplicate = self.peer(self.frame())
        self.assertEqual(self.next_requests(), [])
        self.assert_closed(duplicate)

    def test_slow_initial_frames_expire_and_capacity_recovers(self):
        self.start()
        idle = [self.peer() for _ in range(8)]
        self.assertEqual(self.server.poll(), [])
        overflow = self.peer(self.frame())
        self.assertEqual(self.server.poll(), [])
        self.assert_closed(overflow)
        time.sleep(3.05)
        self.assertEqual(self.server.poll(), [])
        for peer in idle:
            self.assert_closed(peer)
        peer = self.peer(self.frame())
        request, = self.next_requests()
        self.assertTrue(request.respond(True))
        self.assertTrue(json.loads(peer.recv(131072))['ok'])

    def test_response_limit_and_nonblocking_send_failure_close_request(self):
        self.start()
        peer = self.peer(self.frame())
        request, = self.next_requests()
        self.assertFalse(request.respond(True, result='x' * 131072))
        self.assert_closed(peer)
        peer = self.peer(self.frame(nonce='a' * 32))
        request, = self.next_requests()
        # A deliberately tiny real send buffer forces EMSGSIZE, without a mock.
        request._peer.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024)
        started = time.monotonic()
        self.assertFalse(request.respond(True, result='x' * 100000))
        self.assertLess(time.monotonic() - started, 0.2)
        self.assertFalse(request.alive())
        self.assert_closed(peer)

    def test_close_preserves_replacement_socket_inode(self):
        self.start()
        path = self.runtime / 'owner.sock'
        path.unlink()
        replacement = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.addCleanup(replacement.close)
        replacement.bind(str(path))
        identity = path.stat().st_ino
        self.server.close()
        self.assertEqual(path.stat().st_ino, identity)

    def test_stale_socket_replaced_but_live_socket_preserved(self):
        self.runtime.mkdir(mode=0o700)
        path = self.runtime / 'owner.sock'
        stale = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        stale.bind(str(path))
        path.chmod(0o600)
        stale.close()
        self.start()
        self.server.close()
        live = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.addCleanup(live.close)
        live.bind(str(path))
        path.chmod(0o600)
        live.listen(1)
        identity = path.stat().st_ino
        with self.assertRaises(self.ipc.IPCError):
            self.server.open()
        self.assertEqual(path.stat().st_ino, identity)

    def test_unsafe_runtime_and_lock_paths_refused(self):
        self.runtime.mkdir(mode=0o755)
        with self.assertRaises(self.ipc.IPCError):
            self.start()
        self.runtime.chmod(0o700)
        lock = self.runtime / 'owner.lock'
        target = self.root / 'target'
        target.write_text('preserved')
        target.chmod(0o600)
        for make in [lambda: lock.symlink_to(target),
                     lambda: os.link(target, lock),
                     lambda: os.mkfifo(lock, 0o600)]:
            make()
            with self.assertRaises(self.ipc.IPCError):
                self.start()
            lock.unlink()
        self.assertEqual(target.read_text(), 'preserved')
        self.runtime.rmdir()
        self.runtime.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(self.ipc.IPCError):
            self.start()

    def test_nonroot_peer_rejected_with_real_kernel_credentials(self):
        self.start()
        # Saved root plus root fsuid permits only this fixture connection while
        # SO_PEERCRED records the nonroot effective UID. Directory modes stay private.
        source = '''import ctypes,os,socket,sys
os.setresuid(65534,65534,0)
libc=ctypes.CDLL(None)
libc.setfsuid(0)
peer=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET)
peer.connect(sys.argv[1])
peer.send(sys.argv[2].encode())
print('sent',flush=True)
try:
 print('closed' if peer.recv(8192)==b'' else 'open',flush=True)
except ConnectionResetError:
 print('closed',flush=True)
'''
        process = subprocess.Popen([sys.executable, '-I', '-B', '-c', source,
                                    str(self.runtime / 'owner.sock'), self.frame().decode()],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(), 'sent')
            self.assertEqual(self.next_requests(), [])
            output, error = process.communicate(timeout=1)
            self.assertEqual((process.returncode, output.strip(), error), (0, 'closed', ''))
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=1)

    def test_recent_nonce_window_is_bounded(self):
        self.start()
        for index in range(1025):
            peer = self.peer(self.frame(nonce=format(index, '032x')))
            request, = self.next_requests()
            request.close()
            self.assert_closed(peer)
            peer.close()
        recent = self.peer(self.frame(nonce=format(1024, '032x')))
        self.assertEqual(self.next_requests(), [])
        self.assert_closed(recent)
        oldest = self.peer(self.frame(nonce='0' * 32))
        request, = self.next_requests()
        self.assertTrue(request.respond(True))
        self.assertTrue(json.loads(oldest.recv(131072))['ok'])

    def test_extra_frame_before_dispatch_and_disconnect_release_capacity(self):
        self.start()
        peer = self.peer(self.frame())
        peer.send(b'extra')
        self.assertEqual(self.next_requests(), [])
        self.assert_closed(peer)
        for index in range(12):
            peer = self.peer(self.frame(nonce=format(index, '032x')))
            request, = self.next_requests()
            peer.close()
            self.server.poll()
            self.assertFalse(request.alive())


@unittest.skipUnless(os.geteuid() == 0, 'real private IPC requires root')
class ClientTests(IPCFixture):
    def fixture_process(self, body):
        source = ('import json,os,socket,sys,time\n'
                  'sys.path.insert(0, ' + repr(str(LIBRARY)) + ')\n'
                  'runtime = ' + repr(str(self.runtime)) + '\n' + body)
        script = self.root / ('fixture-' + str(time.monotonic_ns()) + '.py')
        script.write_text(source)
        process = subprocess.Popen([sys.executable, '-I', '-B', str(script)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True)
        def cleanup():
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=2)
        self.addCleanup(cleanup)
        self.assertEqual(process.stdout.readline().strip(), 'ready')
        return process

    def raw_server(self, response, *, unprivileged=False):
        self.runtime.mkdir(mode=0o700)
        return self.fixture_process('''listener=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET)
listener.bind(runtime+'/owner.sock')
os.chmod(runtime+'/owner.sock',0o600)
''' + ('os.setuid(65534)\n' if unprivileged else '') + '''listener.listen(1)
print('ready',flush=True)
connection,_=listener.accept()
frame=connection.recv(8192)
request=json.loads(frame) if frame else {}
''' + response)

    def test_client_real_round_trip_and_error(self):
        self.assertTrue(callable(getattr(self.ipc, 'request', None)), 'client request is missing')
        self.fixture_process('''from privacyctl_runtime.ipc import Server
server=Server(runtime)
server.open()
print('ready',flush=True)
handled=0
while handled<2:
 for request in server.poll():
  request.respond(request.command=='scan',result='scan output',error='off failure')
  handled+=1
 time.sleep(0.001)
server.close()
''')
        self.assertEqual(self.ipc.request('scan', runtime=self.runtime, timeout=1), 'scan output')
        with self.assertRaisesRegex(self.ipc.IPCError, 'off failure'):
            self.ipc.request('off', runtime=self.runtime, timeout=1)

    def test_client_unavailable_and_invalid_input(self):
        self.assertTrue(callable(getattr(self.ipc, 'request', None)), 'client request is missing')
        with self.assertRaises(self.ipc.Unavailable):
            self.ipc.request('scan', runtime=self.runtime)
        for command, profile in [('status', None), ('connect', '/tmp/evil'), ('scan', 'iphone-hotspot')]:
            with self.assertRaises(self.ipc.IPCError) as caught:
                self.ipc.request(command, profile, runtime=self.runtime)
            self.assertNotIsInstance(caught.exception, self.ipc.Unavailable)
        self.runtime.mkdir(mode=0o700)
        stale = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        stale.bind(str(self.runtime / 'owner.sock'))
        (self.runtime / 'owner.sock').chmod(0o600)
        stale.close()
        with self.assertRaises(self.ipc.Unavailable):
            self.ipc.request('scan', runtime=self.runtime)

    def test_client_timeout_closes_connection(self):
        self.assertTrue(callable(getattr(self.ipc, 'request', None)), 'client request is missing')
        process = self.raw_server("print('closed' if connection.recv(8192)==b'' else 'open',flush=True)\n")
        started = time.monotonic()
        with self.assertRaises(self.ipc.IPCError):
            self.ipc.request('scan', runtime=self.runtime, timeout=0.05)
        self.assertLess(time.monotonic() - started, 0.5)
        output, error = process.communicate(timeout=1)
        self.assertEqual((process.returncode, output.strip(), error), (0, 'closed', ''))

    def test_client_rejects_nonroot_server_credentials(self):
        self.assertTrue(callable(getattr(self.ipc, 'request', None)), 'client request is missing')
        self.raw_server('time.sleep(0.05)\n', unprivileged=True)
        with self.assertRaisesRegex(self.ipc.IPCError, 'peer is not root'):
            self.ipc.request('scan', runtime=self.runtime, timeout=1)

    def test_client_receives_large_scan_reply(self):
        self.raw_server("connection.send(json.dumps(dict(version=1,nonce=request['nonce'],"
                        "ok=True,result='x'*100000,error='')).encode())\n")
        self.assertEqual(self.ipc.request('scan', runtime=self.runtime, timeout=1), 'x' * 100000)

    def test_client_rejects_malformed_response(self):
        self.assertTrue(callable(getattr(self.ipc, 'request', None)), 'client request is missing')
        responses = [b'\xff', b'[]', b'x' * 131073,
                     b'[' * 1500 + b'0' + b']' * 1500,
                     b'{"version":1,"nonce":"bad","ok":true,"result":"","error":""}']
        for index, packet in enumerate(responses):
            with self.subTest(index=index):
                self.runtime = self.root / ('run-' + str(index))
                self.raw_server('connection.send(' + repr(packet) + ')\n')
                with self.assertRaises(self.ipc.IPCError):
                    self.ipc.request('scan', runtime=self.runtime, timeout=1)

    def test_client_response_field_types_duplicates_and_extra_keys(self):
        mutations = ["reply['version']=True", "reply['version']=2", "reply['ok']=1",
                     "reply['result']=[]", "reply['error']=None", "reply['nonce']='f'*32",
                     "reply['generation']='f'*32", "del reply['error']",
                     "reply['nonce']=[]"]
        for index, mutation in enumerate(mutations + ['duplicate']):
            with self.subTest(mutation=mutation):
                self.runtime = self.root / ('shape-' + str(index))
                body = "reply=dict(version=1,nonce=request['nonce'],ok=True,result='',error='')\n"
                if mutation == 'duplicate':
                    body += "packet=json.dumps(reply).replace('{','{\"version\":1,',1)\n"
                else:
                    body += mutation + '\npacket=json.dumps(reply)\n'
                self.raw_server(body + 'connection.send(packet.encode())\n')
                with self.assertRaises(self.ipc.IPCError):
                    self.ipc.request('scan', runtime=self.runtime, timeout=1)

    def test_client_interruption_closes_connection(self):
        process = self.raw_server("print('closed' if connection.recv(8192)==b'' else 'open',flush=True)\n")
        def interrupt(_signum, _frame):
            raise KeyboardInterrupt
        previous = signal.signal(signal.SIGALRM, interrupt)
        try:
            signal.setitimer(signal.ITIMER_REAL, 0.05)
            with self.assertRaises(KeyboardInterrupt):
                self.ipc.request('scan', runtime=self.runtime, timeout=10)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous)
        output, error = process.communicate(timeout=1)
        self.assertEqual((process.returncode, output.strip(), error), (0, 'closed', ''))

    def test_client_captures_current_fence_without_caller_override(self):
        self.raw_server("connection.send(json.dumps(dict(version=1,nonce=request['nonce'],"
                        "ok=True,result=json.dumps(request),error='')).encode())\n")
        marker = self.runtime / 'off-fence'
        marker.write_text('b' * 32 + '\n')
        marker.chmod(0o600)
        fields = json.loads(self.ipc.request('scan', runtime=self.runtime, timeout=1))
        self.assertEqual(fields['fence'], 'b' * 32)
        with self.assertRaises(TypeError):
            self.ipc.request('scan', runtime=self.runtime, fence=None)


if __name__ == '__main__':
    unittest.main()
