"""Coordinate durable recovery while the caller holds all ownership locks.

The caller must block radios and hold guardian -> owner -> DHCP lifetime locks
before beginning or recovering. No method reconnects or grants a disk record
kernel authority. Unexpected context or link changes retain the journal.
"""
import base64
import copy
import math
import re
import time

from .journal import record_context, validate_record
from .link import LinkIdentity, read_link
from .writers import capture_writer, current_context, drain_writer


class RecoveryError(RuntimeError):
    """Recovery is incomplete; keep the radio blocked and ownership evidence."""


def _require(condition, message):
    if not condition:
        raise RecoveryError(message)


_PERMIT_KEY = object()


class RecoveryPermit:
    """Ephemeral coordinator-issued authority, never deserializable from JSON."""
    def __init__(self, coordinator, key):
        _require(key is _PERMIT_KEY, 'recovery permit cannot be constructed externally')
        self._coordinator = coordinator


def validate_permit(permit, *, generation, interface, deadline, check=lambda: None):
    _require(type(permit) is RecoveryPermit, 'invalid recovery permit')
    owner = permit._coordinator
    _require(owner._permit is permit and owner._recovering, 'expired recovery permit')
    owner.check_link(deadline=deadline, check=check)
    value = owner.record
    _require(value['phase'] == 'active' and value['generation'] == generation and
             value['interface'] == interface and not any(value['writers'].values()),
             'recovery permit identity or writer barrier changed')
    return validate_record(value)


class DNSRecoveryPermit:
    """Ephemeral DNS-only authority; never grants link or kernel ownership."""
    def __init__(self, coordinator, key):
        _require(key is _PERMIT_KEY, 'DNS recovery permit cannot be constructed externally')
        self._coordinator = coordinator


def validate_dns_permit(permit, backend, *, deadline, check=lambda: None):
    _require(type(permit) is DNSRecoveryPermit, 'invalid DNS recovery permit')
    owner = permit._coordinator
    _require(owner._dns_permit is permit and owner._recovering and owner.backend is backend,
             'expired or foreign DNS recovery permit')
    owner._checkpoint(deadline, check)
    owner._context()
    value = owner.record
    _require(not owner._uncertain and value['version'] == 2 and value['phase'] == 'reboot-dns'
             and not any(value['writers'].values()), 'DNS recovery writer barrier changed')
    return validate_record(value)


