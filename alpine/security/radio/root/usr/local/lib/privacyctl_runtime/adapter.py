"""Native owner wiring and an emergency-off fence shared with the CLI.

All alternate paths/dependencies are trusted constructor inputs for private
fixtures. Production CLI requests cannot supply these values.
"""
from ipaddress import IPv6Address, IPv6Interface
import json
import os
from pathlib import Path
import re
import secrets
import stat

from .dhcp import _private_directory
from .network import IPv6Profile, LeaseApplier

RUNTIME = Path('/run/privacyctl')
IPV6_FILE = Path('/etc/privacyctl/ipv6.json')


class Fence:
    def __init__(self, runtime=RUNTIME, name='off-fence'):
        if name not in ('off-fence', 'lease-dirty'):
            raise ValueError('unsupported owner marker')
        self.runtime, self.name = Path(runtime), name

    def read(self):
        directory = _private_directory(self.runtime)
        try:
            try:
                fd = os.open(self.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                             dir_fd=directory)
            except FileNotFoundError:
                return None
            with os.fdopen(fd, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
                    raise RuntimeError('unsafe owner marker')
                value = stream.read(65)
            if not re.fullmatch(rb'[0-9a-f]{32}\n', value):
                raise RuntimeError('invalid owner marker')
            return value[:-1].decode('ascii')
        except OSError as error:
            raise RuntimeError('owner marker unavailable') from error
        finally:
            os.close(directory)

    def write(self, value):
        if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{32}', value):
            raise ValueError('invalid owner marker token')
        directory = _private_directory(self.runtime)
        name = '.marker-' + secrets.token_hex(12)
        try:
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
                         0o600, dir_fd=directory)
            with os.fdopen(fd, 'w') as stream:
                stream.write(value + '\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.rename(name, self.name, src_dir_fd=directory, dst_dir_fd=directory)
            os.fsync(directory)
        finally:
            try:
                os.unlink(name, dir_fd=directory)
            except FileNotFoundError:
                pass
            os.close(directory)

    def clear(self, expected):
        if self.read() != expected:
            raise RuntimeError('owner marker was replaced')
        directory = _private_directory(self.runtime)
        try:
            os.unlink(self.name, dir_fd=directory)
            os.fsync(directory)
        finally:
            os.close(directory)


class JournaledApplier:
    """A crash marker forbids automatic reuse of orphaned network state.

It is deliberately not a deserializer for process-local ownership capabilities.
After an abrupt owner death, explicit recovery must inspect/remove that state.
"""
    def __init__(self, applier, runtime, generation):
        self.applier, self.generation = applier, generation
        self.marker = Fence(runtime, 'lease-dirty')

    @property
    def current(self):
        return self.applier.current

    def apply(self, *args, **kwargs):
        if self.marker.read() not in (None, self.generation):
            raise RuntimeError('orphaned lease state requires recovery')
        self.marker.write(self.generation)
        return self.applier.apply(*args, **kwargs)

    def remove(self, owned):
        self.applier.remove(owned)
        if self.marker.read() is not None:
            self.marker.clear(self.generation)


class NativeAdapter:
    def __init__(self, legacy, *, runtime=RUNTIME, system=None, ipv6_file=IPV6_FILE):
        self.legacy, self.runtime = legacy, Path(runtime)
        self.system = legacy.System() if system is None else system
        self.ipv6_file = Path(ipv6_file)
        self.fence = Fence(runtime)
        self.generation = self.baseline = None

    def begin_generation(self, generation, *, expected_fence=None):
        if not isinstance(generation, str) or not re.fullmatch(r'[0-9a-f]{32}', generation):
            raise ValueError('invalid owner generation')
        with self.legacy.RadioLock(timeout=2):
            if Fence(self.runtime, 'lease-dirty').read() is not None:
                raise RuntimeError('orphaned lease state requires recovery')
            current = self.fence.read()
            if current != expected_fence:
                raise RuntimeError('queued generation cancelled by emergency off')
            self.baseline, self.generation = current, generation

    def check_generation(self, generation):
        if self.generation != generation or self.fence.read() != self.baseline:
            raise RuntimeError('generation cancelled by emergency off')

    def invalidate_fence(self):
        # Also used by normal IPC off while inside an unblock checkpoint.
        # Atomic publication must never recursively acquire RadioLock.
        self.fence.write(secrets.token_hex(16))

    def emergency_off(self):
        attempted_block = False
        try:
            # Publish cancellation before waiting: a cooperative unblock holding
            # the lock sees this fence and unwinds instead of delaying off.
            self.invalidate_fence()
            with self.legacy.RadioLock(timeout=2):
                try:
                    self.invalidate_fence()
                finally:
                    attempted_block = True
                    self.block_all()
                self.clear_session()
        finally:
            if not attempted_block:
                self.block_all()

    def unblock_wifi(self, check):
        # The CLI writes its fence and blocks under this same short lock.
        # check_generation deliberately does not recursively acquire it.
        with self.legacy.RadioLock(timeout=2):
            check()
            self.system.unblock_wifi()
            check()

    def block_all(self):
        self.system.block_all()

    def block_bluetooth(self):
        self.system.block_bluetooth()

    def bluetooth_blocked(self):
        return all(value == '0' for value in self.system.states('bluetooth'))

    def clear_session(self):
        self.legacy.clear_session()

    def write_session(self, profile, network_id, ssid):
        self.legacy.write_session(profile, network_id, ssid)

    def open_wpa(self, check):
        return self.legacy.WpaControl(check=check)

    def applier(self, generation, check):
        return JournaledApplier(LeaseApplier(generation, check=check), self.runtime, generation)

    def read_profile(self, profile):
        network_id, ssid = self.legacy.read_profile(profile, self.legacy.PROFILE_FILE)
        return network_id, ssid, read_ipv6(self.ipv6_file, profile)


def read_ipv6(path, profile):
    """Require explicit private static IPv6 values; never guess home settings."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
            raise RuntimeError('IPv6 policy must be root-owned and private')
        raw = stream.read(8193)
    if len(raw) > 8192:
        raise RuntimeError('IPv6 policy exceeds size limit')
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError('duplicate IPv6 policy key')
            result[key] = value
        return result
    try:
        data = json.loads(raw, object_pairs_hook=pairs)
        if (type(data) is not dict or set(data) != {'version', 'profiles'}
                or type(data['version']) is not int or data['version'] != 1
                or type(data['profiles']) is not dict):
            raise ValueError('invalid IPv6 policy envelope')
        values = data['profiles'][profile]
        if type(values) is not dict or set(values) != {'addresses', 'routers'}:
            raise ValueError('invalid IPv6 profile fields')
        if any(type(values[key]) is not list or len(values[key]) > 4
               or any(type(value) is not str for value in values[key]) for key in values):
            raise ValueError('invalid IPv6 profile values')
        return IPv6Profile(tuple(IPv6Interface(x) for x in values['addresses']),
                           tuple(IPv6Address(x) for x in values['routers']))
    except (ValueError, KeyError, TypeError, RecursionError) as error:
        raise RuntimeError('invalid or missing private IPv6 profile') from error
