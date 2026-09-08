"""DNS retirement over temporary root files and fully mocked native gates."""
import copy
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from test_reboot_recovery import RebootStore, Marker
from test_reboot_journal import CONTEXT
from test_journal import active_record, writer
import test_network_journal as gate_fixtures
from privacyctl_runtime import network, recovery


class DNSCommandGateTests(unittest.TestCase):
    setUp = gate_fixtures.NativeGateTests.setUp
    select = gate_fixtures.NativeGateTests.select
    write = gate_fixtures.NativeGateTests.write
    capture = gate_fixtures.NativeGateTests.capture
    stop = gate_fixtures.NativeGateTests.stop

    def test_command_authority_is_checked_before_spawn(self):
        self.journal.check_command = Mock(side_effect=RuntimeError('denied DNS argv'))
        with self.assertRaisesRegex(RuntimeError, 'denied DNS argv'):
            self.backend._run(['/fixed/native'], deadline=time.monotonic() + 3, check=lambda: None)
        network.subprocess.Popen.assert_not_called()
        self.assertEqual(self.mutations, [])

    def test_command_authority_rechecked_after_registration_before_gate(self):
        calls = []
        def authorize(backend, argv, *, content, **options):
            self.assertIs(backend, self.backend)
            calls.append((tuple(argv), content))
            if len(calls) == 2:
                self.assertTrue(self.journal.pending)
                raise RuntimeError('authority changed after registration')
        self.journal.check_command = authorize
        with self.assertRaisesRegex(RuntimeError, 'authority changed after registration'):
            self.backend._run(['/fixed/native'], deadline=time.monotonic() + 3, check=lambda: None)
        self.assertEqual(calls, [(('/fixed/native',), None)] * 2)
        self.assertNotIn(('gate',), self.journal.events)
        self.assertEqual(self.mutations, [])
        self.assertFalse(self.journal.pending)


