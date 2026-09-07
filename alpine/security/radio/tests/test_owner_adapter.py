"""Owner adapter and cooperative WPA checks; never operate host radios."""
from collections import deque
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import socket
import sys
import tempfile
import time
import unittest
from unittest import mock

SCRIPT = Path(__file__).parents[1] / 'root/usr/local/sbin/privacyctl'
legacy = importlib.machinery.SourceFileLoader('owner_cli_test', str(SCRIPT)).load_module()
sys.path.insert(0, str(SCRIPT.parents[1] / 'lib'))


@unittest.skipUnless(os.geteuid() == 0, 'root-private file contracts')
class NativeAdapterTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.find_spec('privacyctl_runtime.adapter')
        self.assertIsNotNone(spec, 'native owner adapter is not implemented')
        from privacyctl_runtime import adapter
        self.module = adapter
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.calls = []
        class System:
            def block_all(s): self.calls.append('block')
            def unblock_wifi(s): self.calls.append('unblock')
            def states(s, kind): return ['0']
        self.old_lock, self.old_session = legacy.LOCK_FILE, legacy.SESSION_FILE
        legacy.LOCK_FILE, legacy.SESSION_FILE = self.root/'radio.lock', self.root/'session.json'
        self.addCleanup(setattr, legacy, 'LOCK_FILE', self.old_lock)
        self.addCleanup(setattr, legacy, 'SESSION_FILE', self.old_session)
        self.native = adapter.NativeAdapter(legacy, runtime=self.root, system=System())

    def test_emergency_off_invalidates_pending_generation_before_unblock(self):
        self.native.begin_generation('a'*32)
        self.native.emergency_off()
        with self.assertRaisesRegex(RuntimeError, 'off|cancel'):
            self.native.unblock_wifi(lambda: self.native.check_generation('a'*32))
        self.assertEqual(self.calls, ['block'])
        with self.assertRaisesRegex(RuntimeError, 'cancelled'):
            self.native.begin_generation('b'*32)
        self.native.begin_generation('b'*32, expected_fence=self.native.fence.read())
        self.native.unblock_wifi(lambda: self.native.check_generation('b'*32))
        self.assertEqual(self.calls, ['block', 'unblock'])

    def test_unsafe_fence_never_permits_unblock(self):
        self.native.begin_generation('a'*32)
        target = self.root/'other'
        target.write_text('b'*32+'\n')
        (self.root/'off-fence').symlink_to(target)
        with self.assertRaises(RuntimeError):
            self.native.unblock_wifi(lambda: self.native.check_generation('a'*32))
        self.assertNotIn('unblock', self.calls)

    def test_off_still_blocks_when_fence_cannot_be_written(self):
        (self.root/'off-fence').mkdir()
        with self.assertRaises(Exception): self.native.emergency_off()
        self.assertEqual(self.calls, ['block'])

    def test_crash_dirty_marker_rejects_new_generation(self):
        self.module.Fence(self.root, 'lease-dirty').write('a'*32)
        with self.assertRaisesRegex(RuntimeError, 'recovery'):
            self.native.begin_generation('b'*32)
        self.assertEqual(self.calls, [])

    def test_failed_apply_keeps_dirty_marker_until_explicit_cleanup(self):
        class Applier:
            current = None
            def apply(s, *_a, **_k): raise RuntimeError('partial failure')
            def remove(s, owned): self.calls.append('remove')
        wrapped = self.module.JournaledApplier(Applier(), self.root, 'a'*32)
        with self.assertRaisesRegex(RuntimeError, 'partial'): wrapped.apply(None)
        self.assertEqual(self.module.Fence(self.root, 'lease-dirty').read(), 'a'*32)
        wrapped.remove(None)
        self.assertIsNone(self.module.Fence(self.root, 'lease-dirty').read())

    def test_cleanup_error_keeps_crash_marker(self):
        class Applier:
            current = None
            def apply(s, *_a, **_k): return None
            def remove(s, owned): raise RuntimeError('cleanup failure')
        wrapped = self.module.JournaledApplier(Applier(), self.root, 'a'*32)
        wrapped.apply(None)
        with self.assertRaisesRegex(RuntimeError, 'cleanup'): wrapped.remove(None)
        self.assertEqual(self.module.Fence(self.root, 'lease-dirty').read(), 'a'*32)

    def test_initial_probe_cleanup_failure_retains_dirty_marker_without_owned_state(self):
        from privacyctl_runtime.lease import Lease
        from privacyctl_runtime.network import LeaseApplier, NetworkError
        class Backend:
            pending = False
            fail_drain = True
            def resolver(s, **options):
                s.pending = True
                raise RuntimeError('resolver command cleanup pending')
            def drain_pending(s, **options):
                if s.fail_drain:
                    raise RuntimeError('command still alive')
                s.pending = False
        backend = Backend()
        wrapped = self.module.JournaledApplier(
            LeaseApplier('a'*32, backend=backend), self.root, 'a'*32)
        lease = Lease.from_event({'interface': 'wlan0', 'ip': '192.0.2.2', 'mask': '24',
                                  'lease': '60', 'serverid': '192.0.2.1'})
        with self.assertRaises(NetworkError):
            wrapped.apply(lease)
        self.assertIsNone(wrapped.current)
        with self.assertRaisesRegex(NetworkError, 'command still alive'):
            wrapped.remove(None)
        self.assertTrue(backend.pending)
        self.assertEqual(self.module.Fence(self.root, 'lease-dirty').read(), 'a'*32)
        with self.assertRaisesRegex(RuntimeError, 'recovery'):
            self.native.begin_generation('b'*32)
        backend.fail_drain = False
        wrapped.remove(None)
        self.assertFalse(backend.pending)
        self.assertIsNone(self.module.Fence(self.root, 'lease-dirty').read())
        self.native.begin_generation('b'*32)

    def test_ipv6_policy_requires_explicit_profile_and_rejects_bad_types(self):
        import json
        path = self.root/'ipv6.json'
        values = {'addresses':['2001:db8::2/64'], 'routers':['2001:db8::1']}
        path.write_text(json.dumps({'version':1,'profiles':{'shmecklebucket':values}}))
        path.chmod(0o600)
        self.assertEqual(str(self.module.read_ipv6(path, 'shmecklebucket').addresses[0]),
                         '2001:db8::2/64')
        with self.assertRaises(RuntimeError): self.module.read_ipv6(path, 'iphone-hotspot')
        for value in (True, 1, None, '2001:db8::2/64'):
            values['addresses'] = value
            path.write_text(json.dumps({'version':1,'profiles':{'shmecklebucket':values}}))
            with self.assertRaises(RuntimeError): self.module.read_ipv6(path, 'shmecklebucket')
        path.write_text('{"version":1,"version":1,"profiles":{}}')
        with self.assertRaises(RuntimeError): self.module.read_ipv6(path, 'shmecklebucket')


