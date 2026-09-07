"""Journal integration with synthetic networks and mocked process gates only."""
from contextlib import ExitStack
from dataclasses import asdict
from types import ModuleType
from pathlib import Path
import os
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / 'root/usr/local/lib'))
from privacyctl_runtime import network
from privacyctl_runtime.lease import Lease
from privacyctl_runtime.network import Address, LeaseApplier, NativeNetwork, NetworkError, OwnedState, Route
from test_network import FakeNetwork

GENERATION = 'a' * 32


def lease(**changes):
    fields = {'interface': 'test0', 'ip': '192.0.2.17', 'mask': '24',
              'router': '192.0.2.1', 'dns': '192.0.2.53', 'lease': '60', 'serverid': '192.0.2.2'}
    fields.update(changes)
    return Lease.from_event(fields, expected_interface='test0')


class Journal:
    def __init__(self):
        self.events = []
        self.pending = False
        self.fail_start = self.fail_finish = False
        self.fail_record = None
        self.records = []
        self.observe_record = lambda candidate: None

    def writer_started(self, kind, pid, pidfd, operation):
        self.events.append(('started', kind, pid, pidfd, operation))
        self.pending = True
        if self.fail_start:
            raise RuntimeError('journal fsync failed')

    def writer_finished(self, kind):
        self.events.append(('finished', kind))
        if self.fail_finish:
            raise RuntimeError('journal completion fsync failed')
        self.pending = False

    def check_link(self, *, deadline, check):
        check()
        self.events.append(('link',))

    def record_owned(self, candidate):
        self.observe_record(candidate)
        if self.fail_record is not None and self.fail_record(candidate):
            raise RuntimeError('owned journal fsync failed')
        self.records.append(candidate)


class OwnedJournalTests(unittest.TestCase):
    def setUp(self):
        self.backend = FakeNetwork()
        self.journal = Journal()

    def applier(self):
        return LeaseApplier(GENERATION, 'test0', backend=self.backend, journal=self.journal)

    def test_journal_candidate_precedes_each_memory_revision_and_mutation(self):
        applier = self.applier()
        previous = []
        self.journal.observe_record = lambda candidate: previous.append(applier.current)
        owned = applier.apply(lease())
        self.assertIsNone(previous[0])
        self.assertEqual(previous[1:], self.journal.records[:-1])
        self.assertIs(self.journal.records[-1], owned)
        self.assertTrue(self.journal.records[1].addresses)
        applier.remove(owned)
        self.assertIsNone(self.journal.records[-1])
        self.assertIsNone(applier.current)

    def test_failed_initial_record_keeps_memory_empty_and_never_adds_resources(self):
        applier = self.applier()
        self.journal.fail_record = lambda candidate: True
        with self.assertRaises(NetworkError):
            applier.apply(lease())
        self.assertIsNone(applier.current)
        self.assertEqual(self.backend.addresses, set())
        self.assertEqual(self.backend.routes, set())
        self.assertEqual(self.backend.providers, {})

    def test_failed_address_intent_does_not_change_memory_or_mutate_backend(self):
        applier = self.applier()
        self.journal.fail_record = lambda candidate: bool(candidate.addresses)
        with self.assertRaises(NetworkError) as caught:
            applier.apply(lease())
        self.assertEqual(applier.current.addresses, ())
        self.assertIs(caught.exception.owned, applier.current)
        self.assertEqual(self.backend.addresses, set())

    def test_failed_narrowing_retains_full_previous_candidate(self):
        applier = self.applier()
        owned = applier.apply(lease())
        self.journal.fail_record = lambda candidate: candidate is not None and candidate.provider is None
        with self.assertRaises(NetworkError):
            applier.remove(owned)
        self.assertIs(applier.current, owned)
        self.assertTrue(applier.current.dns_contents)
        self.assertEqual(self.backend.providers, {})

    def test_backend_journal_is_used_when_applier_receives_existing_backend(self):
        self.backend.journal = self.journal
        applier = LeaseApplier(GENERATION, 'test0', backend=self.backend)
        applier.apply(lease())
        self.assertTrue(self.journal.records)


    def test_dns_mutation_failure_preserves_both_durable_renewal_candidates(self):
        applier = self.applier()
        previous = applier.apply(lease())
        self.backend.fail, self.backend.partial = 'set_provider', True
        with self.assertRaises(NetworkError):
            applier.apply(lease(dns='192.0.2.54'), previous)
        self.assertEqual(applier.current.dns_contents,
                         ('nameserver 192.0.2.53\n', 'nameserver 192.0.2.54\n'))
        self.assertIs(self.journal.records[-1], applier.current)
        self.assertEqual(self.backend.providers[applier.current.provider], 'nameserver 192.0.2.54\n')

    def test_explicit_applier_journal_reaches_existing_native_backend(self):
        backend = NativeNetwork()
        LeaseApplier(GENERATION, 'test0', backend=backend, journal=self.journal)
        self.assertIs(backend.journal, self.journal)

    def test_conflicting_backend_and_applier_journals_refuse_split_evidence(self):
        backend = NativeNetwork(journal=Journal())
        with self.assertRaises(ValueError):
            LeaseApplier(GENERATION, 'test0', backend=backend, journal=self.journal)


