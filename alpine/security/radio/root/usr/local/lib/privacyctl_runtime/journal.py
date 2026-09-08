"""Bounded durable recovery evidence, never a kernel deletion capability.

Callers provision the private directory and hold the runtime ownership locks.
The store rejects unexpected disk changes; it cannot serialize hostile root
writers. A successful read is required before replacing an existing record.
"""
import base64
import binascii
from contextlib import contextmanager
import copy
import hashlib
from ipaddress import ip_address, ip_interface, ip_network
import json
import os
import re
import secrets
import stat
import uuid


MAX_BYTES = 65536
MAX_DEPTH = 8
_UNREAD = object()


class JournalError(RuntimeError):
    """Malformed evidence or an unsafe/unexpected filesystem instance."""


def _require(condition, message):
    if not condition:
        raise JournalError(message)


def _fields(value, names):
    _require(type(value) is dict and set(value) == set(names.split()),
             'invalid journal object fields')


def _integer(value, minimum=1, maximum=(1 << 63) - 1):
    _require(type(value) is int and minimum <= value <= maximum,
             'invalid journal integer')


def _namespace(value):
    _fields(value, 'dev ino')
    _integer(value['dev'])
    _integer(value['ino'])


def _text(value, pattern):
    _require(type(value) is str and re.fullmatch(pattern, value, re.ASCII) is not None,
             'invalid journal text')


def _ip(value, family, kind='address'):
    _require(type(value) is str and len(value) <= 64 and '%' not in value,
             'invalid journal IP text')
    parser = {'address': ip_address, 'interface': ip_interface, 'network': ip_network}[kind]
    try:
        parsed = parser(value)
    except ValueError as error:
        raise JournalError('invalid journal IP selector') from error
    _require(parsed.version == family and str(parsed) == value,
             'noncanonical or mismatched journal IP selector')


def _bounded_list(value, maximum):
    _require(type(value) is list and len(value) <= maximum, 'unbounded journal list')


def _unique(values):
    result = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def record_context(record):
    """Effective writer context; original v2 identity is inert provenance."""
    return copy.deepcopy(record['recovery_context'] if record['version'] == 2 else
                         {key: record[key] for key in ('boot_id', 'observer_pidns', 'target_netns')})


def _rollover_record(previous, context):
    _fields(context, 'boot_id observer_pidns target_netns')
    _require(context['boot_id'] != record_context(previous)['boot_id'], 'boot did not change')
    value = copy.deepcopy(previous)
    value.update(version=2, phase='reboot-dns', sequence=previous['sequence'] + 1,
                 recovery_context=copy.deepcopy(context), writers={'native': None, 'dhcp': None})
    value['resources']['addresses'] = []
    value['resources']['routes'] = []
    return validate_record(value)


