"""Coordinator crash phases over in-memory kernel stand-ins; no native actions."""
import copy
import importlib
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / 'root/usr/local/lib'))
from privacyctl_runtime.journal import validate_record
from privacyctl_runtime.network import Address, OwnedState
try:
    recovery = importlib.import_module('privacyctl_runtime.recovery')
    link = importlib.import_module('privacyctl_runtime.link')
except ModuleNotFoundError:
    recovery = link = None

CONTEXT = {'boot_id': '01234567-89ab-cdef-0123-456789abcdef',
           'observer_pidns': {'dev': 4, 'ino': 100}, 'target_netns': {'dev': 4, 'ino': 101}}
GENERATION = 'a' * 32


class Store:
    def __init__(self): self.value = None; self.fail = None; self.events = []
    def read(self): return copy.deepcopy(self.value)
    def write(self, value):
        value = validate_record(value)
        if self.fail == 'before': self.fail = None; raise OSError('before write')
        self.value = value; self.events.append(('write', value['phase'], copy.deepcopy(value)))
        if self.fail == 'after': self.fail = None; raise OSError('after rename')
        return copy.deepcopy(value)
    def remove(self):
        assert self.value['phase'] == 'clean'
        self.events.append(('remove',)); self.value = None
    def confirm_absent(self):
        assert self.value is None
        self.events.append(('sync-absent',))


class Marker:
    def __init__(self): self.value = None; self.fail_clear = False
    def read(self): return self.value
    def write(self, value): self.value = value
    def clear(self, expected):
        assert self.value == expected
        if self.fail_clear: raise OSError('marker clear failed')
        self.value = None