class NativeGateTests(unittest.TestCase):
    def setUp(self):
        self.journal = Journal()
        self.backend = NativeNetwork(journal=self.journal)
        self.process = Mock(pid=1000, returncode=0, stdin=None, stdout=None, stderr=None)
        self.dead = False
        self.mutations = []
        self.closed = []
        self.stop_fails = False
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(network.os, 'geteuid', return_value=0))
        self.stack.enter_context(patch.object(network.os, 'pipe2', side_effect=[(10, 11), (12, 13)]))
        self.stack.enter_context(patch.object(network.os, 'open', return_value=20))
        self.stack.enter_context(patch.object(network.os, 'close', side_effect=self.closed.append))
        self.stack.enter_context(patch.object(network.os, 'read', return_value=b'R'))
        self.stack.enter_context(patch.object(network.os, 'write', side_effect=self.write))
        self.stack.enter_context(patch.object(network.os, 'pidfd_open', side_effect=[30, 31]))
        self.stack.enter_context(patch.object(network.os, 'readlink', side_effect=lambda path: 'host' if path == '/proc/self/ns/pid' else 'private'))
        self.stack.enter_context(patch.object(Path, 'read_text', return_value='1001\n'))
        self.stack.enter_context(patch.object(network.subprocess, 'Popen', return_value=self.process))
        self.stack.enter_context(patch.object(network.select, 'select', side_effect=self.select))
        self.stack.enter_context(patch.object(self.backend, '_capture', side_effect=self.capture))
        self.stack.enter_context(patch.object(self.backend, '_stop_command', side_effect=self.stop))
        self.stack.enter_context(patch.object(network.signal, 'pidfd_send_signal', side_effect=AssertionError('actual signal forbidden')))
        self.stack.enter_context(patch.object(network.os, 'kill', side_effect=AssertionError('actual signal forbidden')))

    def select(self, reads, writes, exceptional, timeout):
        return (reads if reads == [10] or (reads == [31] and self.dead) else [], [], [])

    def write(self, fd, data):
        self.assertEqual((fd, data), (13, b'G1001\n'))
        self.journal.events.append(('gate',))
        self.assertTrue(self.journal.pending)
        return len(data)

    def capture(self, *args):
        self.mutations.append('command')
        self.journal.events.append(('command',))
        self.dead = True
        return b'ok\n'

    def stop(self, process, descriptors):
        self.assertIs(process, self.process)
        self.assertEqual(descriptors, (31, 30))
        if self.stop_fails:
            raise RuntimeError('teardown timed out')
        self.dead = True
        self.journal.events.append(('dead',))

    def run_command(self):
        return self.backend._run(['/fixed/native'], deadline=time.monotonic() + 3, check=lambda: None)

    def test_durable_writer_and_link_check_precede_gate_and_completion_follows_death(self):
        self.assertEqual(self.run_command(), 'ok\n')
        self.assertEqual(self.journal.events, [('link',), ('started', 'native', 1001, 31, 'native-command'),
                         ('link',), ('gate',), ('command',), ('finished', 'native'), ('link',)])
        self.assertFalse(self.journal.pending)
        self.assertIn(31, self.closed)

    def test_preflight_refusal_follows_pending_drain_and_precedes_any_helper_creation(self):
        events = []
        def drained(**options):
            events.append('drained')
        def refused(**options):
            self.assertEqual(events, ['drained'])
            raise RuntimeError('preflight cookie or context conflict')
        with patch.object(self.backend, 'drain_pending', side_effect=drained):
            with patch.object(self.journal, 'check_link', side_effect=refused):
                with self.assertRaisesRegex(RuntimeError, 'preflight cookie or context conflict'):
                    self.run_command()
        network.subprocess.Popen.assert_not_called()
        network.os.pipe2.assert_not_called()
        self.assertFalse(self.journal.pending)
        self.assertEqual(self.mutations, [])

    def test_failed_writer_fsync_never_opens_gate_or_runs_command(self):
        self.journal.fail_start = True
        with self.assertRaisesRegex(RuntimeError, 'journal fsync'):
            self.run_command()
        self.assertEqual(self.mutations, [])
        self.assertNotIn(('gate',), self.journal.events)
        self.assertEqual(self.journal.events[-2:], [('dead',), ('finished', 'native')])

    def test_failed_link_check_never_opens_gate(self):
        with patch.object(self.journal, 'check_link', side_effect=RuntimeError('cookie conflict')):
            with self.assertRaisesRegex(RuntimeError, 'cookie conflict'):
                self.run_command()
        self.assertEqual(self.mutations, [])
        self.assertNotIn(('gate',), self.journal.events)

    def test_uncertain_teardown_retains_slot_and_fds_until_later_drain(self):
        self.journal.fail_start = True
        self.stop_fails = True
        with self.assertRaisesRegex(RuntimeError, 'cleanup remains pending'):
            self.run_command()
        self.assertTrue(self.journal.pending)
        self.assertNotIn(31, self.closed)
        self.assertNotIn(30, self.closed)
        self.stop_fails = False
        self.backend.drain_pending(deadline=time.monotonic() + 3, check=lambda: None)
        self.assertFalse(self.journal.pending)
        self.assertIsNone(self.backend._pending_cleanup)
        self.assertEqual(self.closed.count(31), 1)

    def test_failed_completion_fsync_retains_slot_even_after_init_death(self):
        self.journal.fail_finish = True
        with self.assertRaisesRegex(RuntimeError, 'cleanup remains pending'):
            self.run_command()
        self.assertTrue(self.dead)
        self.assertTrue(self.journal.pending)
        self.assertNotIn(31, self.closed)
        self.journal.fail_finish = False
        self.backend.drain_pending(deadline=time.monotonic() + 3, check=lambda: None)
        self.assertFalse(self.journal.pending)
        self.assertIn(31, self.closed)


    def test_live_init_after_command_return_never_clears_writer_without_teardown(self):
        self.stop_fails = True
        with patch.object(self.backend, '_capture', return_value=b'ok\n'):
            with self.assertRaisesRegex(RuntimeError, 'cleanup remains pending'):
                self.run_command()
        self.assertTrue(self.journal.pending)
        self.assertNotIn(('finished', 'native'), self.journal.events)
        self.assertNotIn(31, self.closed)

    def test_post_command_cookie_conflict_retains_error_after_writer_completion(self):
        count = [0]
        def check_link(**options):
            count[0] += 1
            if count[0] == 3:
                raise RuntimeError('post-command cookie conflict')
        with patch.object(self.journal, 'check_link', side_effect=check_link):
            with self.assertRaisesRegex(RuntimeError, 'post-command cookie conflict'):
                self.run_command()
        self.assertFalse(self.journal.pending)
        self.assertTrue(self.dead)
        self.assertEqual(self.mutations, ['command'])

    def test_fsync_consuming_native_deadline_never_opens_gate(self):
        clock = [10.0]
        original_start = self.journal.writer_started
        def delayed_start(*args):
            original_start(*args)
            clock[0] = 11.0
        with patch.object(self.journal, 'writer_started', side_effect=delayed_start):
            with patch.object(network.time, 'monotonic', side_effect=lambda: clock[0]):
                with self.assertRaisesRegex(RuntimeError, 'deadline'):
                    self.run_command()
        self.assertEqual(self.mutations, [])
        self.assertNotIn(('gate',), self.journal.events)