def validate_record(record):
    """Validate v1 leases or v2 DNS retirement, returning independent JSON.

    This is structural validation only. Boot, link cookie, and writer identity
    proofs belong to recovery and are deliberately not inferred from this data.
    """
    _require(type(record) is dict, 'invalid journal object')
    version = record.get('version')
    _integer(version, 1, 2)
    _fields(record, 'version sequence generation boot_id observer_pidns target_netns '
                    'interface ifindex phase cookie previous_alias resources writers' +
                    (' recovery_context' if version == 2 else ''))
    _integer(record['sequence'])
    _text(record['generation'], r'[0-9a-f]{32}')
    _text(record['boot_id'], r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')
    _require(str(uuid.UUID(record['boot_id'])) == record['boot_id'], 'invalid boot ID')
    _namespace(record['observer_pidns'])
    _namespace(record['target_netns'])
    if version == 2:
        context = record['recovery_context']
        _fields(context, 'boot_id observer_pidns target_netns')
        _text(context['boot_id'], r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')
        _require(context['boot_id'] != record['boot_id'], 'DNS retirement must follow the original boot')
        _namespace(context['observer_pidns'])
        _namespace(context['target_netns'])
    _text(record['interface'], r'[A-Za-z0-9][A-Za-z0-9_.-]{0,14}')
    _integer(record['ifindex'])
    phases = ('alias-intent', 'active', 'alias-restore-intent', 'clean') if version == 1 else (
        'reboot-dns', 'reboot-clean')
    _require(type(record['phase']) is str and record['phase'] in phases, 'invalid phase')
    _require(type(record['cookie']) is str and
             record['cookie'] == 'privacyctl:' + record['generation'], 'invalid link cookie')
    alias = record['previous_alias']
    _require(type(alias) is str and len(alias) <= 340, 'invalid previous alias')
    try:
        decoded_alias = base64.b64decode(alias, validate=True)
    except (ValueError, binascii.Error) as error:
        raise JournalError('invalid previous alias encoding') from error
    _require(len(decoded_alias) <= 255 and b'\0' not in decoded_alias and
             base64.b64encode(decoded_alias).decode('ascii') == alias,
             'invalid previous alias bytes')
    resources = record['resources']
    _fields(resources, 'addresses routes provider dns_contents')
    _bounded_list(resources['addresses'], 16)
    _bounded_list(resources['routes'], 64)
    _bounded_list(resources['dns_contents'], 4)
    for address in resources['addresses']:
        _fields(address, 'family cidr protocol')
        _integer(address['family'], 4, 6)
        _require(address['family'] in (4, 6), 'invalid address family')
        _integer(address['protocol'], 196, 196)
        _ip(address['cidr'], address['family'], 'interface')
    for route in resources['routes']:
        _fields(route, 'family destination gateway protocol metric source')
        _integer(route['family'], 4, 6)
        _require(route['family'] in (4, 6), 'invalid route family')
        _integer(route['protocol'], 196, 196)
        _integer(route['metric'], 42700, 42955)
        if route['destination'] != 'default':
            _ip(route['destination'], route['family'], 'network')
        for key in ('gateway', 'source'):
            if route[key] is not None:
                _ip(route[key], route['family'])
    provider = resources['provider']
    _require(provider is None or (type(provider) is str and provider ==
             f"privacyctl.{record['generation']}.{record['interface']}"), 'invalid provider')
    _require(provider is not None or not resources['dns_contents'], 'DNS without provider')
    for content in resources['dns_contents']:
        _require(type(content) is str and len(content) <= 2048 and content.isascii(),
                 'invalid DNS content')
        for line in content.splitlines():
            match = re.fullmatch(r'nameserver[ \t]+([^ \t\r\n]+)[ \t]*', line, re.ASCII)
            _require(match is not None, 'invalid DNS line')
            server = match.group(1)
            _require('%' not in server, 'scoped DNS address')
            try:
                ip_address(server)
            except ValueError as error:
                raise JournalError('invalid DNS address') from error
        _require(not any(ord(char) < 32 and char not in '\n\t' for char in content),
                 'invalid DNS control character')
    _fields(record['writers'], 'native dhcp')
    for value in record['writers'].values():
        if value is None:
            continue
        _fields(value, 'pid start_time pidns nspid operation')
        _integer(value['pid'], 2)
        _integer(value['start_time'])
        _namespace(value['pidns'])
        _integer(value['nspid'], 1, 1)
        _text(value['operation'], r'[a-z][a-z-]{0,63}')
    empty = not any(resources.values())
    if version == 2:
        _require(not resources['addresses'] and not resources['routes'], 'kernel resources in DNS retirement')
        _require(record['writers']['dhcp'] is None, 'DHCP writer in DNS retirement')
    if record['phase'] not in ('active', 'reboot-dns'):
        _require(empty, 'resources contradict journal phase')
    if record['phase'] in ('alias-restore-intent', 'clean'):
        _require(record['writers']['dhcp'] is None, 'DHCP writer contradicts phase')
    if record['phase'] in ('clean', 'reboot-clean'):
        _require(record['writers']['native'] is None, 'native writer contradicts clean phase')
    result = copy.deepcopy(record)
    for key in ('addresses', 'routes', 'dns_contents'):
        result['resources'][key] = _unique(result['resources'][key])
    return result


def _decode(data):
    """Bound nesting before the JSON parser; reject duplicate keys and constants."""
    _require(len(data) <= MAX_BYTES, 'oversize journal')
    depth, quoted, escaped = 0, False, False
    for char in data:
        if quoted:
            if escaped:
                escaped = False
            elif char == 92:
                escaped = True
            elif char == 34:
                quoted = False
        elif char == 34:
            quoted = True
        elif char in (91, 123):
            depth += 1
            _require(depth <= MAX_DEPTH, 'journal nesting limit exceeded')
        elif char in (93, 125):
            depth -= 1
            _require(depth >= 0, 'invalid journal nesting')

    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, 'duplicate journal key')
            result[key] = value
        return result

    def constant(value):
        raise JournalError('invalid JSON constant')

    try:
        return validate_record(json.loads(data.decode('utf-8'), object_pairs_hook=pairs,
                                          parse_constant=constant))
    except (ValueError, UnicodeError, RecursionError) as error:
        raise JournalError('invalid journal JSON') from error


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


class Journal:
    """One fixed-name journal in an existing root-private directory.

    Errors propagate, including a directory-fsync failure after rename/unlink.
    After such uncertain completion, callers must reload and recover the actual
    disk state before continuing. No method repairs malformed existing evidence.
    """

    def __init__(self, directory, filename='lease.json'):
        path = os.fspath(directory)
        _require(type(path) is str and path.startswith('/') and '\0' not in path,
                 'journal directory must be an absolute path')
        self._parts = path.split('/')[1:]
        _require(bool(self._parts) and all(part not in ('', '.', '..') for part in self._parts),
                 'unsafe journal directory component')
        _text(filename, r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}')
        self.directory, self.filename = path, filename
        self._directory_identity = None
        self._token, self._record = _UNREAD, None

    @contextmanager
    def _directory(self):
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        fd = os.open('/', flags)
        try:
            for index, part in enumerate(self._parts):
                child = os.open(part, flags, dir_fd=fd)
                os.close(fd)
                fd = child
                info = os.fstat(fd)
                mode = stat.S_IMODE(info.st_mode)
                _require(info.st_uid == 0, 'journal directory ancestor is not root-owned')
                if index == len(self._parts) - 1:
                    _require(mode == 0o700, 'journal directory is not private')
                else:
                    _require(not mode & 0o022 or bool(mode & stat.S_ISVTX),
                             'writable journal directory ancestor')
            identity = (info.st_dev, info.st_ino)
            _require(self._directory_identity is None or self._directory_identity == identity,
                     'journal directory was replaced')
            self._directory_identity = identity
            yield fd
        finally:
            os.close(fd)

    def _disk(self, directory):
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
        try:
            fd = os.open(self.filename, flags, dir_fd=directory)
        except FileNotFoundError:
            return None, None
        try:
            before = os.fstat(fd)
            _require(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and
                     stat.S_IMODE(before.st_mode) == 0o600 and before.st_nlink == 1,
                     'unsafe journal file')
            _require(before.st_size <= MAX_BYTES, 'oversize journal')
            data = bytearray()
            while len(data) <= MAX_BYTES:
                part = os.read(fd, MAX_BYTES + 1 - len(data))
                if not part:
                    break
                data.extend(part)
            after = os.fstat(fd)
            named = os.stat(self.filename, dir_fd=directory, follow_symlinks=False)
            _require(_identity(before) == _identity(after) == _identity(named),
                     'journal changed while reading')
            value = _decode(bytes(data))
            return (_identity(after), hashlib.sha256(data).digest()), value
        finally:
            os.close(fd)

    def read(self):
        self._token, self._record = _UNREAD, None
        with self._directory() as directory:
            token, value = self._disk(directory)
        self._token, self._record = token, value
        return copy.deepcopy(value)

    def _unchanged(self, directory):
        token, value = self._disk(directory)
        if self._token is _UNREAD:
            _require(token is None, 'existing journal must be read before mutation')
        else:
            _require(token == self._token, 'journal disk instance changed')
        return value

    def write(self, record):
        return self._write(record)

    def rollover_boot(self, context):
        """Retire extinct kernel intent; caller authenticates the new kernel context.

        Only this explicit transition may replace effective writer context. DNS
        intent and original provenance survive; ordinary writes remain immutable.
        """
        _require(self._token is not _UNREAD and self._record is not None,
                 'rollover requires an existing loaded journal')
        return self._write(_rollover_record(self._record, context), rollover=True)

    def _write(self, record, *, rollover=False):
        value = validate_record(record)
        data = (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
                + '\n').encode('ascii')
        _require(len(data) <= MAX_BYTES, 'oversize encoded journal')
        with self._directory() as directory:
            previous = self._unchanged(directory)
            _require(value['sequence'] == (1 if previous is None else previous['sequence'] + 1),
                     'journal sequence is not the next revision')
            if previous is not None:
                for key in ('generation', 'boot_id', 'observer_pidns', 'target_netns',
                            'interface', 'ifindex', 'cookie', 'previous_alias'):
                    _require(value[key] == previous[key], 'journal lease identity changed')
                if rollover:
                    _require(value == _rollover_record(previous, value['recovery_context']),
                             'invalid boot rollover')
                else:
                    _require(value['version'] == previous['version'] and
                             record_context(value) == record_context(previous),
                             'journal recovery context changed without rollover')
                    if previous['phase'] == 'reboot-clean':
                        _require(value['phase'] == 'reboot-clean', 'completed DNS retirement cannot reopen')
            else:
                _require(not rollover and value['version'] == 1, 'retirement requires an existing journal')
            temporary = '.journal-' + secrets.token_hex(16)
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=directory)
            pending = True
            try:
                os.fchmod(fd, 0o600)
                view = memoryview(data)
                while view:
                    written = os.write(fd, view)
                    if written <= 0:
                        raise OSError('journal write made no progress')
                    view = view[written:]
                os.fsync(fd)
                self._unchanged(directory)
                os.rename(temporary, self.filename, src_dir_fd=directory, dst_dir_fd=directory)
                pending = False
                os.fsync(directory)
                token, stored = self._disk(directory)
                _require(stored == value and token[0] == _identity(os.fstat(fd)),
                         'journal changed after replacement')
                self._token, self._record = token, stored
            finally:
                os.close(fd)
                if pending:
                    os.unlink(temporary, dir_fd=directory)
        return copy.deepcopy(value)

    def remove(self):
        _require(self._record is not None and self._record['phase'] in ('clean', 'reboot-clean'),
                 'only a loaded clean journal may be removed')
        with self._directory() as directory:
            self._unchanged(directory)
            os.unlink(self.filename, dir_fd=directory)
            os.fsync(directory)
        self._token, self._record = None, None

    def confirm_absent(self):
        """Durably confirm already-read absence; never remove or recreate a file.

        The recovery coordinator separately proves whether absence may finish a
        known clean-removal attempt. This method provides only directory fsync.
        """
        _require(self._token is None and self._record is None,
                 'journal absence must be read before confirmation')
        with self._directory() as directory:
            self._unchanged(directory)
            os.fsync(directory)
            self._unchanged(directory)
