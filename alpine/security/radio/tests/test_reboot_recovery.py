"""Synthetic reboot classification and DNS-only writer barriers; no native calls."""
import copy
import unittest
from unittest.mock import Mock

from test_journal import active_record, record, writer
from test_reboot_journal import CONTEXT, retired
from test_recovery import Store, Marker
from privacyctl_runtime import journal, recovery


class RebootStore(Store):
    def rollover_boot(self, context):
        return self.write(journal._rollover_record(self.value, context))

    def remove(self):
        assert self.value['phase'] in ('clean', 'reboot-clean')
        self.events.append(('remove',)); self.value = None


class RebootRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.store = RebootStore(); self.store.value = active_record()
        self.marker = Marker(); self.marker.value = self.store.value['generation']
        self.context = copy.deepcopy(CONTEXT)
        self.events = []; self.fail_cleanup = False
        self.backend = Mock()
        self.backend.resolvconf = '/fixed/resolvconf'
        self.backend.drain_pending = lambda **kw: None
        self.backend.retire_dns = self.cleanup
        self.link = Mock(side_effect=AssertionError('old link must not be read'))
        self.coordinator = self.new()

    def new(self):
        return recovery.RecoveryJournal(self.store, self.backend, marker=self.marker,
            context_reader=lambda: copy.deepcopy(self.context), link_reader=self.link,
            capture=lambda pid, fd, operation: dict(writer(), pid=pid, operation=operation),
            drain=lambda value, **kw: self.events.append(('drain', value['pid'], kw['boot_id'])) or 'dead',
            clock=lambda: 10)

    def cleanup(self, permit, *, deadline, check):
        value = recovery.validate_dns_permit(permit, self.backend, deadline=deadline, check=check)
        self.events.append(('dns', value['resources']['provider']))
        if self.fail_cleanup: raise OSError('injected DNS failure')

    def test_reboot_discards_old_kernel_authority_and_retires_exact_dns(self):
        original = copy.deepcopy(self.store.value)
        self.assertEqual(self.coordinator.recover(deadline=100), 'clean')
        self.assertEqual(self.events, [('dns', original['resources']['provider'])])
        rollover = self.store.events[0][2]
        self.assertEqual(rollover['recovery_context'], CONTEXT)
        self.assertEqual(rollover['boot_id'], original['boot_id'])
        self.assertEqual(rollover['resources']['addresses'], [])
        self.assertIsNone(self.store.value); self.assertIsNone(self.marker.value)
        self.assertEqual(self.new().recover(deadline=100), 'clean')
        self.link.assert_not_called()

    def test_all_old_phases_without_dns_need_no_resolver_or_alias_action(self):
        for phase in ('alias-intent', 'active', 'alias-restore-intent', 'clean'):
            with self.subTest(phase=phase):
                self.store.value = record(phase); self.coordinator = self.new()
                self.events.clear()
                self.assertEqual(self.coordinator.recover(deadline=100), 'clean')
                self.assertEqual(self.events, [])
                self.link.assert_not_called()

    def test_same_boot_changed_namespace_or_marker_refuses_without_mutation(self):
        self.store.value = retired()
        self.context['observer_pidns']['ino'] += 1
        with self.assertRaises(recovery.RecoveryError): self.new().recover(deadline=100)
        self.assertEqual(self.events, []); self.assertEqual(self.store.events, [])
        self.context = copy.deepcopy(CONTEXT); self.marker.value = 'b' * 32
        with self.assertRaises(recovery.RecoveryError): self.new().recover(deadline=100)
        self.assertEqual(self.events, [])

    def test_reboot_cleanup_crash_retains_dns_and_drains_new_boot_writer(self):
        self.fail_cleanup = True
        with self.assertRaises(OSError): self.coordinator.recover(deadline=100)
        self.assertEqual(self.store.value['version'], 2)
        self.store.value['writers']['native'] = dict(writer(), pid=6789)
        self.fail_cleanup = False; self.events.clear()
        self.new().recover(deadline=100)
        self.assertEqual(self.events[0], ('drain', 6789, CONTEXT['boot_id']))
        self.assertEqual(self.events[1][0], 'dns')

    def test_second_reboot_never_drains_previous_recovery_boot_pid(self):
        self.store.value = retired(); self.store.value['writers']['native'] = writer()
        self.context['boot_id'] = '32345678-1234-1234-1234-123456789abc'
        self.new().recover(deadline=100)
        self.assertEqual([e[0] for e in self.events], ['dns'])

    def test_new_boot_writer_drain_failure_retains_slot_before_dns(self):
        self.store.value = retired(); self.store.value['writers']['native'] = writer()
        self.coordinator._drain = Mock(side_effect=RuntimeError('init teardown pending'))
        with self.assertRaisesRegex(RuntimeError, 'init teardown pending'):
            self.coordinator.recover(deadline=100)
        self.assertIsNotNone(self.store.value['writers']['native'])
        self.assertEqual(self.events, [])

    def test_dns_clear_and_clean_phase_uncertainty_retry_actual_durable_state(self):
        for phase in ('reboot-dns', 'reboot-clean'):
            for after in (False, True):
                with self.subTest(phase=phase, after=after):
                    self.store.value = retired(); self.coordinator = self.new()
                    original = self.store.write
                    def failed(value):
                        if value['phase'] == phase:
                            if after: original(value)
                            raise OSError('completion write fsync')
                        return original(value)
                    self.store.write = failed
                    with self.assertRaises(OSError): self.coordinator.recover(deadline=100)
                    self.store.write = original
                    self.coordinator.recover(deadline=100)
                    self.assertIsNone(self.store.value)

    def test_empty_journal_with_marker_and_unexpected_disappearance_refuse(self):
        self.store.value = None
        with self.assertRaises(recovery.RecoveryError): self.new().recover(deadline=100)
        self.store.value = retired(); self.fail_cleanup = True
        with self.assertRaises(OSError): self.coordinator.recover(deadline=100)
        self.store.value = None; self.marker.value = None
        with self.assertRaises(recovery.RecoveryError): self.coordinator.recover(deadline=100)

    def test_rollover_write_uncertainty_reloads_old_or_new_before_retry(self):
        for point in ('before', 'after'):
            with self.subTest(point=point):
                self.store.value = active_record(); self.coordinator = self.new()
                self.store.fail = point; self.events.clear()
                with self.assertRaises(OSError): self.coordinator.recover(deadline=100)
                self.assertEqual(self.events, [])
                self.assertIsNotNone(self.store.value['resources']['provider'])
                self.coordinator.recover(deadline=100)
                self.assertIsNone(self.store.value)

    def test_current_context_change_during_rollover_refuses_before_native(self):
        original = self.store.rollover_boot
        def changed(context):
            value = original(context)
            self.context['target_netns']['ino'] += 1
            return value
        self.store.rollover_boot = changed
        with self.assertRaises(recovery.RecoveryError): self.coordinator.recover(deadline=100)
        self.assertEqual(self.events, [])
        self.assertIsNotNone(self.store.value)

    def test_only_exact_dns_commands_authorized_during_retirement(self):
        def cleanup(permit, **options):
            owner = self.coordinator
            provider = owner.record['resources']['provider']
            for argv in ([self.backend.resolvconf, '-u'],
                         [self.backend.resolvconf, '--host-pid-lock-version'],
                         [self.backend.resolvconf, '-f', '-d', provider]):
                owner.check_command(self.backend, argv, content=None, **options)
            for argv in (['/sbin/ip', 'link', 'set', 'wlan0', 'up'],
                         [self.backend.resolvconf, '-I'],
                         [self.backend.resolvconf, '-a', provider],
                         [self.backend.resolvconf, '-f', '-d', 'privacyctl.' + 'b' * 32 + '.wlan0']):
                with self.assertRaises(recovery.RecoveryError):
                    owner.check_command(self.backend, argv, content=None, **options)
            with self.assertRaises(recovery.RecoveryError):
                owner.check_command(self.backend, [self.backend.resolvconf, '-u'], content='data', **options)
            with self.assertRaises(recovery.RecoveryError):
                owner.writer_started('dhcp', 5432, 42, 'dhcp-client')
            with self.assertRaises(recovery.RecoveryError): owner.check_link(**options)
            with self.assertRaises(recovery.RecoveryError):
                recovery.validate_permit(permit, generation=owner.record['generation'],
                    interface='wlan0', **options)
            owner.writer_started('native', 5432, 42, 'native-command')
            self.assertEqual(self.store.value['writers']['native']['pid'], 5432)
            owner.check_command(self.backend, [self.backend.resolvconf, '-u'], content=None, **options)
            owner.writer_finished('native')
        self.backend.retire_dns = cleanup
        self.coordinator.recover(deadline=100)
        with self.assertRaises(recovery.RecoveryError):
            self.coordinator.check_command(self.backend, [self.backend.resolvconf, '-u'],
                                           content=None, deadline=100)

    def test_clean_unlink_uncertainty_finishes_without_link_or_dns_repetition(self):
        for after in (False, True):
            with self.subTest(after=after):
                self.store.value = active_record(); self.coordinator = self.new()
                remove = self.store.remove
                def failed():
                    if after: remove()
                    raise OSError('unlink fsync')
                self.store.remove = failed
                with self.assertRaises(OSError): self.coordinator.recover(deadline=100)
                self.store.remove = remove; self.events.clear()
                self.coordinator.recover(deadline=100)
                self.assertEqual(self.events, [])
                self.assertIsNone(self.store.value)