class NativeMutationTests(unittest.TestCase):
    def test_alias_bytes_round_trip_in_fixed_argv_without_shell_interpolation(self):
        backend = NativeNetwork()
        raw = b'old \xff\n--alias'
        with patch.object(backend, '_run', return_value='') as run:
            backend.set_alias('test0', raw, deadline=100, check=lambda: None)
        argv = run.call_args.args[0]
        self.assertEqual(argv[:-1], [backend.ip, 'link', 'set', 'dev', 'test0', 'alias'])
        self.assertEqual(os.fsencode(argv[-1]), raw)
        self.assertEqual(run.call_args.kwargs['operation'], 'native-alias')

    def test_alias_rejects_nul_oversize_and_nonbytes_before_any_command(self):
        backend = NativeNetwork()
        with patch.object(backend, '_run', side_effect=AssertionError('invalid alias command')):
            for raw in (b'bad\0alias', b'x' * 256, 'alias', None):
                with self.subTest(raw=raw):
                    with self.assertRaises(ValueError):
                        backend.set_alias('test0', raw, deadline=100, check=lambda: None)


class ResolverRegenerationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.subscribers = self.root / 'subscribers'
        self.subscribers.mkdir()
        (self.subscribers / 'libc').write_text('synthetic libc subscriber')
        self.backend = NativeNetwork(resolver=self.root / 'resolv.conf', providers=self.root / 'state/keys',
                                     resolver_config=self.root / 'resolvconf.conf', subscribers=self.subscribers)
        policy = {'resolv_conf': str(self.backend.resolver_path),
                  'state_dir': str(self.backend.providers.parent), 'libc_restart': ':',
                  **{name: 'NO' for name in network._CACHE_SUBSCRIBERS.values()}}
        self.files = {self.backend.resolver_config: ''.join(key + '=' + value + '\n' for key, value in policy.items()),
                      self.backend.resolver_path: '# Generated by resolvconf\nnameserver broken\n'}
        self.commands = []
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(self.backend, '_read', side_effect=lambda path: self.files[path]))
        self.stack.enter_context(patch.object(self.backend, 'all_provider_dns', return_value={'198.51.100.53'}))
        self.stack.enter_context(patch.object(self.backend, '_run', side_effect=self.run_native))

    def run_native(self, argv, **options):
        self.commands.append(argv)
        if argv == [self.backend.resolvconf, '--host-pid-lock-version']:
            return '1\n'
        self.assertEqual(argv, [self.backend.resolvconf, '-u'])
        self.files[self.backend.resolver_path] = '# Generated by resolvconf\nnameserver 198.51.100.53\n'
        return ''

    def test_regeneration_repairs_payload_using_current_providers_under_lock_bridge(self):
        self.backend.regenerate_dns(deadline=time.monotonic() + 3, check=lambda: None)
        self.assertIn([self.backend.resolvconf, '-u'], self.commands)
        self.assertEqual(self.commands[0], [self.backend.resolvconf, '--host-pid-lock-version'])
        self.assertEqual(self.backend.resolver(deadline=time.monotonic() + 3, check=lambda: None), ('198.51.100.53',))

    def test_missing_or_truncated_managed_signature_never_authorizes_regeneration(self):
        for content in ('nameserver 192.0.2.53\n', '# Generated by res', ''):
            with self.subTest(content=content):
                self.commands.clear()
                self.files[self.backend.resolver_path] = content
                with self.assertRaises(RuntimeError):
                    self.backend.regenerate_dns(deadline=time.monotonic() + 3, check=lambda: None)
                self.assertNotIn([self.backend.resolvconf, '-u'], self.commands)

    def test_unreviewed_policy_or_subscriber_never_reaches_regeneration(self):
        self.files[self.backend.resolver_config] += 'unbound=YES\n'
        with self.assertRaises(RuntimeError):
            self.backend.regenerate_dns(deadline=time.monotonic() + 3, check=lambda: None)
        self.assertNotIn([self.backend.resolvconf, '-u'], self.commands)

    def test_unreviewed_libc_hook_never_reaches_regeneration(self):
        (self.subscribers / 'libc.d').mkdir()
        (self.subscribers / 'libc.d/unreviewed').write_text('synthetic hook')
        with self.assertRaises(RuntimeError):
            self.backend.regenerate_dns(deadline=time.monotonic() + 3, check=lambda: None)
        self.assertNotIn([self.backend.resolvconf, '-u'], self.commands)

    def test_regeneration_that_drops_unrelated_provider_is_refused(self):
        def wrong_output(argv, **options):
            result = self.run_native(argv, **options)
            if argv[-1] == '-u':
                self.files[self.backend.resolver_path] = '# Generated by resolvconf\n'
            return result
        with patch.object(self.backend, '_run', side_effect=wrong_output):
            with self.assertRaises(RuntimeError):
                self.backend.regenerate_dns(deadline=time.monotonic() + 3, check=lambda: None)


