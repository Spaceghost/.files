"""Owned lease application tests; this fake backend cannot change host state."""
from ipaddress import IPv6Address, IPv6Interface
from pathlib import Path
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / 'root/usr/local/lib'))
from privacyctl_runtime.lease import Lease
from privacyctl_runtime.network import (APPLY_TIMEOUT, Address, IPv6Profile, LeaseApplier, NetworkError,
                                       NativeNetwork, Route, Snapshot)


GENERATION = 'a' * 32


class FakeNetwork:
    def __init__(self):
        self.addresses = set()
        self.routes = set()
        self.providers = {}
        self.output = ()
        self.managed = True
        self.ifindex = 7
        self.calls = []
        self.fail = None
        self.partial = False
        self.stale_output = False

    def operation(self, name, mutation=lambda: None):
        self.calls.append(name)
        if self.fail == name and not self.partial:
            raise RuntimeError('synthetic operation failure')
        mutation()
        if self.fail == name:
            raise RuntimeError('synthetic partial failure')

    def snapshot(self, interface, **options):
        self.operation('snapshot')
        return Snapshot(self.ifindex, frozenset(self.addresses), frozenset(self.routes))

    def drain_pending(self, **options):
        self.operation('drain_pending')

    def resolver(self, **options):
        self.operation('resolver')
        if not self.managed:
            raise RuntimeError('unmanaged resolver')
        return self.output

    def provider(self, key, **options):
        self.operation('provider')
        return self.providers.get(key)

    def all_provider_dns(self, **options):
        return {line.split()[1] for content in self.providers.values()
                for line in content.splitlines() if line.startswith('nameserver ')}

    def add_address(self, interface, value, lease_seconds, **options):
        self.operation('add_address', lambda: self.addresses.add(value))

    def renew_address(self, interface, value, lease_seconds, **options):
        self.operation('renew_address')

    def delete_address(self, interface, value, **options):
        self.operation('delete_address', lambda: self.addresses.discard(value))

    def add_route(self, interface, value, **options):
        self.operation('add_route', lambda: self.routes.add(value))

    def delete_route(self, interface, value, **options):
        self.operation('delete_route', lambda: self.routes.discard(value))

    def _merge(self):
        if not self.stale_output:
            self.output = tuple(sorted(self.all_provider_dns()))

    def set_provider(self, key, content, **options):
        def update():
            self.providers[key] = content
            self._merge()
        self.operation('set_provider', update)

    def delete_provider(self, key, **options):
        def update():
            self.providers.pop(key, None)
            self._merge()
        self.operation('delete_provider', update)


class VirtualClock:
    def __init__(self):
        self.now = 100.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def advance(self, duration):
        self.now = round(self.now + duration, 9)

    def sleep(self, duration):
        self.sleeps.append(duration)
        self.advance(duration)


class DADNetwork(FakeNetwork):
    """Timed native-operation outcomes without real sleeps or network writes."""
    def __init__(self, clock, outcome='complete'):
        super().__init__()
        self.clock, self.outcome = clock, outcome
        self.probed = False
        self.dad_started = None
        self.publications = []

    def resolver(self, **options):
        if not self.probed:
            self.clock.advance(2.2)
            self.probed = True
        return super().resolver(**options)

    def add_address(self, interface, value, lease_seconds, **options):
        super().add_address(interface, value, lease_seconds, **options)
        if value.family == 6:
            self.dad_started = self.clock.now

    def snapshot(self, interface, **options):
        snapshot = super().snapshot(interface, **options)
        tentative = failed = frozenset()
        if self.dad_started is not None:
            ipv6 = frozenset(value for value in snapshot.addresses if value.family == 6)
            elapsed = self.clock.now - self.dad_started
            if self.outcome == 'duplicate' and elapsed >= .2:
                failed = ipv6
            elif self.outcome != 'complete' or elapsed < 1:
                tentative = ipv6
        return Snapshot(snapshot.ifindex, snapshot.addresses, snapshot.routes,
                        tentative=tentative, failed=failed)

    def add_route(self, *args, **options):
        self.publications.append(('route', self.clock.now))
        return super().add_route(*args, **options)

    def set_provider(self, *args, **options):
        self.publications.append(('dns', self.clock.now))
        self.clock.advance(.2)
        return super().set_provider(*args, **options)


