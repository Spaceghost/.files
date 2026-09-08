"""Recovery startup ordering using private sockets and synthetic dependencies."""
import inspect
from contextlib import nullcontext
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parents[1] / 'root/usr/local/lib'))
from privacyctl_runtime import adapter, ipc, runner


@unittest.skipUnless(os.geteuid() == 0, 'private root-owned IPC fixtures')
class OwnershipBeforeReadinessTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(hasattr(ipc.Server, 'acquire'), 'separate owner acquisition missing')
        self.temporary = tempfile.TemporaryDirectory(prefix='owner-startup-')
        self.addCleanup(self.temporary.cleanup)
        self.runtime = Path(self.temporary.name) / 'run'
        self.server = ipc.Server(self.runtime)
        self.addCleanup(self.server.close)

    def test_lock_excludes_competitor_before_socket_is_published(self):
        self.server.acquire()
        self.server.acquire()
        self.assertFalse((self.runtime / 'owner.sock').exists())
        self.assertEqual(self.server.poll(), [])
        second = ipc.Server(self.runtime)
        self.addCleanup(second.close)
        with self.assertRaises(ipc.IPCError):
            second.acquire()
        self.server.listen()
        with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as peer:
            peer.connect(str(self.runtime / 'owner.sock'))
        self.server.close()
        second.acquire()
        self.assertFalse((self.runtime / 'owner.sock').exists())

    def test_listen_requires_ownership_and_cannot_replace_live_listener(self):
        with self.assertRaises(ipc.IPCError):
            self.server.listen()
        self.server.open()
        identity = (self.runtime / 'owner.sock').stat().st_ino
        with self.assertRaises(ipc.IPCError):
            self.server.listen()
        self.assertEqual((self.runtime / 'owner.sock').stat().st_ino, identity)


class RunnerRecoveryTests(unittest.TestCase):
    def exercise(self, failure=None):
        events, stop = [], [False]
        journal = object()
        def event(name):
            events.append(name)
            if name == failure:
                raise RuntimeError('injected ' + name)
        class Adapter:
            def __init__(self, legacy): self.journal = journal
            def emergency_off(self): event('block')
            def block_all(self): event('block')
            def check_generation(self, generation): pass
            def prepare_recovery(self, *, check): check(); event('recover')
            def applier(self, *args): raise AssertionError('unexpected generation')
        class Server:
            def acquire(self): event('owner.acquire')
            def open(self): raise AssertionError('readiness opened before recovery')
            def listen(self): event('listen')
            def close(self): event('owner.close')
        class Manager:
            def __init__(self, runtime): self.journal = None
            def acquire(self): event('dhcp.acquire')
            def close(self): event('dhcp.close')
        class Owner:
            def __init__(self, *, server, adapter, dhcp, applier_factory):
                if dhcp.journal is not journal:
                    raise AssertionError('DHCP must share recovered journal')
            def start(self): event('owner.start')
            def step(self): event('step'); stop[0] = True
            def shutdown(self): event('shutdown')
        def guarded(child, block):
            event('guardian.acquire')
            try:
                block()
                child(lambda: stop[0])
            finally:
                event('guardian.close')
            return 0
        with patch.multiple(runner, NativeAdapter=Adapter, Server=Server,
                            DHCPManager=Manager, Owner=Owner, guarded=guarded):
            if failure:
                with self.assertRaisesRegex(RuntimeError, 'injected'):
                    runner.run(object())
            else:
                runner.run(object())
        return events

    def test_recovery_precedes_readiness_under_all_lifetime_locks(self):
        self.assertEqual(self.exercise(), [
            'guardian.acquire', 'block', 'owner.acquire', 'dhcp.acquire',
            'recover', 'owner.start', 'listen', 'step', 'shutdown',
            'dhcp.close', 'owner.close', 'guardian.close'])

    def test_failed_recovery_never_listens_and_releases_in_reverse_order(self):
        events = self.exercise('recover')
        self.assertNotIn('listen', events)
        self.assertNotIn('owner.start', events)
        self.assertEqual(events[-3:], ['dhcp.close', 'owner.close', 'guardian.close'])

    def test_dhcp_lock_failure_never_recovers_or_listens(self):
        events = self.exercise('dhcp.acquire')
        self.assertNotIn('recover', events)
        self.assertNotIn('listen', events)


