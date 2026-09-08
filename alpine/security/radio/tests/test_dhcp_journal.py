"""DHCP journal/gate and lifetime-lock tests; all process operations are fake."""
from contextlib import ExitStack
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / 'root/usr/local/lib'))
from privacyctl_runtime import dhcp

GENERATION = 'a' * 32


class FakeSelector:
    def __init__(self):
        self.registered = []

    def register(self, *args):
        self.registered.append(args)

    def unregister(self, file):
        pass

    def close(self):
        pass


class FakeSocket:
    def __init__(self, events):
        self.events = events
        self.closed = False

    def fileno(self):
        return 901

    def send(self, data):
        self.events.append(('send', data))
        return len(data)

    def recvmsg(self, limit):
        frame = {'version': 1, 'generation': GENERATION, 'event': 'ready',
                 'fields': {'interface': 'synthetic0'}}
        return json.dumps(frame).encode(), [], 0, None

    def close(self):
        self.closed = True


class FakeListener:
    def bind(self, path):
        # An ordinary disposable file gives stop() a real identity to unlink.
        Path(path).write_bytes(b'listener fixture')

    def listen(self, count):
        pass

    def setblocking(self, enabled):
        pass

    def close(self):
        pass


class FakeJournal:
    def __init__(self, events):
        self.events = events
        self.started_error = None
        self.finished_error = None
        self.slot = None

    def writer_started(self, kind, pid, pidfd, operation):
        os.fstat(pidfd)
        self.slot = {'kind': kind, 'pid': pid, 'operation': operation}
        self.events.append(('persist', kind, pid, pidfd, operation))
        if self.started_error:
            raise self.started_error

    def writer_finished(self, kind):
        self.events.append(('finish', kind))
        if self.finished_error:
            raise self.finished_error
        self.slot = None


class ClosedManagerTests(unittest.TestCase):
    def test_close_releases_selector_and_is_terminal_and_idempotent(self):
        manager = dhcp.DHCPManager('/unused-dhcp-close')
        try:
            manager.close()
            with self.assertRaises(ValueError):
                manager._selector.fileno()
            manager.close()
            with self.assertRaises(dhcp.DHCPError):
                manager.acquire()
            with self.assertRaises(dhcp.DHCPError):
                manager.start(GENERATION, 'synthetic0')
        finally:
            manager._selector.close()