@unittest.skipUnless(os.geteuid() == 0, 'root-owned temporary resolver files required')
class DNSRetirementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.root.chmod(0o700)
        self.subscribers = self.root / 'subscribers'; self.subscribers.mkdir()
        (self.subscribers / 'libc').write_text('fixture')
        self.backend = network.NativeNetwork(resolver=self.root / 'resolv.conf',
            providers=self.root / 'state/keys', resolver_config=self.root / 'resolvconf.conf',
            subscribers=self.subscribers)
        policy = {'resolv_conf': str(self.backend.resolver_path),
                  'state_dir': str(self.backend.providers.parent), 'libc_restart': ':',
                  **{name: 'NO' for name in network._CACHE_SUBSCRIBERS.values()}}
        self.backend.resolver_config.write_text(''.join(k + '=' + v + '\n' for k, v in policy.items()))
        self.backend.resolver_path.write_text(network.SIGNATURE + '\nnameserver 192.0.2.53\n')
        self.store = RebootStore(); self.store.value = active_record()
        self.provider = self.store.value['resources']['provider']
        self.owned_dns = self.store.value['resources']['dns_contents'][0]
        self.events = []; self.fail = None
        self.backend._run = self.command
        self.context = copy.deepcopy(CONTEXT)
        self.new()

    def new(self):
        self.coordinator = recovery.RecoveryJournal(self.store, self.backend,
            context_reader=lambda: copy.deepcopy(self.context),
            link_reader=Mock(side_effect=AssertionError('no link query')),
            capture=lambda pid, fd, operation: dict(writer(), pid=pid, operation=operation),
            drain=Mock(side_effect=AssertionError('no old writer drain')))
        return self.coordinator

    def command(self, argv, *, deadline, check, content=None, operation='native-command'):
        # Exercise real coordinator durable gate rules; only the native process
        # boundary is substituted with changes to these disposable files.
        owner = self.backend.journal
        owner.check_command(self.backend, argv, content=content, deadline=deadline, check=check)
        owner.writer_started('native', 5432, 42, operation)
        owner.check_command(self.backend, argv, content=content, deadline=deadline, check=check)
        self.events.append(tuple(argv))
        try:
            if argv[-1] == '--host-pid-lock-version': return '1\n'
            if argv[1:] == ['-u']:
                servers = self.backend.all_provider_dns()
                self.backend.resolver_path.write_text(network.SIGNATURE + '\n' + ''.join(
                    'nameserver ' + value + '\n' for value in sorted(servers)))
            elif argv[1:] == ['-f', '-d', self.provider]:
                (self.backend.providers / self.provider).unlink(missing_ok=True)
            else: raise AssertionError('unexpected native argv')
            if self.fail == argv[1:]:
                self.fail = None; raise OSError('injected postmutation native failure')
            return ''
        finally:
            owner.writer_finished('native')

    def run_recovery(self):
        return self.coordinator.recover(deadline=time.monotonic() + 10)

    def populate(self):
        self.backend.providers.mkdir(parents=True)
        (self.backend.providers / self.provider).write_text(self.owned_dns)
        (self.backend.providers / 'vpn0').write_text('nameserver 198.51.100.53\nnameserver 2001:db8::53\n')

    def test_exact_provider_deleted_and_unrelated_shared_dns_preserved(self):
        self.populate()
        self.assertEqual(self.run_recovery(), 'clean')
        self.assertEqual(set(p.name for p in self.backend.providers.iterdir()), {'vpn0'})
        self.assertEqual(set(network._servers(self.backend.resolver_path.read_text())),
                         {'198.51.100.53', '2001:db8::53'})
        self.assertIsNone(self.store.value)
        self.assertEqual([e for e in self.events if '-d' in e],
                         [(self.backend.resolvconf, '-f', '-d', self.provider)])

    def test_missing_transient_provider_tree_repairs_persistent_managed_output(self):
        self.assertFalse(self.backend.providers.exists())
        self.run_recovery()
        self.assertTrue(self.backend.providers.is_dir())
        self.assertEqual(network._servers(self.backend.resolver_path.read_text()), ())
        self.assertFalse(any('-d' in e for e in self.events))

    def test_foreign_provider_refuses_before_any_native_or_generated_output_change(self):
        self.populate(); (self.backend.providers / self.provider).write_text('nameserver 203.0.113.53\n')
        before = self.backend.resolver_path.read_bytes()
        with self.assertRaises(RuntimeError): self.run_recovery()
        self.assertEqual(self.events, [])
        self.assertEqual(self.backend.resolver_path.read_bytes(), before)
        self.assertIsNotNone(self.store.value['resources']['provider'])

    def test_unmanaged_output_and_unknown_policy_refuse_without_creating_state(self):
        for malformed in ('signature', 'policy'):
            with self.subTest(malformed=malformed):
                if malformed == 'signature': self.backend.resolver_path.write_text('nameserver 192.0.2.53\n')
                else:
                    self.backend.resolver_path.write_text(network.SIGNATURE + '\n')
                    with self.backend.resolver_config.open('a') as stream: stream.write('unbound=YES\n')
                with self.assertRaises(RuntimeError): self.run_recovery()
                self.assertFalse(self.backend.providers.exists())
                self.assertEqual(self.events, [])

    def test_legacy_layout_and_state_symlink_refuse_without_touching_target(self):
        external = self.root / 'external'; external.mkdir()
        self.backend.providers.parent.symlink_to(external)
        with self.assertRaises(RuntimeError): self.run_recovery()
        self.assertEqual(list(external.iterdir()), [])
        self.backend.providers.parent.unlink(); self.backend.providers.parent.mkdir()
        (self.backend.providers.parent / 'interfaces').mkdir()
        with self.assertRaises(RuntimeError): self.run_recovery()
        self.assertEqual(self.events, [])

    def test_postdelete_failure_retains_intent_and_retry_repairs_stale_output(self):
        self.populate(); self.fail = ['-f', '-d', self.provider]
        with self.assertRaises(OSError): self.run_recovery()
        self.assertIsNotNone(self.store.value['resources']['provider'])
        self.assertFalse((self.backend.providers / self.provider).exists())
        self.new(); self.run_recovery()
        self.assertEqual(set(network._servers(self.backend.resolver_path.read_text())),
                         {'198.51.100.53', '2001:db8::53'})
        self.assertIsNone(self.store.value)