class NetworkTests(unittest.TestCase):
    def lease(self, **changes):
        fields = {'interface': 'test0', 'ip': '192.0.2.17', 'mask': '24',
                  'router': '192.0.2.1', 'dns': '192.0.2.53', 'lease': '60',
                  'serverid': '192.0.2.2'}
        fields.update(changes)
        return Lease.from_event(fields, expected_interface='test0')

    def setUp(self):
        self.backend = FakeNetwork()
        self.applier = LeaseApplier(GENERATION, 'test0', backend=self.backend)

    def test_apply_verifies_owned_state_and_removal_preserves_unrelated_resources(self):
        other_address = Address(4, '198.51.100.2/24', 99)
        other_route = Route(4, '198.51.100.0/24', None, 99, 900)
        self.backend.addresses.add(other_address)
        self.backend.routes.add(other_route)
        self.backend.providers['vpn0'] = 'nameserver 198.51.100.53\n'
        self.backend._merge()
        owned = self.applier.apply(self.lease())
        self.assertEqual(owned.provider, f'privacyctl.{GENERATION}.test0')
        self.assertTrue(owned.addresses)
        self.assertTrue(owned.routes)
        self.assertEqual(set(self.backend.output), {'192.0.2.53', '198.51.100.53'})
        self.assertIsNone(self.applier.remove(owned))
        self.assertEqual(self.backend.addresses, {other_address})
        self.assertEqual(self.backend.routes, {other_route})
        self.assertEqual(self.backend.providers, {'vpn0': 'nameserver 198.51.100.53\n'})
        self.assertEqual(self.backend.output, ('198.51.100.53',))

    def test_each_partial_application_failure_returns_cleanup_ownership(self):
        for operation in ('add_address', 'add_route', 'set_provider'):
            with self.subTest(operation=operation):
                backend = FakeNetwork()
                backend.fail, backend.partial = operation, True
                applier = LeaseApplier(GENERATION, 'test0', backend=backend)
                with self.assertRaises(NetworkError) as caught:
                    applier.apply(self.lease())
                owned = caught.exception.owned
                self.assertIsNotNone(owned)
                backend.fail = None
                self.assertIsNone(applier.remove(owned))
                self.assertFalse(backend.addresses | backend.routes)
                self.assertFalse(backend.providers)

    def test_unmanaged_resolver_is_refused_before_any_mutation(self):
        self.backend.managed = False
        with self.assertRaises(NetworkError):
            self.applier.apply(self.lease())
        self.assertFalse(self.backend.addresses | self.backend.routes)
        self.assertFalse(self.backend.providers)
        self.assertNotIn('add_address', self.backend.calls)

    def test_existing_unowned_exact_address_and_provider_are_not_adopted(self):
        self.backend.addresses.add(Address(4, '192.0.2.17/24', 99))
        with self.assertRaises(NetworkError):
            self.applier.apply(self.lease())
        self.assertNotIn('add_address', self.backend.calls)
        self.backend.addresses.clear()
        self.backend.providers[f'privacyctl.{GENERATION}.test0'] = 'nameserver 192.0.2.53\n'
        with self.assertRaises(NetworkError):
            self.applier.apply(self.lease())
        self.assertNotIn('add_address', self.backend.calls)

    def test_renewal_replaces_only_old_owned_state_and_stale_record_is_rejected(self):
        before = self.applier.apply(self.lease())
        after = self.applier.apply(self.lease(ip='192.0.2.18', dns='198.51.100.53'), before)
        with self.assertRaises(NetworkError):
            self.applier.remove(before)
        self.assertEqual({item.cidr for item in self.backend.addresses}, {'192.0.2.18/24'})
        self.assertEqual(self.backend.output, ('198.51.100.53',))
        self.assertIsNone(self.applier.remove(after))

    def test_same_lease_renewal_refreshes_address_without_delete_add(self):
        before = self.applier.apply(self.lease())
        self.backend.calls.clear()
        after = self.applier.apply(self.lease(lease='120'), before)
        self.assertIn('renew_address', self.backend.calls)
        self.assertNotIn('delete_address', self.backend.calls)
        self.assertNotIn('add_address', self.backend.calls)
        self.assertNotEqual(before.revision, after.revision)

    def test_home_hotspot_home_restores_explicit_ipv6_without_flushing_other_ipv6(self):
        link_local = Address(6, 'fe80::1234/64', 2)
        self.backend.addresses.add(link_local)
        home = IPv6Profile((IPv6Interface('2001:db8:1::17/64'),), (IPv6Address('fe80::1'),))
        first = self.applier.apply(self.lease(), ipv6=home)
        self.assertIn('2001:db8:1::17/64', {value.cidr for value in self.backend.addresses})
        hotspot = self.applier.apply(self.lease(ip='198.51.100.17', router='198.51.100.1',
                                              dns='198.51.100.53'), first, ipv6=IPv6Profile())
        self.assertEqual({value for value in self.backend.addresses if value.family == 6}, {link_local})
        last = self.applier.apply(self.lease(), hotspot, ipv6=home)
        self.assertIn('2001:db8:1::17/64', {value.cidr for value in self.backend.addresses})
        self.assertTrue(any(value.gateway == 'fe80::1' for value in self.backend.routes))
        self.applier.remove(last)
        self.assertEqual(self.backend.addresses, {link_local})

    def test_changed_provider_contents_or_link_identity_refuse_cleanup(self):
        owned = self.applier.apply(self.lease())
        self.backend.providers[owned.provider] = 'nameserver 203.0.113.53\n'
        with self.assertRaises(NetworkError):
            self.applier.remove(owned)
        self.assertIn(owned.provider, self.backend.providers)
        self.backend.providers[owned.provider] = owned.dns_contents[0]
        self.backend.ifindex += 1
        with self.assertRaises(NetworkError):
            self.applier.remove(owned)
        self.assertTrue(self.backend.addresses)

    def test_subscriber_success_with_stale_output_is_rejected_on_add_and_delete(self):
        self.backend.stale_output = True
        with self.assertRaises(NetworkError) as caught:
            self.applier.apply(self.lease())
        self.backend.stale_output = False
        self.applier.remove(caught.exception.owned)
        owned = self.applier.apply(self.lease())
        self.backend.stale_output = True
        with self.assertRaises(NetworkError):
            self.applier.remove(owned)

    def test_partial_cleanup_failure_can_be_retried(self):
        owned = self.applier.apply(self.lease())
        self.backend.fail = 'delete_route'
        with self.assertRaises(NetworkError) as caught:
            self.applier.remove(owned)
        self.backend.fail = None
        self.applier.remove(caught.exception.owned)
        self.assertFalse(self.backend.addresses | self.backend.routes)

    def test_cancellation_between_operations_exposes_partial_state_for_cleanup(self):
        def check():
            if 'add_address' in self.backend.calls:
                raise RuntimeError('cancelled')
        self.applier = LeaseApplier(GENERATION, 'test0', backend=self.backend, check=check)
        with self.assertRaises(NetworkError) as caught:
            self.applier.apply(self.lease())
        self.assertTrue(caught.exception.owned.addresses)
        self.assertNotIn('add_route', self.backend.calls)
        # The owner has blocked the radio; cleanup is independent of request cancellation.
        self.applier.remove(caught.exception.owned)
        self.assertFalse(self.backend.addresses)

    def test_generation_interface_and_private_ipv6_profile_are_validated(self):
        for generation in ('x', '../x', 'A' * 32, 'a' * 33):
            with self.subTest(generation=generation), self.assertRaises(ValueError):
                LeaseApplier(generation, 'test0', backend=self.backend)
        with self.assertRaises(ValueError):
            IPv6Profile((IPv6Interface('ff02::1/64'),), ())
        with self.assertRaises(ValueError):
            IPv6Profile((), (IPv6Address('2001:db8::1'),))
        with self.assertRaises(ValueError):
            IPv6Profile(['2001:db8::1/64'], ())
        with self.assertRaises(NetworkError):
            LeaseApplier(GENERATION, backend=self.backend).apply(self.lease())

    def test_native_numeric_address_protocol_and_host_route_json_are_normalized(self):
        # Actual iproute2 -j -N uses hexadecimal address protocols and omits /32.
        rows = [json.dumps([{'ifindex': 7, 'ifname': 'test0', 'addr_info': [
            {'family': 'inet', 'local': '192.0.2.17', 'prefixlen': 32, 'protocol': '0xc4'},
            {'family': 'inet6', 'local': 'fe80::1234', 'prefixlen': 64, 'protocol': '0x2'}]}]),
            json.dumps([{'dst': '192.0.2.17', 'protocol': '196', 'metric': 42700,
                         'prefsrc': '192.0.2.17'}]), '[]']
        backend = NativeNetwork()
        with patch.object(backend, '_run', side_effect=rows):
            snapshot = backend.snapshot('test0')
        self.assertIn(Address(4, '192.0.2.17/32'), snapshot.addresses)
        self.assertIn(Route(4, '192.0.2.17/32', None, source='192.0.2.17'), snapshot.routes)

    def test_native_mutations_use_argument_arrays_and_exact_resource_selectors(self):
        backend = NativeNetwork()
        address = Address(4, '192.0.2.17/24')
        route = Route(4, 'default', '192.0.2.1', metric=42701, source='192.0.2.17')
        with patch.object(backend, '_run') as run:
            backend.add_address('test0', address, 60)
            backend.delete_address('test0', address)
            backend.add_route('test0', route)
            backend.delete_route('test0', route)
        for call in run.call_args_list:
            argv = call.args[0]
            self.assertIsInstance(argv, list)
            self.assertEqual(argv[0], '/sbin/ip')
            self.assertEqual(argv[argv.index('proto') + 1], '196')
            self.assertEqual(argv[argv.index('dev') + 1], 'test0')
            self.assertNotIn('flush', argv)
        self.assertIn('noprefixroute', run.call_args_list[0].args[0])
        self.assertIn('60', run.call_args_list[0].args[0])

    def test_total_deadline_is_not_reset_for_each_backend_operation(self):
        class Time:
            value = 100.0
            def monotonic(self):
                self.value += APPLY_TIMEOUT / 20
                return self.value
        clock = Time()
        with patch('privacyctl_runtime.network.time.monotonic', clock.monotonic):
            with self.assertRaisesRegex(NetworkError, 'deadline') as caught:
                self.applier.apply(self.lease())
        if caught.exception.owned:
            self.applier.remove(caught.exception.owned)
        self.assertNotIn('set_provider', self.backend.calls)

    def dad_fixture(self, outcome='complete', check=lambda: None):
        clock = VirtualClock()
        backend = DADNetwork(clock, outcome)
        applier = LeaseApplier(GENERATION, 'test0', backend=backend, check=check)
        profile = IPv6Profile((IPv6Interface('2001:db8:1::17/64'),),
                              (IPv6Address('fe80::1'),))
        return clock, backend, applier, profile

    def test_delayed_dad_completes_before_routes_and_dns_within_apply_budget(self):
        clock, backend, applier, profile = self.dad_fixture()
        with patch('privacyctl_runtime.network.time.monotonic', clock.monotonic), \
             patch('privacyctl_runtime.network.time.sleep', clock.sleep):
            owned = applier.apply(self.lease(), ipv6=profile)
            # Literal scenario: 2.2s setup, 1s DAD, then 0.2s DNS publication.
            self.assertGreaterEqual(clock.now, 103.4)
            self.assertLess(clock.now, 103.45)
            self.assertTrue(clock.sleeps, 'tentative IPv6 must wait before publication')
            self.assertTrue(backend.publications)
            self.assertTrue(all(when >= 103.2 for _, when in backend.publications))
            self.assertIn(Address(6, '2001:db8:1::17/64'), owned.addresses)
            self.assertEqual(backend.output, ('192.0.2.53',))
            applier.remove(owned)
        self.assertFalse(backend.addresses | backend.routes)

    def test_duplicate_dad_fails_without_publishing_routes_or_dns(self):
        clock, backend, applier, profile = self.dad_fixture('duplicate')
        with patch('privacyctl_runtime.network.time.monotonic', clock.monotonic), \
             patch('privacyctl_runtime.network.time.sleep', clock.sleep):
            with self.assertRaisesRegex(NetworkError, 'duplicate-address') as caught:
                applier.apply(self.lease(), ipv6=profile)
            self.assertLess(clock.now, 102.45)
            self.assertIn(Address(6, '2001:db8:1::17/64'), caught.exception.owned.addresses)
            self.assertEqual(backend.publications, [])
            applier.remove(caught.exception.owned)
        self.assertFalse(backend.addresses | backend.routes)

    def test_stuck_dad_hits_shared_deadline_and_preserves_cleanup_ownership(self):
        clock, backend, applier, profile = self.dad_fixture('stuck')
        with patch('privacyctl_runtime.network.time.monotonic', clock.monotonic), \
             patch('privacyctl_runtime.network.time.sleep', clock.sleep):
            with self.assertRaisesRegex(NetworkError, 'deadline') as caught:
                applier.apply(self.lease(), ipv6=profile)
            self.assertLessEqual(clock.now, 100 + APPLY_TIMEOUT + .025)
            self.assertEqual(backend.publications, [])
            self.assertIn(Address(6, '2001:db8:1::17/64'), caught.exception.owned.addresses)
            applier.remove(caught.exception.owned)
        self.assertFalse(backend.addresses | backend.routes)

    def test_cancellation_during_dad_remains_responsive_and_cleanup_is_independent(self):
        clock, backend, applier, profile = self.dad_fixture('stuck')
        def cancel():
            if backend.dad_started is not None and clock.now >= backend.dad_started + .125:
                raise RuntimeError('cancelled while waiting for DAD')
        applier.check = cancel
        with patch('privacyctl_runtime.network.time.monotonic', clock.monotonic), \
             patch('privacyctl_runtime.network.time.sleep', clock.sleep):
            with self.assertRaisesRegex(NetworkError, 'cancelled while waiting') as caught:
                applier.apply(self.lease(), ipv6=profile)
            self.assertLessEqual(clock.now - backend.dad_started, .15)
            self.assertTrue(all(duration <= .025 for duration in clock.sleeps))
            self.assertEqual(backend.publications, [])
            self.assertIsNotNone(caught.exception.owned)
            applier.remove(caught.exception.owned)
        self.assertFalse(backend.addresses | backend.routes)

    def test_removal_refuses_primary_ipv4_with_unowned_secondary_in_same_prefix(self):
        owned = self.applier.apply(self.lease())
        secondary = Address(4, '192.0.2.18/24', 99)
        self.backend.addresses.add(secondary)
        with self.assertRaises(NetworkError):
            self.applier.remove(owned)
        self.assertIn(secondary, self.backend.addresses)
        self.assertTrue(any(value.cidr == '192.0.2.17/24' for value in self.backend.addresses))

    def test_replaced_provider_is_preserved_before_renewal_changes_any_resource(self):
        owned = self.applier.apply(self.lease())
        self.backend.providers[owned.provider] = 'nameserver 203.0.113.53\n'
        self.backend.calls.clear()
        with self.assertRaises(NetworkError):
            self.applier.apply(self.lease(ip='192.0.2.18'), owned)
        self.assertNotIn('delete_address', self.backend.calls)
        self.assertNotIn('set_provider', self.backend.calls)
        self.assertEqual(self.backend.providers[owned.provider], 'nameserver 203.0.113.53\n')

    def test_interruption_exposes_current_partial_record_without_swallowing_signal(self):
        def check():
            if 'add_address' in self.backend.calls:
                raise KeyboardInterrupt()
        self.applier.check = check
        with self.assertRaises(KeyboardInterrupt):
            self.applier.apply(self.lease())
        self.assertTrue(self.applier.current.addresses)
        self.applier.remove(self.applier.current)
        self.assertFalse(self.backend.addresses)

    def test_second_pipe_failure_closes_first_pipe_pair(self):
        backend = NativeNetwork()
        with patch('privacyctl_runtime.network.os.geteuid', return_value=0):
            with patch('privacyctl_runtime.network.os.pipe2', side_effect=[(123, 124), OSError('EMFILE')]):
                with patch('privacyctl_runtime.network.os.close') as close:
                    with self.assertRaises(OSError):
                        backend._run(['/bin/true'], deadline=time.monotonic() + 3, check=lambda: None)
        self.assertEqual({call.args[0] for call in close.call_args_list}, {123, 124})