class JournalGateTests(unittest.TestCase):
    def setUp(self):
        self.assertIn('journal', inspect.signature(dhcp.DHCPManager).parameters,
                      'DHCP durable journal integration is missing')
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.events = []
        self.journal = FakeJournal(self.events)
        self.manager = dhcp.DHCPManager('/unused-dhcp-test', journal=self.journal)
        self.manager._selector.close()
        self.manager._selector = FakeSelector()
        self.stack.enter_context(patch.object(dhcp.selectors, 'DefaultSelector', FakeSelector))
        self.stack.enter_context(patch.object(dhcp.subprocess, 'Popen', side_effect=AssertionError('real Popen forbidden')))
        self.stack.enter_context(patch.object(dhcp.os, 'kill', side_effect=AssertionError('real numeric signal forbidden')))
        self.stack.enter_context(patch.object(dhcp.signal, 'pidfd_send_signal', side_effect=self.signal))
        self.stack.enter_context(patch.object(dhcp.select, 'select', side_effect=self.ready))
        self.process_dead = False
        self.file = self.stack.enter_context(tempfile.TemporaryFile())
        self.client_fd = os.dup(self.file.fileno())
        self.addCleanup(self.close_client)
        self.stack.enter_context(patch.object(dhcp.os, 'pidfd_open', return_value=self.client_fd))
        self.stack.enter_context(patch.object(dhcp.Path, 'read_text', return_value='NSpid:\t321\t1\n'))
        self.stack.enter_context(patch.object(dhcp.os, 'readlink', side_effect=lambda path:
            'pid:[100]' if str(path) == '/proc/self/ns/pid' else 'pid:[200]'))
        self.stack.enter_context(patch.object(dhcp, 'process_start', return_value=100))
        self.stack.enter_context(patch.object(self.manager, '_peer_allowed', return_value=True))
        self.manager.phase = 'starting'
        self.manager._interface = 'synthetic0'
        self.manager._generation = GENERATION
        self.socket = FakeSocket(self.events)
        self.peer = dhcp._Peer(self.socket, 321, 100.0)
        self.manager._peers[self.socket.fileno()] = self.peer

    def close_client(self):
        try:
            os.close(self.client_fd)
        except OSError:
            pass

    def signal(self, fd, sig):
        self.events.append(('signal', fd))

    def ready(self, read, write, exceptional, timeout):
        if self.process_dead:
            self.events.append(('dead', read[0]))
        return (read if self.process_dead else [], [], [])

    def test_durable_writer_is_registered_before_readiness_yes(self):
        self.manager._receive(self.peer)
        self.assertEqual(self.events, [('persist', 'dhcp', 321, self.client_fd, 'dhcp-client'),
                                       ('send', dhcp.YES)])
        self.assertEqual(self.manager.phase, 'acquiring')
        self.assertEqual(self.manager._client_fd, self.client_fd)

    def test_journal_failure_never_sends_yes_and_retains_init_handle(self):
        self.journal.started_error = RuntimeError('injected directory fsync failure')
        self.manager._receive(self.peer)
        self.assertEqual(self.manager.phase, 'failed')
        self.assertFalse(any(event[0] == 'send' for event in self.events))
        self.assertTrue(self.socket.closed)
        self.assertEqual(self.manager._client_fd, self.client_fd)
        os.fstat(self.client_fd)
        self.assertIsNotNone(self.journal.slot)

    def test_slot_clears_only_after_init_death_and_remains_on_timeout(self):
        self.manager._ready(self.peer, {'interface': 'synthetic0'})
        with self.assertRaises(dhcp.DHCPError):
            self.manager.stop()
        self.assertIsNotNone(self.journal.slot)
        self.assertFalse(any(event[0] == 'finish' for event in self.events))
        os.fstat(self.client_fd)
        self.process_dead = True
        self.manager.stop()
        self.assertIsNone(self.journal.slot)
        death = next(index for index, event in enumerate(self.events) if event[0] == 'dead')
        finish = self.events.index(('finish', 'dhcp'))
        self.assertLess(death, finish)
        with self.assertRaises(OSError):
            os.fstat(self.client_fd)

    def test_uncertain_started_write_can_clear_only_after_death(self):
        self.journal.started_error = OSError('injected file fsync failure')
        self.manager._receive(self.peer)
        self.process_dead = True
        self.manager.stop()
        self.assertIn(('finish', 'dhcp'), self.events)
        self.assertIsNone(self.journal.slot)
        self.assertFalse(any(event[0] == 'send' for event in self.events))

    def test_failed_completion_write_retains_handles_for_retry(self):
        self.manager._ready(self.peer, {'interface': 'synthetic0'})
        self.process_dead = True
        self.journal.finished_error = RuntimeError('injected clean-slot fsync failure')
        with self.assertRaises(dhcp.DHCPError):
            self.manager.stop()
        self.assertEqual(self.manager.phase, 'failed')
        self.assertIsNotNone(self.journal.slot)
        self.assertEqual(self.manager._client_fd, self.client_fd)
        os.fstat(self.client_fd)
        self.journal.finished_error = None
        self.manager.stop()
        self.assertIsNone(self.journal.slot)

    def test_no_journal_preserves_readiness_and_stop_contract(self):
        self.manager.journal = None
        self.manager._ready(self.peer, {'interface': 'synthetic0'})
        self.assertEqual(self.events, [('send', dhcp.YES)])
        self.process_dead = True
        self.manager.stop()
        self.assertEqual(self.manager.phase, 'idle')

    def test_launcher_reap_failure_retains_slot_even_when_init_is_dead(self):
        self.manager._ready(self.peer, {'interface': 'synthetic0'})
        self.process_dead = True
        process = SimpleNamespace(wait=lambda **kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired('synthetic-launcher', 0)), kill=lambda: None)
        self.manager._process = process
        with self.assertRaises(dhcp.DHCPError):
            self.manager.stop()
        self.assertIsNotNone(self.journal.slot)
        self.assertFalse(any(event[0] == 'finish' for event in self.events))
        os.fstat(self.client_fd)
        process.wait = lambda **kwargs: 0
        self.manager.stop()
        self.assertIsNone(self.journal.slot)


