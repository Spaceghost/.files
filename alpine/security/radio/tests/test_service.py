"""Persistent owner behavior with synthetic radios and no host network writes."""
from collections import deque
from pathlib import Path
import sys
import secrets
import threading
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / 'root/usr/local/lib'))
from privacyctl_runtime.dhcp import Failure, LeaseEvent
from privacyctl_runtime.lease import Lease
from privacyctl_runtime.network import IPv6Profile, NetworkError
from privacyctl_runtime.service import Owner


class Request:
    def __init__(self, command, profile=None, nonce=None, fence=None):
        self.command, self.profile = command, profile
        self.fence = fence
        self.nonce = nonce or secrets.token_hex(16)
        self.connected = True
        self.sent = []
        self.send_ok = True

    def alive(self):
        return self.connected

    def respond(self, ok, result='', error=''):
        self.sent.append((ok, result, error))
        return self.send_ok and self.connected

    def close(self):
        self.connected = False


class Server:
    def __init__(self):
        self.requests = []

    def poll(self):
        requests, self.requests = self.requests, []
        return requests


class WPA:
    def __init__(self, adapter, check):
        self.adapter, self.check = adapter, check
        self.events = deque()
        self.state = {'wpa_state': 'SCANNING'}

    def operation(self, name):
        self.check()
        self.adapter.log.append(name)
        if self.adapter.callback:
            callback, self.adapter.callback = self.adapter.callback, None
            callback()
        self.check()

    def expect_ok(self, command):
        self.operation(command)

    def network_ssid(self, network_id):
        self.operation('network_ssid')
        return self.adapter.configured_ssid

    def status(self):
        self.operation('status')
        return self.state.copy()

    def start_scan(self):
        self.operation('scan')
        self.events.clear()
        return 27

    def read_event(self, timeout=0):
        self.operation('event')
        return self.events.popleft() if self.events else None

    def request(self, command):
        self.operation(command)
        return 'bssid / frequency / signal level / flags / ssid\n'

    def close(self):
        self.adapter.log.append('wpa.close')


class Adapter:
    def __init__(self, log):
        self.log = log
        self.blocked = False
        self.bluetooth = True
        self.configured_ssid = 'synthetic-home'
        self.fence = None
        self.session = None
        self.callback = None
        self.fail_block = False
        self.fail_clear = False
        self.fail_fence = False

    def block_all(self):
        self.log.append('block')
        if self.fail_block:
            raise RuntimeError('block failed')
        self.blocked = True

    def block_bluetooth(self):
        self.log.append('bluetooth')
        raise RuntimeError('Bluetooth enforcement failed')

    def bluetooth_blocked(self):
        return self.bluetooth

    def clear_session(self):
        self.log.append('clear')
        if self.fail_clear:
            raise RuntimeError('clear failed')
        self.session = None

    def invalidate_fence(self):
        if self.fail_fence:
            raise RuntimeError('fence write failed')
        self.fence = secrets.token_hex(16)

    def begin_generation(self, generation, *, expected_fence):
        if expected_fence != self.fence:
            raise RuntimeError('request predates emergency off')
        self.captured_fence = self.fence

    def check_generation(self, generation):
        if self.fence != self.captured_fence:
            raise RuntimeError('emergency fence changed')

    def open_wpa(self, check):
        self.wpa = WPA(self, check)
        return self.wpa

    def read_profile(self, profile):
        return 3, 'synthetic-home', IPv6Profile()

    def write_session(self, profile, network_id, ssid):
        self.log.append('write_session')
        self.session = (profile, network_id, ssid)

    def unblock_wifi(self, check):
        check()
        self.log.append('unblock')
        self.blocked = False