class CliRoutingTests(unittest.TestCase):
    def test_connect_and_scan_use_owner_without_legacy_fallback(self):
        self.assertTrue(hasattr(legacy, 'request_owner'), 'owner CLI routing missing')
        with mock.patch.object(legacy, 'request_owner', side_effect=legacy.PrivacyError('unavailable')) as request, \
             mock.patch.object(legacy, 'run_locked', side_effect=AssertionError('legacy fallback')), \
             mock.patch.object(legacy.os, 'geteuid', return_value=0):
            self.assertEqual(legacy.main(['connect','shmecklebucket']), 1)
            self.assertEqual(legacy.main(['scan']), 1)
        self.assertEqual(request.call_count, 2)

    def test_off_has_emergency_fence_fallback(self):
        self.assertTrue(hasattr(legacy, 'request_owner'), 'owner CLI routing missing')
        with mock.patch.object(legacy, 'request_owner', side_effect=legacy.PrivacyError('unavailable')), \
             mock.patch.object(legacy, 'emergency_off') as emergency, \
             mock.patch.object(legacy.os, 'geteuid', return_value=0):
            self.assertEqual(legacy.main(['off']), 0)
            emergency.assert_called_once()


class CooperativeWpaTests(unittest.TestCase):
    def control(self, client):
        control = object.__new__(legacy.WpaControl)
        control.sock, control.events = client, deque()
        end = time.monotonic() + .05
        def check():
            if time.monotonic() >= end:
                raise RuntimeError('cancelled by owner')
        control.check = check
        return control

    def test_cancel_during_unanswered_command(self):
        client, peer = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
        with client, peer:
            control = self.control(client)
            started = time.monotonic()
            with self.assertRaisesRegex(RuntimeError, 'cancelled by owner'):
                control.request('STATUS', deadline=.5)
            self.assertLess(time.monotonic() - started, .25)

    def test_cancel_during_full_command_send_queue(self):
        client, peer = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
        with client, peer:
            client.setblocking(False)
            while True:
                try:
                    client.send(b'x' * 4096)
                except BlockingIOError:
                    break
            control = self.control(client)
            with self.assertRaisesRegex(RuntimeError, 'cancelled by owner'):
                control.request('STATUS', deadline=.5)

    def test_cancel_during_event_wait(self):
        client, peer = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
        with client, peer:
            control = self.control(client)
            with self.assertRaisesRegex(RuntimeError, 'cancelled by owner'):
                control.read_event(.5)


if __name__ == '__main__':
    unittest.main()