class RecoveredRemovalTests(unittest.TestCase):
    def setUp(self):
        self.backend = FakeNetwork()
        self.journal = Journal()
        self.applier = LeaseApplier(GENERATION, 'test0', backend=self.backend, journal=self.journal)
        self.address = Address(4, '192.0.2.17/24')
        self.route = Route(4, 'default', '192.0.2.1')
        self.provider = f'privacyctl.{GENERATION}.test0'
        self.record = {'generation': GENERATION, 'interface': 'test0', 'ifindex': 7, 'sequence': 9,
                       'resources': {'addresses': [asdict(self.address)], 'routes': [asdict(self.route)],
                                     'provider': self.provider, 'dns_contents': ['nameserver 192.0.2.53\n']}}
        self.permit = object()
        self.backend.addresses.add(self.address)
        self.backend.routes.add(self.route)
        self.backend.providers['vpn0'] = 'nameserver 198.51.100.53\n'
        self.backend.output = ('192.0.2.53', '198.51.100.53')
        self.backend.regenerate_dns = self.regenerate
        # The coordinator's independently tested proof validator is the trust
        # boundary. This double grants exactly one opaque synthetic permit.
        module = ModuleType('privacyctl_runtime.recovery')
        module.validate_permit = self.validate
        self.patch = patch.dict(sys.modules, {'privacyctl_runtime.recovery': module})
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def validate(self, permit, *, generation, interface, deadline, check):
        check()
        if permit is not self.permit or generation != GENERATION or interface != 'test0':
            raise RuntimeError('invalid recovery permit')
        return self.record

    def regenerate(self, **options):
        if not self.backend.managed:
            raise RuntimeError('unmanaged resolver')
        self.backend.output = tuple(sorted(self.backend.all_provider_dns()))
        self.backend.calls.append('regenerate_dns')

    def remove(self, permit=None):
        return self.applier.remove_recovered(self.permit if permit is None else permit,
                                            deadline=time.monotonic() + 3, check=lambda: None)

    def test_valid_permit_removes_exact_union_and_repairs_absent_provider_stale_output(self):
        other = Address(4, '198.51.100.2/24', 99)
        self.backend.addresses.add(other)
        self.assertIsNone(self.remove())
        self.assertEqual(self.backend.addresses, {other})
        self.assertEqual(self.backend.routes, set())
        self.assertEqual(self.backend.output, ('198.51.100.53',))
        self.assertIsNone(self.journal.records[-1])

    def test_arbitrary_owned_state_cannot_grant_recovery_authority(self):
        owned = OwnedState(GENERATION, 'test0', 7, 1, (self.address,), (self.route,))
        with self.assertRaises(NetworkError):
            self.remove(owned)
        self.assertEqual(self.backend.addresses, {self.address})
        self.assertEqual(self.journal.records, [])

    def test_matching_delete_key_with_changed_protocol_refuses(self):
        replacement = Address(4, self.address.cidr, 99)
        self.backend.addresses = {replacement}
        with self.assertRaises(NetworkError):
            self.remove()
        self.assertEqual(self.backend.addresses, {replacement})
        self.assertEqual(self.backend.routes, {self.route})

    def test_primary_address_with_unrelated_secondary_is_preserved(self):
        other = Address(4, '192.0.2.18/24', 99)
        self.backend.addresses.add(other)
        with self.assertRaises(NetworkError):
            self.remove()
        self.assertEqual(self.backend.addresses, {self.address, other})

    def test_unexplained_reserved_protocol_state_is_conflict_not_extra_deletion_authority(self):
        other = Address(4, '203.0.113.4/24')
        self.backend.addresses.add(other)
        with self.assertRaises(NetworkError):
            self.remove()
        self.assertIn(other, self.backend.addresses)
        self.assertIsNotNone(self.applier.current)

    def test_recovery_cannot_replace_an_existing_live_capability(self):
        self.applier._current = OwnedState(GENERATION, 'test0', 7, 2)
        with self.assertRaises(NetworkError):
            self.remove()
        self.assertEqual(self.backend.addresses, {self.address})
        self.assertEqual(self.journal.records, [])


if __name__ == '__main__':
    unittest.main()