class Manager:
    def __init__(self, log):
        self.log = log
        self.active = False
        self.events = []
        self.thread_ids = []
        self.starts = []
        self.replies = []
        self.fail_stop = False
        self.ack_ok = True

    def start(self, generation, interface):
        self.thread_ids.append(threading.get_ident())
        if self.active:
            raise AssertionError('overlapping DHCP ownership')
        self.log.append('start')
        self.starts.append((generation, interface))
        self.active = True

    def poll(self, timeout=0):
        self.thread_ids.append(threading.get_ident())
        events, self.events = self.events, []
        return events

    def reply(self, event_id, accepted):
        self.thread_ids.append(threading.get_ident())
        self.log.append('ack' if accepted else 'reject')
        self.replies.append((event_id, accepted))
        return self.ack_ok and accepted

    def stop(self):
        self.thread_ids.append(threading.get_ident())
        self.log.append('stop')
        if self.fail_stop:
            raise RuntimeError('child still alive')
        self.active = False
        self.events.clear()


class Applier:
    def __init__(self, test, check):
        self.test, self.check = test, check
        self.current = None
        self.fail_remove = False
        self.callback = None

    def apply(self, lease, previous=None, *, ipv6=IPv6Profile()):
        self.test.log.append('apply')
        self.current = object()
        if self.callback:
            self.callback()
        self.check()
        return self.current

    def remove(self, owned):
        self.test.log.append('remove')
        if self.fail_remove:
            raise NetworkError('partial cleanup', self.current)
        self.current = None