@unittest.skipUnless(os.geteuid() == 0, 'root-private ownership fixtures require root')
class LifetimeLockTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(hasattr(dhcp.DHCPManager, 'acquire'), 'DHCP lifetime ownership is missing')
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix='dhcp-lock-')))
        self.manager = dhcp.DHCPManager(self.root / 'runtime')
        self.addCleanup(self.manager.close)
        self.stack.enter_context(patch.object(dhcp.subprocess, 'Popen', side_effect=AssertionError('real Popen forbidden')))
        self.stack.enter_context(patch.object(dhcp.os, 'kill', side_effect=AssertionError('real numeric signal forbidden')))
        self.stack.enter_context(patch.object(dhcp.signal, 'pidfd_send_signal', side_effect=AssertionError('real pidfd signal forbidden')))

    def assert_locked(self):
        contender = dhcp.DHCPManager(self.manager.runtime)
        try:
            with self.assertRaises(dhcp.DHCPError):
                contender.acquire()
        finally:
            contender.close()

    def fake_launch(self):
        """Replace only child/bootstrap operations; keep locks and files real."""
        file = self.stack.enter_context(tempfile.TemporaryFile())
        self.manager._selector.close()
        self.manager._selector = FakeSelector()
        self.stack.enter_context(patch.object(dhcp.selectors, 'DefaultSelector', FakeSelector))
        self.stack.enter_context(patch.object(dhcp, 'executable', return_value=None))
        self.stack.enter_context(patch.object(dhcp.socket, 'socket', return_value=FakeListener()))
        self.stack.enter_context(patch.object(dhcp, 'context_fd', side_effect=lambda value: os.dup(file.fileno())))
        self.stack.enter_context(patch.object(dhcp, 'process_start', return_value=100))
        self.stack.enter_context(patch.object(dhcp.Path, 'read_text', return_value='12345678-1234-1234-1234-123456789abc'))
        self.stack.enter_context(patch.object(dhcp.os, 'pidfd_open', side_effect=lambda pid, flags: os.dup(file.fileno())))
        self.stack.enter_context(patch.object(dhcp.signal, 'pidfd_send_signal', return_value=None))
        self.stack.enter_context(patch.object(dhcp.select, 'select', side_effect=lambda read, *args: (read, [], [])))
        child = SimpleNamespace(pid=543, wait=lambda **kwargs: 0)
        self.stack.enter_context(patch.object(dhcp.subprocess, 'Popen', return_value=child))

    def test_acquire_is_idempotent_and_has_no_socket_or_process(self):
        self.manager.acquire()
        lock = self.manager._lock
        self.manager.acquire()
        self.assertEqual(self.manager._lock, lock)
        self.assertFalse(self.manager.active)
        self.assertIsNone(self.manager._listener)
        self.assertEqual(list(self.manager.runtime.iterdir()), [self.manager.runtime / 'dhcp.lock'])
        self.assert_locked()

    def test_explicit_lock_survives_stop_and_close_releases_it(self):
        self.manager.acquire()
        self.manager.stop()
        self.assert_locked()
        self.manager.close()
        contender = dhcp.DHCPManager(self.manager.runtime)
        contender.acquire()
        contender.close()

    def test_explicit_lock_survives_failed_start_and_allows_retry(self):
        self.manager.acquire()
        for generation in ['a' * 32, 'b' * 32]:
            with patch.object(dhcp, 'executable', side_effect=ValueError('synthetic invalid executable')):
                with self.assertRaises(dhcp.DHCPError):
                    self.manager.start(generation, 'synthetic0')
            self.assert_locked()

    def test_explicit_lock_spans_successful_start_stop_and_next_generation(self):
        self.fake_launch()
        self.manager.acquire()
        lock = self.manager._lock
        for generation in ['a' * 32, 'b' * 32]:
            self.manager.start(generation, 'synthetic0')
            self.assertTrue(self.manager.active)
            self.assertEqual(self.manager._lock, lock)
            with self.assertRaises(dhcp.DHCPError):
                self.manager.start('c' * 32, 'synthetic0')
            self.manager.stop()
            self.assertFalse(self.manager.active)
            self.assertFalse(Path(self.manager.socket_path).exists())
            self.assertEqual(self.manager._lock, lock)
            self.assert_locked()

    def test_lazy_start_stop_releases_ownership_for_existing_users(self):
        self.fake_launch()
        self.manager.start(GENERATION, 'synthetic0')
        self.assert_locked()
        self.manager.stop()
        self.assertIsNone(self.manager._lock)
        contender = dhcp.DHCPManager(self.manager.runtime)
        contender.acquire()
        contender.close()

    def test_longer_hook_budget_does_not_extend_launch_readiness(self):
        self.fake_launch()
        with patch.object(dhcp, 'HOOK_TIMEOUT', 12), patch.object(dhcp, 'boottime', return_value=100):
            self.manager.start(GENERATION, 'synthetic0')
        with patch.object(dhcp, 'boottime', return_value=104.999):
            self.manager._deadlines()
        self.assertEqual(self.manager.phase, 'starting')
        with patch.object(dhcp, 'boottime', return_value=105):
            self.manager._deadlines()
        self.assertEqual(self.manager.phase, 'failed')
        self.assertEqual(list(self.manager._output), [dhcp.Failure('DHCP readiness deadline exceeded')])

    def test_lazy_start_failure_releases_lock_and_socket(self):
        self.fake_launch()
        with patch.object(dhcp.subprocess, 'Popen', side_effect=OSError('synthetic launch failure')):
            with self.assertRaises(dhcp.DHCPError):
                self.manager.start(GENERATION, 'synthetic0')
        self.assertIsNone(self.manager._lock)
        self.assertIsNone(self.manager._directory)
        self.assertFalse(Path(self.manager.socket_path).exists())

    def test_failed_stop_or_close_retains_explicit_ownership(self):
        self.manager.acquire()
        file = self.stack.enter_context(tempfile.TemporaryFile())
        self.manager._client_fd = os.dup(file.fileno())
        with patch.object(dhcp.signal, 'pidfd_send_signal'), patch.object(
                dhcp.select, 'select', return_value=([], [], [])):
            with self.assertRaises(dhcp.DHCPError):
                self.manager.close()
        self.assert_locked()
        os.close(self.manager._client_fd)
        self.manager._client_fd = None

    def test_unsafe_lock_and_non_root_acquire_are_rejected(self):
        with patch.object(dhcp.os, 'geteuid', return_value=1000):
            with self.assertRaises(dhcp.DHCPError):
                self.manager.acquire()
        self.manager.runtime.mkdir(mode=0o700)
        lock = self.manager.runtime / 'dhcp.lock'
        lock.write_bytes(b'')
        lock.chmod(0o644)
        with self.assertRaises(dhcp.DHCPError):
            self.manager.acquire()
        self.assertIsNone(self.manager._lock)
        self.assertIsNone(self.manager._directory)


if __name__ == '__main__':
    unittest.main()