class PreparedApplierTests(unittest.TestCase):
    def setUp(self):
        self.assertIn('journal', inspect.signature(adapter.JournaledApplier).parameters,
                      'durable applier wrapper missing')
        self.events = []
        self.begin_failure = False
        self.finish_failure = False
        test = self
        class Journal:
            needs_recovery = False
            def begin(self, generation, **kwargs):
                test.events.append('begin')
                if test.begin_failure:
                    raise RuntimeError('uncertain begin')
            def recover(self, **kwargs): test.events.append('recover')
            def finish(self, **kwargs):
                test.events.append('finish')
                if test.finish_failure:
                    raise RuntimeError('uncertain finish')
        class Applier:
            current = None
            def apply(self, *args, **kwargs): test.events.append('apply')
            def remove(self, owned): test.events.append('remove')
        self.wrapper = adapter.JournaledApplier(
            Applier(), '/unused', 'a' * 32, journal=Journal())

    def test_prepare_happens_once_before_apply_and_finish_after_remove(self):
        self.wrapper.prepare()
        self.wrapper.apply(None)
        self.wrapper.remove(None)
        self.assertEqual(self.events, ['begin', 'apply', 'remove', 'finish'])

    def test_failed_prepare_remains_recoverable_without_claiming_live_state(self):
        self.begin_failure = True
        with self.assertRaisesRegex(RuntimeError, 'uncertain'):
            self.wrapper.prepare()
        self.wrapper.remove(None)
        self.assertEqual(self.events, ['begin', 'recover'])

    def test_failed_finish_retries_through_disk_recovery(self):
        self.wrapper.prepare()
        self.finish_failure = True
        with self.assertRaisesRegex(RuntimeError, 'uncertain finish'):
            self.wrapper.remove(None)
        self.wrapper.remove(None)
        self.assertEqual(self.events, ['begin', 'remove', 'finish', 'recover'])
        self.assertIsNone(self.wrapper.current)
        with self.assertRaises(RuntimeError):
            self.wrapper.apply(None)

    def test_uncertain_apply_intent_goes_directly_to_recovery(self):
        self.wrapper.prepare()
        self.wrapper.journal.needs_recovery = True
        self.wrapper.remove(None)
        self.assertEqual(self.events, ['begin', 'recover'])


@unittest.skipUnless(os.geteuid() == 0, 'private root-owned journal fixture')
class AdapterJournalBindingTests(unittest.TestCase):
    def test_actual_adapter_provisions_private_state_and_shares_one_journal(self):
        self.assertIn('backend', inspect.signature(adapter.NativeAdapter).parameters,
                      'trusted backend injection missing')
        with tempfile.TemporaryDirectory(prefix='adapter-journal-') as tmp:
            root = Path(tmp)
            legacy = SimpleNamespace(RadioLock=lambda **kwargs: nullcontext(),
                                     clear_session=lambda: None)
            system = SimpleNamespace(block_all=lambda: None)
            # Construction and empty recovery never start a native command.
            backend = adapter.NativeNetwork()
            with patch.object(backend, '_run', side_effect=AssertionError('native execution forbidden')):
                native = adapter.NativeAdapter(legacy, runtime=root/'run', state=root/'state',
                                               system=system, backend=backend)
                with self.assertRaisesRegex(RuntimeError, 'startup recovery'):
                    native.applier('a' * 32, lambda: None)
                self.assertFalse((root/'state').exists())
                native.prepare_recovery(check=lambda: None)
                self.assertEqual((root/'state').stat().st_mode & 0o777, 0o700)
                self.assertIs(backend.journal, native.journal)
                wrapper = native.applier('a' * 32, lambda: None)
                self.assertIs(wrapper.journal, native.journal)
                self.assertIs(wrapper.applier.backend, backend)
                self.assertIs(wrapper.applier.journal, native.journal)


if __name__ == '__main__':
    unittest.main()