class RecoveryJournal:
    """Trusted coordinator; injectable helpers exist for isolated fixtures only.

    writer_finished is a completion callback: callers must prove the associated
    borrowed init pidfd dead before invoking it. Failed registration is tracked
    even when rename/fsync completion is uncertain, so another slot is never
    cleared accidentally. Backend native commands remain responsible for gates.
    """
    def __init__(self, store, backend, interface='wlan0', marker=None, *,
                 context_reader=current_context, link_reader=read_link,
                 capture=capture_writer, drain=drain_writer, cleanup=None,
                 clock=time.monotonic):
        _require(type(interface) is str and
                 re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,14}', interface, re.ASCII), 'invalid interface')
        self.store, self.backend, self.interface, self.marker = store, backend, interface, marker
        self._context_reader, self._link_reader = context_reader, link_reader
        self._capture, self._drain, self._cleanup, self._clock = capture, drain, cleanup, clock
        self._record = self._identity = None
        self._uncertain = False
        self._removal_attempted = self._absent_after_removal = False
        self._attempted, self._failed, self._completed = {}, set(), set()
        self._permit, self._recovering = None, False
        self._dns_permit = None
        backend.journal = self

    @property
    def record(self):
        return copy.deepcopy(self._record)

    @property
    def needs_recovery(self):
        """Uncertain evidence requires recovery before any new native command."""
        return (self._uncertain or bool(self._failed) or self._removal_attempted
                or self._absent_after_removal)

    def _checkpoint(self, deadline, check):
        _require(type(deadline) in (int, float) and math.isfinite(deadline), 'invalid recovery deadline')
        check()
        _require(self._clock() < deadline, 'recovery deadline expired')

    @staticmethod
    def _lease_identity(value):
        return {key: copy.deepcopy(value[key]) for key in
                ('generation', 'boot_id', 'observer_pidns', 'target_netns', 'interface',
                 'ifindex', 'cookie', 'previous_alias')}

    def _context(self):
        _require(self._record is not None, 'no loaded recovery record')
        expected = record_context(self._record)
        _require(self._context_reader() == expected, 'recovery boot or namespace changed')
        self._provenance()

    def _provenance(self):
        _require(self._record['interface'] == self.interface, 'recovery interface changed')
        if self.marker is not None:
            _require(self.marker.read() in (None, self._record['generation']), 'dirty marker belongs to another generation')

    def _load(self, *, allow_reboot=False):
        value = self.store.read()
        if value is not None:
            value = validate_record(value)
            identity = self._lease_identity(value)
            _require(self._identity is None or identity == self._identity, 'journal lease identity changed')
            self._identity = identity
        elif self._identity is not None:
            _require(self._removal_attempted and self._record is not None and
                     self._record['phase'] in ('clean', 'reboot-clean') and
                     (self.marker is None or self.marker.read() is None),
                     'loaded journal unexpectedly disappeared')
            self._context()
            self._absent_after_removal, self._uncertain = True, False
            return self.record
        self._absent_after_removal = False
        self._record, self._uncertain = value, False
        if value is not None:
            self._provenance() if allow_reboot else self._context()
        return value

    def _save(self, **changes):
        _require(self._record is not None and not self._uncertain, 'journal must be reloaded after uncertain write')
        self._context()
        value = copy.deepcopy(self._record)
        value.update(changes)
        value['sequence'] += 1
        try:
            stored = self.store.write(value)
        except BaseException:
            self._uncertain = True
            raise
        self._record = stored

    def check_link(self, *, deadline, check=lambda: None):
        self._checkpoint(deadline, check)
        _require(not self._uncertain, 'journal completion is uncertain')
        self._context()
        _require(self._record['version'] == 1, 'DNS retirement has no link authority')
        value = self._link_reader(self.interface, deadline=deadline, check=check)
        self._checkpoint(deadline, check)
        _require(type(value) is LinkIdentity and value.name == self.interface and
                 value.ifindex == self._record['ifindex'], 'link was renamed or replaced')
        cookie = self._record['cookie'].encode('ascii')
        previous = base64.b64decode(self._record['previous_alias'])
        allowed = (cookie,) if self._record['phase'] == 'active' else (
            (previous,) if self._record['phase'] == 'clean' else (previous, cookie))
        _require(value.alias in allowed, 'link cookie or prior alias changed')
        self._context()
        return value

    def check_command(self, backend, argv, *, content, deadline, check=lambda: None):
        """Authorize actual argv at both sides of native writer registration."""
        self._checkpoint(deadline, check)
        _require(not self._uncertain, 'journal completion is uncertain')
        self._context()
        _require(backend is self.backend, 'foreign native backend')
        if self._record['version'] == 1:
            self.check_link(deadline=deadline, check=check)
            return
        _require(self._recovering and self._dns_permit is not None and
                 self._record['phase'] == 'reboot-dns', 'DNS retirement is not active')
        allowed = [(backend.resolvconf, '--host-pid-lock-version'), (backend.resolvconf, '-u')]
        provider = self._record['resources']['provider']
        if provider is not None:
            allowed.append((backend.resolvconf, '-f', '-d', provider))
        _require(content is None and type(argv) in (list, tuple) and tuple(argv) in allowed,
                 'command has no DNS retirement authority')

    def begin(self, generation, *, deadline, check=lambda: None):
        self._checkpoint(deadline, check)
        _require(type(generation) is str and re.fullmatch(r'[0-9a-f]{32}', generation), 'invalid generation')
        _require(self.store.read() is None, 'orphan journal requires recovery')
        _require(self.marker is None or self.marker.read() is None, 'orphan marker requires recovery')
        context = self._context_reader()
        identity = self._link_reader(self.interface, deadline=deadline, check=check)
        _require(type(identity) is LinkIdentity and identity.name == self.interface and
                 not identity.alias.startswith(b'privacyctl:'), 'unexplained link cookie')
        self._checkpoint(deadline, check)
        _require(context == self._context_reader(), 'context changed during begin')
        value = dict(version=1, sequence=1, generation=generation, **context,
                     interface=self.interface, ifindex=identity.ifindex, phase='alias-intent',
                     cookie='privacyctl:' + generation,
                     previous_alias=base64.b64encode(identity.alias).decode('ascii'),
                     resources={'addresses': [], 'routes': [], 'provider': None, 'dns_contents': []},
                     writers={'native': None, 'dhcp': None})
        value = validate_record(value)
        self._identity = self._lease_identity(value)
        try:
            self._record = self.store.write(value)
        except BaseException:
            self._uncertain = True
            raise
        if self.marker is not None:
            self.marker.write(generation)
        self.check_link(deadline=deadline, check=check)
        self.backend.set_alias(self.interface, value['cookie'].encode(), deadline=deadline, check=check)
        observed = self.check_link(deadline=deadline, check=check)
        _require(observed.alias == value['cookie'].encode(), 'link cookie was not installed')
        _require(not any(self._record['writers'].values()), 'alias writer completion is pending')
        self._save(phase='active')
        self._checkpoint(deadline, check)
        return self.record

    def writer_started(self, kind, pid, pidfd, operation):
        _require(kind in ('native', 'dhcp'), 'invalid writer slot')
        _require(self._record is not None and not self._uncertain, 'journal unavailable for writer')
        _require(self._record['phase'] not in ('clean', 'reboot-clean') and self._record['writers'][kind] is None
                 and kind not in self._attempted, 'writer slot is already owned')
        _require(kind != 'dhcp' or self._record['phase'] == 'active', 'DHCP requires active link cookie')
        self._completed.discard(kind)
        self._failed.add(kind)
        self._attempted[kind] = None
        # Even context reads can fail after the caller has acquired its init
        # pidfd. Preserve this known pre-gate attempt before any fallible reads.
        self._context()
        expected = self._capture(pid, pidfd, operation)
        self._attempted[kind] = copy.deepcopy(expected)
        slots = copy.deepcopy(self._record['writers']); slots[kind] = expected
        self._save(writers=slots)
        self._failed.discard(kind)

    def writer_finished(self, kind):
        _require(kind in ('native', 'dhcp'), 'invalid writer slot')
        if self._uncertain:
            self._load()
        self._context()
        slot = self._record['writers'][kind]
        if kind not in self._attempted:
            _require(kind in self._completed and slot is None, 'no matching attempted writer')
            return
        expected = self._attempted[kind]
        if slot is None:
            _require(kind in self._failed, 'writer slot disappeared without completion')
        else:
            _require(expected is not None and slot == expected, 'writer slot was replaced')
            slots = copy.deepcopy(self._record['writers']); slots[kind] = None
            try:
                self._save(writers=slots)
            except BaseException:
                self._failed.add(kind)
                raise
        self._attempted.pop(kind)
        self._failed.discard(kind); self._completed.add(kind)

    def record_owned(self, owned):
        self._context()
        _require(self._record['phase'] == 'active', 'resources require active link cookie')
        if owned is None:
            resources = {'addresses': [], 'routes': [], 'provider': None, 'dns_contents': []}
        else:
            # Only the trusted live applier calls this. JSON is never accepted.
            from .network import OwnedState
            _require(type(owned) is OwnedState and owned.generation == self._record['generation']
                     and owned.interface == self.interface and owned.ifindex == self._record['ifindex'],
                     'owned lease identity changed')
            import dataclasses
            resources = {'addresses': [dataclasses.asdict(v) for v in owned.addresses],
                         'routes': [dataclasses.asdict(v) for v in owned.routes],
                         'provider': owned.provider, 'dns_contents': list(owned.dns_contents)}
        self._save(resources=resources)

    def _clear(self):
        _require(self._record['phase'] in ('clean', 'reboot-clean'), 'journal is not clean')
        generation = self._record['generation']
        if self.marker is not None:
            value = self.marker.read()
            _require(value in (None, generation), 'dirty marker belongs to another generation')
            if value is not None:
                self.marker.clear(generation)
        if self._absent_after_removal:
            self.store.confirm_absent()
        else:
            self._removal_attempted = True
            try:
                self.store.remove()
            except BaseException:
                self._uncertain = True
                raise
        self._record = self._identity = None
        self._removal_attempted = self._absent_after_removal = False
        self._attempted.clear(); self._failed.clear(); self._completed.clear()

    def _drain_local(self, deadline, check):
        pending = getattr(self.backend, 'drain_pending', None)
        if pending is not None:
            pending(deadline=deadline, check=check)
            if self._uncertain:
                self._load()

    def finish(self, *, deadline, check=lambda: None):
        self._checkpoint(deadline, check)
        if self._uncertain:
            self._load()
        self._context()
        self._drain_local(deadline, check)
        observed = self.check_link(deadline=deadline, check=check)
        _require(not any(self._record['resources'].values()) and
                 not any(self._record['writers'].values()), 'resources or writers remain')
        if self._record['phase'] != 'clean':
            if self._record['phase'] != 'alias-restore-intent':
                self._save(phase='alias-restore-intent')
            previous = base64.b64decode(self._record['previous_alias'])
            if observed.alias != previous:
                self.backend.set_alias(self.interface, previous, deadline=deadline, check=check)
            observed = self.check_link(deadline=deadline, check=check)
            _require(observed.alias == previous and not any(self._record['writers'].values()),
                     'alias restoration or writer completion is unproved')
            self._save(phase='clean')
        self.check_link(deadline=deadline, check=check)
        self._clear()
        return 'clean'

    def _finish_reboot(self, deadline, check):
        self._checkpoint(deadline, check)
        self._context()
        _require(not any(self._record['writers'].values()), 'DNS writer completion remains pending')
        if self._record['phase'] != 'reboot-clean':
            if self._record['resources']['provider'] is not None:
                self._dns_permit = DNSRecoveryPermit(self, _PERMIT_KEY)
                self.backend.retire_dns(self._dns_permit, deadline=deadline, check=check)
                validate_dns_permit(self._dns_permit, self.backend, deadline=deadline, check=check)
                self._save(resources={'addresses': [], 'routes': [], 'provider': None, 'dns_contents': []})
            self._save(phase='reboot-clean')
        self._checkpoint(deadline, check)
        self._context()
        self._clear()
        return 'clean'

    def recover(self, *, deadline, check=lambda: None):
        self._checkpoint(deadline, check)
        self._permit, self._recovering = None, False
        self._dns_permit = None
        # A failed begin may have created no record; read actual state afresh.
        if self._record is None:
            self._identity = None
        value = self._load(allow_reboot=True)
        if value is None:
            _require(self.marker is None or self.marker.read() is None, 'unexplained legacy dirty marker')
            return 'clean'
        context = self._context_reader()
        if context['boot_id'] != record_context(value)['boot_id']:
            _require(not self._attempted, 'local writer handles cannot cross a boot boundary')
            self._checkpoint(deadline, check)
            _require(self._context_reader() == context, 'context changed during boot rollover')
            try:
                self._record = self.store.rollover_boot(context)
            except BaseException:
                self._uncertain = True
                raise
            self._uncertain = False
            self._removal_attempted = self._absent_after_removal = False
            self._failed.clear(); self._completed.clear()
        self._context()
        self._recovering = True
        try:
            self._drain_local(deadline, check)
            for kind in ('native', 'dhcp'):
                writer = self._record['writers'][kind]
                if writer is None:
                    continue
                self._checkpoint(deadline, check)
                self._context()
                outcome = self._drain(writer, **record_context(self._record), deadline=deadline, check=check)
                _require(outcome in ('absent', 'reused', 'dead', 'killed'), 'writer death was not proved')
                self._attempted[kind] = copy.deepcopy(writer)
                self._failed.discard(kind)
                self.writer_finished(kind)
            if self._record['version'] == 2:
                return self._finish_reboot(deadline, check)
            self.check_link(deadline=deadline, check=check)
            if self._record['phase'] == 'active':
                self._permit = RecoveryPermit(self, _PERMIT_KEY)
                if self._cleanup is None:
                    from .network import LeaseApplier
                    LeaseApplier(self._record['generation'], self.interface, backend=self.backend,
                                 journal=self, check=check).remove_recovered(self._permit, deadline=deadline, check=check)
                else:
                    self._cleanup(self._permit, deadline=deadline, check=check)
                _require(not any(self._record['resources'].values()), 'recovered resources remain')
            return self.finish(deadline=deadline, check=check)
        finally:
            self._permit, self._recovering = None, False
            self._dns_permit = None