class Crash(BaseException): pass


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(recovery, 'recovery coordinator not implemented')
        self.store, self.marker = Store(), Marker()
        self.identity = link.LinkIdentity(7, 'wlan0', b'previous\xff alias')
        self.original = self.identity.alias
        self.context = copy.deepcopy(CONTEXT)
        self.events = []; self.crash = None
        self.backend = type('Backend', (), {})()
        self.backend.set_alias = self.set_alias
        self.coordinator = self.new()

    def new(self):
        result = recovery.RecoveryJournal(self.store, self.backend, marker=self.marker,
            context_reader=lambda: copy.deepcopy(self.context),
            link_reader=lambda interface, **kw: self.identity,
            capture=lambda pid, fd, operation: {'pid': pid, 'start_time': pid + 100,
                'pidns': {'dev': 4, 'ino': pid + 1000}, 'nspid': 1, 'operation': operation},
            drain=self.drain, cleanup=self.cleanup, clock=lambda: 10)
        return result

    def drain(self, record, **kwargs):
        self.events.append(('drain', record['pid']))
        if self.crash == 'drain': raise RuntimeError('drain incomplete')
        return 'dead'

    def set_alias(self, interface, alias, **kwargs):
        owner = self.backend.journal
        owner.check_link(**kwargs)
        owner.writer_started('native', 321, 30, 'set-alias')
        if self.crash == 'before-alias': raise Crash()
        self.identity = link.LinkIdentity(7, interface, alias)
        self.events.append(('alias', alias))
        if self.crash == 'after-alias': raise Crash()
        owner.writer_finished('native')
        owner.check_link(**kwargs)

    def cleanup(self, permit, *, deadline, check):
        value = recovery.validate_permit(permit, generation=GENERATION, interface='wlan0',
                                         deadline=deadline, check=check)
        self.assertFalse(any(value['writers'].values()))
        self.events.append(('cleanup', value['resources']))
        if self.crash == 'cleanup': raise Crash()
        self.backend.journal.record_owned(None)

    def begin(self): self.coordinator.begin(GENERATION, deadline=100)

    def owned(self):
        return OwnedState(GENERATION, 'wlan0', 7, 1, (Address(4, '192.0.2.10/24'),))

    def test_begin_orders_durable_intent_marker_alias_and_active(self):
        self.begin()
        self.assertEqual(self.store.events[0][1], 'alias-intent')
        self.assertEqual(self.marker.value, GENERATION)
        self.assertEqual(self.identity.alias, b'privacyctl:' + GENERATION.encode())
        self.assertEqual(self.store.value['phase'], 'active')

    def test_begin_refuses_existing_evidence_cookie_or_marker(self):
        self.marker.value = 'b' * 32
        with self.assertRaises(recovery.RecoveryError): self.begin()
        self.marker.value = None
        self.identity = link.LinkIdentity(7, 'wlan0', b'privacyctl:' + b'b' * 32)
        with self.assertRaises(recovery.RecoveryError): self.begin()
        self.assertEqual(self.events, [])

    def test_initial_journal_failure_prevents_alias_mutation(self):
        for point in ('before', 'after'):
            self.store.value = None; self.store.fail = point
            with self.assertRaises(OSError): self.begin()
            self.assertEqual(self.identity.alias, self.original)
            self.assertEqual(self.events, [])
            self.assertEqual(self.new().recover(deadline=100), 'clean')

    def test_empty_recovery_refuses_unexplained_legacy_marker(self):
        self.assertEqual(self.coordinator.recover(deadline=100), 'clean')
        self.marker.value = GENERATION
        with self.assertRaises(recovery.RecoveryError): self.coordinator.recover(deadline=100)

    def test_record_owned_validates_identity_and_preserves_candidates(self):
        self.begin(); self.coordinator.record_owned(self.owned())
        self.assertEqual(self.store.value['resources']['addresses'][0]['cidr'], '192.0.2.10/24')
        bad = OwnedState('b' * 32, 'wlan0', 7, 1)
        with self.assertRaises(recovery.RecoveryError): self.coordinator.record_owned(bad)
        with self.assertRaises(recovery.RecoveryError): self.coordinator.finish(deadline=100)

    def test_recovery_drains_both_slots_before_any_resource_cleanup(self):
        self.begin(); self.coordinator.record_owned(self.owned())
        self.coordinator.writer_started('dhcp', 322, 31, 'dhcp-start')
        self.coordinator.writer_started('native', 323, 32, 'address-add')
        self.events.clear(); self.assertEqual(self.new().recover(deadline=100), 'clean')
        self.assertEqual(self.events[:2], [('drain', 323), ('drain', 322)])
        self.assertEqual(self.events[2][0], 'cleanup')
        self.assertIsNone(self.store.value); self.assertIsNone(self.marker.value)
        self.assertEqual(self.identity.alias, self.original)

    def test_failed_writer_drain_retains_evidence_and_never_cleans(self):
        self.begin(); self.coordinator.record_owned(self.owned())
        self.coordinator.writer_started('native', 323, 32, 'address-add')
        self.events.clear(); self.crash = 'drain'
        with self.assertRaises(RuntimeError): self.new().recover(deadline=100)
        self.assertEqual(self.events, [('drain', 323)])
        self.assertIsNotNone(self.store.value['writers']['native'])

    def test_context_or_link_replacement_prevents_signals_and_cleanup(self):
        self.begin(); self.coordinator.record_owned(self.owned())
        self.coordinator.writer_started('native', 323, 32, 'address-add')
        self.events.clear()
        self.context['boot_id'] = '11234567-89ab-cdef-0123-456789abcdef'
        with self.assertRaises(recovery.RecoveryError): self.new().recover(deadline=100)
        self.assertEqual(self.events, [])
        self.context = copy.deepcopy(CONTEXT)
        self.identity = link.LinkIdentity(7, 'wlan0', b'replacement')
        with self.assertRaises(recovery.RecoveryError): self.new().recover(deadline=100)
        self.assertFalse(any(e[0] in ('cleanup', 'alias') for e in self.events))

    def test_alias_intent_crashes_recover_before_and_after_mutation(self):
        for point in ('before-alias', 'after-alias'):
            self.crash = point
            with self.assertRaises(Crash): self.begin()
            self.crash = None
            self.assertEqual(self.new().recover(deadline=100), 'clean')
            self.assertEqual(self.identity.alias, self.original)
            self.assertIsNone(self.store.value)
            self.coordinator = self.new()

    def test_restore_crash_accepts_prior_alias_only_in_final_phase(self):
        self.begin(); self.crash = 'after-alias'
        with self.assertRaises(Crash): self.coordinator.finish(deadline=100)
        self.assertEqual(self.store.value['phase'], 'alias-restore-intent')
        self.assertEqual(self.identity.alias, self.original)
        self.crash = None; self.assertEqual(self.new().recover(deadline=100), 'clean')
        self.assertEqual(self.new().recover(deadline=100), 'clean')

    def test_clean_phase_survives_marker_failure_and_retries(self):
        self.begin(); self.marker.fail_clear = True
        with self.assertRaises(OSError): self.coordinator.finish(deadline=100)
        self.assertEqual(self.store.value['phase'], 'clean')
        self.marker.fail_clear = False
        self.assertEqual(self.new().recover(deadline=100), 'clean')

    def test_failed_registration_before_and_after_write_can_finish_exact_slot(self):
        self.begin()
        for point in ('before', 'after'):
            self.store.fail = point
            with self.assertRaises(OSError):
                self.coordinator.writer_started('native', 323, 32, 'address-add')
            self.coordinator.writer_finished('native')
            self.assertIsNone(self.store.value['writers']['native'])
            self.coordinator.writer_finished('native')

    def test_registration_failure_never_clears_a_foreign_slot(self):
        self.begin(); self.store.fail = 'after'
        with self.assertRaises(OSError): self.coordinator.writer_started('native', 323, 32, 'address-add')
        self.store.value['writers']['native']['pid'] = 999
        with self.assertRaises(recovery.RecoveryError): self.coordinator.writer_finished('native')
        self.assertEqual(self.store.value['writers']['native']['pid'], 999)

    def test_finish_refuses_pending_dhcp_and_foreign_marker(self):
        self.begin(); self.coordinator.writer_started('dhcp', 322, 31, 'dhcp-start')
        with self.assertRaises(recovery.RecoveryError): self.coordinator.finish(deadline=100)
        self.coordinator.writer_finished('dhcp'); self.marker.value = 'b' * 32
        with self.assertRaises(recovery.RecoveryError): self.coordinator.finish(deadline=100)

    def test_permit_cannot_be_forged_or_reused_after_recovery(self):
        with self.assertRaises(recovery.RecoveryError):
            recovery.validate_permit({}, generation=GENERATION, interface='wlan0', deadline=100)
        self.begin(); self.coordinator.record_owned(self.owned()); saved = []
        original = self.cleanup
        def cleanup(permit, **kwargs): saved.append(permit); original(permit, **kwargs)
        owner = self.new(); owner._cleanup = cleanup
        owner.recover(deadline=100)
        with self.assertRaises(recovery.RecoveryError):
            recovery.validate_permit(saved[0], generation=GENERATION, interface='wlan0', deadline=100)

    def test_deadline_and_cancellation_prevent_alias_operations(self):
        with self.assertRaises(recovery.RecoveryError): self.coordinator.begin(GENERATION, deadline=9)
        def cancel(): raise RuntimeError('cancelled')
        with self.assertRaisesRegex(RuntimeError, 'cancelled'):
            self.coordinator.begin(GENERATION, deadline=100, check=cancel)
        self.assertIsNone(self.store.value); self.assertEqual(self.events, [])

    def test_same_backend_pending_handles_finish_before_new_alias_writer(self):
        self.begin(); self.coordinator.writer_started('native', 323, 32, 'address-add')
        self.events.clear()
        def pending(**kwargs):
            self.events.append(('pending-dead',))
            self.coordinator.writer_finished('native')
        self.backend.drain_pending = pending
        self.coordinator.recover(deadline=100)
        self.assertEqual(self.events[0], ('pending-dead',))
        self.assertFalse(any(e[0] == 'drain' for e in self.events))

    def test_failed_completion_write_reloads_already_cleared_slot(self):
        self.begin(); self.coordinator.writer_started('native', 323, 32, 'address-add')
        self.store.fail = 'after'
        with self.assertRaises(OSError): self.coordinator.writer_finished('native')
        self.coordinator.writer_finished('native')
        self.assertIsNone(self.store.value['writers']['native'])

    def test_unknown_drain_outcome_is_not_a_death_proof(self):
        self.begin(); self.coordinator.writer_started('native', 323, 32, 'address-add')
        owner = self.new(); owner._drain = lambda *args, **kwargs: None
        with self.assertRaises(recovery.RecoveryError): owner.recover(deadline=100)
        self.assertIsNotNone(self.store.value['writers']['native'])

    def test_link_change_after_alias_mutation_retains_record(self):
        original = self.backend.set_alias
        def replacement(*args, **kwargs):
            original(*args, **kwargs)
            self.identity = link.LinkIdentity(8, 'wlan0', b'replacement')
        self.backend.set_alias = replacement
        with self.assertRaises(recovery.RecoveryError): self.begin()
        self.assertEqual(self.store.value['phase'], 'alias-intent')

    def test_real_applier_accepts_only_coordinator_permit_and_preserves_unrelated(self):
        from test_network import FakeNetwork
        from privacyctl_runtime import network
        self.backend = FakeNetwork(); self.backend.set_alias = self.set_alias
        self.backend.regenerate_dns = lambda **kw: self.backend._merge()
        self.coordinator = self.new(); self.begin()
        provider = 'privacyctl.' + GENERATION + '.wlan0'
        contents = 'nameserver 192.0.2.53\n'
        owned = OwnedState(GENERATION, 'wlan0', 7, 1, (Address(4, '192.0.2.10/24'),),
                           (), provider, (contents,))
        self.coordinator.record_owned(owned)
        unrelated = Address(4, '198.51.100.9/24', 0)
        self.backend.addresses.update((*owned.addresses, unrelated))
        self.backend.providers.update({provider: contents, 'other': 'nameserver 198.51.100.53\n'})
        self.backend._merge()
        owner = self.new(); owner._cleanup = None
        with patch.object(network.time, 'monotonic', return_value=10):
            self.assertEqual(owner.recover(deadline=100), 'clean')
        self.assertEqual(self.backend.addresses, {unrelated})
        self.assertEqual(self.backend.providers, {'other': 'nameserver 198.51.100.53\n'})
        self.assertEqual(self.backend.output, ('198.51.100.53',))
        self.assertIsNone(self.store.value)

    def test_finish_retries_uncertain_restore_and_clean_phase_writes(self):
        for phase in ('alias-restore-intent', 'clean'):
            for point in ('before', 'after'):
                self.coordinator = self.new(); self.begin()
                original = self.store.write
                armed = [True]
                def failed(value):
                    if value['phase'] == phase and armed[0]:
                        armed[0] = False; self.store.fail = point
                    return original(value)
                self.store.write = failed
                with self.assertRaises(OSError): self.coordinator.finish(deadline=100)
                self.store.write = original
                self.assertEqual(self.coordinator.finish(deadline=100), 'clean')
                self.assertIsNone(self.store.value); self.assertIsNone(self.marker.value)

    def test_same_object_retries_remove_failure_before_or_after_unlink(self):
        for after in (False, True):
            self.coordinator = self.new(); self.begin()
            original = self.store.remove
            def failed():
                if after: original()
                raise OSError('remove durability failed')
            self.store.remove = failed
            with self.assertRaises(OSError): self.coordinator.finish(deadline=100)
            self.store.remove = original
            self.assertEqual(self.coordinator.finish(deadline=100), 'clean')
            self.assertIsNone(self.store.value)

    def test_finish_drains_retained_alias_writer_before_retry(self):
        self.begin(); self.crash = 'after-alias'
        with self.assertRaises(Crash): self.coordinator.finish(deadline=100)
        self.crash = None
        def pending(**kwargs): self.coordinator.writer_finished('native')
        self.backend.drain_pending = pending
        self.assertEqual(self.coordinator.finish(deadline=100), 'clean')

    def test_unexplained_disappearance_is_not_known_clean_removal(self):
        self.begin(); self.store.value = None; self.marker.value = None
        with self.assertRaises(recovery.RecoveryError): self.coordinator.recover(deadline=100)

    def test_uncertain_owned_candidates_recover_from_actual_disk(self):
        self.begin(); self.store.fail = 'after'
        with self.assertRaises(OSError): self.coordinator.record_owned(self.owned())
        self.assertEqual(self.coordinator.recover(deadline=100), 'clean')
        cleaned = next(event[1] for event in self.events if event[0] == 'cleanup')
        self.assertEqual(len(cleaned['addresses']), 1)

    def test_absent_after_known_remove_requires_context_and_prior_alias(self):
        self.begin(); original = self.store.remove
        def failed(): original(); raise OSError('directory fsync')
        self.store.remove = failed
        with self.assertRaises(OSError): self.coordinator.finish(deadline=100)
        self.store.remove = original
        self.identity = link.LinkIdentity(7, 'wlan0', b'replacement')
        with self.assertRaises(recovery.RecoveryError): self.coordinator.recover(deadline=100)
        self.assertNotIn(('sync-absent',), self.store.events)

    def test_needs_recovery_is_readonly_and_tracks_uncertain_resource_intent(self):
        self.assertFalse(self.coordinator.needs_recovery)
        self.begin(); self.assertFalse(self.coordinator.needs_recovery)
        self.store.fail = 'after'
        with self.assertRaises(OSError): self.coordinator.record_owned(self.owned())
        self.assertTrue(self.coordinator.needs_recovery)
        with self.assertRaises(AttributeError): self.coordinator.needs_recovery = False
        self.coordinator.recover(deadline=100)
        self.assertFalse(self.coordinator.needs_recovery)

    def test_needs_recovery_tracks_failed_registration_and_clean_removal(self):
        self.begin(); self.store.fail = 'before'
        with self.assertRaises(OSError): self.coordinator.writer_started('native', 323, 32, 'address-add')
        self.assertTrue(self.coordinator.needs_recovery)
        self.coordinator.writer_finished('native')
        self.assertFalse(self.coordinator.needs_recovery)
        original = self.store.remove
        def failed(): original(); raise OSError('directory fsync')
        self.store.remove = failed
        with self.assertRaises(OSError): self.coordinator.finish(deadline=100)
        self.assertTrue(self.coordinator.needs_recovery)
        self.store.remove = original; self.coordinator.recover(deadline=100)
        self.assertFalse(self.coordinator.needs_recovery)

    def test_pregate_context_failure_keeps_known_attempt_for_dead_writer_cleanup(self):
        self.begin()
        with patch.object(self.marker, 'read', side_effect=OSError('transient marker read')):
            with self.assertRaises(OSError):
                self.coordinator.writer_started('native', 323, 32, 'address-add')
        self.assertTrue(self.coordinator.needs_recovery)
        self.assertIsNone(self.store.value['writers']['native'])
        self.coordinator.writer_finished('native')  # Caller has proved its held init dead.
        self.assertFalse(self.coordinator.needs_recovery)
        self.assertIsNone(self.store.value['writers']['native'])

    def test_registration_preflight_does_not_overwrite_an_existing_attempt(self):
        self.begin(); self.coordinator.writer_started('native', 323, 32, 'address-add')
        original = copy.deepcopy(self.store.value['writers']['native'])
        with patch.object(self.marker, 'read', side_effect=AssertionError('read before slot refusal')):
            with self.assertRaises(recovery.RecoveryError):
                self.coordinator.writer_started('native', 999, 99, 'other-command')
        self.assertEqual(self.store.value['writers']['native'], original)
        self.coordinator.writer_finished('native')
        self.assertIsNone(self.store.value['writers']['native'])


if __name__ == '__main__': unittest.main()