class OwnerTests(unittest.TestCase):
    def setUp(self):
        self.log = []
        self.now = 100.
        self.server = Server()
        self.adapter = Adapter(self.log)
        self.manager = Manager(self.log)
        self.owner = Owner(server=self.server, adapter=self.adapter, dhcp=self.manager,
                           applier_factory=self.factory, clock=lambda: self.now)

    def factory(self, generation, check):
        self.applier = Applier(self, check)
        return self.applier

    def request(self, command='connect', profile='home', **kwargs):
        request = Request(command, profile, **kwargs)
        self.server.requests.append(request)
        self.owner.step()
        return request

    def acquire(self):
        self.owner.start()
        request = self.request()
        self.adapter.wpa.state = {'wpa_state': 'COMPLETED', 'id': '3', 'ssid': 'synthetic-home'}
        self.now += .25
        self.owner.step()
        self.assertTrue(self.manager.active)
        return request

    def lease(self, event_id=1, kind='bound'):
        return LeaseEvent(event_id, kind, self.now, Lease.from_event({
            'interface': 'wlan0', 'ip': '192.0.2.2', 'mask': '24',
            'lease': '30', 'serverid': '192.0.2.1'}))

    def bound(self):
        request = self.acquire()
        self.manager.events.append(self.lease())
        self.owner.step()
        self.assertTrue(request.sent[0][0])
        return request

    def test_start_blocks_before_removing_stale_record(self):
        self.adapter.session = ('old', 99, 'old')
        self.owner.start()
        self.assertEqual(self.log[:2], ['block', 'clear'])
        self.assertIsNone(self.adapter.session)
        self.assertTrue(self.adapter.blocked)

    def test_initial_success_requires_apply_ack_and_record(self):
        request = self.acquire()
        self.assertFalse(request.sent)
        self.manager.events.append(self.lease())
        self.owner.step()
        self.assertEqual(self.owner.phase, 'bound')
        self.assertLess(self.log.index('apply'), self.log.index('ack'))
        self.assertLess(self.log.index('ack'), self.log.index('write_session'))
        self.assertTrue(request.sent[0][0])
        self.assertEqual(self.manager.starts[0][1], 'wlan0')
        self.assertEqual(set(self.manager.thread_ids), {threading.get_ident()})

    def test_policy_and_disable_precede_unblock(self):
        self.owner.start()
        self.request()
        for operation in ('DISCONNECT', 'DISABLE_NETWORK all', 'network_ssid'):
            self.assertLess(self.log.index(operation), self.log.index('unblock'))

    def test_wrong_configured_identity_never_unblocks(self):
        self.owner.start()
        self.adapter.configured_ssid = 'untrusted'
        request = self.request()
        self.assertFalse(request.sent[0][0])
        self.assertNotIn('unblock', self.log)

    def test_wrong_completed_identity_fails_immediately(self):
        self.owner.start()
        request = self.request()
        self.adapter.wpa.state = {'wpa_state': 'COMPLETED', 'id': '4', 'ssid': 'synthetic-home'}
        self.now += .25
        self.owner.step()
        self.assertTrue(self.adapter.blocked)
        self.assertFalse(self.manager.active)
        self.assertFalse(request.sent[0][0])

    def test_pending_caller_disconnection_cancels(self):
        request = self.acquire()
        request.connected = False
        self.owner.step()
        self.assertTrue(self.adapter.blocked)
        self.assertFalse(self.manager.active)

    def test_successful_caller_exit_preserves_session_and_renewal(self):
        request = self.bound()
        request.connected = False
        for i in range(2, 12):
            self.now += 25
            self.manager.events.append(self.lease(i, 'renew'))
            self.owner.step()
            self.assertEqual(self.owner.phase, 'bound')
        self.assertEqual(len(self.manager.starts), 1)
        self.assertEqual(len(self.manager.replies), 11)
        self.assertFalse(self.adapter.blocked)

    def test_off_during_apply_blocks_before_rejection_or_cleanup(self):
        request = self.acquire()
        off = Request('off')
        self.applier.callback = lambda: self.server.requests.append(off)
        self.log.clear()
        self.manager.events.append(self.lease())
        self.owner.step()
        self.assertTrue(self.adapter.blocked)
        self.assertNotIn((1, True), self.manager.replies)
        self.assertLess(self.log.index('block'), self.log.index('stop'))
        self.assertLess(self.log.index('block'), self.log.index('remove'))
        self.assertFalse(request.sent[0][0])
        self.assertTrue(off.sent[0][0])

    def test_off_during_wpa_wait_prevents_unblock(self):
        self.owner.start()
        off = Request('off')
        self.adapter.callback = lambda: self.server.requests.append(off)
        request = self.request()
        self.assertTrue(self.adapter.blocked)
        self.assertNotIn('unblock', self.log)
        self.assertFalse(request.sent[0][0])
        self.assertTrue(off.sent[0][0])

    def test_failure_during_apply_rejects_and_removes_partial_state(self):
        self.acquire()
        self.applier.callback = lambda: self.manager.events.append(Failure('hook died'))
        self.manager.events.append(self.lease())
        self.owner.step()
        self.assertTrue(self.adapter.blocked)
        self.assertFalse(self.manager.active)
        self.assertIsNone(self.applier.current)
        self.assertNotIn((1, True), self.manager.replies)

    def test_external_off_fence_during_apply_cancels(self):
        self.acquire()
        self.applier.callback = lambda: setattr(self.adapter, 'fence', 1)
        self.manager.events.append(self.lease())
        self.owner.step()
        self.assertTrue(self.adapter.blocked)
        self.assertNotIn((1, True), self.manager.replies)

    def test_wpa_identity_rechecked_after_apply_before_ack(self):
        self.acquire()
        self.applier.callback = lambda: self.adapter.wpa.state.update(id='9')
        self.manager.events.append(self.lease())
        self.owner.step()
        self.assertTrue(self.adapter.blocked)
        self.assertNotIn((1, True), self.manager.replies)

    def test_failed_cleanup_retains_handles_and_refuses_replacement(self):
        self.bound()
        self.applier.fail_remove = True
        old = self.applier
        off = self.request('off')
        self.assertFalse(off.sent[0][0])
        request = self.request()
        self.assertFalse(request.sent[0][0])
        self.assertEqual(len(self.manager.starts), 1)
        self.assertIsNotNone(old.current)
        old.fail_remove = False
        self.owner.step()
        self.assertIsNone(old.current)
        self.assertTrue(self.adapter.blocked)

    def test_failed_child_teardown_prevents_replacement(self):
        self.bound()
        self.log.clear()
        self.manager.fail_stop = True
        self.request('off')
        self.assertNotIn('remove', self.log, 'live DHCP writer must drain before lease removal')
        request = self.request()
        self.assertFalse(request.sent[0][0])
        self.assertEqual(len(self.manager.starts), 1)
        self.manager.fail_stop = False
        self.owner.step()
        self.assertFalse(self.manager.active)

    def test_response_send_failure_revokes_initial_lease(self):
        request = self.acquire()
        request.send_ok = False
        self.manager.events.append(self.lease())
        self.owner.step()
        self.assertTrue(self.adapter.blocked)
        self.assertFalse(self.manager.active)
        self.assertIsNone(self.adapter.session)

    def test_failure_and_bluetooth_or_wpa_loss_block_bound_session(self):
        for cause in ('dhcp', 'bluetooth', 'wpa'):
            with self.subTest(cause=cause):
                self.setUp()
                self.bound()
                self.log.clear()
                if cause == 'dhcp':
                    self.manager.events.append(Failure('lease expired'))
                elif cause == 'bluetooth':
                    self.adapter.bluetooth = False
                else:
                    self.adapter.wpa.state['wpa_state'] = 'DISCONNECTED'
                self.now += .25
                self.owner.step()
                self.assertTrue(self.adapter.blocked)
                self.assertLess(self.log.index('block'), self.log.index('stop'))

    def test_scan_requires_exact_native_identifier_and_finishes_blocked(self):
        self.owner.start()
        request = self.request('scan')
        self.adapter.wpa.events.extend(['<3>CTRL-EVENT-SCAN-RESULTS',
                                       '<3>CTRL-EVENT-SCAN-RESULTS id=26'])
        self.owner.step()
        self.assertFalse(request.sent)
        self.adapter.wpa.events.append('<3>CTRL-EVENT-SCAN-RESULTS id=27')
        self.owner.step()
        self.assertTrue(request.sent[0][0])
        self.assertTrue(self.adapter.blocked)
        self.assertFalse(self.manager.starts)

    def test_association_and_scan_timeouts_cancel(self):
        for command, seconds in [('connect', 20), ('scan', 15)]:
            with self.subTest(command=command):
                self.setUp()
                self.owner.start()
                request = self.request(command)
                self.now += seconds
                self.owner.step()
                self.assertFalse(request.sent[0][0])
                self.assertTrue(self.adapter.blocked)

    def test_ack_failure_cannot_publish_session(self):
        request = self.acquire()
        self.manager.ack_ok = False
        self.manager.events.append(self.lease())
        self.owner.step()
        self.assertFalse(request.sent[0][0])
        self.assertTrue(self.adapter.blocked)
        self.assertIsNone(self.adapter.session)

    def test_stale_queued_event_cannot_apply_to_replacement(self):
        self.bound()
        self.manager.events.append(self.lease(2, 'renew'))
        self.request()
        self.assertEqual(self.log.count('apply'), 1)

    def test_simultaneous_connects_cannot_replace_without_blocked_teardown(self):
        self.owner.start()
        first, second = Request('connect', 'home'), Request('connect', 'home')
        self.server.requests.extend([first, second])
        self.owner.step()
        self.adapter.wpa.state = {'wpa_state': 'COMPLETED', 'id': '3', 'ssid': 'synthetic-home'}
        self.now += .25
        self.owner.step()
        self.assertTrue(first.sent, 'superseded caller must receive a cancellation')
        self.assertFalse(first.sent[0][0])
        self.assertIn('wpa.close', self.log)

    def test_retry_cleanup_reasserts_block_before_releasing_resources(self):
        self.bound()
        self.manager.fail_stop = True
        self.request('off')
        self.adapter.blocked = False
        self.manager.fail_stop = False
        self.log.clear()
        self.owner.step()
        self.assertTrue(self.adapter.blocked)
        self.assertLess(self.log.index('block'), self.log.index('stop'))

    def test_lease_received_during_wpa_checkpoint_is_preserved(self):
        self.acquire()
        self.adapter.callback = lambda: self.manager.events.append(self.lease())
        self.now += .25
        self.owner.step()
        self.assertEqual(self.owner.phase, 'bound')
        self.assertEqual(self.manager.replies, [(1, True)])

    def test_repeated_nonce_cannot_replace_bound_session(self):
        request = self.bound()
        duplicate = self.request(nonce=request.nonce)
        self.assertFalse(duplicate.sent[0][0])
        self.assertEqual(self.owner.phase, 'bound')
        self.assertEqual(len(self.manager.starts), 1)

    def test_shutdown_blocks_before_teardown(self):
        self.bound()
        self.log.clear()
        self.owner.shutdown()
        self.assertEqual(self.owner.phase, 'stopped')
        self.assertLess(self.log.index('block'), self.log.index('stop'))
        self.assertFalse(self.manager.active)

    def test_block_failure_retains_resources_until_a_verified_retry(self):
        self.bound()
        self.adapter.fail_block = True
        self.log.clear()
        self.request('off')
        self.assertTrue(self.manager.active)
        self.assertNotIn('stop', self.log)
        self.assertNotIn('remove', self.log)
        self.adapter.fail_block = False
        self.owner.step()
        self.assertFalse(self.manager.active)

    def test_startup_record_failure_never_reaches_idle(self):
        self.adapter.fail_clear = True
        with self.assertRaises(RuntimeError):
            self.owner.start()
        self.assertTrue(self.adapter.blocked)
        self.assertEqual(self.owner.phase, 'stopped')

    def test_caller_disappearing_during_apply_revokes_partial_lease(self):
        request = self.acquire()
        self.applier.callback = lambda: setattr(request, 'connected', False)
        self.manager.events.append(self.lease())
        self.owner.step()
        self.assertTrue(self.adapter.blocked)
        self.assertFalse(self.manager.active)
        self.assertIsNone(self.applier.current)
        self.assertNotIn((1, True), self.manager.replies)

    def test_apply_exception_preserves_ownership_for_cleanup(self):
        self.acquire()
        def fail():
            raise NetworkError('kernel operation failed', self.applier.current)
        self.applier.callback = fail
        self.manager.events.append(self.lease())
        self.owner.step()
        self.assertTrue(self.adapter.blocked)
        self.assertIsNone(self.applier.current)
        self.assertNotIn((1, True), self.manager.replies)

    def test_owner_rejects_cross_thread_step_before_manager_access(self):
        self.owner.start()
        errors = []
        def wrong_thread():
            try:
                self.owner.step()
            except RuntimeError as error:
                errors.append(str(error))
        thread = threading.Thread(target=wrong_thread)
        thread.start()
        thread.join()
        self.assertEqual(len(errors), 1)
        self.assertEqual(self.manager.thread_ids, [])

    def test_idle_owner_reasserts_block_once_per_second(self):
        self.owner.start()
        self.adapter.blocked = False
        self.log.clear()
        for i in range(1, 10):
            self.now = 100 + i / 10
            self.owner.step()
        self.assertNotIn('block', self.log)
        self.now = 101
        self.owner.step()
        self.assertTrue(self.adapter.blocked)
        self.assertEqual(self.log.count('block'), 1)
        self.owner.step()
        self.assertEqual(self.log.count('block'), 1)

    def test_request_submitted_before_emergency_off_cannot_unblock(self):
        self.owner.start()
        self.adapter.fence = 'b' * 32
        request = self.request(fence='a' * 32)
        self.assertFalse(request.sent[0][0])
        self.assertTrue(self.adapter.blocked)
        self.assertNotIn('unblock', self.log)

    def test_request_submitted_after_emergency_off_uses_new_fence(self):
        self.owner.start()
        self.adapter.fence = 'b' * 32
        request = self.request(fence='b' * 32)
        self.assertFalse(request.sent)
        self.assertFalse(self.adapter.blocked)
        self.assertEqual(self.owner.phase, 'connecting')

    def test_successful_off_rejects_request_captured_before_off(self):
        self.owner.start()
        delayed = Request('connect', 'home', fence=self.adapter.fence)
        off = self.request('off')
        self.assertTrue(off.sent[0][0])
        self.server.requests.append(delayed)
        self.owner.step()
        self.assertFalse(delayed.sent[0][0])
        self.assertNotIn('unblock', self.log)
        fresh = self.request(fence=self.adapter.fence)
        self.assertFalse(fresh.sent)
        self.assertFalse(self.adapter.blocked)

    def test_failed_off_barrier_still_blocks_but_cannot_report_success(self):
        self.bound()
        self.adapter.fail_fence = True
        self.log.clear()
        off = self.request('off')
        self.assertFalse(off.sent[0][0])
        self.assertIn('fence', off.sent[0][2])
        self.assertTrue(self.adapter.blocked)
        self.assertFalse(self.manager.active)
        self.assertLess(self.log.index('block'), self.log.index('stop'))


if __name__ == '__main__':
    unittest.main()