@unittest.skipUnless(os.geteuid() == 0, 'native namespace and root-file checks require root')
class NativeNetworkTests(unittest.TestCase):
    """Real process tests run only synthetic sleepers; never ip/resolvconf on the host."""
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='privacyctl-network-test-')
        self.addCleanup(self.temporary.cleanup)
        self.work = Path(self.temporary.name)
        self.marker = self.work / 'namespace'
        self.backend = NativeNetwork()
        self.fixture = self.work / 'fixture.py'
        self.fixture.write_text('''import os,sys,time
from pathlib import Path
if os.fork()==0:
    os.setsid()
    Path(sys.argv[1]).write_text(os.readlink('/proc/self/ns/pid'))
    time.sleep(60)
else:
    time.sleep(60)
''')
        self.command = [sys.executable, '-I', '-S', str(self.fixture), str(self.marker)]

    def namespace_members(self, namespace):
        self.assertNotEqual(namespace, os.readlink('/proc/self/ns/pid'))
        members = []
        for path in Path('/proc').iterdir():
            if path.name.isdecimal():
                try:
                    if os.readlink(path / 'ns/pid') == namespace:
                        members.append(int(path.name))
                except (FileNotFoundError, PermissionError, ProcessLookupError):
                    pass
        return members

    def wait_marker(self):
        deadline = time.monotonic() + 1.5
        while not self.marker.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(self.marker.exists(), 'synthetic detached child never started')
        return self.marker.read_text()

    def assert_namespace_gone(self, namespace):
        deadline = time.monotonic() + 1
        while self.namespace_members(namespace) and time.monotonic() < deadline:
            time.sleep(0.01)
        remaining = self.namespace_members(namespace)
        # A failing lifetime test still cleans only this recorded private namespace.
        for pid in remaining:
            try:
                descriptor = os.pidfd_open(pid)
                if os.readlink(f'/proc/{pid}/ns/pid') == namespace:
                    signal.pidfd_send_signal(descriptor, signal.SIGKILL)
                os.close(descriptor)
            except ProcessLookupError:
                pass
        self.assertEqual(remaining, [], 'owned command descendants survived teardown')

    def test_native_timeout_removes_detached_descendants(self):
        started = time.monotonic()
        with self.assertRaisesRegex(RuntimeError, 'timed out'):
            self.backend._run(self.command, deadline=started + 3, check=lambda: None)
        self.assertLess(time.monotonic() - started, 1.4)
        self.assert_namespace_gone(self.wait_marker())

    def test_remove_without_owned_state_retries_retained_command_cleanup(self):
        applier = LeaseApplier(GENERATION, 'test0', backend=self.backend)
        lease = Lease.from_event({'interface': 'test0', 'ip': '192.0.2.17',
                                  'mask': '24', 'lease': '60', 'serverid': '192.0.2.2'},
                                 expected_interface='test0')
        stop = self.backend._stop_command
        def resolver(**options):
            return self.backend._run(self.command, **options)
        def fail_capture(*args, **options):
            self.wait_marker()
            raise RuntimeError('synthetic resolver timeout')
        try:
            with patch.object(self.backend, 'resolver', resolver), \
                 patch.object(self.backend, '_capture', fail_capture), \
                 patch.object(self.backend, '_stop_command',
                              side_effect=RuntimeError('synthetic teardown timeout')):
                with self.assertRaises(NetworkError) as caught:
                    applier.apply(lease)
                self.assertIsNone(caught.exception.owned)
                process, descriptors = self.backend._pending_cleanup
                self.assertIsNone(process.poll())
                with self.assertRaisesRegex(NetworkError, 'teardown timeout'):
                    applier.remove(None)
                self.assertEqual(self.backend._pending_cleanup, (process, descriptors))
                for descriptor in descriptors:
                    os.fstat(descriptor)
            self.assertIsNone(applier.remove(None))
            self.assertIsNone(self.backend._pending_cleanup)
            self.assertIsNotNone(process.returncode)
            for descriptor in descriptors:
                with self.assertRaises(OSError):
                    os.fstat(descriptor)
            self.assert_namespace_gone(self.wait_marker())
        finally:
            # A red test still kills/reaps only this recorded private namespace.
            if self.backend._pending_cleanup is not None:
                process, descriptors = self.backend._pending_cleanup
                stop(process, descriptors)
                for descriptor in descriptors:
                    if descriptor is not None:
                        os.close(descriptor)
                self.backend._pending_cleanup = None

    def test_native_stderr_capture_is_bounded_before_command_completion(self):
        command = [sys.executable, '-I', '-S', '-c', 'import os;os.write(2,b"x"*300000)']
        with self.assertRaisesRegex(RuntimeError, 'output.*large'):
            self.backend._run(command, deadline=time.monotonic() + 3, check=lambda: None)

    def test_normal_command_exit_removes_detached_descendants(self):
        self.fixture.write_text('''import os,sys,time
from pathlib import Path
if os.fork()==0:
    os.setsid()
    Path(sys.argv[1]).write_text(os.readlink('/proc/self/ns/pid'))
    time.sleep(60)
else:
    while not Path(sys.argv[1]).exists(): time.sleep(.005)
''')
        self.backend._run(self.command, deadline=time.monotonic() + 3, check=lambda: None)
        self.assert_namespace_gone(self.wait_marker())

    def test_native_pidfd_failure_kills_and_reaps_unreleased_direct_child(self):
        processes = []
        original = subprocess.Popen
        def capture(*args, **options):
            process = original(*args, **options)
            processes.append(process)
            return process
        with patch('privacyctl_runtime.network.subprocess.Popen', side_effect=capture):
            with patch('privacyctl_runtime.network.os.pidfd_open', side_effect=OSError('synthetic EMFILE')):
                with self.assertRaisesRegex(OSError, 'synthetic EMFILE'):
                    self.backend._run(self.command, deadline=time.monotonic() + 3, check=lambda: None)
        self.assertEqual(len(processes), 1)
        self.assertIsNotNone(processes[0].returncode)
        self.assertFalse(self.marker.exists())

    def test_native_baseexception_interrupt_removes_detached_descendants(self):
        def interrupt(process, *args, **options):
            self.wait_marker()
            raise KeyboardInterrupt()
        with patch.object(self.backend, '_capture', interrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.backend._run(self.command, deadline=time.monotonic() + 3, check=lambda: None)
        self.assert_namespace_gone(self.wait_marker())

    def test_native_owner_death_removes_detached_descendants(self):
        module = Path(__file__).parents[1] / 'root/usr/local/lib'
        code = ('import sys,time;sys.path.insert(0,sys.argv[1]);'
                'from privacyctl_runtime.network import NativeNetwork;'
                'NativeNetwork()._run(sys.argv[2:],deadline=time.monotonic()+3,check=lambda:None)')
        owner = subprocess.Popen([sys.executable, '-I', '-S', '-c', code, str(module), *self.command],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            namespace = self.wait_marker()
            owner.kill()
            owner.wait(timeout=1)
            self.assert_namespace_gone(namespace)
        finally:
            if owner.poll() is None:
                owner.kill()
                owner.wait(timeout=1)

    def test_native_bridge_carries_original_proc_view_and_captured_init_host_pid(self):
        code = ('import os,json,pathlib;'
                'fd=int(os.environ["OPENRESOLV_HOST_PROC_FD"]);'
                'provided=int(os.environ["OPENRESOLV_HOST_PID"]);'
                'actual=int(pathlib.Path(f"/proc/self/fd/{fd}/self/stat").read_text().split()[0]);'
                'print(json.dumps({"pid_matches":provided==actual,"namespace_init":os.getpid()==1,'
                '"distinct_pid":provided!=os.getpid(),"directory_fd":pathlib.Path(f"/proc/self/fd/{fd}").is_dir()}))')
        descriptors = {path.name for path in Path('/proc/self/fd').iterdir()}
        with patch.dict(os.environ, {'OPENRESOLV_HOST_PID': '1', 'OPENRESOLV_HOST_PROC_FD': '999999'}):
            output = self.backend._run([sys.executable, '-I', '-S', '-c', code],
                                       deadline=time.monotonic() + 3, check=lambda: None)
        self.assertEqual(json.loads(output), {'pid_matches': True, 'namespace_init': True,
                                             'distinct_pid': True, 'directory_fd': True})
        self.assertEqual({path.name for path in Path('/proc/self/fd').iterdir()}, descriptors)

    def test_native_resolver_requires_lock_bridge_capability_before_reading_policy(self):
        with patch.object(self.backend, '_run', return_value='0\n'):
            with patch.object(self.backend, '_read') as read:
                with self.assertRaisesRegex(RuntimeError, 'locking capability'):
                    self.backend.resolver()
                read.assert_not_called()

    def test_native_root_state_rejects_symlinks_permissions_and_unreviewed_resolver_policy(self):
        from privacyctl_runtime.network import _CACHE_SUBSCRIBERS
        resolver = self.work / 'resolv.conf'
        config = self.work / 'resolvconf.conf'
        providers = self.work / 'state/keys'
        providers.mkdir(parents=True)
        subscribers = self.work / 'subscribers'
        subscribers.mkdir()
        (subscribers / 'libc').write_text('# synthetic subscriber\n')
        backend = NativeNetwork(resolver=resolver, providers=providers,
                                resolver_config=config, subscribers=subscribers)
        capability = patch.object(backend, '_run', return_value='1\n')
        capability.start()
        self.addCleanup(capability.stop)
        resolver.write_text('# Generated by resolvconf\nnameserver 192.0.2.53\n')
        policy = {'resolv_conf': str(resolver), 'state_dir': str(providers.parent),
                  'libc_restart': ':', **{name: 'NO' for name in _CACHE_SUBSCRIBERS.values()}}
        config.write_text(''.join(f'{key}={value}\n' for key, value in policy.items()))
        self.assertEqual(backend.resolver(), ('192.0.2.53',))
        (subscribers / 'libc.d').mkdir()
        hook = subscribers / 'libc.d/unreviewed'
        hook.write_text('exit 0\n')
        with self.assertRaises(RuntimeError):
            backend.resolver()
        hook.unlink()
        config.write_text('resolv_conf=/etc/resolv.conf\n')
        with self.assertRaises(RuntimeError):
            backend.resolver()
        key = f'privacyctl.{GENERATION}.test0'
        provider = providers / key
        provider.symlink_to(resolver)
        with self.assertRaises(OSError):
            backend.provider(key)
        provider.unlink()
        provider.write_text('nameserver 192.0.2.53\n')
        provider.chmod(0o666)
        with self.assertRaises(RuntimeError):
            backend.provider(key)


if __name__ == '__main__':
    unittest.main()
